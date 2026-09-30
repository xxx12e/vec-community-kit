"""Read a run's log(s), build the unified events and the summary, write the HTML report / summary JSON / events JSONL.
Stdlib only. Nothing is sent anywhere; the input files are only read.
"""
from __future__ import annotations

import heapq
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from vec_agent_evidence import common as C

from . import __version__, inputs, parsers as P, report, summary as S
from .redact import Redactor, scan_bytes
from .schema import SCHEMA


class OutputRefused(Exception):
    """A credential-shaped string survived redaction: nothing is written."""


def _named_inputs(result, files) -> list:
    """[(name, Path or bytes)] of what the parser actually read (for the input list and the secret scan)."""
    return result.inputs or [(Path(f).name, Path(f)) for f in files]


def _sources(named) -> list:
    out = []
    for name, x in named:
        if isinstance(x, (bytes, bytearray)):
            out.append({"file": name, "bytes": len(x), "sha256": C.sha256_bytes(bytes(x))})
        else:
            out.append({"file": name, "bytes": x.stat().st_size, "sha256": C.sha256_file(x)})
    return out


def _raw_scan(named, extra_values) -> dict:
    """The evidence skeleton's secret scan over what was read (vec_agent_evidence/common.py patterns)."""
    hits = []
    for name, x in named:
        if not isinstance(x, (bytes, bytearray)) and x.stat().st_size > 1024 ** 3:
            hits.append({"file": name, "patterns": ["not scanned: over 1 GB"]})
            continue
        labels = scan_bytes(bytes(x) if isinstance(x, (bytes, bytearray)) else x.read_bytes(), extra_values)
        if labels:
            hits.append({"file": name, "patterns": labels})
    return {"clean": not hits, "hits": hits}


def order_events(events) -> list:
    """Interleave by time the events of several files (a Claude Code session and its subagent files, a Codex rollout
    and stream) and of several sessions in one file (OpenCode subagent sessions). Inside one (file, session) group
    the order of the log is kept; groups are merged on the latest timestamp seen so far in each group (an event
    without a timestamp stays with the one before it). A group with no timestamp at all (the Codex exec stream) stays
    where it was read, after the group before it. The source field still names the file and line of every event."""
    groups: dict = {}
    for e in events:
        key = (re.sub(r"[:#]\d+$", "", e.source or ""), e.session)
        groups.setdefault(key, []).append(e)
    if len(groups) < 2:
        return list(events)
    streams, carry = [], ""
    for rank, evs in enumerate(groups.values()):
        first = next((e.ts for e in evs if e.ts), None)
        if first is None:                              # no timestamp at all: keep its place after the group before
            streams.append([(carry, rank, i, e) for i, e in enumerate(evs)])
            continue
        run, rows = first, []
        for i, e in enumerate(evs):
            run = max(run, e.ts) if e.ts else run
            rows.append((run, rank, i, e))
        carry = max(carry, run)
        streams.append(rows)
    return [row[3] for row in heapq.merge(*streams, key=lambda r: r[:3])]


def analyse(path, framework="auto", session=None, subagents=True, extra_values=()):
    """(summary dict, [Event]) for one run. Raises inputs.InputError on an input this tool cannot read."""
    tmp = None
    p = Path(path)
    if p.is_file() and p.suffix.lower() == ".zip":
        tmp = inputs.extract_zip(p)
        p = Path(tmp.name)
    try:
        fw, files = inputs.resolve(p, framework, session, subagents)
        try:
            result = P.PARSERS[fw].parse(files, {"session": session})
        except SystemExit as e:
            raise inputs.InputError(str(e).replace("REFUSED: ", "", 1)) from None
        events = result.events = order_events(result.events)
        network = S.flag_network(events)                  # on the original command text
        red = Redactor(extra_values)
        for e in events:
            red.event(e)
        for row in network:
            row["command"], _ = red.text(row["command"])
        result.notes = [red.text(n)[0] for n in result.notes]
        result.session_ids = [red.text(s)[0] for s in result.session_ids]
        result.cli_version = red.text(result.cli_version)[0]
        result.native, _ = red.obj(result.native)
        named = _named_inputs(result, files)
        scan = _raw_scan(named, extra_values)
        summ = S.build(result, events, _sources(named), network, scan, dict(red.counts), red.labels)
        summ["input"] = Path(path).name
        return summ, events
    finally:
        if tmp is not None:
            tmp.cleanup()


def _guard(name: str, data: bytes, extra_values) -> None:
    labels = scan_bytes(data, extra_values)
    if labels:
        raise OutputRefused(f"{name}: credential-shaped content survived redaction ({', '.join(labels)}); nothing was "
                            "written. Please report this with a synthetic example.")


def write_outputs(summ, events, out_html=None, out_json=None, out_events=None, title=None, max_text=3000,
                  extra_values=()) -> dict:
    """Render everything in memory, check every output once more with the secret patterns, then write."""
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    blobs = {}
    if out_html:
        page = report.render(summ, events, title or f"Trajectory Lens - {summ['input']}", generated, max_text)
        blobs[out_html] = page.encode("utf-8")
    if out_json:
        doc = {"schema": SCHEMA, "generator": f"vec_trajectory_lens {__version__}", "generated_utc": generated,
               "summary": summ}
        blobs[out_json] = (json.dumps(doc, indent=2, ensure_ascii=True, default=str) + "\n").encode("utf-8")
    if out_events:
        head = json.dumps({"schema": SCHEMA, "generator": f"vec_trajectory_lens {__version__}", "events": len(events)})
        blobs[out_events] = (head + "\n" + "".join(json.dumps(e.to_dict(), ensure_ascii=True) + "\n"
                                                   for e in events)).encode("utf-8")
    for name, data in blobs.items():
        _guard(str(name), data, extra_values)
    for name, data in blobs.items():
        Path(name).parent.mkdir(parents=True, exist_ok=True)
        with open(name, "wb") as f:
            f.write(data)
    return {str(k): len(v) for k, v in blobs.items()}


def read_events(path) -> list:
    """Events back from an --events JSONL file (the first line is a header)."""
    from .schema import Event
    out = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            d = json.loads(line)
            if i == 0 and "schema" in d:
                if d["schema"] != SCHEMA:
                    raise ValueError(f"{path}: schema {d['schema']!r}, expected {SCHEMA!r}")
                continue
            out.append(Event.from_dict(d))
    return out


def env_values(names) -> list:
    return [os.environ[n] for n in names or () if os.environ.get(n)]
