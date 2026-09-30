"""Claude Code: the stdout of `claude -p --output-format stream-json --verbose` and the session JSONL the CLI writes
under ~/.claude/projects/<encoded cwd>/<session id>.jsonl (plus <session id>/subagents/*.jsonl).

Both are one JSON object per line. What is read (field names as the CLI writes them; nothing else is assumed):
  stream-json   {"type": "system", "subtype": "init", "model", "tools", "claude_code_version", "session_id", ...},
                {"type": "assistant" | "user", "message": {...}, "parent_tool_use_id", "session_id"},
                {"type": "result", "subtype", "num_turns", "duration_ms", "total_cost_usd", "usage", "modelUsage"}
  session JSONL {"type": "user" | "assistant" | "system", "message": {...}, "timestamp", "sessionId", "version",
                "isSidechain", "isMeta", "uuid", ...} plus bookkeeping records (titles, file-history snapshots,
                attachments, queue operations, ...) that are counted, not shown.
  message       {"id", "model", "role", "content": [text | thinking | tool_use | tool_result blocks], "usage"}
One model response can be split over several lines that repeat the same message id and usage: usage is counted once
per message id (the last line's usage), and "turns" counts distinct assistant message ids.
"""
from __future__ import annotations

from pathlib import Path

from ..schema import Event, usage_from
from . import ParseResult, iso_from_str, read_records, register, short_json, src

SHELL_TOOLS = {"Bash", "PowerShell", "BashOutput"}
WRITE_TOOLS = {"Write": "write", "Edit": "edit", "MultiEdit": "edit", "NotebookEdit": "edit", "Read": "read"}
BOOKKEEPING = {"summary", "custom-title", "ai-title", "agent-name", "mode", "atis-latch", "last-prompt", "cost-state",
               "queue-operation", "file-history-snapshot", "file-history-delta", "attachment", "progress"}


def sniff(records) -> int:
    score = 0
    for d in records:
        t = d.get("type")
        m = d.get("message")
        if t in ("user", "assistant") and isinstance(m, dict) and m.get("role") in ("user", "assistant"):
            score += 3
        elif t == "system" and d.get("subtype") == "init" and "tools" in d:
            score += 5
        elif t == "result" and "num_turns" in d:
            score += 5
        elif t in BOOKKEEPING and ("sessionId" in d or "messageId" in d):
            score += 1
    return score


def _usage(u):
    return usage_from(u, input="input_tokens", output="output_tokens", cache_read="cache_read_input_tokens",
                      cache_write="cache_creation_input_tokens")


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text" and isinstance(b.get("text"), str):
                    parts.append(b["text"])
                elif b.get("type") == "image":
                    parts.append("[image]")
                elif b.get("type") not in ("tool_result", "tool_use"):
                    parts.append(short_json(b, 2000))
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts)
    return "" if content is None else short_json(content)


def _tool_call(block: dict, base: dict) -> Event:
    name = str(block.get("name") or "?")
    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
    command, files, op = None, [], None
    if name in SHELL_TOOLS and isinstance(inp.get("command"), str):
        command = inp["command"]
    if name in WRITE_TOOLS:
        path = inp.get("file_path") or inp.get("notebook_path")
        if isinstance(path, str):
            files, op = [path], WRITE_TOOLS[name]
    if name == "Write" and isinstance(inp.get("content"), str):
        shown = dict(inp, content=inp["content"][:4000] + (f"... [{len(inp['content'])} chars]"
                                                           if len(inp["content"]) > 4000 else ""))
    else:
        shown = inp
    text = command if command is not None else short_json(shown)
    return Event(kind="tool_call", tool=name, command=command, files=files, file_op=op, text=text,
                 call_id=block.get("id"), **base)


