"""Launch the agent under the locked configuration, tee its stream, enforce the wall clock.

The agent process gets the initial prompt as stdin bytes and nothing else, ever. stdout (stream-json) is teed
byte-for-byte into stream.jsonl; the init event is asserted against the lock (model, permission mode, tool
set); the wall clock is enforced (interrupt, grace period, then kill of the whole process tree); a long silence
is treated as a stall (rate limit / hang) and killed. The harness never writes to the agent after launch.

The current implementation targets the Claude Code CLI in headless mode: `build_command` emits the exact
`claude -p --output-format stream-json ...` argv and `launch` parses that CLI's stream-json events (system/init,
assistant, result). Another agent CLI needs `build_command` adapted (and the event parsing in `launch` if its
stream differs).
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

from . import common as C


def build_command(cfg: dict, run: Path, exe=None) -> list:
    """The exact `claude -p` command of the locked configuration."""
    cmd = [str(exe or cfg["claude_exe"]), "-p",
           "--output-format", "stream-json", "--verbose",
           "--model", cfg["model"],
           "--max-turns", str(cfg["max_turns"]),
           "--permission-mode", cfg["permission_mode"],
           "--tools", ",".join(cfg["tools"]), "--disallowedTools", ",".join(cfg["disallowed_tools"]),
           "--settings", str(run / "claude_settings.json"), "--setting-sources", "project", "--strict-mcp-config",
           "--add-dir", cfg["data_root"],
           "--session-id", cfg["session_id"]]
    if cfg.get("effort"):
        cmd += ["--effort", str(cfg["effort"])]
    if cfg.get("max_budget_usd") is not None:
        cmd += ["--max-budget-usd", str(cfg["max_budget_usd"])]
    if (run / "system_prompt_appendix.md").exists():
        cmd += ["--append-system-prompt-file", str(run / "system_prompt_appendix.md")]
    return cmd


def child_env(cfg: dict, run: Path) -> dict:
    """Scrubbed + frozen environment for the agent process."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(C.ENV_SCRUB_PREFIXES)}
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        # launched from inside an agent session: its endpoint / token belong to that session, not to this run
        for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(k, None)
    env.update(cfg["env_overrides"])
    ws = run / "workspace"
    env["PYTHONHASHSEED"] = str(cfg["seed"])
    env["PYTHONPATH"] = str(ws / "tools")
    env["VEC_RUN_DIR"] = str(run)
    env["VEC_DEADLINE_UTC"] = cfg["deadline_utc"]
    env["VEC_TASK"] = cfg["task"]
    env["VEC_BOARDS"] = ",".join(cfg["boards"])
    env["VEC_SESSION_ID"] = cfg["session_id"]
    env["VEC_DATA_DIR"] = cfg["data_root"]
    env["VEC_PANELS_DIR"] = cfg["panels_dir"]
    if cfg.get("claude_projects_dir"):
        env["VEC_CLAUDE_PROJECTS_DIR"] = cfg["claude_projects_dir"]
    env["PATH"] = os.pathsep.join([str(C.PY.parent), env.get("PATH", "")])
    return env


def kill_tree(pid: int) -> dict:
    """Kill the agent and every child it started (training jobs holding GPU memory included)."""
    if os.name == "nt":
        rc, out, err = C.run_cmd(["taskkill", "/PID", str(pid), "/T", "/F"], timeout=120)
    else:
        rc, out, err = C.run_cmd(["pkill", "-KILL", "-P", str(pid)], timeout=60)
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError as e:
            err += f"; os.kill: {e}"
    return {"pid": pid, "rc": rc, "stdout": out.strip()[:500], "stderr": err.strip()[:500], "utc": C.iso(C.now_utc())}


def _interrupt(p) -> None:
    if os.name == "nt":
        p.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        p.send_signal(signal.SIGINT)


