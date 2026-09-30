#!/usr/bin/env python
"""Trajectory Lens: turn an agent run's log into one readable offline report.

  python -m vec_trajectory_lens <path> --out report.html --json summary.json [--framework auto|claude|codex|opencode]

<path> is a log file (Claude Code stream-json or session JSONL, Codex exec --json stream or rollout, OpenCode run
--format json stream or `opencode export` JSON, OpenCode's database), a directory (this kit's run directory or
unzipped evidence package, a Claude Code project directory, an OpenCode data directory) or a .zip (trajectory.zip,
evidence_bundle.zip). Credential-shaped strings are redacted in every output; each output is checked once more
before it is written. Nothing is sent anywhere.

Exit codes: 0 written, 2 input not readable, 3 refused (a credential-shaped string survived redaction).
"""
from __future__ import annotations

import argparse
import sys

from vec_agent_evidence import common as C

from . import __version__, core, inputs, parsers as P


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="python -m vec_trajectory_lens", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="log file, run / package directory, or .zip")
    ap.add_argument("--out", default=None, help="HTML report to write (self-contained, offline)")
    ap.add_argument("--json", default=None, help="summary JSON to write")
    ap.add_argument("--events", default=None, help="also write the unified events (redacted, not shortened further) "
                                                   "as JSONL")
    ap.add_argument("--framework", choices=["auto"] + sorted(P.PARSERS), default="auto")
    ap.add_argument("--session", default=None, help="session id, when the path holds several sessions "
                                                    "(Claude Code project directory, OpenCode data directory or "
                                                    "database)")
    ap.add_argument("--no-subagents", action="store_true", help="Claude Code: do not add <session>/subagents/*.jsonl")
    ap.add_argument("--max-text", type=int, default=3000, help="characters of each event's text kept in the HTML "
                                                               "(default 3000; the --events file is not shortened "
                                                               "further)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--redact-env", action="append", default=[], metavar="NAME",
                    help="also redact the literal value of this environment variable (repeatable), e.g. a gateway key")
    ap.add_argument("--version", action="version", version=f"vec_trajectory_lens {__version__}")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    C.safe_std_streams()
    args = parse_args(argv)
    extra = core.env_values(args.redact_env)
    try:
        summ, events = core.analyse(args.path, args.framework, args.session, not args.no_subagents, extra)
    except inputs.InputError as e:
        print(f"CANNOT READ: {e}")
        return 2
    try:
        written = core.write_outputs(summ, events, args.out, args.json, args.events, args.title, args.max_text, extra)
    except core.OutputRefused as e:
        print(f"REFUSED: {e}")
        return 3
    tok = summ["tokens"]
    print(f"{summ['framework_label']} {summ['cli_version'] or ''}: {summ['events']} events, {summ['turns']} turns, "
          f"{summ['tool_calls']} tool calls, models {[m['model'] for m in summ['models']]}, tokens in/out "
          f"{tok['input']}/{tok['output']}, network-shaped {len(summ['network_flags'])}, secret scan "
          f"{'clean' if summ['secret_scan']['clean'] else 'HITS (redacted in the outputs)'}")
    for w in summ["warnings"]:
        print(f"  warn: {w}")
    for name, n in written.items():
        print(f"  wrote {name} ({n:,} bytes)")
    if not written:
        print("  (nothing written: pass --out, --json and/or --events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
