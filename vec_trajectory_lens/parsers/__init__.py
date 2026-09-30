"""Pluggable parsers: each framework module registers a sniffer and a parser.

    register(name, label, sniff, parse)

sniff(records) -> int     a score for the first parsed JSON records of a JSONL file (0 = not this framework)
parse(files, options) -> ParseResult   the events of one run (files: the log files of that run, in order)

A new framework is one module that calls register(); nothing else needs to change. Registered: claude (Claude Code
stream-json and session JSONL), codex (Codex CLI exec --json stream and session rollout), opencode (OpenCode run
--format json stream, `opencode export` document, database rows, JSON storage of v1.1.x).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PARSERS: dict = {}


@dataclass
class ParseResult:
    framework: str
    events: list
    cli_version: str | None = None
    session_ids: list = field(default_factory=list)
    native: dict = field(default_factory=dict)      # framework-reported totals: usage, turns, duration_ms, cost, ...
    notes: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)       # lines read, unparseable, skipped record types
    # what was actually read, for the input list and the secret scan: [(name, Path or bytes)]; empty = the input files
    inputs: list = field(default_factory=list)


@dataclass
class Parser:
    name: str
    label: str
    sniff: object
    parse: object


def register(name: str, label: str, sniff, parse) -> None:
    PARSERS[name] = Parser(name, label, sniff, parse)


def read_records(path, limit=None):
    """[(line number, dict)] of a JSONL file plus (lines, unparseable). Lines are UTF-8 with replacement."""
    out, n, bad = [], 0, 0
    with open(path, "rb") as f:
        for lineno, raw in enumerate(f, 1):
            if not raw.strip():
                continue
            n += 1
            try:
                d = json.loads(str(raw, "utf-8", "replace"))
            except ValueError:
                bad += 1
                continue
            if isinstance(d, dict):
                out.append((lineno, d))
            else:
                bad += 1
            if limit and n >= limit:
                break
    return out, n, bad


def sniff_file(path, limit: int = 300) -> dict:
    """{parser name: score} for a JSONL file."""
    recs, _, _ = read_records(path, limit)
    records = [d for _, d in recs]
    return {name: p.sniff(records) for name, p in PARSERS.items()}


def iso_from_ms(ms):
    if not isinstance(ms, (int, float)) or isinstance(ms, bool):
        return None
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def iso_from_str(s):
    """Normalise an ISO 8601 string to UTC 'Z' form; None when it does not parse."""
    if not isinstance(s, str) or not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def short_json(obj, n: int = 20000) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + f"... [{len(s)} chars]"


def src(path, lineno) -> str:
    return f"{Path(path).name}:{lineno}"


from . import claude, codex, opencode  # noqa: E402,F401  (registration side effects)
