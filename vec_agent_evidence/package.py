"""Build the portal upload package for a completed run (postrun done): byte-identical prediction copies (sha256 verified
against run_manifest.json) plus the three evidence kinds (trajectory, prompts, harness) as a folder and as zips.

    python -m vec_agent_evidence package --run-dir runs/<run_id> [--out-root runs/_upload]

Writes <out-root>/<run_id>/{predictions/, evidence/, trajectory.zip, prompts.zip, harness.zip, evidence_bundle.zip,
README.md}. Never modifies the run directory. Refuses if the manifest reports a lock-integrity problem, a
secret-scan hit, an abort, a submission that is not ok, or a board whose finalized sha256 does not match the file
on disk. Every file and every zip must stay under the portal's per-file cap.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
import zipfile
from pathlib import Path

from . import common as C

PER_FILE_LIMIT = int(C.UPLOAD_LIMITS["per_file_mb"] * 1024 * 1024)
TRAJECTORY = {"transcript", "stream.jsonl", "stderr.log", "hooks", "launch_state.json"}
PROMPTS = {"initial_prompt.md", "system_prompt_appendix.md", "prompts.manifest.json"}
EXCLUDE = {"workspace", "submission", "RUNNING"}


def rm_tree(path: Path) -> None:
    def onerror(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if path.exists():
        shutil.rmtree(path, onerror=onerror)


def copy_writable(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    os.chmod(dst, stat.S_IWRITE | stat.S_IREAD)


def copy_tree(src: Path, dst: Path) -> list:
    out = []
    for p in sorted(src.rglob("*")):
        if p.is_file():
            q = dst / p.relative_to(src)
            copy_writable(p, q)
            out.append(q)
    return out


def zip_paths(zip_path: Path, base: Path, paths: list) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(paths):
            z.write(p, p.relative_to(base).as_posix())


def kind_of(rel_top: str) -> str:
    if rel_top in TRAJECTORY:
        return "trajectory"
    if rel_top in PROMPTS:
        return "prompts"
    return "harness"


def package(run_dir, out_root=None, allow_abort_unknown: bool = False, team_uploaded_mb: float = 0.0) -> Path:
    """Build the package; raises SystemExit with the reason when the run must not be uploaded.

    team_uploaded_mb: evidence MB your team has already uploaded (your own bookkeeping from the portal); the README
    states the running total against the per-team cap and warns when this package's three kind zips would exceed it.
    """
    run = Path(run_dir).resolve()
    manifest_path = run / "run_manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"REFUSED: {manifest_path} missing (run not finished / postrun not done)")
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems = []
    if not m.get("lock_integrity", {}).get("ok"):
        problems.append(f"lock_integrity: {m.get('lock_integrity')}")
    if not m.get("secret_scan", {}).get("clean"):
        problems.append(f"secret_scan: {m.get('secret_scan')}")
    abort_note = ""
    if m.get("abort"):
        if allow_abort_unknown and str(m.get("abort")).startswith("unknown"):
            abort_note = (f"run_manifest abort = {m.get('abort')!r}: the harness process did not survive to the end of "
                          "the run; evidence recovered with postrun (the trajectory is the transcript copied by session id)")
        else:
            problems.append(f"abort: {m.get('abort')} (pass --allow-abort-unknown only for a postrun-recovered run whose "
                            "transcript is complete)")
    if m.get("submission", {}).get("status") != "ok":
        problems.append(f"submission status: {m.get('submission', {}).get('status')}")
    if problems:
        raise SystemExit("\n  ".join(["REFUSED:"] + problems))

    run_id = m["run_id"]
    out = (Path(out_root).resolve() if out_root else run.parent / "_upload") / run_id
    rm_tree(out)
    (out / "predictions").mkdir(parents=True)
    (out / "evidence").mkdir(parents=True)

    pred_rows = []
    for board, info in sorted(m["submission"]["boards"].items()):
        if info.get("status") != "ok":
            continue
        src = run / "submission" / info["file"]
        entries = info.get("agent_manifest_entries") or []
        final_entry = entries[-1] if entries else {}
        expected = final_entry.get("sha256") or info.get("sha256")
        actual = C.sha256_file(src)
        if expected is not None and actual != expected:
            raise SystemExit(f"REFUSED: {board}: sha on disk {actual} != finalized {expected}")
        if not info.get("uploadable", True):
            raise SystemExit(f"REFUSED: {board}: file is flagged not uploadable (relaxed min_cells dry run)")
        dst = out / "predictions" / info["file"]
        copy_writable(src, dst)
        pred_rows.append((board, info["file"], dst.stat().st_size, actual, final_entry.get("candidate", "?"),
                          final_entry.get("n_obs")))

    # evidence tree: every top-level file / dir of the run except the workspace and the submission files
    copied = []
    for p in sorted(run.iterdir()):
        if p.name in EXCLUDE:
            continue
        if p.is_dir():
            copied += copy_tree(p, out / "evidence" / p.name)
        else:
            q = out / "evidence" / p.name
            copy_writable(p, q)
            copied.append(q)
    sub_manifest = run / "submission" / "MANIFEST.json"
    if sub_manifest.exists():
        q = out / "evidence" / "submission" / "MANIFEST.json"
        copy_writable(sub_manifest, q)
        copied.append(q)
    ev = out / "evidence"

    # secret scan over text-like evidence files (the postrun already scanned the run; this is belt and braces)
    hits = []
    for p in copied:
        if p.suffix.lower() not in C.SECRET_SCAN_SUFFIXES:
            continue
        data = p.read_bytes()
        for label, rx in C.SECRET_PATTERNS:
            if rx.search(data):
                hits.append((str(p.relative_to(out)), label))
    if hits:
        raise SystemExit("REFUSED: credential-shaped content in evidence: " + ", ".join(f"{f}:{lab}" for f, lab in hits[:10]))

    kinds = {"trajectory": [], "prompts": [], "harness": []}
    for p in copied:
        kinds[kind_of(p.relative_to(ev).parts[0])].append(p)
    zips = {}
    for kind, paths in kinds.items():
        zp = out / f"{kind}.zip"
        zip_paths(zp, ev, paths)
        zips[kind] = zp
    bundle = out / "evidence_bundle.zip"
    zip_paths(bundle, ev, copied)
    zips["evidence_bundle"] = bundle
    oversize = [p for p in copied + list(zips.values()) if p.stat().st_size > PER_FILE_LIMIT]
    if oversize:
        raise SystemExit(f"REFUSED: over {C.UPLOAD_LIMITS['per_file_mb']} MB: " + ", ".join(p.name for p in oversize))

    lines = [f"# Upload package for run {run_id} ({len(pred_rows)} board(s))", "",
             "Predictions are byte-identical copies of the agent's finalized files (sha256 verified against "
             "run_manifest.json and the agent's own submission manifest).", "",
             "| board | file | MB | sha256 | candidate | cells |", "|---|---|---|---|---|---|"]
    for board, fn, size, sha, cand, n_obs in pred_rows:
        lines.append(f"| {board} | predictions/{fn} | {size / 1e6:.1f} | {sha} | {cand} | {n_obs} |")
    lines += ["", "Evidence (three kinds; the rules require at least two):", "",
              "| kind | zip | MB | sha256 | files |", "|---|---|---|---|---|"]
    for kind in ("trajectory", "prompts", "harness", "evidence_bundle"):
        zp = zips[kind]
        n = len(copied) if kind == "evidence_bundle" else len(kinds[kind])
        lines.append(f"| {kind} | {zp.name} | {zp.stat().st_size / 1e6:.1f} | {C.sha256_file(zp)} | {n} |")
    upload_mb = sum(zips[k].stat().st_size for k in ("trajectory", "prompts", "harness")) / 1e6
    team_cap = float(C.UPLOAD_LIMITS.get("team_total_mb", 600))
    team_total = float(team_uploaded_mb) + upload_mb
    team_line = (f"Team evidence total: {float(team_uploaded_mb):.1f} MB reported as already uploaded + {upload_mb:.1f} MB "
                 f"for this package's three kind zips = {team_total:.1f} MB of the {team_cap:g} MB per-team cap "
                 "(the cap is per team across every upload; only you know the running total - pass --team-uploaded-mb).")
    if team_total > team_cap:
        team_line += (" EXCEEDS THE CAP: upload two kinds instead of three, or file a summarised trace; "
                      "the portal enforces the total.")
        print(f"WARNING: {team_line}")
    lines += ["", team_line]
    if abort_note:
        lines += ["", "NOTE: " + abort_note]
    lines += ["",
              "Portal steps (human): Submit -> pick the board tab -> upload the prediction file above -> attach the "
              "evidence ON THAT TAB (trajectory.zip + prompts.zip, or evidence_bundle.zip if one attachment is enough) "
              "-> submit. Repeat per board. The prediction file must be uploaded exactly as it is here.",
              "", f"Run usage: {(m.get('usage') or {}).get('output_tokens')} output tokens, "
              f"{(m.get('usage') or {}).get('cache_read_input_tokens')} cache-read tokens, {m.get('num_turns')} turns, "
              f"{m.get('wall_clock_hours')} h wall clock budget."]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"OK {out}\n  predictions: " + "; ".join(f"{b} {s / 1e6:.1f} MB" for b, _, s, *_ in pred_rows)
          + f"\n  evidence files: {len(copied)}; bundle {bundle.stat().st_size / 1e6:.1f} MB; package total {total / 1e6:.1f} MB")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m vec_agent_evidence package", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out-root", default=None, help="default: <runs root>/_upload")
    ap.add_argument("--allow-abort-unknown", action="store_true",
                    help="accept a manifest whose abort field is 'unknown (...)' because the harness died and postrun "
                         "reconstructed the state; recorded in README.md")
    ap.add_argument("--team-uploaded-mb", type=float, default=0.0,
                    help="evidence MB your team has already uploaded (from the portal's evidence list); the README then "
                         "states the running total against the 600 MB per-team cap and warns when it would be exceeded")
    args = ap.parse_args(argv)
    try:
        package(args.run_dir, args.out_root, args.allow_abort_unknown, team_uploaded_mb=args.team_uploaded_mb)
    except SystemExit as e:
        if str(e).startswith("REFUSED"):
            print(str(e))
            return 2
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
