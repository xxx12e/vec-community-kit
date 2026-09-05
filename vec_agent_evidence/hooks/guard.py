#!/usr/bin/env python
"""PreToolUse guard hook for an Agent-track run (stdlib only, ASCII only, no imports from the kit).

Contract (Claude Code hooks, https://code.claude.com/docs/en/hooks):
  stdin  : one JSON object with session_id, transcript_path, cwd, permission_mode, hook_event_name,
           tool_name, tool_input, tool_use_id
  stdout : on deny -> {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
           "permissionDecisionReason": "..."}} and exit code 2 (exit 2 blocks regardless of JSON; the JSON
           reason is what the agent sees). On allow -> no output, exit 0.

Denies
  * network-shaped Bash commands (curl, wget, Invoke-WebRequest/iwr/irm, git clone|fetch|pull|push, pip/uv/conda
    install, npm/npx, ssh/scp/ftp/nc, python one-liners using requests/httpx/urllib/socket/huggingface_hub/
    torch.hub/scanpy.datasets, any http(s):// URL);
  * any reference to the Claude configuration directory (~/.claude, .credentials.json);
  * any reference to a run directory under runs/ other than the current one ($VEC_RUN_DIR);
  * writes to <run>/submission/ except through tools/finalize_submission.py (Write/Edit file paths and Bash
    segments; read-only commands on submission/ are allowed);
  * Write/Edit outside the workspace, or into workspace/tools, workspace/baselines, workspace/data,
    DEADLINE.txt, README_WORKSPACE.md; mutating Bash commands / redirections aimed at those paths;
  * process-kill commands (taskkill, pkill, kill, Stop-Process, ...): they can kill the supervising harness;
  * recursive `claude -p` invocations.
Fail-closed: an internal error denies with the error text as the reason (the run is never silently exposed).
Every denial is appended to $VEC_RUN_DIR/hooks/guard_denials.jsonl.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

NETWORK_PATTERNS = [
    r"\bcurl\b", r"\bwget\b", r"Invoke-WebRequest", r"Invoke-RestMethod", r"\biwr\b", r"\birm\b",
    r"Start-BitsTransfer", r"\bbitsadmin\b", r"certutil\b.*-urlcache",
    r"\bgit\s+(?:-C\s+\S+\s+)?(?:clone|fetch|pull|push|remote|submodule|ls-remote)\b",
    r"\bpip3?\s+(?:install|download|wheel)\b", r"\bpython\S*\s+-m\s+pip\s+(?:install|download|wheel)\b",
    r"\buv\s", r"\bconda\s+(?:install|create|update|env)\b", r"\bmamba\s+(?:install|create|update)\b",
    r"\bnpm\b", r"\bnpx\b", r"\bpnpm\b", r"\byarn\b", r"\bssh\b", r"\bscp\b", r"\bsftp\b", r"\bftp\b",
    r"\bnc\b", r"\bncat\b", r"\bnetcat\b", r"\btelnet\b", r"\brsync\b", r"\baria2c\b", r"\bgdown\b",
    r"\bkaggle\b", r"\bwandb\b", r"\brequests\b", r"\bhttpx\b", r"\burllib\d?\b", r"\baiohttp\b",
    r"\bsocket\b", r"huggingface_hub", r"hf_hub_download", r"snapshot_download", r"torch\.hub",
    r"scanpy\.datasets", r"\bsc\.datasets\b", r"\bpooch\b", r"https?://", r"/dev/tcp/",
    r"\bclaude(?:\.exe|\.cmd)?\s+(?:-p\b|--)",
]
NETWORK_RE = re.compile("|".join(f"(?:{p})" for p in NETWORK_PATTERNS), re.IGNORECASE)
CLAUDE_DIR_RE = re.compile(r"(?:^|[\\/\s\"'=:~(])\.claude(?:[\\/]|\.json|$|[\"'\s)])|\.credentials\.json|CLAUDE_CONFIG_DIR",
                           re.IGNORECASE)
RUNS_RE = re.compile(r"(?:^|[\\/\s\"'=:(])runs[\\/]+([^\\/\s\"'`;&|<>()]+)", re.IGNORECASE)
RUN_ID_RE = re.compile(r"^\d{8}-\d{4}_T[123]_[0-9a-f]{8}$")
SUBMISSION_RE = re.compile(r"(?:^|[\\/\s\"'=:.(])submission[\\/]", re.IGNORECASE)
SPLIT_RE = re.compile(r"&&|\|\||;|\||\n")
MUTATING_RE = re.compile(r"(?:^|[\s;&|(`$])(?:rm|rmdir|mv|cp|tee|truncate|install|chmod|chown|attrib|del|erase|rd|ren|"
                         r"shred|ln|unlink|mkdir|touch|rmdir|sed\s+-i|perl\s+-i|dd|xcopy|robocopy|move|copy)\b", re.IGNORECASE)
REDIRECT_RE = re.compile(r">>?\s*['\"]?([^\s'\"|;&]+)")
# Killing by image name or by arbitrary pid can take down the harness supervising the run and unrelated jobs.
PROCESS_KILL_RE = re.compile(r"(?:^|[\s;&|(`$])(?:taskkill|tskill|pkill|killall|kill|Stop-Process|spps|"
                             r"wmic\s+process[^\n]*\b(?:delete|terminate)|Get-Process[^\n|]*\|\s*Stop-Process)\b", re.IGNORECASE)
PROTECTED_REL_RE = re.compile(r"(?:^|[\s\"'=:(])(?:\.{1,2}[\\/])*(?:tools|baselines|data)[\\/]|DEADLINE\.txt|README_WORKSPACE\.md",
                              re.IGNORECASE)
READ_ONLY_HEADS = {"cat", "head", "tail", "ls", "dir", "stat", "wc", "sha256sum", "md5sum", "file", "du", "less", "more",
                   "type", "python", "python3", "jq", "grep", "diff", "cmp"}
RUN_META_TOKENS = ("config.lock", "initial_prompt", "system_prompt_appendix", "claude_settings", "harness_snapshot",
                   "stream.jsonl", "stderr.log", "transcript", "run_manifest", "LOCK_TIMESTAMP", "launch_command",
                   "launch_state", "prompts.manifest", "hooks", "env", "artifacts")


def _norm(p: Path) -> str:
    return os.path.normcase(str(p)).rstrip("\\/") + os.sep


def _under(child: Path, parent: Path) -> bool:
    return _norm(child).startswith(_norm(parent))


def _record(run_dir, payload, reason):
    if not run_dir:
        return
    try:
        d = Path(run_dir) / "hooks"
        d.mkdir(parents=True, exist_ok=True)
        line = {"utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "event": "PreToolUse.deny", "tool_name": payload.get("tool_name"), "tool_use_id": payload.get("tool_use_id"),
                "reason": reason, "tool_input": json.dumps(payload.get("tool_input"), default=str)[:2000]}
        with open(d / "guard_denials.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except OSError:
        pass


def other_run_reference(blob: str, run_dir):
    current = Path(run_dir).name if run_dir else None
    for m in RUNS_RE.finditer(blob):
        comp = m.group(1).rstrip(",.)")
        if current and comp.lower() == current.lower():
            continue
        if RUN_ID_RE.match(comp) or current:
            return f"references another run directory (runs/{comp}); each run is isolated to its own directory"
    return None


def check_write_path(p, ws: Path, run_dir):
    if not p:
        return None
    path = Path(p)
    if not path.is_absolute():
        path = ws / path
    path = Path(os.path.abspath(str(path)))
    if run_dir and _under(path, Path(run_dir) / "submission"):
        return "only tools/finalize_submission.py may write to submission/ (validated + hashed + manifest)"
    if not _under(path, ws):
        return f"writes are confined to the workspace ({ws}); refused: {path}"
    for sub in ("tools", "baselines", "data"):
        if _under(path, ws / sub):
            return f"workspace/{sub}/ is read-only for the agent"
    if _norm(path) in (_norm(ws / "DEADLINE.txt"), _norm(ws / "README_WORKSPACE.md")):
        return f"{path.name} is part of the frozen workspace contract and may not be modified"
    return None


def check_bash(cmd: str, ws: Path, run_dir):
    m = NETWORK_RE.search(cmd)
    if m:
        return (f"network access is forbidden inside a run (matched {m.group(0)!r}); all data is under data/, "
                "all packages are preinstalled")
    mk = PROCESS_KILL_RE.search(" " + cmd)
    if mk:
        return (f"process-kill commands are forbidden inside a run (matched {mk.group(0).strip()!r}): they can kill the "
                "harness supervising this run and unrelated jobs on the machine. Do not start background workers you "
                "cannot wait for; run long jobs sequentially instead")
    for seg in SPLIT_RE.split(cmd):
        s = seg.strip()
        if not s:
            continue
        head = s.split()[0].lower() if s.split() else ""
        redirect_targets = REDIRECT_RE.findall(s)
        if SUBMISSION_RE.search(s) and "finalize_submission" not in s:
            if head in READ_ONLY_HEADS and not redirect_targets and "open(" not in s:
                pass
            else:
                return ("only tools/finalize_submission.py may write to submission/ (use: python tools/finalize_submission.py "
                        "--board <board> --candidate <file>)")
        if re.search(r"\.\.[\\/]", s):
            for tok in RUN_META_TOKENS:
                if re.search(r"\.\.[\\/](?:[^\s\"']*[\\/])?" + re.escape(tok), s):
                    return f"run metadata ({tok}) outside the workspace is off limits"
        for tgt in redirect_targets:
            if tgt.lower() in ("/dev/null", "&1", "&2", "nul"):
                continue
            if PROTECTED_REL_RE.search(" " + tgt):
                return f"redirection into a read-only path ({tgt}); write under src/, scratch/ or out/"
        if MUTATING_RE.search(" " + s) and PROTECTED_REL_RE.search(s):
            return "mutating command aimed at tools/, baselines/, data/, DEADLINE.txt or README_WORKSPACE.md (read-only)"
    return None


def decide(payload: dict):
    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") or {}
    run_dir = os.environ.get("VEC_RUN_DIR") or None
    ws = Path(run_dir) / "workspace" if run_dir else Path(payload.get("cwd") or os.getcwd())
    blob = json.dumps(ti, default=str)
    if CLAUDE_DIR_RE.search(blob):
        return "references the Claude configuration directory (~/.claude); it is off limits inside a run"
    r = other_run_reference(blob, run_dir)
    if r:
        return r
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return check_write_path(ti.get("file_path") or ti.get("notebook_path"), ws, run_dir)
    if tool in ("Bash", "PowerShell"):
        return check_bash(str(ti.get("command") or ""), ws, run_dir)
    return None


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return 0                                    # not our contract; do not block
    if not isinstance(payload, dict):
        return 0
    try:
        reason = decide(payload)
    except Exception as e:  # noqa: BLE001 - fail closed, but tell the agent why
        reason = f"guard internal error ({e!r}); denied fail-closed - note it in NOTES.md and try a simpler command"
    if not reason:
        return 0
    _record(os.environ.get("VEC_RUN_DIR"), payload, reason)
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                  "permissionDecisionReason": "harness guard: " + reason}}
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    sys.stderr.write("harness guard: " + reason + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