def launch(run: Path, cfg: dict, cmd: list, env: dict, poll_seconds: float = 15.0) -> dict:
    ws = run / "workspace"
    state = {"init": None, "result": None, "assistant_events": 0, "events": 0, "events_by_type": {},
             "last_event_utc": None, "abort": None, "deadline_hit": False, "kill": None, "returncode": None,
             "pid": None, "started_utc": C.iso(C.now_utc()), "ended_utc": None, "init_problems": [],
             "init_tool_extras": []}
    C.write_json(run / "launch_command.json", {"argv": cmd, "cwd": str(ws), "env": C.redact_env(env),
                                                "started_utc": state["started_utc"]})
    C.write_text(run / "RUNNING", f"started {state['started_utc']} deadline {cfg['deadline_utc']}\n"
                                  "Do not open stream.jsonl, workspace/ or the public ranking for this run until "
                                  "run_manifest.json exists.\n")
    last_event = [time.time()]
    flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}

    with open(run / "initial_prompt.md", "rb") as stdin, open(run / "stream.jsonl", "ab") as out, \
            open(run / "stderr.log", "ab") as err:
        p = subprocess.Popen(cmd, cwd=str(ws), env=env, stdin=stdin, stdout=subprocess.PIPE, stderr=err, **flags)
        state["pid"] = p.pid
        C.log(f"launched pid {p.pid}; deadline {cfg['deadline_utc']}; stream -> stream.jsonl")

        def pump():
            for raw in p.stdout:                       # bytes, line-delimited JSON
                out.write(raw)
                out.flush()
                last_event[0] = time.time()
                state["events"] += 1
                try:
                    ev = json.loads(str(raw, "utf-8", "replace"))
                except ValueError:
                    continue
                if not isinstance(ev, dict):
                    continue
                t = ev.get("type")
                state["events_by_type"][str(t)] = state["events_by_type"].get(str(t), 0) + 1
                if t == "system" and ev.get("subtype") == "init":
                    state["init"] = ev
                    problems = []
                    model = str(ev.get("model") or "")
                    if not (model == cfg["model"] or model.startswith(cfg["model"] + "[")):
                        problems.append(f"model {model!r} != locked {cfg['model']!r}")
                    if ev.get("permissionMode") != cfg["permission_mode"]:
                        problems.append(f"permissionMode {ev.get('permissionMode')!r} != {cfg['permission_mode']!r}")
                    extra = sorted(set(ev.get("tools") or []) - set(cfg["tools"]))
                    state["init_tool_extras"] = extra
                    extra = [x for x in extra if x not in C.INIT_TOOL_EXTRAS_OK]
                    if extra:
                        problems.append(f"unexpected tools {extra}")
                    if problems:
                        state["init_problems"] = problems
                        state["abort"] = "init mismatch (locked config not honoured, run voided): " + "; ".join(problems)
                        C.log("ABORT: " + state["abort"])
                        state["kill"] = kill_tree(p.pid)
                elif t == "assistant":
                    state["assistant_events"] += 1
                elif t == "result":
                    state["result"] = ev

        t = threading.Thread(target=pump, daemon=True)
        t.start()
        deadline = C.parse_iso(cfg["deadline_utc"])
        grace = float(cfg["grace_minutes"]) * 60.0
        stall = float(cfg["stall_hours"]) * 3600.0
        while p.poll() is None:
            time.sleep(poll_seconds)
            if p.poll() is not None:
                break
            if state["abort"] and not state["kill"]:
                state["kill"] = kill_tree(p.pid)
            if not state["deadline_hit"] and C.now_utc() > deadline:
                state["deadline_hit"] = True
                C.log("wall-clock deadline reached -> interrupt, then kill after the grace period")
                try:
                    _interrupt(p)
                except OSError as e:
                    C.log(f"interrupt failed ({e!r}); killing tree")
                    state["kill"] = kill_tree(p.pid)
                try:
                    p.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    state["kill"] = kill_tree(p.pid)
            if time.time() - last_event[0] > stall and not state["abort"]:
                state["abort"] = f"stalled: no stream event for {cfg['stall_hours']} h (rate limit or hang)"
                C.log("ABORT: " + state["abort"])
                state["kill"] = kill_tree(p.pid)
        try:
            state["returncode"] = p.wait(timeout=120)
        except subprocess.TimeoutExpired:
            state["kill"] = kill_tree(p.pid)
            state["returncode"] = p.poll()
        t.join(timeout=120)

    state["last_event_utc"] = C.iso(C.now_utc()) if state["events"] else None
    state["ended_utc"] = C.iso(C.now_utc())
    (run / "RUNNING").unlink(missing_ok=True)
    C.write_json(run / "launch_state.json", state)
    res = state["result"] or {}
    C.log(f"agent exited rc={state['returncode']} result={res.get('subtype')} turns={res.get('num_turns')} "
          f"assistant_events={state['assistant_events']} abort={state['abort']}")
    return state
