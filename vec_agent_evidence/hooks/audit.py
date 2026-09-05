#!/usr/bin/env python
"""PostToolUse / PostToolUseFailure / SessionStart / PreCompact / Stop audit hook (stdlib only, ASCII only).

Appends one JSON line per event to $VEC_RUN_DIR/hooks/tool_audit.jsonl (fallback: <cwd>/../hooks/ if that
directory exists, else <cwd>/hooks_audit_fallback.jsonl). A SessionStart event additionally writes
hooks/session_start.json (it carries transcript_path, the authoritative location of the trajectory).
Never blocks and never fails the tool call: no stdout, exit 0 always.

Hook input contract (https://code.claude.com/docs/en/hooks): session_id, transcript_path, cwd,
permission_mode, hook_event_name, tool_name, tool_input, tool_use_id, tool_response (PostToolUse),
source and model (SessionStart).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_INPUT = 2000
MAX_RESPONSE = 600


def audit_dir() -> Path:
    run_dir = os.environ.get("VEC_RUN_DIR")
    if run_dir:
        return Path(run_dir) / "hooks"
    cand = Path.cwd().parent / "hooks"
    return cand if cand.is_dir() else Path.cwd()


def clip(obj, n: int) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    return s if len(s) <= n else s[:n] + f"...<{len(s)} chars>"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {"unparseable_stdin": raw[:500]}
    if not isinstance(payload, dict):
        payload = {"non_object_stdin": str(payload)[:500]}
    event = payload.get("hook_event_name") or ("SessionStart" if "--session-start" in argv else "unknown")
    d = audit_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        line = {
            "utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "event": event, "session_id": payload.get("session_id"), "tool_name": payload.get("tool_name"),
            "tool_use_id": payload.get("tool_use_id"), "cwd": payload.get("cwd"),
            "permission_mode": payload.get("permission_mode"), "transcript_path": payload.get("transcript_path"),
            "tool_input": clip(payload.get("tool_input"), MAX_INPUT) if "tool_input" in payload else None,
            "tool_response": clip(payload.get("tool_response"), MAX_RESPONSE) if "tool_response" in payload else None,
        }
        target = d / "tool_audit.jsonl" if d.name == "hooks" else d / "hooks_audit_fallback.jsonl"
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        if event == "SessionStart":
            ss = d / "session_start.json"
            existing = []
            if ss.exists():
                try:
                    existing = json.loads(ss.read_text(encoding="utf-8"))
                    if not isinstance(existing, list):
                        existing = [existing]
                except ValueError:
                    existing = []
            existing.append(payload)
            ss.write_text(json.dumps(existing, indent=2, default=str) + "\n", encoding="utf-8")
    except OSError as e:
        sys.stderr.write(f"audit hook could not write: {e}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
