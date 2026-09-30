"""Scratchpad: run the tutorial's commands, in order and as written, against the REAL released files.

Run it from the root of a fresh copy of the kit on a Linux machine that already holds the downloaded release:

    python3 scratchpad/tutorial_realrun.py --downloads /path/to/downloads > realrun_raw.txt 2>&1

`--downloads` is a directory laid out as T1/, T2_heart/, T2_embryo/, T3/ with the files from the Data page. The
script links them into data/raw/ (section 2 of the tutorials; symlinks, nothing is copied or modified), creates
.venv with the `python` on PATH (section 3), installs the kit and veckit the way section 3 says, and then runs the
commands of sections 3-7 and 9 from the kit root, each in a fresh `bash -c "source .venv/bin/activate && ..."`.
Every step records its exit code, wall time and peak memory (max RSS of the command and its children).

It prints the full output (the raw log, which contains values computed from the data: keep it private) and writes
a trimmed log with --trimmed PATH: commands, versions, exit codes, shapes, cell and gene counts, timings, memory,
with every expression-derived value (value ranges, hashes, metric values, scores) replaced by <omitted>. Nothing is
uploaded anywhere; section 8 (upload) is not run, and neither is `vec_agent_evidence run` (it would launch an agent).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path.cwd()
T3_NAME = "E9.5_mab21l2_ko.h5ad"
LAYOUT = {  # data/raw/<rel> -> <downloads>/<rel>
    "T1/E8.5_RNA.h5ad": "T1/E8.5_RNA.h5ad",
    "T1/E9.5_RNA.h5ad": "T1/E9.5_RNA.h5ad",
    "T2_heart/E8.25_late.h5ad": "T2_heart/E8.25_late.h5ad",
    "T2_heart/E8.75.h5ad": "T2_heart/E8.75.h5ad",
    "T2_heart/E9.5.h5ad": "T2_heart/E9.5.h5ad",
    "T2_embryo/E6.75.h5ad": "T2_embryo/E6.75.h5ad",
    "T2_embryo/E7.25.h5ad": "T2_embryo/E7.25.h5ad",
    "T2_embryo/E8.0.h5ad": "T2_embryo/E8.0.h5ad",
    "T3/" + T3_NAME: "T3/" + T3_NAME,
}
VECKIT = "git+https://github.com/aristoteleo/veckit.git@46d41e63f42a9aab815db20b742feeccd249cb17"
ACT = "source .venv/bin/activate && "

RESULTS = []


def run(key, cmd, section, venv=True, timeout=3600, show=60):
    full = (ACT + cmd) if venv else cmd
    print(f"\n### [{key}] section {section}\n$ {cmd}", flush=True)
    with tempfile.TemporaryFile(mode="w+b") as out:
        t0 = time.time()
        p = subprocess.Popen(["bash", "-c", full], cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT)
        try:
            _, status, ru = os.wait4(p.pid, 0)
            rc = os.waitstatus_to_exitcode(status)
        except KeyboardInterrupt:
            p.kill()
            raise
        dt = time.time() - t0
        p.returncode = rc
        out.seek(0)
        text = out.read().decode("utf-8", "replace")
    lines = text.rstrip().splitlines()
    shown = lines if len(lines) <= show else lines[: show // 2] + [f"  ... ({len(lines) - show} lines)"] + lines[-show // 2:]
    print("\n".join("  " + x for x in shown))
    peak_mb = ru.ru_maxrss / 1024.0  # Linux: KiB
    print(f"  -> rc={rc}  wall={dt:.1f}s  peak_rss={peak_mb:.0f}MB", flush=True)
    RESULTS.append({"key": key, "section": section, "cmd": cmd, "rc": rc, "wall_s": round(dt, 1),
                    "peak_rss_mb": round(peak_mb), "output": text})
    return rc, text


INSPECT = r'''
import h5py, json, os, sys
from pathlib import Path
from vec_submit_check import checker as vc
idx = vc.load_index(None)
panels = {k: vc.panel_for_board(k)[1] for k in idx}
rows = []
for p in sorted(Path("data/raw").rglob("*.h5ad")):
    with h5py.File(p, "r") as f:
        X = f["X"]
        enc = X.attrs.get("encoding-type", "array" if isinstance(X, h5py.Dataset) else "?")
        if isinstance(X, h5py.Dataset):
            shape, dtype = list(X.shape), str(X.dtype)
        else:
            shape, dtype = [int(v) for v in X.attrs["shape"]], str(X["data"].dtype)
        var = f["var"]
        vi = var.attrs.get("_index", "_index")
        genes = [g.decode() if isinstance(g, bytes) else str(g) for g in var[vi][...]]
        obs = sorted(k for k in f["obs"].keys() if not k.startswith("__"))
        obsm = sorted(f["obsm"].keys()) if "obsm" in f else []
        sp3 = list(f["obsm"]["spatial_3D"].shape) if "obsm" in f and "spatial_3D" in f["obsm"] else None
    cover = {}
    have = set(genes)
    for k, pl in panels.items():
        if k.startswith("T1") != (len(genes) > 1000):
            continue
        miss = [g for g in pl if g not in have]
        cover[k] = "same genes, same order" if genes == pl else (
            "has every panel gene (other order or extra genes)" if not miss else f"missing {len(miss)}: {miss[:3]}")
    rows.append({"file": str(p.relative_to("data/raw")), "MB": round(os.path.getsize(p) / 1e6, 1),
                 "n_obs": shape[0], "n_vars": shape[1], "X": f"{enc} {dtype}", "obs": obs, "obsm": obsm,
                 "spatial_3D": sp3, "panels": cover})
for r in rows:
    print(json.dumps(r))
'''

PY_API = '''from vec_community_baselines import io as bio, methods as bm
spec, panel = bio.panel_for_board("T3:gata4")
wt = bio.load_stage("data/raw/T2_heart/E8.75.h5ad", panel)
X, C, info = bm.wt_identity(wt)
report = bio.write_submission(X, C, panel, "out/t3_wt_identity.h5ad", "T3:gata4", n_cells=5000)
print(report["ok"], report["info"]["n_obs"])
'''

MINE = ("python -c \"import anndata as ad, numpy as np; a = ad.read_h5ad('out/pseudo_pred.h5ad'); "
        "a.obsm['spatial_3D'] = (np.asarray(a.obsm['spatial_3D']) * 1.25).astype(np.float32); "
        "a.write_h5ad('out/pseudo_pred_mine.h5ad')\"")

MB = "python -m vec_community_baselines.make_baseline"
LS = "python -m vec_local_score"


def steps(downloads: Path):
    # ---- section 2: the data root (symlinks into the layout the tutorial expects)
    for rel, src in LAYOUT.items():
        dst = ROOT / "data" / "raw" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            os.symlink(downloads / src, dst)
    print("linked the downloaded release into data/raw/ (symlinks):")
    for rel in LAYOUT:
        print("  data/raw/" + rel)
    (ROOT / "out").mkdir(exist_ok=True)

    # ---- section 3: install
    run("venv", "python --version && python -m venv .venv && source .venv/bin/activate && python --version", 3, venv=False)
    run("pip_install", 'pip install -e ".[test]"', 3, timeout=1800, show=8)
    run("pip_versions", "python -m pip list 2>/dev/null | grep -i -E '^(anndata|numpy|scipy|pandas|h5py|pytest|scikit-learn|veckit|vec-community-kit|setuptools|pip) '", 3)
    run("pytest_no_veckit", "python -m pytest -q", 3, show=6)
    run("pip_requirements", "pip install -r requirements.txt", 3, show=4)
    run("console_scripts", "for c in vec-community-check vec-community-baseline vec-community-score vec-community-split "
        "vec-community-evidence; do $c --help >/dev/null 2>&1; echo \"$c rc=$?\"; done", 3)
    run("veckit_install", f'pip install "{VECKIT}"', 3, timeout=1800, show=6)
    run("veckit_check", 'python -c "from vec_local_score import veckit_available, veckit_info; '
        'print(veckit_available(), veckit_info())"', 3)
    run("pip_versions_after", "python -m pip list 2>/dev/null | grep -i -E '^(anndata|numpy|scipy|pandas|h5py|pytest|scikit-learn|veckit) '", 3)
    run("pytest_with_veckit", "python -m pytest -q -rs", 3, show=12)

    # ---- section 2 / 4: what the release holds, and the contracts
    run("inventory", "python - <<'EOF'\n" + INSPECT + "EOF", 2, show=40)
    run("panel_lines", "wc -l data/panels/*.genes.txt", 4)

    # ---- section 5: the five baseline commands as written
    run("b_t1", f"{MB} --method copy_last   --board T1:val               --last data/raw/T1/E9.5_RNA.h5ad          --out out/t1_copy_last.h5ad --n-cells 5000", 5)
    run("b_embryo", f"{MB} --method copy_last   --board T2:embryo:val_interp --last data/raw/T2_embryo/E8.0.h5ad       --out out/embryo_copy_last.h5ad --n-cells 5000", 5)
    run("b_heart_interp", f"{MB} --method copy_last   --board T2:heart:val_interp  --last data/raw/T2_heart/E8.25_late.h5ad  --out out/heart_interp_copy_last.h5ad --n-cells 5000", 5)
    run("b_heart_extrap", f"{MB} --method copy_last   --board T2:heart:val_extrap  --last data/raw/T2_heart/E9.5.h5ad        --out out/heart_extrap_copy_last.h5ad --n-cells 5000", 5)
    run("b_t3", f"{MB} --method wt_identity --board T3:gata4             --wt   data/raw/T2_heart/E8.75.h5ad       --out out/t3_wt_identity.h5ad --n-cells 5000", 5)
    # the comments next to the commands say `all` would error on every one of these inputs
    for key, board, flag, src in (("all_t1", "T1:val", "--last", "data/raw/T1/E9.5_RNA.h5ad"),
                                  ("all_embryo", "T2:embryo:val_interp", "--last", "data/raw/T2_embryo/E8.0.h5ad"),
                                  ("all_heart_interp", "T2:heart:val_interp", "--last", "data/raw/T2_heart/E8.25_late.h5ad"),
                                  ("all_heart_extrap", "T2:heart:val_extrap", "--last", "data/raw/T2_heart/E9.5.h5ad"),
                                  ("all_t3", "T3:gata4", "--wt", "data/raw/T2_heart/E8.75.h5ad")):
        method = "wt_identity" if board == "T3:gata4" else "copy_last"
        run(key, f"{MB} --method {method} --board {board} {flag} {src} --out out/{key}.h5ad --n-cells all", 5, show=6)
    run("py_api", "python - <<'EOF'\n" + PY_API + "EOF", 5)
    run("b_heart_extrap_pbshift", f"{MB} --method pseudobulk_shift --board T2:heart:val_extrap --prev data/raw/T2_heart/E8.75.h5ad --last data/raw/T2_heart/E9.5.h5ad --out out/heart_extrap_pbshift.h5ad --n-cells 5000", 5, show=12)

    # ---- section 6: validate (the two commands as written, then the other three baseline files)
    run("check_heart_interp", "python -m vec_submit_check --board T2:heart:val_interp out/heart_interp_copy_last.h5ad", 6)
    run("check_t1_json", "python -m vec_submit_check --board T1:val out/t1_copy_last.h5ad --json out/t1_check.json", 6)
    run("check_embryo", "python -m vec_submit_check --board T2:embryo:val_interp out/embryo_copy_last.h5ad", 6)
    run("check_heart_extrap", "python -m vec_submit_check --board T2:heart:val_extrap out/heart_extrap_copy_last.h5ad", 6)
    run("check_t3", "python -m vec_submit_check --board T3:gata4 out/t3_wt_identity.h5ad", 6)
    run("check_console_script", "vec-community-check --board T3:gata4 out/t3_wt_identity.h5ad", 6)
    run("check_wrong_board", "python -m vec_submit_check --board T2:embryo:val_interp out/heart_interp_copy_last.h5ad", 6)

    # ---- section 7: local scoring on pseudo splits of released stages
    run("ls_veckit_check", 'python -c "from vec_local_score import veckit_available, veckit_info; '
        'print(veckit_available(), veckit_info())"', 7)
    run("ls_heart_interp_pred", f"{MB} --method copy_last --board T2:heart:val_interp --last data/raw/T2_heart/E8.25_late.h5ad --out out/pseudo_pred.h5ad --n-cells 5000", 7)
    run("ls_heart_interp_band", f"{LS} --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad", 7)
    run("ls_heart_interp_single", f"{LS} --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --single-seed", 7)
    run("ls_t1_pred", f"{MB} --method copy_last --board T1:val --last data/raw/T1/E8.5_RNA.h5ad --out out/t1_pseudo_pred.h5ad --n-cells 5000", 7)
    run("ls_t1_band", f"{LS} --task T1 --pred out/t1_pseudo_pred.h5ad --target data/raw/T1/E9.5_RNA.h5ad --reference data/raw/T1/E8.5_RNA.h5ad", 7)
    run("ls_t3_pred", f"{MB} --method wt_identity --board T3:gata4 --wt data/raw/T2_heart/E9.5.h5ad --out out/t3_pseudo_pred.h5ad --n-cells 5000", 7)
    run("ls_t3_band", f"{LS} --task T3 --pred out/t3_pseudo_pred.h5ad --target data/raw/T3/{T3_NAME} --wt data/raw/T2_heart/E9.5.h5ad", 7)
    run("ls_embryo_pred", f"{MB} --method copy_last --board T2:embryo:val_interp --last data/raw/T2_embryo/E6.75.h5ad --out out/embryo_pseudo_pred.h5ad --n-cells 5000", 7)
    run("ls_embryo_band", f"{LS} --task T2 --setting embryo --pred out/embryo_pseudo_pred.h5ad --target data/raw/T2_embryo/E7.25.h5ad --reference data/raw/T2_embryo/E6.75.h5ad", 7)
    run("ls_heart_extrap_pred", f"{MB} --method copy_last --board T2:heart:val_extrap --last data/raw/T2_heart/E8.75.h5ad --out out/heart_extrap_pseudo_pred.h5ad --n-cells 5000", 7)
    run("ls_heart_extrap_band", f"{LS} --task T2 --setting heart --pred out/heart_extrap_pseudo_pred.h5ad --target data/raw/T2_heart/E9.5.h5ad --reference data/raw/T2_heart/E8.75.h5ad", 7)
    run("ls_heart_interp_maxcells", f"{LS} --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --single-seed --max-cells 6000", 7)
    run("ls_mine", MINE, 7)
    run("ls_paired", f"{LS} --task T2 --setting heart --pred out/pseudo_pred.h5ad --pred out/pseudo_pred_mine.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad", 7)
    run("ls_split", "python -m vec_local_score.make_pseudo_split --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --out-dir pseudo/heart --panel data/panels/T2__heart__val_interp.genes.txt --require-coords", 7)
    run("ls_split_refused", f"{LS} --task T2 --setting heart --pred out/pseudo_pred.h5ad --target pseudo/heart/target_score.h5ad --reference pseudo/heart/reference.h5ad", 7)

    # ---- section 9: the Agent-track skeleton (dry-run tests; lock only, no launch)
    run("evidence_tests", "python -m pytest tests/test_evidence.py -q", 9, show=6)
    run("evidence_lock", "which claude || echo 'claude: not on PATH (lock records it as missing; nothing is launched)'; "
        "python -m vec_agent_evidence lock --task T3 --prompt vec_agent_evidence/example_prompt.md --model <full-model-id> "
        "--data-root ./data --hours 8 --max-turns 400 --runs-root runs_realrun".replace("<full-model-id>", "claude-opus-5"), 9, show=30)


# ---------------------------------------------------------------------------------------------- trimming
NUM = r"-?\d+(?:\.\d+)?(?:e-?\d+)?"


def trim_output(key: str, text: str, downloads: str) -> list:
    out = []
    text = text.replace(str(ROOT), "<kit>").replace(downloads, "<downloads>").replace(str(ROOT.parent), "<work>")
    lines = text.splitlines()
    in_table = False
    depth = 0
    for ln in lines:
        s = ln.strip()
        if depth:  # inside an omitted JSON block (per-type statistics of the baseline writer)
            depth += s.count("{") + s.count("[") - s.count("}") - s.count("]")
            depth = max(depth, 0)
            continue
        m = re.match(r'^"(per_type|shared_types|unmatched_types_in_last|types_only_in_prev)"\s*:\s*([\[{])?', s)
        if m:
            out.append(ln[: len(ln) - len(ln.lstrip())] + f'"{m.group(1)}": <omitted>')
            if m.group(2) and not s.rstrip(",").endswith(("}", "]")):
                depth = 1
            continue
        # the pseudobulk_shift warning names cell types with their counts
        if s.startswith("WARNING:") and "{" in s:
            out.append(ln[: len(ln) - len(ln.lstrip())] + s.split(";")[0].split(" only ")[0]
                       + " (cell-type names and counts omitted)")
            continue
        # value ranges, hashes, per-file statistics printed by the writer and the validator
        ln = re.sub(r"\bmin=" + NUM, "min=<omitted>", ln)
        ln = re.sub(r"\bmax=" + NUM, "max=<omitted>", ln)
        if re.match(r"^(X_min|X_max|X_nonzero_frac|spatial_3D_rms_radius|sha256)\s*:", s):
            ln = re.sub(r":\s.*$", ": <omitted>", ln)
        if re.match(r'^"?(config_lock_sha256|sha256)"?\s*:', s):
            ln = re.sub(r":\s.*$", ": <omitted>", ln)
        # local-score tables and score lines: keep the headers, omit every value
        if s.startswith(("metric ", "group ")):
            out.append(ln)
            in_table = True
            continue
        if in_table and re.match(r"^\S.*\s" + NUM + r"\s", s) and not s.startswith(("TASK", "*", "note", "veckit")):
            if not out or not out[-1].endswith("values omitted)"):
                out.append("  (per-metric rows printed; values omitted)")
            continue
        in_table = False if s.startswith(("TASK", "veckit", "note")) else in_table
        if s.startswith("TASK SCORE") or re.search(r"\bband " + NUM, s) or re.search(r"\+- " + NUM, s) \
                or re.match(r"^[AB] = ", s) or "B higher on" in s:
            m = re.search(r"\[(" + NUM + r")s\]", s)
            label = re.sub(r"\s+" + NUM + r"\s+\[.*$", "", s.split(": ")[0])
            out.append("  " + label + ": <scores omitted>" + (f"  [{m.group(1)}s]" if m else ""))
            continue
        # the baseline writer's method-info JSON: keep counts and row selection, drop value statistics
        if re.match(r'^"(n_entries_clipped_at_zero)"', s):
            ln = re.sub(r":\s.*$", ": <omitted>", ln)
        out.append(ln)
    return out


def floor_check(text: str):
    """For a band run of a floor-model prediction: is the band within a few points of 50 (the tutorial's claim)?"""
    m = re.search(r"mean (" + NUM + r")\s+sd (" + NUM + r")\s+band (" + NUM + r")\.\.(" + NUM + r")", text)
    if not m:
        return None
    mean, lo, hi = float(m.group(1)), float(m.group(3)), float(m.group(4))
    return {"band_contains_50": lo <= 50.0 <= hi, "mean_within_5_of_50": abs(mean - 50.0) <= 5.0}


def write_trimmed(path: Path, header: list, downloads: str):
    lines = list(header)
    for r in RESULTS:
        lines.append("")
        lines.append(f"$ {r['cmd']}".replace(str(ROOT), "<kit>"))
        body = trim_output(r["key"], r["output"], downloads)
        if r["key"].startswith(("pip_install", "veckit_install", "pip_requirements")):
            body = [b for b in body if b.strip().startswith(("Successfully", "Requirement already", "ERROR", "error"))][-3:]
        if len(body) > 60:
            body = body[:30] + [f"  ... ({len(body) - 50} lines)"] + body[-20:]
        lines += ["  " + b if not b.startswith("  ") else b for b in body]
        fc = floor_check(r["output"]) if r["key"].endswith("_band") else None
        if fc:
            lines.append(f"  floor-model check (tutorial section 7: a copy_last / wt_identity file lands near 50): "
                         f"band contains 50: {'yes' if fc['band_contains_50'] else 'no'}; mean within 5 points of 50: "
                         f"{'yes' if fc['mean_within_5_of_50'] else 'no'}")
        lines.append(f"  -> rc={r['rc']}  wall={r['wall_s']}s  peak_rss={r['peak_rss_mb']}MB")
    lines.append("")
    lines.append("SUMMARY " + json.dumps({r["key"]: r["rc"] for r in RESULTS}, indent=1))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--downloads", required=True, type=Path)
    ap.add_argument("--trimmed", type=Path, default=None)
    ap.add_argument("--machine", default="Linux")
    args = ap.parse_args()
    t0 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        steps(args.downloads.resolve())
    finally:
        t1 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        print(f"\nstarted {t0}, finished {t1}")
        print("SUMMARY", json.dumps({r["key"]: r["rc"] for r in RESULTS}, indent=1))
        if args.trimmed:
            header = [f"# commands executed {t0} .. {t1} (UTC) on {args.machine}",
                      f"# environment: OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')} "
                      f"MKL_NUM_THREADS={os.environ.get('MKL_NUM_THREADS')} "
                      f"OPENBLAS_NUM_THREADS={os.environ.get('OPENBLAS_NUM_THREADS')} "
                      f"LOKY_MAX_CPU_COUNT={os.environ.get('LOKY_MAX_CPU_COUNT')}, niceness {os.nice(0)}, "
                      f"user id {os.getuid()}"]
            write_trimmed(args.trimmed, header, str(args.downloads.resolve()))


if __name__ == "__main__":
    sys.exit(main())
