#!/usr/bin/env python
"""vec_rules_watch - watch the Virtual Embryo Challenge's public pages, board contract, phase endpoint and scorer.

Sub-commands
  run   fetch every source once, compare with the previous snapshot in --out (and the full text in --state), write
        the public snapshot and prepend a dated entry to CHANGES.md / CHANGES.zh.md when something changed.
        Exit code 0 even when a source could not be fetched: the error is recorded in status.json, and the
        changelog says when a source starts failing, when it still fails after still_failing_days days (an issue
        for the contract, the phase endpoint, the scorer or every page) and when it is back. --strict turns fetch
        errors into exit code 3.
  diff  compare two saved pages, two JSON files or two --out directories locally (no network). Exit code 0 = no
        difference, 1 = differences printed, 2 = an input is missing or unreadable (for example not JSON).

Examples
  python -m vec_rules_watch run --state .rules-watch-state --out rules-watch
  python -m vec_rules_watch run --state .rules-watch-state --out rules-watch --full-text
  python -m vec_rules_watch run --state st --out out --only contract,phase
  python -m vec_rules_watch diff rules_old.html rules_new.html
  python -m vec_rules_watch diff old/index.json new/index.json --lang zh
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _truthy(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _append(path, text: str) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _gh_output(path, key: str, value: str) -> None:
    if "\n" in value:
        delim = "EOF_VEC_RULES_WATCH"
        _append(path, f"{key}<<{delim}\n{value}\n{delim}\n")
    else:
        _append(path, f"{key}={value}\n")


def cmd_run(args) -> int:
    from .runner import load_watchlist, make_fetcher, run

    cfg = load_watchlist(args.config)
    fetcher = make_fetcher(cfg, delay=args.delay)
    full_text = args.full_text or _truthy(os.environ.get("RULES_WATCH_FULL_TEXT"))
    only = [x.strip() for x in args.only.split(",") if x.strip()] if args.only else None
    res = run(args.state, args.out, fetcher=fetcher, full_text=full_text, config=cfg, only=only)

    print(f"rules-watch {res['date']}: {res['headline']}; files changed: {res['changed']}; "
          f"fetch errors: {len(res['errors'])}; requests: {res['requests']}")
    if res["first_run"]:
        print("first run: baseline recorded")
    if res["rebaselined"]:
        print("state cache missing or stale: pages compared by section hash and re-baselined")
    for sid, err in res["errors"]:
        print(f"  could not fetch {sid}: {err}")

    summary = args.summary or os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        lines = ["# Rules watch " + res["date"], ""]
        lines.append(res["entry_en"] if res["entry_en"] else "No change in this run.\n")
        if res["errors"]:
            lines += ["", "| source | error |", "|---|---|"] + [f"| {s} | {e} |" for s, e in res["errors"]]
        if res["rebaselined"]:
            lines += ["", "The state cache was missing or stale: pages were compared by section hash."]
        _append(summary, "\n".join(lines) + "\n")
    gh_out = args.github_output or os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        _gh_output(gh_out, "changed", "true" if res["changed"] else "false")
        _gh_output(gh_out, "entry", "true" if res["entry"] else "false")
        _gh_output(gh_out, "high_signal", "true" if res["high_signal"] else "false")
        _gh_output(gh_out, "headline", res["headline"])
        _gh_output(gh_out, "errors", str(len(res["errors"])))
        _gh_output(gh_out, "date", res["date"])
    if args.issue_file:
        if res["issue_body"]:
            Path(args.issue_file).parent.mkdir(parents=True, exist_ok=True)
            with open(args.issue_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(res["issue_body"])
        elif Path(args.issue_file).exists():
            Path(args.issue_file).unlink()
    return 3 if (args.strict and res["errors"]) else 0


def cmd_diff(args) -> int:
    from .localdiff import BadInput, diff_dirs, diff_files, render
    from .runner import load_watchlist

    old, new = Path(args.old), Path(args.new)
    for p in (old, new):
        if not p.exists():
            print(f"not found: {p}", file=sys.stderr)
            return 2
    pinned = (load_watchlist().get("scorer") or {}).get("pinned", "?")
    if not ((old.is_dir() and new.is_dir()) or (old.is_file() and new.is_file())):
        print("compare two files or two directories", file=sys.stderr)
        return 2
    try:
        entry = diff_dirs(old, new, pinned) if old.is_dir() else diff_files(old, new, pinned)
    except BadInput as exc:
        print(exc, file=sys.stderr)
        return 2
    langs = ("en", "zh") if args.lang == "both" else (args.lang,)
    for i, lang in enumerate(langs):
        if i:
            sys.stdout.write("\n")
        sys.stdout.write(render(entry, lang))
    return 1 if entry.has_content() else 0


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass
    ap = argparse.ArgumentParser(prog="python -m vec_rules_watch", description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch every source once and update --out")
    r.add_argument("--state", required=True, help="private working state (the Actions cache): full page text")
    r.add_argument("--out", required=True, help="public output directory (committed): snapshots and changelog")
    r.add_argument("--full-text", action="store_true",
                   help="also store the full normalised page text in --out (off by default; also "
                        "RULES_WATCH_FULL_TEXT=true)")
    r.add_argument("--config", default=None, help="watch list JSON (default: the packaged watchlist.json)")
    r.add_argument("--only", default=None, help="comma-separated source ids: contract, phase, scorer, page, "
                                                "page:<id>")
    r.add_argument("--delay", type=float, default=None, help="seconds between two requests to the same host")
    r.add_argument("--summary", default=None, help="append a Markdown summary here (default $GITHUB_STEP_SUMMARY)")
    r.add_argument("--github-output", default=None, help="append key=value outputs here (default $GITHUB_OUTPUT)")
    r.add_argument("--issue-file", default=None,
                   help="write an issue body here when the run is worth an issue (a contract, phase or scorer "
                        "change, a change of a page marked issue, a key source failing for days); else remove it")
    r.add_argument("--strict", action="store_true", help="exit 3 when any source could not be fetched")
    r.set_defaults(func=cmd_run)
    d = sub.add_parser("diff", help="compare two pages / JSON files / output directories (no network)")
    d.add_argument("old")
    d.add_argument("new")
    d.add_argument("--lang", choices=("en", "zh", "both"), default="en")
    d.set_defaults(func=cmd_diff)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
