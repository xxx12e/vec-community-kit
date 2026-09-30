"""OpenCode: the stdout of `opencode run --format json`, an `opencode export <sessionID>` document (also the
session_export.json that opencode-package writes), a session in OpenCode's database (read-only, the session tables
only) and the JSON storage of OpenCode up to v1.1.x. The reading code is vec_agent_evidence/opencode.py's (checked
against the OpenCode source, tag v1.18.33; untested against a live OpenCode run).

  stream   {"type": step_start | step_finish | text | reasoning | tool_use | error, "timestamp" (ms), "sessionID",
           "part" | "error"}; no user message and no model string (those are only in the stored session)
  export   {"info": session, "messages": [{"info": message, "parts": [...]}], "children": [...] (subagents)}
           parts: text, reasoning, tool {tool, callID, state {status, input, output | error, time}}, step-start,
           step-finish {tokens, cost}, patch {files}, file, subtask, agent, retry, compaction, snapshot
Token usage is taken from the step-finish parts (one per model call); an assistant message's own "tokens" field is
the LAST step's usage (OpenCode overwrites it per step), so it is not summed.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vec_agent_evidence import opencode as O

from ..schema import Event, usage_from
from . import ParseResult, iso_from_ms, read_records, register, short_json, src


def sniff(records) -> int:
    return sum(3 for d in records if d.get("type") in O.STREAM_TYPES and isinstance(d.get("sessionID"), str))


def _usage(t):
    return usage_from(t, input="input", output="output", reasoning="reasoning", cache_read="cache.read",
                      cache_write="cache.write")


def _tool_events(part: dict, base: dict) -> list:
    state = part.get("state") if isinstance(part.get("state"), dict) else {}
    inp = state.get("input") if isinstance(state.get("input"), dict) else {}
    tool = str(part.get("tool") or "?")
    command = inp.get("command") if tool == "bash" and isinstance(inp.get("command"), str) else None
    files = O.tool_files(part)
    op = None
    if files:
        op = "write" if tool == "write" else "edit"
    elif tool == "read" and isinstance(inp.get("filePath"), str):
        files, op = [inp["filePath"]], "read"
    shown = dict(inp)
    if isinstance(shown.get("content"), str) and len(shown["content"]) > 4000:
        shown["content"] = shown["content"][:4000] + f"... [{len(inp['content'])} chars]"
    t = state.get("time") if isinstance(state.get("time"), dict) else {}
    call = Event(kind="tool_call", tool=tool, command=command, files=files, file_op=op,
                 text=command if command is not None else short_json(shown), call_id=part.get("callID"),
                 **dict(base, ts=iso_from_ms(t.get("start")) or base.get("ts")))
    status = state.get("status")
    if status not in ("completed", "error"):
        return [call]
    out = state.get("output") if status == "completed" else state.get("error")
    result = Event(kind="tool_result", tool=tool, call_id=part.get("callID"), is_error=(status == "error") or None,
                   text=str(out or ""), **dict(base, actor="tool", model=None,
                                               ts=iso_from_ms(t.get("end")) or base.get("ts")))
    return [call, result]


def _part_events(p: dict, base: dict, role: str) -> list:
    t = p.get("type")
    ptime = p.get("time") if isinstance(p.get("time"), dict) else {}
    b = dict(base, ts=iso_from_ms(ptime.get("start")) or base.get("ts"))
    sysb = dict(b, actor="system", model=None)
    if t == "text":
        if role == "user":
            if p.get("synthetic"):
                return [Event(kind="user", subkind="synthetic", text=p.get("text") or "",
                              **dict(b, actor="system", model=None))]
            return [Event(kind="user", text=p.get("text") or "", **dict(b, model=None))]
        return [Event(kind="assistant", text=p.get("text") or "", **b)]
    if t == "reasoning":
        return [Event(kind="assistant", subkind="reasoning", text=p.get("text") or "", **b)]
    if t == "tool":
        return _tool_events(p, b)
    if t == "step-finish":
        return [Event(kind="system", subkind="step", usage=_usage(p.get("tokens")),
                      text=f"step finished: {p.get('reason')} cost={p.get('cost')} tokens={short_json(p.get('tokens'))}",
                      **sysb)]
    if t in ("step-start", "snapshot"):
        return []
    if t == "patch":
        files = [f for f in p.get("files") or [] if isinstance(f, str)]
        return [Event(kind="system", subkind="patch", files=files, file_op="edit" if files else None,
                      text="patch: " + ", ".join(files), **sysb)]
    if t == "file":
        return [Event(kind="user" if role == "user" else "system", subkind="attachment",
                      text=f"file {p.get('filename') or ''} {p.get('mime') or ''}",
                      **(dict(b, model=None) if role == "user" else sysb))]
    if t == "retry":
        return [Event(kind="system", subkind="error", is_error=True, text="retry: " + short_json(p.get("error"), 2000),
                      **sysb)]
    return [Event(kind="system", subkind=str(t), text=short_json({k: v for k, v in p.items()
                                                                   if k not in ("id", "sessionID", "messageID")}, 4000),
                  **sysb)]


def events_from_export(exp: dict, source_name: str) -> ParseResult:
    res = ParseResult(framework="opencode", events=[])
    info = exp.get("info") if isinstance(exp.get("info"), dict) else {}
    res.cli_version = info.get("version")
    idx = 0
    for depth, si, mi, parts in O.iter_messages(exp):
        sid = si.get("id")
        if sid and sid not in res.session_ids:
            res.session_ids.append(sid)
        role = mi.get("role")
        actor = "subagent" if depth else ("agent" if role == "assistant" else "user")
        mtime = mi.get("time") if isinstance(mi.get("time"), dict) else {}
        base = {"ts": iso_from_ms(mtime.get("created")), "actor": actor, "session": sid,
                "model": O.model_string(mi) if role == "assistant" else None, "msg_id": mi.get("id")}
        if role == "assistant" and isinstance(mi.get("error"), dict):
            res.events.append(Event(kind="system", actor="system", subkind="error", is_error=True, session=sid,
                                    text=short_json(mi["error"], 2000), source=f"{source_name}#{idx}",
                                    ts=base["ts"]))
        for p in parts:
            for e in _part_events(p, base, role):
                e.source = f"{source_name}#{idx}"
                res.events.append(e)
            idx += 1
    res.native["assistant_messages"] = sum(1 for _, _, mi, _ in O.iter_messages(exp) if mi.get("role") == "assistant")
    s = O.summarise_export(exp)
    res.native["cost"] = s["cost"]
    res.native["steps"] = s["steps"]
    res.native["session_title"] = s["title"]
    return res


def _latest_root_session_db(db) -> str | None:
    con = sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        row = con.execute("SELECT id FROM session WHERE parent_id IS NULL ORDER BY time_updated DESC LIMIT 1").fetchone()
        return row[0] if row else None
    finally:
        con.close()


def _latest_root_session_storage(ddir) -> str | None:
    best = None
    for p in sorted((Path(ddir) / "storage" / "session").glob("*/*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and not d.get("parentID"):
            upd = ((d.get("time") or {}).get("updated")) or 0
            if best is None or upd > best[0]:
                best = (upd, d.get("id"))
    return best[1] if best else None


def parse(files, options=None) -> ParseResult:
    options = options or {}
    session = options.get("session")
    results = []
    for path in files:
        path = Path(path)
        if path.is_dir():                                   # a data directory or its storage/ (OpenCode <= v1.1.x)
            ddir = path.parent if path.name == "storage" else path
            sid = session or _latest_root_session_storage(ddir)
            sfiles = O.storage_session_files(ddir, sid) if sid else []
            got = O.export_from_storage(sfiles) if sfiles else None
            if not got:
                raise SystemExit(f"no OpenCode session {sid or ''} under {ddir / 'storage'}")
            r = events_from_export(got, "storage")
            r.inputs = [("storage/" + rel, p) for rel, p in sfiles]      # only this session's files, never auth.json
            if not session:
                r.notes.append(f"no --session given: the most recently updated session ({sid}) was read")
            results.append(r)
        elif O.is_sqlite(path):
            sid = session or _latest_root_session_db(path)
            got = O.export_from_db(path, sid) if sid else None
            if not got:
                raise SystemExit(f"no OpenCode session {sid or ''} in {path.name}")
            r = events_from_export(got, path.name)
            # the rows that were read (not the database file, which also holds account tokens)
            r.inputs = [(f"{path.name}: session {sid} (session / message / part / todo rows)",
                         json.dumps(got, default=str).encode("utf-8"))]
            r.notes.append(f"read read-only from {path.name} (session tables only)" +
                           ("" if session else f"; no --session given: the most recently updated session ({sid}) was read"))
            results.append(r)
        elif path.suffix.lower() == ".json":
            results.append(events_from_export(O.load_export(path), path.name))
        else:
            results.append(parse_stream(path))
    if len(results) == 1:
        return results[0]
    merged = ParseResult(framework="opencode", events=[e for r in results for e in r.events],
                         cli_version=next((r.cli_version for r in results if r.cli_version), None),
                         session_ids=list(dict.fromkeys(s for r in results for s in r.session_ids)),
                         notes=[n for r in results for n in r.notes],
                         inputs=[x for r, f in zip(results, files) for x in (r.inputs or [(Path(f).name, Path(f))])])
    return merged


def parse_stream(path) -> ParseResult:
    res = ParseResult(framework="opencode", events=[])
    recs, n, bad = read_records(path)
    cost = 0.0
    for lineno, d in recs:
        t = d.get("type")
        sid = d.get("sessionID")
        if sid and sid not in res.session_ids:
            res.session_ids.append(sid)
        base = {"ts": iso_from_ms(d.get("timestamp")), "actor": "agent", "session": sid, "source": src(path, lineno)}
        part = d.get("part") if isinstance(d.get("part"), dict) else {}
        if t == "tool_use":
            res.events += _tool_events(part, dict(base, msg_id=part.get("messageID")))
        elif t in ("text", "reasoning"):
            res.events += _part_events(part, dict(base, msg_id=part.get("messageID")), "assistant")
        elif t == "step_finish":
            if isinstance(part.get("cost"), (int, float)):
                cost += part["cost"]
            res.events += _part_events(part, base, "assistant")
        elif t == "step_start":
            continue
        elif t == "error":
            err = d.get("error")
            msg = err.get("data", {}).get("message") if isinstance(err, dict) and isinstance(err.get("data"), dict) else None
            res.events.append(Event(kind="system", subkind="error", is_error=True,
                                    text=str(msg or short_json(err, 2000)), **dict(base, actor="system")))
        else:
            res.events.append(Event(kind="system", subkind=str(t), text=short_json(d, 4000), **dict(base, actor="system")))
    for e in res.events:
        if e.source is None:
            e.source = src(path, 0)
    res.native["cost"] = cost
    res.native["assistant_messages"] = len({e.msg_id for e in res.events if e.kind in ("assistant", "tool_call")
                                            and e.msg_id})
    res.notes.append("the `opencode run --format json` stream carries no user message and no model string; parse the "
                     "`opencode export` document (or the database) for those")
    res.stats = {"lines": n, "unparseable_lines": bad, "shape": "opencode-run-json"}
    return res


register("opencode", "OpenCode", sniff, parse)
