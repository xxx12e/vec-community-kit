"""Minimal Codex CLI adapter: package a finished `codex exec --json` run as the three Agent-track evidence kinds
(trajectory, prompts, harness), plus byte-identical, format-checked prediction copies.

STATUS: MINIMAL, AND UNTESTED AGAINST A LIVE CODEX RUN. It was written from the Codex CLI's documentation
(https://developers.openai.com/codex/noninteractive, read 2026-09-30: event types and a sample stream) plus the
authors' understanding of the session files, and is tested only on synthetic transcripts written from those names:

  * `codex exec --json` prints one JSON event per line on stdout: thread.started {thread_id}, turn.started,
    turn.completed {usage}, turn.failed {error}, item.started / item.updated / item.completed {item} with item types
    agent_message, reasoning, command_execution, file_change, mcp_tool_call, web_search, todo_list, error; older
    Codex versions printed {"id", "msg": {"type": ...}} events instead (session_configured, exec_command_begin,
    token_count, task_complete, ...). Both shapes are summarised; anything else is counted and kept verbatim.
  * Codex also writes a session "rollout" file (not with --ephemeral), as far as we know under
    $CODEX_HOME/sessions/YYYY/MM/DD/rollout-<time>-<thread id>.jsonl (CODEX_HOME defaults to ~/.codex), with
    session_meta / turn_context / response_item / event_msg records; it is looked up by the thread id and copied
    byte for byte when found. The rollout layout is NOT from the page above: treat that part as a best guess.
  * Codex reads instruction files named AGENTS.md (and AGENTS.override.md) from the working tree and from
    $CODEX_HOME; those are prompts in the rules' sense and go into the prompts kind.

The trajectory is always the byte copy of what Codex wrote; only the summary fields depend on the event names
above. If your Codex version writes something else, the summary comes out empty and the package README says so.

What this adapter does NOT do (the Claude Code path of this package does): lock a configuration before the run,
launch the agent, enforce a wall clock, or install guard / audit hooks. Codex's own sandbox (`--sandbox
workspace-write`) is the enforcement layer there. This module only packages evidence after the run, refusing on a
credential-shaped string, an oversized file, an unreadable stream, or a prediction that fails the board contract.

Suggested run (check `codex exec --help` for your version; `-` reads the whole prompt from stdin; do not pass
--ephemeral, which suppresses the rollout file; --ignore-user-config keeps $CODEX_HOME/config.toml out of the run,
otherwise pass that file with --harness so the evidence shows it):
  codex exec --json --model <model> --sandbox workspace-write --skip-git-repo-check --cd <workspace> - \\
      < prompt.md > codex_stream.jsonl 2> codex_stderr.log

Package it:
  python -m vec_agent_evidence codex-package --stream codex_stream.jsonl --prompt prompt.md --workspace <workspace> \\
      --prediction T3:gata4=<workspace>/out/pred.h5ad --out runs/_upload_codex/<name> [--stderr codex_stderr.log]
      [--codex-home ~/.codex] [--harness my_loop.py ...] [--command-file cmd.txt] [--model <model string>]
      [--team-uploaded-mb N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from pathlib import Path

from . import common as C

ADAPTER = "vec_agent_evidence.codex (minimal; untested against a live Codex run)"
PER_FILE_LIMIT = int(C.UPLOAD_LIMITS["per_file_mb"] * 1024 * 1024)
NEW_SHAPE_TYPES = {"thread.started", "turn.started", "turn.completed", "turn.failed", "item.started", "item.updated",
                   "item.completed"}
INSTRUCTION_NAMES = ("AGENTS.md", "AGENTS.override.md")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "data", "scratch"}


# ------------------------------------------------------------------------------------------ reading
def read_jsonl(path):
    """Return (events, n_lines, n_unparseable). Lines are decoded as UTF-8 with replacement; blank lines skipped."""
    events, n, bad = [], 0, 0
    with open(path, "rb") as f:
        for raw in f:
            if not raw.strip():
                continue
            n += 1
            try:
                ev = json.loads(str(raw, "utf-8", "replace"))
            except ValueError:
                bad += 1
                continue
            if isinstance(ev, dict):
                events.append(ev)
            else:
                bad += 1
    return events, n, bad


def event_type(ev: dict) -> str:
    """'thread.started', 'item.completed', ... for the current shape; 'legacy:<msg type>' for the older one."""
    t = ev.get("type")
    if isinstance(t, str):
        return t
    msg = ev.get("msg")
    if isinstance(msg, dict) and isinstance(msg.get("type"), str):
        return "legacy:" + msg["type"]
    return "unknown"


def _short(text, n=300) -> str:
    text = text if isinstance(text, str) else json.dumps(text, default=str)
    return text if len(text) <= n else text[:n] + "..."


def summarise_stream(path) -> dict:
    """Summary of a `codex exec --json` stream (either shape). Never raises on content; missing fields stay None."""
    events, n_lines, bad = read_jsonl(path)
    by_type: dict = {}
    for ev in events:
        t = event_type(ev)
        by_type[t] = by_type.get(t, 0) + 1
    shape = ("exec-json" if any(t in NEW_SHAPE_TYPES for t in by_type)
             else "legacy" if any(t.startswith("legacy:") for t in by_type) else "unknown")
    out = {"shape": shape, "lines": n_lines, "unparseable_lines": bad, "events": len(events),
           "events_by_type": by_type, "thread_id": None, "model": None, "turns_started": 0, "turns_completed": 0,
           "turns_failed": 0, "usage": {}, "items_by_type": {}, "commands": 0, "commands_nonzero_exit": 0,
           "files_changed": [], "errors": [], "last_agent_message": None}
    usage: dict = {}
    for ev in events:
        t = event_type(ev)
        msg = ev.get("msg") if isinstance(ev.get("msg"), dict) else {}
        if t == "thread.started":
            out["thread_id"] = out["thread_id"] or ev.get("thread_id")
        elif t == "legacy:session_configured":
            out["thread_id"] = out["thread_id"] or msg.get("session_id")
            out["model"] = out["model"] or msg.get("model")
        if isinstance(ev.get("model"), str):
            out["model"] = out["model"] or ev["model"]
        if t in ("turn.started", "legacy:task_started"):
            out["turns_started"] += 1
        elif t in ("turn.completed", "legacy:task_complete"):
            out["turns_completed"] += 1
            u = ev.get("usage")
            if isinstance(u, dict):
                for k, v in u.items():
                    if isinstance(v, (int, float)):
                        usage[k] = usage.get(k, 0) + v
        elif t == "turn.failed":
            out["turns_failed"] += 1
            out["errors"].append(_short((ev.get("error") or {}).get("message") if isinstance(ev.get("error"), dict)
                                        else ev.get("error")))
        elif t in ("error", "legacy:error", "legacy:stream_error"):
            out["errors"].append(_short(ev.get("message") or msg.get("message") or ev))
        elif t == "legacy:token_count":
            info = msg.get("info") if isinstance(msg.get("info"), dict) else {}
            total = info.get("total_token_usage")
            if isinstance(total, dict):
                usage = {k: v for k, v in total.items() if isinstance(v, (int, float))}
        elif t == "legacy:exec_command_end":
            out["commands"] += 1
            if msg.get("exit_code") not in (0, None):
                out["commands_nonzero_exit"] += 1
        elif t == "legacy:agent_message":
            out["last_agent_message"] = _short(msg.get("message"), 500)
        if t == "item.completed" and isinstance(ev.get("item"), dict):
            item = ev["item"]
            it = str(item.get("type") or item.get("item_type") or "unknown")
            out["items_by_type"][it] = out["items_by_type"].get(it, 0) + 1
            if it == "command_execution":
                out["commands"] += 1
                if item.get("exit_code") not in (0, None):
                    out["commands_nonzero_exit"] += 1
            elif it == "file_change":
                for ch in item.get("changes") or []:
                    if isinstance(ch, dict) and ch.get("path") and len(out["files_changed"]) < 200:
                        out["files_changed"].append({"path": str(ch["path"]), "kind": ch.get("kind")})
            elif it == "agent_message":
                out["last_agent_message"] = _short(item.get("text"), 500)
            elif it == "error":
                out["errors"].append(_short(item.get("message")))
    out["usage"] = usage
    out["errors"] = out["errors"][:20]
    return out


def mentions(path, needle: str) -> int:
    """Lines of the stream that contain `needle` (e.g. the prediction's file name): the provenance link."""
    needle_b = needle.encode("utf-8")
    with open(path, "rb") as f:
        return sum(1 for raw in f if needle_b in raw)


def codex_home(explicit=None) -> Path:
    return Path(explicit or os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def find_rollouts(home, thread_id) -> list:
    """Rollout files of this thread under <home>/sessions (matched on the thread id in the file name)."""
    if not thread_id or not re.fullmatch(r"[A-Za-z0-9_\-]{6,}", str(thread_id)):
        return []
    root = Path(home) / "sessions"
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob(f"*{thread_id}*.jsonl") if p.is_file())


def summarise_rollout(path) -> dict:
    """CLI version, models, sandbox / approval policies and the user-role messages of a rollout file."""
    events, n_lines, bad = read_jsonl(path)
    out = {"file": Path(path).name, "lines": n_lines, "unparseable_lines": bad, "session_id": None,
           "cli_version": None, "models": [], "sandbox_policies": [], "approval_policies": [], "user_messages": []}
    for ev in events:
        typ = ev.get("type")
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        if typ == "session_meta":
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else payload
            out["session_id"] = out["session_id"] or meta.get("id")
            out["cli_version"] = out["cli_version"] or meta.get("cli_version")
        elif typ == "turn_context":
            for key, dest in (("model", "models"), ("sandbox_policy", "sandbox_policies"),
                              ("approval_policy", "approval_policies")):
                v = payload.get(key)
                if v is not None:
                    v = v if isinstance(v, str) else json.dumps(v, sort_keys=True)
                    if v not in out[dest]:
                        out[dest].append(v)
        elif typ == "response_item" and payload.get("type") == "message" and payload.get("role") == "user":
            texts = [c.get("text") for c in payload.get("content") or []
                     if isinstance(c, dict) and isinstance(c.get("text"), str)]
            if texts:
                out["user_messages"].append({"timestamp": ev.get("timestamp"), "text": "\n".join(texts)})
    return out


def find_instruction_files(workspace=None, home=None) -> list:
    """(label, path) of the AGENTS.md-style instruction files Codex reads: <workspace>/** (depth <= 4, skipping data
    and VCS directories and links) and <CODEX_HOME>/ (global instructions)."""
    found = []
    if workspace:
        ws = Path(workspace)
        stack = [(ws, 0)]
        while stack:
            d, depth = stack.pop()
            try:
                entries = sorted(os.scandir(d), key=lambda e: e.name)
            except OSError:
                continue
            for e in entries:
                p = Path(e.path)
                if C.is_junction_or_link(p):
                    continue
                if e.is_dir(follow_symlinks=False):
                    if depth < 4 and e.name not in SKIP_DIRS:
                        stack.append((p, depth + 1))
                elif e.name in INSTRUCTION_NAMES:
                    found.append(("workspace/" + p.relative_to(ws).as_posix(), p))
    if home:
        for name in INSTRUCTION_NAMES:
            p = Path(home) / name
            if p.is_file():
                found.append(("codex_home/" + name, p))
    return sorted(found)


# ------------------------------------------------------------------------------------------ packaging
def _copy(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(Path(src).read_bytes())
    return dst


def _zip(zip_path: Path, base: Path, paths) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(paths):
            z.write(p, p.relative_to(base).as_posix())


def _scan(paths, extra_values=()) -> list:
    patterns = list(C.SECRET_PATTERNS)
    for i, v in enumerate(extra_values):
        if v:
            patterns.append((f"extra_value_{i}", re.compile(re.escape(str(v).encode("utf-8")))))
    hits = []
    for p in paths:
        if p.suffix.lower() not in C.SECRET_SCAN_SUFFIXES:
            continue
        data = p.read_bytes()
        found = [label for label, rx in patterns if rx.search(data)]
        if found:
            hits.append((p, found))
    return hits


def parse_prediction_args(items) -> dict:
    """['T3:gata4=path', ...] -> {board: Path}. The board is everything before the last '='."""
    out = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"--prediction expects BOARD=PATH, got {it!r}")
        board, path = it.rsplit("=", 1)
        out[board.strip()] = Path(path)
    return out


def package_codex(stream, prompt, out, workspace=None, home=None, stderr=None, predictions=None, harness=(),
                  command_file=None, model=None, team_uploaded_mb: float = 0.0, extra_secret_values=(),
                  panels=None) -> Path:
    """Build <out>/{predictions/, evidence/{trajectory,prompts,harness}/, trajectory.zip, prompts.zip, harness.zip,
    evidence_bundle.zip, README.md}. Raises SystemExit("REFUSED: ...") when the package must not be uploaded."""
    from vec_submit_check import check as check_file

    stream, prompt, out = Path(stream), Path(prompt), Path(out)
    for p, what in ((stream, "--stream"), (prompt, "--prompt")):
        if not p.is_file():
            raise SystemExit(f"REFUSED: {what} {p} not found")
    summary = summarise_stream(stream)
    if summary["events"] == 0:
        raise SystemExit(f"REFUSED: {stream} holds no JSON events; pass the stdout of `codex exec --json`")
    home = codex_home(home)
    warnings = []
    if summary["shape"] == "unknown":
        warnings.append("no known Codex event type in the stream (the summary is empty; the trajectory is still the "
                        "byte copy)")
    if summary["turns_completed"] == 0:
        warnings.append("no completed turn in the stream (turn.completed / task_complete): the run may have been cut off")
    if summary["turns_failed"] or summary["errors"]:
        warnings.append(f"{summary['turns_failed']} failed turn(s), {len(summary['errors'])} error event(s) in the stream")
    rollouts = find_rollouts(home, summary["thread_id"])
    if not summary["thread_id"]:
        warnings.append("no thread id in the stream, so no rollout file could be located")
    elif not rollouts:
        warnings.append(f"no rollout file for thread {summary['thread_id']} under {home / 'sessions'}")
    rollout_info = [summarise_rollout(r) for r in rollouts]

    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"REFUSED: {out} exists and is not empty; choose a new --out directory")
    ev = out / "evidence"
    kinds = {"trajectory": [], "prompts": [], "harness": []}

    # trajectory: byte copies of what Codex wrote
    kinds["trajectory"].append(_copy(stream, ev / "trajectory" / "codex_stream.jsonl"))
    if stderr:
        kinds["trajectory"].append(_copy(Path(stderr), ev / "trajectory" / "codex_stderr.log"))
    for r in rollouts:
        kinds["trajectory"].append(_copy(r, ev / "trajectory" / "rollout" / r.name))

    # prompts: the initial prompt, the instruction files Codex reads, every user message found in the rollout(s)
    kinds["prompts"].append(_copy(prompt, ev / "prompts" / "initial_prompt.md"))
    instr = find_instruction_files(workspace, home)
    for label, p in instr:
        kinds["prompts"].append(_copy(p, ev / "prompts" / "instructions" / label))
    user_msgs = [dict(m, rollout=ri["file"]) for ri in rollout_info for m in ri["user_messages"]]
    if user_msgs:
        um = ev / "prompts" / "user_messages.jsonl"
        C.write_text(um, "".join(json.dumps(m) + "\n" for m in user_msgs))
        kinds["prompts"].append(um)
    prompt_bytes = prompt.read_bytes()
    if user_msgs and not any(prompt_bytes.decode("utf-8", "replace").strip()[:200] in m["text"] for m in user_msgs):
        warnings.append("the --prompt text was not found among the rollout's user messages (check it is the prompt "
                        "the run was given)")

    # harness: the files that drove the run, the exact command, and this adapter's manifest
    for h in harness or ():
        h = Path(h)
        if not h.is_file():
            raise SystemExit(f"REFUSED: --harness {h} not found")
        kinds["harness"].append(_copy(h, ev / "harness" / "files" / h.name))
    if command_file:
        kinds["harness"].append(_copy(Path(command_file), ev / "harness" / "command.txt"))
    else:
        warnings.append("no --command-file: the exact `codex exec` command line is not part of the harness evidence")

    # predictions: byte copies, format-checked, provenance looked up in the stream
    pred_rows = []
    for board, src in sorted((predictions or {}).items()):
        if not src.is_file():
            raise SystemExit(f"REFUSED: prediction for {board} not found: {src}")
        try:
            rep = check_file(src, board, panels)
        except KeyError as e:
            raise SystemExit(f"REFUSED: {e}") from None
        if not rep["ok"]:
            raise SystemExit(f"REFUSED: {src} fails the {board} contract: {rep['errors']}")
        dst = _copy(src, out / "predictions" / f"pred_{C.board_sanitised(board)}.h5ad")
        sha = C.sha256_file(src)
        if C.sha256_file(dst) != sha:
            raise SystemExit(f"REFUSED: copy of {src} does not match its sha256")
        n_mentions = mentions(stream, src.name)
        if n_mentions == 0:
            warnings.append(f"{board}: the file name {src.name} never appears in the stream, so the trajectory does not "
                            "show the agent writing it")
        pred_rows.append({"board": board, "file": dst.name, "source": str(src), "sha256": sha, "bytes": dst.stat().st_size,
                          "n_obs": rep["info"].get("n_obs"), "stream_mentions": n_mentions})
    if not pred_rows:
        warnings.append("no --prediction given: the package holds evidence only")

    models = [m for m in ([model, summary["model"]] + [x for ri in rollout_info for x in ri["models"]]) if m]
    model_string = models[0] if models else None
    if not model_string:
        warnings.append("model string unknown (not given with --model, not found in the stream or a rollout); the "
                        "portal asks for the model string you actually ran")
    elif model and any(m != model for m in models[1:]):
        warnings.append(f"--model {model!r} differs from the model(s) recorded by Codex: {sorted(set(models[1:]))}")
    cli_version = next((ri["cli_version"] for ri in rollout_info if ri["cli_version"]), None)

    manifest = {"adapter": ADAPTER, "status": "minimal adapter; untested against a live Codex run", "framework":
                f"OpenAI Codex CLI {cli_version or '(version unknown)'} via `codex exec --json`",
                "model_string": model_string, "stream_summary": summary, "rollouts": rollout_info,
                "instruction_files": [label for label, _ in instr], "predictions": pred_rows, "warnings": warnings,
                "sources": {"stream": str(stream), "prompt": str(prompt), "workspace": str(workspace) if workspace else None,
                            "codex_home": str(home)}}
    summary_path = ev / "trajectory" / "trajectory_summary.json"
    C.write_json(summary_path, {"stream": summary, "rollouts": [dict(ri, user_messages=len(ri["user_messages"]))
                                                                 for ri in rollout_info]})
    kinds["trajectory"].append(summary_path)
    files = [p for paths in kinds.values() for p in paths]
    manifest["evidence"] = {p.relative_to(ev).as_posix(): {"bytes": p.stat().st_size, "sha256": C.sha256_file(p)}
                            for p in files}
    man_path = ev / "harness" / "codex_manifest.json"
    C.write_json(man_path, manifest)
    kinds["harness"].append(man_path)
    files.append(man_path)

    hits = _scan(files, extra_secret_values)
    if hits:
        raise SystemExit("REFUSED: credential-shaped content in evidence (nothing to upload; review and remove it): "
                         + ", ".join(f"{p.relative_to(out).as_posix()}:{'/'.join(labels)}" for p, labels in hits[:10]))

    zips = {}
    for kind, paths in kinds.items():
        zips[kind] = out / f"{kind}.zip"
        _zip(zips[kind], ev, paths)
    zips["evidence_bundle"] = out / "evidence_bundle.zip"
    _zip(zips["evidence_bundle"], ev, files)
    oversize = [p for p in files + list(zips.values()) if p.stat().st_size > PER_FILE_LIMIT]
    if oversize:
        raise SystemExit(f"REFUSED: over {C.UPLOAD_LIMITS['per_file_mb']} MB: " + ", ".join(p.name for p in oversize))

    upload_mb = sum(zips[k].stat().st_size for k in ("trajectory", "prompts", "harness")) / 1e6
    team_total = float(team_uploaded_mb) + upload_mb
    cap = float(C.UPLOAD_LIMITS["team_total_mb"])
    lines = ["# Codex run - upload package (MINIMAL ADAPTER)", "",
             "Built by `vec_agent_evidence.codex`, a minimal adapter that is **untested against a live Codex run** (its "
             "tests use synthetic transcripts). The trajectory files are byte copies of what Codex wrote; check them "
             "before you upload.", "",
             f"Framework: {manifest['framework']}", f"Model string: {model_string or 'UNKNOWN - state the model you ran'}",
             f"Thread id: {summary['thread_id']}; stream shape: {summary['shape']}; turns completed: "
             f"{summary['turns_completed']}; commands: {summary['commands']}; usage: {json.dumps(summary['usage'])}", ""]
    if pred_rows:
        lines += ["| board | file | MB | sha256 | cells | stream mentions |", "|---|---|---|---|---|---|"]
        for r in pred_rows:
            lines.append(f"| {r['board']} | predictions/{r['file']} | {r['bytes'] / 1e6:.1f} | {r['sha256']} | "
                         f"{r['n_obs']} | {r['stream_mentions']} |")
        lines.append("")
    lines += ["Evidence (three kinds; the rules require at least two, one of them the trajectory):", "",
              "| kind | zip | MB | sha256 | files |", "|---|---|---|---|---|"]
    for kind in ("trajectory", "prompts", "harness", "evidence_bundle"):
        n = len(files) if kind == "evidence_bundle" else len(kinds[kind])
        lines.append(f"| {kind} | {zips[kind].name} | {zips[kind].stat().st_size / 1e6:.1f} | "
                     f"{C.sha256_file(zips[kind])} | {n} |")
    lines += ["", f"Team evidence total: {float(team_uploaded_mb):.1f} MB already uploaded + {upload_mb:.1f} MB for this "
              f"package's three kind zips = {team_total:.1f} MB of the {cap:g} MB per-team cap."
              + (" EXCEEDS THE CAP." if team_total > cap else "")]
    if warnings:
        lines += ["", "Warnings:", ""] + [f"* {w}" for w in warnings]
    lines += ["", "Not covered by this adapter: no configuration lock before the run, no launcher or wall clock, no "
              "guard / audit hooks (Codex's own sandbox is the enforcement layer). The prediction files must be the "
              "agent's unedited output."]
    C.write_text(out / "README.md", "\n".join(lines) + "\n")
    print(f"OK {out}\n  predictions: {len(pred_rows)}; evidence files: {len(files)}; warnings: {len(warnings)}")
    for w in warnings:
        print(f"  warn: {w}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m vec_agent_evidence codex-package", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_args(ap)
    return run_from_args(ap.parse_args(argv))


def add_args(ap) -> None:
    ap.add_argument("--stream", required=True, help="stdout of `codex exec --json` (JSONL)")
    ap.add_argument("--prompt", required=True, help="the prompt file the run was given")
    ap.add_argument("--out", required=True, help="new, empty output directory")
    ap.add_argument("--workspace", default=None, help="the directory Codex ran in (AGENTS.md files are collected)")
    ap.add_argument("--codex-home", default=None, help="default: $CODEX_HOME or ~/.codex (rollouts, global AGENTS.md)")
    ap.add_argument("--stderr", default=None, help="stderr of the codex process, if you kept it")
    ap.add_argument("--prediction", action="append", default=[], metavar="BOARD=PATH",
                    help="a prediction written by the agent, e.g. T3:gata4=ws/out/pred.h5ad (repeatable)")
    ap.add_argument("--harness", action="append", default=[], help="a harness file (orchestration script, config) to "
                    "include (repeatable); credential scan applies")
    ap.add_argument("--command-file", default=None, help="text file with the exact codex command line you ran")
    ap.add_argument("--model", default=None, help="the model string you ran (checked against what Codex recorded)")
    ap.add_argument("--team-uploaded-mb", type=float, default=0.0)
    ap.add_argument("--panels", default=None, help="directory with index.json + *.genes.txt (default: the kit's)")


def run_from_args(args) -> int:
    try:
        package_codex(args.stream, args.prompt, args.out, workspace=args.workspace, home=args.codex_home,
                      stderr=args.stderr, predictions=parse_prediction_args(args.prediction), harness=args.harness,
                      command_file=args.command_file, model=args.model, team_uploaded_mb=args.team_uploaded_mb,
                      panels=args.panels)
    except SystemExit as e:
        if str(e).startswith("REFUSED"):
            print(str(e))
            return 2
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