def parse(files, options=None) -> ParseResult:
    res = ParseResult(framework="claude", events=[])
    names, usage_by_msg, model_by_msg = {}, {}, {}
    sessions, lines, bad, skipped = [], 0, 0, {}
    stream_seen = False
    for idx, path in enumerate(files):
        sub_file = idx > 0 and "subagents" in Path(path).parts
        recs, n, b = read_records(path)
        lines, bad = lines + n, bad + b
        for lineno, d in recs:
            t = d.get("type")
            sid = d.get("sessionId") or d.get("session_id")
            if sid and sid not in sessions:
                sessions.append(sid)
            if isinstance(d.get("version"), str) and not res.cli_version:
                res.cli_version = d["version"]
            side = bool(d.get("isSidechain")) or bool(d.get("parent_tool_use_id")) or sub_file
            base = {"ts": iso_from_str(d.get("timestamp")), "session": sid, "source": src(path, lineno)}
            if t == "system" and d.get("subtype") == "init":
                stream_seen = True
                res.cli_version = d.get("claude_code_version") or res.cli_version
                tools = d.get("tools") or []
                res.native["init_model"] = d.get("model")
                res.native["init_tools"] = tools
                res.native["permission_mode"] = d.get("permissionMode")
                res.events.append(Event(kind="system", actor="system", subkind="init", model=d.get("model"),
                                        text=f"init: model={d.get('model')} permissionMode={d.get('permissionMode')} "
                                             f"tools={', '.join(map(str, tools))}", **base))
            elif t == "result":
                stream_seen = True
                for k in ("subtype", "is_error", "num_turns", "duration_ms", "duration_api_ms", "total_cost_usd"):
                    if k in d:
                        res.native[k] = d[k]
                if _usage(d.get("usage")):
                    res.native["usage"] = _usage(d.get("usage"))
                if isinstance(d.get("modelUsage"), dict):
                    res.native["models"] = sorted(d["modelUsage"])
                res.events.append(Event(kind="system", actor="system", subkind="result", is_error=bool(d.get("is_error")),
                                        text=f"result: {d.get('subtype')} turns={d.get('num_turns')} "
                                             f"duration_ms={d.get('duration_ms')} cost_usd={d.get('total_cost_usd')}\n"
                                             + _content_text(d.get("result"))[:4000], **base))
            elif t == "system":
                text = d.get("content") if isinstance(d.get("content"), str) else short_json(
                    {k: v for k, v in d.items() if k not in ("parentUuid", "uuid", "sessionId", "cwd", "userType",
                                                             "gitBranch", "version", "entrypoint", "slug")}, 4000)
                res.events.append(Event(kind="system", actor="system", subkind=str(d.get("subtype") or "system"),
                                        is_error=True if d.get("level") == "error" or "error" in str(d.get("subtype"))
                                        else None, text=text, **base))
            elif t in ("user", "assistant") and isinstance(d.get("message"), dict):
                m = d["message"]
                content = m.get("content")
                if t == "assistant":
                    mid = m.get("id") or d.get("uuid")
                    model = m.get("model")
                    if mid:
                        if _usage(m.get("usage")):
                            usage_by_msg[mid] = _usage(m.get("usage"))
                        if model:
                            model_by_msg[mid] = model
                    actor = "subagent" if side else "agent"
                    blocks = content if isinstance(content, list) else [{"type": "text", "text": _content_text(content)}]
                    for bl in blocks:
                        if not isinstance(bl, dict):
                            continue
                        bt = bl.get("type")
                        if bt == "tool_use":
                            ev = _tool_call(bl, dict(base, actor=actor, model=model, msg_id=mid))
                            names[bl.get("id")] = ev.tool
                            res.events.append(ev)
                        elif bt == "thinking":
                            res.events.append(Event(kind="assistant", actor=actor, subkind="thinking", model=model,
                                                    msg_id=mid, text=bl.get("thinking") or "[thinking, text not stored]",
                                                    **base))
                        elif bt == "text":
                            res.events.append(Event(kind="assistant", actor=actor, model=model, msg_id=mid,
                                                    text=bl.get("text") or "", **base))
                        else:
                            res.events.append(Event(kind="assistant", actor=actor, subkind=str(bt), model=model,
                                                    msg_id=mid, text=short_json(bl, 4000), **base))
                else:
                    blocks = content if isinstance(content, list) else None
                    results = [b for b in blocks or [] if isinstance(b, dict) and b.get("type") == "tool_result"]
                    for b in results:
                        cid = b.get("tool_use_id")
                        res.events.append(Event(kind="tool_result", actor="tool", tool=names.get(cid), call_id=cid,
                                                is_error=bool(b.get("is_error")) or None,
                                                text=_content_text(b.get("content")), **base))
                    rest = [b for b in blocks or [] if not (isinstance(b, dict) and b.get("type") == "tool_result")]
                    text = _content_text(content if blocks is None else rest)
                    if text.strip() or (blocks is None and not results):
                        meta = bool(d.get("isMeta")) or bool(d.get("isCompactSummary"))
                        res.events.append(Event(kind="user", actor="subagent" if side else ("system" if meta else "user"),
                                                subkind="meta" if meta else None, text=text, **base))
            else:
                skipped[str(t)] = skipped.get(str(t), 0) + 1
    # usage once per model response: on the last event of that message id
    last = {}
    for i, e in enumerate(res.events):
        if e.msg_id and e.kind in ("assistant", "tool_call"):
            last[e.msg_id] = i
    for mid, i in last.items():
        if mid in usage_by_msg:
            res.events[i].usage = dict(usage_by_msg[mid])
    res.session_ids = sessions
    res.stats = {"lines": lines, "unparseable_lines": bad, "skipped_records_by_type": skipped,
                 "shape": "stream-json" if stream_seen else "session-jsonl"}
    res.native["usage_by_message"] = len(usage_by_msg)
    total = {}
    for u in usage_by_msg.values():
        for k, v in u.items():
            total[k] = total.get(k, 0) + v
    res.native["usage_sum"] = total
    res.native["assistant_messages"] = len({e.msg_id for e in res.events if e.kind in ("assistant", "tool_call")
                                            and e.msg_id})
    res.native["models_by_message"] = model_by_msg
    return res


register("claude", "Claude Code", sniff, parse)
