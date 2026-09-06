#!/usr/bin/env python
"""vec_agent_evidence - configuration lock, launch, evidence collection and upload packaging for an Agent-track run.

Targets the Claude Code CLI (`claude -p --output-format stream-json`); adapt launch.build_command for another CLI.
The hooks are regex hooks (reject recognised network commands and restricted file operations; audit log), not a sandbox.

Sub-commands
  lock      freeze a run directory (config.lock.json, prompt, settings, hooks, snapshot, workspace) and stop
  run       lock -> launch the agent CLI -> postrun   (the lock is the start of the run: no human afterwards)
  postrun   collect evidence for an already-finished run directory (recovery after a harness crash)
  package   build the upload package (predictions + trajectory.zip / prompts.zip / harness.zip) for a run after postrun

Examples
  python -m vec_agent_evidence lock --task T3 --prompt my_prompt.md --model <model-id> --data-root ./data --hours 8
  python -m vec_agent_evidence run  --task T2 --boards T2:heart:val_extrap --prompt my_prompt.md --model <model-id> \
      --data-root ./data --hours 10 --max-turns 600
  python -m vec_agent_evidence postrun --run-dir runs/<run_id>
  python -m vec_agent_evidence package --run-dir runs/<run_id>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import common as C
from . import evidence, launch as launch_mod, lock as lock_mod, package as package_mod


def _add_lock_args(sp):
    sp.add_argument("--task", choices=["T1", "T2", "T3"], required=True)
    sp.add_argument("--boards", help="comma-separated board keys of the task (default: all boards of the task)")
    sp.add_argument("--prompt", required=True, help="initial prompt template (placeholders {{...}} are rendered)")
    sp.add_argument("--settings", default=str(C.DEFAULT_SETTINGS_TEMPLATE), help="settings template with hooks + deny rules")
    sp.add_argument("--appendix", default=None, help="optional --append-system-prompt-file template")
    sp.add_argument("--model", required=True, help="FULL model id; asserted against the CLI init event")
    sp.add_argument("--effort", default=None)
    sp.add_argument("--hours", type=float, default=10.0, help="wall clock for the agent")
    sp.add_argument("--max-turns", type=int, default=400)
    sp.add_argument("--max-budget-usd", type=float, default=None)
    sp.add_argument("--tools", default=None, help="comma-separated tool set (default: " + ",".join(C.DEFAULT_TOOLS) + ")")
    sp.add_argument("--disallowed-tools", default=None)
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--data-root", required=True, help="directory with the released data (and optionally panels/)")
    sp.add_argument("--data-glob", action="append", default=None, help="glob under --data-root to hash (default **/*.h5ad)")
    sp.add_argument("--runs-root", default=str(C.DEFAULT_RUNS_ROOT))
    sp.add_argument("--claude-exe", default=os.environ.get("VEC_CLAUDE_EXE"), help="agent CLI binary to pin (default: `claude` on PATH)")
    sp.add_argument("--projects-dir", default=os.environ.get("VEC_CLAUDE_PROJECTS_DIR"),
                    help="where the CLI writes transcripts (default ~/.claude/projects)")
    sp.add_argument("--grace-minutes", type=float, default=10.0, help="after the deadline: interrupt, wait this long, then kill")
    sp.add_argument("--stall-hours", type=float, default=3.0, help="kill the run after this long without a stream event")
    sp.add_argument("--note", default="", help="free text recorded in config.lock.json (e.g. which completed runs informed this prompt)")
    sp.add_argument("--dry-run", action="store_true", help="mark the run as a dry run (VEC_ALLOW_RELAX=1; never uploadable)")


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="python -m vec_agent_evidence", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    _add_lock_args(sub.add_parser("lock", help="freeze a run directory and stop"))
    sp = sub.add_parser("run", help="lock, launch the agent CLI, postrun")
    _add_lock_args(sp)
    sp.add_argument("--agent-exe", default=None, help="override the executable actually launched (dry runs with a stand-in)")
    sp.add_argument("--poll-seconds", type=float, default=15.0)
    sp = sub.add_parser("postrun", help="collect evidence for a finished run directory")
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--projects-dir", default=os.environ.get("VEC_CLAUDE_PROJECTS_DIR"))
    sp = sub.add_parser("package", help="build the upload package for a run after postrun")
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--out-root", default=None)
    sp.add_argument("--allow-abort-unknown", action="store_true")
    return p.parse_args(argv)


def _lock_from_args(args):
    boards = args.boards.split(",") if args.boards else None
    tools = args.tools.split(",") if args.tools else None
    disallowed = args.disallowed_tools.split(",") if args.disallowed_tools else None
    return lock_mod.lock(args.task, boards, args.prompt, args.model, args.hours, args.data_root, runs_root=args.runs_root,
                         settings=args.settings, appendix=args.appendix, max_turns=args.max_turns, effort=args.effort,
                         tools=tools, disallowed_tools=disallowed, seed=args.seed, claude_exe=args.claude_exe,
                         projects_dir=args.projects_dir, max_budget_usd=args.max_budget_usd,
                         grace_minutes=args.grace_minutes, stall_hours=args.stall_hours,
                         data_globs=tuple(args.data_glob or ["**/*.h5ad"]), dry_run=args.dry_run, note=args.note)


def cmd_lock(args) -> int:
    run, cfg = _lock_from_args(args)
    print(json.dumps({"run_id": cfg["run_id"], "run_dir": str(run),
                      "config_lock_sha256": (run / "config.lock.sha256").read_text(encoding="utf-8").strip(),
                      "launch_command": launch_mod.build_command(cfg, run)}, indent=2))
    return 0


def cmd_run(args) -> int:
    run, cfg = _lock_from_args(args)
    env = launch_mod.child_env(cfg, run)
    cmd = launch_mod.build_command(cfg, run, exe=args.agent_exe)
    C.log("CONFIGURATION LOCK IS NOW IN EFFECT - the human walks away until run_manifest.json exists")
    state = launch_mod.launch(run, cfg, cmd, env, poll_seconds=args.poll_seconds)
    manifest = evidence.postrun(run, args.projects_dir, state=state)
    summary = {k: manifest.get(k) for k in ("run_id", "result_subtype", "num_turns", "abort")}
    summary["submission_status"] = manifest["submission"]["status"]
    summary["secret_scan_clean"] = manifest["secret_scan"]["clean"]
    summary["run_dir"] = str(run)
    print(json.dumps(summary))
    return 0


def cmd_postrun(args) -> int:
    manifest = evidence.postrun(Path(args.run_dir), args.projects_dir)
    print(json.dumps({"run_id": manifest["run_id"], "submission_status": manifest["submission"]["status"],
                      "secret_scan_clean": manifest["secret_scan"]["clean"]}))
    return 0


def main(argv=None) -> int:
    C.safe_std_streams()
    args = parse_args(argv)
    if args.cmd == "lock":
        return cmd_lock(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "postrun":
        return cmd_postrun(args)
    if args.cmd == "package":
        return package_mod.main(["--run-dir", args.run_dir] + (["--out-root", args.out_root] if args.out_root else [])
                                + (["--allow-abort-unknown"] if args.allow_abort_unknown else []))
    return 2


if __name__ == "__main__":
    sys.exit(main())
