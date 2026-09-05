"""Post-run evidence collection.

Copies the CLI transcript (located by session UUID, byte copy), copies the agent's small artefacts, validates
every submission file with vec_submit_check, re-verifies every hash of the configuration lock, scans every text
file for credential-shaped patterns, writes run_manifest.json (result, usage, every evidence file's bytes +
sha256, size warnings against the portal limits) and seals the run directory read-only.

    python -m vec_agent_evidence postrun --run-dir runs/<run_id> [--projects-dir ~/.claude/projects]
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from vec_submit_check import check as check_file

from . import common as C

# What gets uploaded as evidence (the prediction .h5ad is the submission itself, not evidence).
UPLOAD_PREFIXES = ("transcript/", "stream.jsonl", "stderr.log", "initial_prompt.md", "system_prompt_appendix.md",
                   "prompts.manifest.json", "config.lock.json", "config.lock.sha256", "claude_settings.json",
                   "harness_snapshot.zip", "env/", "hooks/", "launch_command.json", "launch_state.json",
                   "LOCK_TIMESTAMP", "artifacts/", "submission/MANIFEST.json")
EXCLUDED_SUFFIXES = (".h5ad", ".pt", ".pth", ".ckpt", ".npy", ".npz", ".pkl", ".bin", ".safetensors")


# ------------------------------------------------------------------------------------------ transcript
def find_transcripts(projects_dir: Path, session_id: str) -> list:
    """The CLI encodes the working directory into a project folder name; never compute it, glob for the UUID."""
    projects_dir = Path(projects_dir)
    if not projects_dir.exists():
        return []
    return sorted(projects_dir.glob(f"*/{session_id}.jsonl"))


def collect_transcript(run: Path, cfg: dict, projects_dir: Path) -> dict:
    matches = find_transcripts(projects_dir, cfg["session_id"])
    rep = {"projects_dir": str(projects_dir), "session_id": cfg["session_id"],
           "matches": [str(m) for m in matches], "copied": []}
    dest = run / "transcript"
    dest.mkdir(parents=True, exist_ok=True)
    for src in matches:
        shutil.copy2(src, dest / src.name)
        rep["copied"].append(src.name)
        side = src.with_suffix("")                      # <projects>/<enc-cwd>/<session-id>/
        for sub in ("tool-results", "subagents"):
            if (side / sub).is_dir():
                shutil.copytree(side / sub, dest / sub, dirs_exist_ok=True)
                rep["copied"].append(sub + "/")
    if not matches:
        rep["warning"] = ("no transcript found for this session id under projects_dir; check --projects-dir / "
                          "VEC_CLAUDE_PROJECTS_DIR and that session persistence was not disabled")
    return rep


def collect_artifacts(run: Path) -> list:
    ws, art = run / "workspace", run / "artifacts"
    copied = []
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", *("*" + s for s in EXCLUDED_SUFFIXES))
    for rel in ("src", "experiments.jsonl", "NOTES.md", "README_WORKSPACE.md", "DEADLINE.txt"):
        src = ws / rel
        if src.is_dir():
            shutil.copytree(src, art / rel, dirs_exist_ok=True, ignore=ignore)
            copied.append(rel + "/")
        elif src.is_file():
            art.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, art / rel)
            copied.append(rel)
    for cand in sorted((ws / "out" / "candidates").glob("*")):
        if not cand.is_dir():
            continue
        for f in sorted(cand.iterdir()):
            if f.is_file() and f.suffix.lower() in (".json", ".md", ".txt", ".log", ".csv"):
                (art / "candidates" / cand.name).mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, art / "candidates" / cand.name / f.name)
                copied.append(f"candidates/{cand.name}/{f.name}")
    return copied


def find_writer_tool_uses(transcript_dir: Path, needles=("finalize_submission",)) -> list:
    """Provenance link: the tool_use records in the trajectory that invoked the submission writer."""
    hits = []
    for jsonl in sorted(Path(transcript_dir).glob("*.jsonl")):
        with open(jsonl, "rb") as f:
            for lineno, raw in enumerate(f, 1):
                try:
                    d = json.loads(str(raw, "utf-8", "replace"))
                except ValueError:
                    continue
                if not isinstance(d, dict) or d.get("type") != "assistant":
                    continue
                content = (d.get("message") or {}).get("content") or []
                if not isinstance(content, list):
                    continue
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        s = json.dumps(b.get("input"), default=str)
                        if any(n in s for n in needles):
                            hits.append({"file": jsonl.name, "line": lineno, "uuid": d.get("uuid"),
                                         "tool_use_id": b.get("id"), "tool": b.get("name"),
                                         "timestamp": d.get("timestamp"),
                                         "line_sha256": C.sha256_bytes(raw.rstrip(b"\r\n"))})
    return hits


# ------------------------------------------------------------------------------------------ submission
def read_agent_manifest(run: Path) -> list:
    p = run / "submission" / "MANIFEST.json"
    if not p.exists():
        return []
    try:
        m = C.read_json(p)
    except ValueError:
        return [{"error": "MANIFEST.json unparseable"}]
    return m.get("entries", []) if isinstance(m, dict) else list(m)


def validate_submissions(run: Path, cfg: dict) -> dict:
    entries = read_agent_manifest(run)
    writer = find_writer_tool_uses(run / "transcript")
    relax_allowed = cfg.get("env_overrides", {}).get("VEC_ALLOW_RELAX") == "1"
    boards, n_ok = {}, 0
    for board in cfg["boards"]:
        f = run / "submission" / f"pred_{C.board_sanitised(board)}.h5ad"
        mine = [e for e in entries if isinstance(e, dict) and e.get("board") == board]
        rep = {"file": f.name, "status": "no_submission", "agent_manifest_entries": mine, "writer_tool_uses": writer}
        if f.exists():
            try:
                fmt = check_file(f, board, cfg.get("panels_dir"))
            except Exception as e:  # noqa: BLE001 - a crash is a format failure, never a harness crash
                fmt = {"ok": False, "errors": [f"checker crashed: {e!r}"], "warnings": [], "info": {}}
            relaxed = bool(relax_allowed and fmt["errors"] and all("< min_cells" in x for x in fmt["errors"]))
            rep.update(format=fmt, sha256=C.sha256_file(f), bytes=f.stat().st_size,
                       status="ok" if (fmt["ok"] or relaxed) else "format_invalid",
                       relaxed_min_cells=relaxed, uploadable=bool(fmt["ok"]))
            if mine and mine[-1].get("sha256") != rep["sha256"]:
                rep["manifest_sha_mismatch"] = True
            n_ok += rep["status"] == "ok"
        boards[board] = rep
    status = "ok" if n_ok == len(cfg["boards"]) else ("partial" if n_ok else "no_submission")
    return {"status": status, "boards": boards}


# ------------------------------------------------------------------------------------------ manifest
def verify_lock_integrity(run: Path, cfg: dict) -> dict:
    problems = []
    blob = (run / "config.lock.json").read_bytes()
    if C.sha256_bytes(blob) != (run / "config.lock.sha256").read_text(encoding="utf-8").strip():
        problems.append("config.lock.json does not match config.lock.sha256")
    for fname, key in (("initial_prompt.md", "initial_prompt_sha256"),
                       ("system_prompt_appendix.md", "system_prompt_appendix_sha256"),
                       ("claude_settings.json", "claude_settings_sha256")):
        if key in cfg["prompts"]:
            if not (run / fname).exists() or C.sha256_file(run / fname) != cfg["prompts"][key]:
                problems.append(f"{fname} modified after lock")
    for name, h in cfg.get("hooks", {}).items():
        if C.sha256_file(run / "hooks" / name) != h:
            problems.append(f"hooks/{name} modified after lock")
    if C.sha256_file(run / "harness_snapshot.zip") != cfg.get("harness_snapshot_sha256"):
        problems.append("harness_snapshot.zip modified after lock")
    return {"ok": not problems, "problems": problems}


def evidence_files(run: Path):
    skip = [Path("workspace/scratch"), Path("workspace/data")]
    for f in C.iter_files(run, skip_rel_dirs=skip):
        rel = f.relative_to(run).as_posix()
        if rel == "run_manifest.json":
            continue
        if rel.startswith("workspace/") and f.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        yield rel, f


def secret_scan(run: Path, extra_values=()) -> dict:
    """Credentials must never enter an evidence bundle: scan every text evidence file for credential-shaped
    markers (common.SECRET_PATTERNS) and for any literal values passed in `extra_values` (e.g. a gateway key you
    know you used). The report carries pattern labels only, never values."""
    patterns = list(C.SECRET_PATTERNS)
    for i, v in enumerate(extra_values):
        if v:
            import re
            patterns.append((f"extra_value_{i}", re.compile(re.escape(str(v).encode("utf-8")))))
    hits = []
    for rel, f in evidence_files(run):
        if f.suffix.lower() not in C.SECRET_SCAN_SUFFIXES or f.stat().st_size > 200 * 1024 * 1024:
            continue
        with open(f, "rb") as fh:
            data = fh.read()
        found = [label for label, rx in patterns if rx.search(data)]
        if found:
            hits.append({"file": rel, "patterns": found})
    if hits:
        C.log(f"SECRET SCAN HIT: {hits} - do NOT upload before reviewing these files")
    return {"clean": not hits, "hits": hits, "patterns": [label for label, _ in patterns]}


def size_report(ev: dict) -> dict:
    lim = C.UPLOAD_LIMITS
    upload = sum(v["bytes"] for rel, v in ev.items() if rel.startswith(UPLOAD_PREFIXES))
    big = [rel for rel, v in ev.items() if v["bytes"] > lim["per_file_mb"] * 1e6]
    warnings = []
    if big:
        warnings.append(f"{len(big)} evidence file(s) exceed the {lim['per_file_mb']} MB per-file cap: {big[:5]}")
    if upload > lim["team_total_mb"] * 1e6:
        warnings.append(f"upload set {upload / 1e6:.1f} MB exceeds the {lim['team_total_mb']} MB team total by itself")
    return {"upload_set_bytes": upload, "files_over_per_file_limit": big, "limits": dict(lim), "warnings": warnings}


def build_manifest(run: Path, cfg: dict, state: dict, transcript: dict, artifacts: list, submission: dict,
                   integrity: dict) -> dict:
    res = state.get("result") or {}
    ev = {rel: {"bytes": f.stat().st_size, "sha256": C.sha256_file(f)} for rel, f in evidence_files(run)}
    scan = secret_scan(run)
    sizes = size_report(ev)
    for w in sizes["warnings"]:
        C.log("size warning: " + w)
    return {
        "run_id": cfg["run_id"], "dry_run": bool(cfg.get("dry_run")),
        "config_lock_sha256": (run / "config.lock.sha256").read_text(encoding="utf-8").strip(),
        "lock_integrity": integrity,
        "locked_utc": cfg["created_utc"], "launch_started_utc": state.get("started_utc"),
        "ended_utc": C.iso(C.now_utc()), "deadline_utc": cfg["deadline_utc"], "wall_clock_hours": cfg["wall_clock_hours"],
        "model_locked": cfg["model"], "effort": cfg.get("effort"), "max_turns": cfg["max_turns"],
        "claude_exe": cfg.get("claude_exe"), "claude_version": cfg.get("claude_version"),
        "claude_init": state.get("init"), "init_problems": state.get("init_problems"),
        "init_tool_extras": state.get("init_tool_extras"), "secret_scan": scan,
        "result_subtype": res.get("subtype"), "is_error": res.get("is_error"), "num_turns": res.get("num_turns"),
        "assistant_events": state.get("assistant_events"), "stream_events": state.get("events"),
        "events_by_type": state.get("events_by_type"), "total_cost_usd": res.get("total_cost_usd"),
        "usage": res.get("usage"), "modelUsage": res.get("modelUsage"),
        "permission_denials": res.get("permission_denials"), "structured_output": res.get("structured_output"),
        "abort": state.get("abort"), "deadline_hit": state.get("deadline_hit"), "kill": state.get("kill"),
        "returncode": state.get("returncode"),
        "transcript": transcript, "artifacts": artifacts, "submission": submission,
        "evidence": ev, "evidence_total_bytes": sum(v["bytes"] for v in ev.values()),
        "upload_set_bytes": sizes["upload_set_bytes"], "sizes": sizes,
        "human_touch": "none - run directory sealed read-only by the harness; any later modification changes "
                       "the hashes recorded here",
    }


def seal(run: Path) -> int:
    return C.set_read_only(run, skip_rel_dirs=[Path("workspace/scratch")])


def state_from_stream(run: Path) -> dict:
    """Recovery path: rebuild the launch state from stream.jsonl when launch_state.json is missing."""
    state = {"init": None, "result": None, "assistant_events": 0, "events": 0, "events_by_type": {},
             "abort": "unknown (state reconstructed from stream.jsonl)", "recovered": True}
    p = run / "stream.jsonl"
    if not p.exists():
        return state
    with open(p, "rb") as f:
        for raw in f:
            state["events"] += 1
            try:
                ev = json.loads(str(raw, "utf-8", "replace"))
            except ValueError:
                continue
            t = ev.get("type") if isinstance(ev, dict) else None
            state["events_by_type"][str(t)] = state["events_by_type"].get(str(t), 0) + 1
            if t == "system" and ev.get("subtype") == "init":
                state["init"] = ev
            elif t == "assistant":
                state["assistant_events"] += 1
            elif t == "result":
                state["result"] = ev
    return state


def postrun(run: Path, projects_dir=None, state=None) -> dict:
    """Collect the evidence of a finished run and write run_manifest.json. Not repeatable (sealed evidence)."""
    run = Path(run).resolve()
    cfg = C.read_json(run / "config.lock.json")
    if (run / "run_manifest.json").exists():
        raise SystemExit(f"{run} already has run_manifest.json; postrun is not repeatable (sealed evidence)")
    if (run / "RUNNING").exists():
        raise SystemExit(f"{run} has a RUNNING sentinel; postrun only after the agent process has exited")
    C.set_writable(run)
    if state is None:
        state = C.read_json(run / "launch_state.json") if (run / "launch_state.json").exists() else state_from_stream(run)
    projects_dir = Path(projects_dir or cfg.get("claude_projects_dir") or C.DEFAULT_PROJECTS_DIR)
    C.log("postrun: collecting evidence")
    integrity = verify_lock_integrity(run, cfg)
    if not integrity["ok"]:
        C.log(f"LOCK INTEGRITY PROBLEMS: {integrity['problems']}")
    transcript = collect_transcript(run, cfg, projects_dir)
    artifacts = collect_artifacts(run)
    submission = validate_submissions(run, cfg)
    manifest = build_manifest(run, cfg, state, transcript, artifacts, submission, integrity)
    C.write_json(run / "run_manifest.json", manifest)
    n = seal(run)
    C.log(f"sealed {n} files read-only; run_manifest.json written; submission status = {submission['status']}")
    return manifest
