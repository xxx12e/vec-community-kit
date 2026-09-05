#!/usr/bin/env python
"""Stand-in for the agent CLI used by the tests. Never calls any API.

Speaks the stream-json contract (init -> assistant -> result), honours --model / --tools / --permission-mode /
--session-id from argv, reads the prompt from stdin, exercises the run-local hooks (one denied network call, one
audit line), finalizes a candidate through tools/finalize_submission.py, writes NOTES.md and a candidate note,
and drops a transcript at $VEC_CLAUDE_PROJECTS_DIR/<encoded-cwd>/<session-id>.jsonl like the real CLI does.

VEC_FAKE_MODE: "" (normal) | "model_mismatch" (init echoes a different model) | "hang" (sleeps after init)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def arg(flag, default=None):
    argv = sys.argv
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def emit(obj) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> int:
    prompt = sys.stdin.read()
    model = arg("--model", "unknown-model")
    tools = [t for t in arg("--tools", "").split(",") if t]
    session = arg("--session-id", "no-session")
    mode = os.environ.get("VEC_FAKE_MODE", "")
    ws = Path.cwd()
    run_dir = Path(os.environ["VEC_RUN_DIR"])
    board = os.environ.get("VEC_BOARDS", "T3:gata4").split(",")[0]
    emit({"type": "system", "subtype": "init", "session_id": session,
          "model": "some-other-model" if mode == "model_mismatch" else model,
          "permissionMode": arg("--permission-mode", "bypassPermissions"), "tools": tools + ["StructuredOutput"]})
    if mode in ("hang", "model_mismatch"):
        time.sleep(3600)
        return 0

    py = sys.executable
    # 1. a network attempt, denied by the run-local guard (shows up in hooks/guard_denials.jsonl)
    denied_cmd = "curl https://example.org/data.h5ad"
    guard_payload = {"session_id": session, "transcript_path": "", "cwd": str(ws), "permission_mode": "bypassPermissions",
                     "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": denied_cmd},
                     "tool_use_id": "toolu_fake_1"}
    subprocess.run([py, str(run_dir / "hooks" / "guard.py")], input=json.dumps(guard_payload).encode("utf-8"),
                   capture_output=True, timeout=60)

    # 2. finalize the floor candidate through the sanctioned route
    candidate = Path(os.environ["VEC_DATA_DIR"]) / "raw" / "tiny_wt.h5ad"
    cand_dir = ws / "out" / "candidates" / "c1"
    cand_dir.mkdir(parents=True, exist_ok=True)
    (cand_dir / "notes.md").write_text("floor row: matched wild type resubmitted\n", encoding="utf-8")
    fin_cmd = [py, str(ws / "tools" / "finalize_submission.py"), "--board", board, "--candidate", str(candidate),
               "--candidate-id", "c1"]
    if os.environ.get("VEC_ALLOW_RELAX") == "1":
        fin_cmd.append("--relax-cells")
    r = subprocess.run(fin_cmd, capture_output=True, timeout=600, cwd=str(ws), text=True, encoding="utf-8", errors="replace")
    tool_use = {"type": "tool_use", "id": "toolu_fake_2", "name": "Bash", "input": {"command": " ".join(fin_cmd)}}
    emit({"type": "assistant", "uuid": "a1", "message": {"role": "assistant", "content": [tool_use]}})
    audit_payload = {"session_id": session, "transcript_path": "", "cwd": str(ws), "permission_mode": "bypassPermissions",
                     "hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": tool_use["input"],
                     "tool_use_id": "toolu_fake_2", "tool_response": {"stdout": r.stdout[-500:], "rc": r.returncode}}
    subprocess.run([py, str(run_dir / "hooks" / "audit.py")], input=json.dumps(audit_payload).encode("utf-8"),
                   capture_output=True, timeout=60)
    (ws / "NOTES.md").write_text(f"# NOTES\n\nfinalized c1 for {board}: rc={r.returncode}\n{r.stdout}\n{r.stderr}\n", encoding="utf-8")

    # 3. transcript, where the real CLI would put it
    projects = Path(os.environ.get("VEC_CLAUDE_PROJECTS_DIR") or (ws / "fake_projects"))
    d = projects / "encoded-cwd"
    d.mkdir(parents=True, exist_ok=True)
    records = [
        {"type": "user", "uuid": "u1", "timestamp": "2026-01-01T00:00:00Z", "message": {"role": "user", "content": prompt[:400]}},
        {"type": "assistant", "uuid": "a1", "timestamp": "2026-01-01T00:00:01Z",
         "message": {"role": "assistant", "content": [tool_use]}},
        {"type": "user", "uuid": "u2", "timestamp": "2026-01-01T00:00:02Z",
         "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_fake_2", "content": r.stdout[-300:]}]}},
    ]
    (d / f"{session}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in records), encoding="utf-8")
    (d / session / "tool-results").mkdir(parents=True, exist_ok=True)
    (d / session / "tool-results" / "toolu_fake_2.txt").write_text(r.stdout, encoding="utf-8")

    emit({"type": "result", "subtype": "success" if r.returncode == 0 else "error", "is_error": r.returncode != 0,
          "num_turns": 3, "duration_ms": 1000, "total_cost_usd": 0.0, "session_id": session,
          "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 0},
          "permission_denials": [{"tool_name": "Bash", "tool_input": {"command": denied_cmd}}]})
    return 0 if r.returncode == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
