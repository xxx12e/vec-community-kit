"""The PreToolUse guard and the audit hook, exercised exactly as the agent CLI runs them (subprocess, JSON on stdin)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "vec_agent_evidence" / "hooks" / "guard.py"
AUDIT = ROOT / "vec_agent_evidence" / "hooks" / "audit.py"
PY = sys.executable


def env_for(run_dir: Path) -> dict:
    env = dict(os.environ, PYTHONUTF8="1", VEC_RUN_DIR=str(run_dir))
    return env


def hook(script: Path, payload: dict, run_dir: Path, extra_args=()):
    r = subprocess.run([PY, str(script), *extra_args], input=json.dumps(payload).encode("utf-8"), capture_output=True,
                       env=env_for(run_dir), timeout=60)
    return r.returncode, str(r.stdout, "utf-8", "replace"), str(r.stderr, "utf-8", "replace")


def pre_payload(tool, tool_input, ws: Path) -> dict:
    return {"session_id": "test-session", "transcript_path": str(ws / "t.jsonl"), "cwd": str(ws),
            "permission_mode": "bypassPermissions", "hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": tool_input, "tool_use_id": "toolu_test"}


def reason(out: str) -> str:
    d = json.loads(out)["hookSpecificOutput"]
    assert d["hookEventName"] == "PreToolUse" and d["permissionDecision"] == "deny"
    return d["permissionDecisionReason"]


def make_run(tmp_path: Path):
    run_dir = tmp_path / "runs" / "20260902-1200_T3_abcdef01"
    ws = run_dir / "workspace"
    (ws / "src").mkdir(parents=True)
    return run_dir, ws


def test_guard_denies_and_allows(tmp_path):
    run_dir, ws = make_run(tmp_path)
    denied = [
        ("Bash", {"command": "curl https://example.org/x.h5ad -o scratch/x.h5ad"}, "network"),
        ("Bash", {"command": "pip install scvi-tools"}, "network"),
        ("Bash", {"command": "python -c \"import requests; requests.get('http://x')\""}, "network"),
        ("Bash", {"command": "git clone https://github.com/x/y"}, "network"),
        ("Write", {"file_path": "../submission/x.h5ad", "content": "x"}, "finalize_submission"),
        ("Bash", {"command": "cp out/c1/pred.h5ad ../submission/pred_T3_gata4.h5ad"}, "finalize_submission"),
        ("Bash", {"command": "cat ~/.claude/settings.json"}, ".claude"),
        ("Read", {"file_path": str(tmp_path / "runs" / "20260901-0900_T3_11112222" / "workspace" / "NOTES.md")}, "another run"),
        ("Edit", {"file_path": "tools/finalize_submission.py", "old_string": "a", "new_string": "b"}, "read-only"),
        ("Write", {"file_path": str(tmp_path / "elsewhere.py"), "content": "x"}, "confined"),
        ("Write", {"file_path": "DEADLINE.txt", "content": "x"}, "frozen"),
        ("Bash", {"command": "echo 1 > data/panels/index.json"}, "read-only"),
        ("Bash", {"command": "rm -rf tools/"}, "read-only"),
        ("Bash", {"command": "cat ../config.lock.json"}, "run metadata"),
        ("Bash", {"command": "claude -p 'hello'"}, "network"),
    ]
    for tool, ti, needle in denied:
        rc, out, err = hook(GUARD, pre_payload(tool, ti, ws), run_dir)
        assert rc == 2, (tool, ti, out, err)
        assert needle in reason(out), (tool, ti, reason(out))
    allowed = [
        ("Bash", {"command": "python src/train.py --epochs 3"}),
        ("Bash", {"command": "python tools/finalize_submission.py --board T3:gata4 --candidate out/candidates/c1/pred.h5ad"}),
        ("Bash", {"command": "python -m vec_submit_check --board T3:gata4 out/candidates/c1/pred.h5ad"}),
        ("Bash", {"command": "ls ../submission/"}),
        ("Bash", {"command": "cat data/panels/index.json | head -5"}),
        ("Write", {"file_path": str(ws / "src" / "model.py"), "content": "x"}),
        ("Write", {"file_path": "NOTES.md", "content": "x"}),
        ("Edit", {"file_path": "out/candidates/c1/notes.md", "old_string": "a", "new_string": "b"}),
        ("Read", {"file_path": "data/raw/E9.5.h5ad"}),
        ("Read", {"file_path": str(run_dir / "workspace" / "tools" / "vec_baselines" / "io.py")}),
    ]
    for tool, ti in allowed:
        rc, out, err = hook(GUARD, pre_payload(tool, ti, ws), run_dir)
        assert rc == 0 and out.strip() == "", (tool, ti, out, err)
    # unparseable stdin is not our contract: never blocks
    r = subprocess.run([PY, str(GUARD)], input=b"not json", capture_output=True, env=env_for(run_dir))
    assert r.returncode == 0
    denials = (run_dir / "hooks" / "guard_denials.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(denials) == len(denied)
    assert all(json.loads(d)["event"] == "PreToolUse.deny" for d in denials)


def test_guard_denies_process_kill(tmp_path):
    run_dir, ws = make_run(tmp_path)
    for cmd in ("taskkill //F //IM python.exe", "cd scratch && taskkill /PID 1234 /F", "pkill -f local_score",
                "Get-Process python | Stop-Process -Force", "kill -9 4242", "wmic process where name='python.exe' delete"):
        rc, out, err = hook(GUARD, pre_payload("Bash", {"command": cmd}, ws), run_dir)
        assert rc == 2, cmd
        assert "process-kill" in reason(out), cmd
    for cmd in ("python src/skill_table.py", "echo killed_by_gate > scratch/log.txt", "python -m vec_local_score --help"):
        rc, out, err = hook(GUARD, pre_payload("Bash", {"command": cmd}, ws), run_dir)
        assert rc == 0 and out.strip() == "", cmd


def test_guard_without_run_dir_uses_cwd_as_workspace(tmp_path):
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k != "VEC_RUN_DIR"}
    env["PYTHONUTF8"] = "1"
    r = subprocess.run([PY, str(GUARD)], input=json.dumps(pre_payload("Write", {"file_path": str(tmp_path / "x.py"), "content": "x"}, ws)).encode("utf-8"),
                       capture_output=True, env=env)
    assert r.returncode == 2
    r = subprocess.run([PY, str(GUARD)], input=json.dumps(pre_payload("Write", {"file_path": str(ws / "src" / "x.py"), "content": "x"}, ws)).encode("utf-8"),
                       capture_output=True, env=env)
    assert r.returncode == 0


def test_audit_appends(tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "hooks").mkdir(parents=True)
    base = {"session_id": "s1", "transcript_path": "C:/x/s1.jsonl", "cwd": "C:/x", "permission_mode": "bypassPermissions"}
    rc, out, err = hook(AUDIT, dict(base, hook_event_name="SessionStart", source="startup"), run_dir, ("--session-start",))
    assert rc == 0 and out == ""
    rc, out, err = hook(AUDIT, dict(base, hook_event_name="PostToolUse", tool_name="Bash", tool_use_id="t1",
                                    tool_input={"command": "ls"}, tool_response={"type": "text", "text": "x" * 5000}), run_dir)
    assert rc == 0 and out == ""
    r = subprocess.run([PY, str(AUDIT)], input=b"garbage", capture_output=True, env=env_for(run_dir))
    assert r.returncode == 0
    lines = [json.loads(x) for x in (run_dir / "hooks" / "tool_audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 3 and lines[0]["event"] == "SessionStart" and lines[1]["tool_name"] == "Bash"
    assert "chars>" in lines[1]["tool_response"] and lines[1]["transcript_path"] == "C:/x/s1.jsonl"
    assert lines[2]["event"] == "unknown"
    ss = json.loads((run_dir / "hooks" / "session_start.json").read_text(encoding="utf-8"))
    assert ss[0]["transcript_path"] == "C:/x/s1.jsonl"
