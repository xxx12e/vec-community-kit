"""Codex CLI: the stdout of `codex exec --json` (current {"type": ...} shape and the older {"id", "msg"} shape) and the
session rollout files ($CODEX_HOME/sessions/.../rollout-*.jsonl, or the dedup copy made by codex-package).

The event names are the ones vec_agent_evidence/codex.py reads (its event_type() and summarise_rollout() are reused):
  exec --json   thread.started, turn.started, turn.completed {usage}, turn.failed, item.completed {item: agent_message,
                reasoning, command_execution, file_change, mcp_tool_call, web_search, todo_list, error}; item.started /
                item.updated are progress copies of item.completed and are counted, not shown
  legacy        session_configured, task_started, agent_message, agent_reasoning, exec_command_begin / _end,
                patch_apply_begin, token_count, task_complete, error
  rollout       session_meta, turn_context, response_item {message, reasoning, function_call, function_call_output,
                local_shell_call, custom_tool_call, custom_tool_call_output, web_search_call}, event_msg (mirror of
                the exec events: task_started / task_complete (the turns; alias turn_started / turn_complete),
                turn_aborted and token_count are read, the rest repeats the response items)
  exit codes    a function_call_output holds the tool's text: current Codex starts it with "Exit code: N" (shell) or
                has "Process exited with code N" in its header (unified exec); older versions wrote a JSON string
                {"output", "metadata": {"exit_code"}}. A non-zero code marks the result as failed.
  tokens        turn.completed carries the thread's RUNNING TOTAL (codex-rs/exec event_processor_with_jsonl_output.rs,
                usage_from_last_total), so each turn.completed event gets the difference to the previous one and the
                sum of the events is the last total; a rollout's last token_count total is used when there is no
                stream.
Like the adapter, this was written from the Codex documentation and source (openai/codex main, read 2026-09-30:
rollout/src/policy.rs, protocol/src/protocol.rs, core/src/tools/mod.rs and context.rs, exec/src/
event_processor_with_jsonl_output.rs) and tested on synthetic files only.
"""
from __future__ import annotations

import json
import re

from vec_agent_evidence import codex as X

from ..schema import Event, usage_from
from . import ParseResult, iso_from_str, read_records, register, short_json, src

ROLLOUT_TYPES = {"session_meta", "turn_context", "response_item", "event_msg", "compacted"}
PATCH_FILE_RE = re.compile(r"(?m)^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$")
EXIT_CODE_RES = (re.compile(r"(?m)^Exit code: (-?\d+)\s*$"), re.compile(r"(?m)^Process exited with code (-?\d+)\s*$"))


def sniff(records) -> int:
    score = 0
    for d in records:
        t = X.event_type(d)
        if t in X.NEW_SHAPE_TYPES:
            score += 3
        elif t.startswith("legacy:"):
            score += 2
        elif d.get("type") in ROLLOUT_TYPES and isinstance(d.get("payload"), dict):
            score += 3
    return score


def _usage(u):
    return usage_from(u, input="input_tokens", output="output_tokens", cache_read="cached_input_tokens",
                      cache_write="cache_write_input_tokens", reasoning="reasoning_output_tokens")


def _exit_code(out):
    """The exit code a function_call_output reports (see the module docstring), or None."""
    if not isinstance(out, str):
        return None
    s = out.lstrip()
    if s.startswith("{"):
        try:
            d = json.loads(s)
        except ValueError:
            d = None
        md = d.get("metadata") if isinstance(d, dict) else None
        if isinstance(md, dict) and isinstance(md.get("exit_code"), int) and not isinstance(md["exit_code"], bool):
            return md["exit_code"]
    head = out[:1000]
    cut = head.find("\nOutput:")                   # only the header, never the command's own output
    head = head[:cut] if cut >= 0 else "\n".join(head.splitlines()[:6])
    for rx in EXIT_CODE_RES:
        m = rx.search(head)
        if m:
            return int(m.group(1))
    return None


def _command(c):
    if isinstance(c, list):
        c = [str(x) for x in c]
        # ["bash", "-lc", "<script>"] -> the script
        if len(c) >= 3 and c[-2] in ("-lc", "-c") and re.search(r"(?:^|[\\/])(?:ba|z)?sh(?:\.exe)?$", c[0]):
            return c[-1]
        return " ".join(c)
    return c if isinstance(c, str) else None


def _args(a):
    if isinstance(a, str):
        try:
            return json.loads(a)
        except ValueError:
            return a
    return a


def _texts(content) -> str:
    out = []
    for c in content or []:
        if isinstance(c, dict):
            if isinstance(c.get("text"), str):
                out.append(c["text"])
    return "\n".join(out)


def _item(item: dict, base: dict, res: ParseResult) -> list:
    it = str(item.get("type") or item.get("item_type") or "unknown")
    if it == "agent_message":
        return [Event(kind="assistant", text=item.get("text") or "", **base)]
    if it == "reasoning":
        return [Event(kind="assistant", subkind="reasoning", text=item.get("text") or "", **base)]
    if it == "command_execution":
        cmd = _command(item.get("command"))
        code = item.get("exit_code")
        return [Event(kind="tool_call", tool="shell", command=cmd, text=cmd or "", call_id=item.get("id"), **base),
                Event(kind="tool_result", tool="shell", call_id=item.get("id"),
                      is_error=(code not in (0, None)) or None, text=f"exit {code}\n{item.get('aggregated_output') or ''}",
                      **dict(base, actor="tool"))]
    if it == "file_change":
        changes = [c for c in item.get("changes") or [] if isinstance(c, dict)]
        files = [str(c.get("path")) for c in changes if c.get("path")]
        op = "write" if changes and all(c.get("kind") == "add" for c in changes) else "edit"
        return [Event(kind="tool_call", tool="file_change", files=files, file_op=op if files else None,
                      text=short_json(changes, 4000), call_id=item.get("id"), **base)]
    if it == "mcp_tool_call":
        name = f"mcp:{item.get('server')}/{item.get('tool')}"
        return [Event(kind="tool_call", tool=name, text=short_json(item.get("arguments")), call_id=item.get("id"), **base),
                Event(kind="tool_result", tool=name, call_id=item.get("id"), text=short_json(item.get("result")),
                      is_error=True if item.get("error") else None, **dict(base, actor="tool"))]
    if it == "web_search":
        return [Event(kind="tool_call", tool="web_search", text=str(item.get("query") or ""), call_id=item.get("id"),
                      **base)]
    if it == "error":
        return [Event(kind="system", actor="system", subkind="error", is_error=True, text=str(item.get("message") or ""),
                      **{k: v for k, v in base.items() if k != "actor"})]
    return [Event(kind="system", actor="system", subkind=it, text=short_json(item, 4000),
                  **{k: v for k, v in base.items() if k != "actor"})]


def _exec_event(d: dict, t: str, base: dict, res: ParseResult) -> list:
    sysbase = {k: v for k, v in base.items() if k != "actor"}
    msg = d.get("msg") if isinstance(d.get("msg"), dict) else {}
    if t == "thread.started":
        res.session_ids.append(d.get("thread_id"))
        return [Event(kind="system", actor="system", subkind="thread", session=d.get("thread_id"),
                      text=f"thread {d.get('thread_id')}", **{k: v for k, v in sysbase.items() if k != "session"})]
    if t == "turn.started":
        return [Event(kind="system", actor="system", subkind="turn", text="turn started", **sysbase)]
    if t == "turn.completed":
        res.native["turns_completed"] = res.native.get("turns_completed", 0) + 1
        return [Event(kind="system", actor="system", subkind="turn", usage=_usage(d.get("usage")),
                      text="turn completed " + short_json(d.get("usage")), **sysbase)]
    if t == "turn.failed":
        err = d.get("error")
        return [Event(kind="system", actor="system", subkind="error", is_error=True,
                      text="turn failed: " + short_json(err.get("message") if isinstance(err, dict) else err), **sysbase)]
    if t == "item.completed" and isinstance(d.get("item"), dict):
        return _item(d["item"], base, res)
    if t in ("item.started", "item.updated"):
        return []
    if t == "error":
        return [Event(kind="system", actor="system", subkind="error", is_error=True, text=str(d.get("message") or d),
                      **sysbase)]
    # older {"id", "msg"} shape
    if t == "legacy:session_configured":
        res.session_ids.append(msg.get("session_id"))
        return [Event(kind="system", actor="system", subkind="init", model=msg.get("model"),
                      text=f"session configured: model={msg.get('model')}", **sysbase)]
    if t == "legacy:agent_message":
        return [Event(kind="assistant", text=str(msg.get("message") or ""), **base)]
    if t == "legacy:agent_reasoning":
        return [Event(kind="assistant", subkind="reasoning", text=str(msg.get("text") or ""), **base)]
    if t == "legacy:exec_command_begin":
        cmd = _command(msg.get("command"))
        return [Event(kind="tool_call", tool="shell", command=cmd, text=cmd or "", call_id=msg.get("call_id"), **base)]
    if t == "legacy:exec_command_end":
        code = msg.get("exit_code")
        out = (msg.get("stdout") or "") + (msg.get("stderr") or "") or msg.get("aggregated_output") or ""
        return [Event(kind="tool_result", actor="tool", tool="shell", call_id=msg.get("call_id"),
                      is_error=(code not in (0, None)) or None, text=f"exit {code}\n{out}", **sysbase)]
    if t == "legacy:patch_apply_begin":
        files = sorted((msg.get("changes") or {}).keys()) if isinstance(msg.get("changes"), dict) else []
        return [Event(kind="tool_call", tool="apply_patch", files=files, file_op="edit" if files else None,
                      text=short_json(msg.get("changes"), 4000), call_id=msg.get("call_id"), **base)]
    if t == "legacy:token_count":
        info = msg.get("info") if isinstance(msg.get("info"), dict) else {}
        if _usage(info.get("total_token_usage")):
            res.native["usage_last_total"] = _usage(info.get("total_token_usage"))
        return []
    if t in ("legacy:task_started", "legacy:task_complete"):
        if t == "legacy:task_complete":
            res.native["turns_completed"] = res.native.get("turns_completed", 0) + 1
        return [Event(kind="system", actor="system", subkind="turn", text=t.split(":", 1)[1], **sysbase)]
    if t in ("legacy:error", "legacy:stream_error"):
        return [Event(kind="system", actor="system", subkind="error", is_error=True, text=str(msg.get("message") or ""),
                      **sysbase)]
    res.stats.setdefault("other_events", {})
    res.stats["other_events"][t] = res.stats["other_events"].get(t, 0) + 1
    return [Event(kind="system", actor="system", subkind="other", text=short_json(d, 4000), **sysbase)]


def _rollout_record(d: dict, base: dict, res: ParseResult, state: dict) -> list:
    typ = d.get("type")
    p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
    sysbase = {k: v for k, v in base.items() if k != "actor"}
    if typ == "session_meta":
        meta = p.get("meta") if isinstance(p.get("meta"), dict) else p
        res.cli_version = res.cli_version or meta.get("cli_version")
        if meta.get("id"):
            res.session_ids.append(meta.get("id"))
        return [Event(kind="system", actor="system", subkind="init",
                      text=f"session {meta.get('id')} cli_version={meta.get('cli_version')} "
                           f"originator={meta.get('originator')}", **sysbase)]
    if typ == "turn_context":
        state["model"] = p.get("model") or state.get("model")
        return [Event(kind="system", actor="system", subkind="turn", model=p.get("model"),
                      text=f"turn context: model={p.get('model')} approval={p.get('approval_policy')} "
                           f"sandbox={short_json(p.get('sandbox_policy'), 300)}", **sysbase)]
    if typ == "event_msg":
        et = p.get("type")
        if et == "token_count":
            info = p.get("info") if isinstance(p.get("info"), dict) else {}
            if _usage(info.get("total_token_usage")):
                res.native["usage_last_total"] = _usage(info.get("total_token_usage"))
        elif et in ("task_started", "turn_started"):
            return [Event(kind="system", actor="system", subkind="turn", text="turn started", **sysbase)]
        elif et in ("task_complete", "turn_complete"):
            res.native["turns_completed"] = res.native.get("turns_completed", 0) + 1
            err = p.get("error")
            dur = p.get("duration_ms")
            return [Event(kind="system", actor="system", subkind="turn", is_error=True if err else None,
                          text="turn completed" + (f" in {dur / 1000:.1f} s" if isinstance(dur, (int, float)) else "")
                               + (": " + short_json(err, 2000) if err else ""), **sysbase)]
        elif et == "turn_aborted":
            return [Event(kind="system", actor="system", subkind="error", is_error=True,
                          text="turn aborted: " + str(p.get("reason") or ""), **sysbase)]
        return []
    if typ != "response_item":
        return [Event(kind="system", actor="system", subkind=str(typ), text=short_json(p, 4000), **sysbase)]
    pt = p.get("type")
    model = state.get("model")
    if pt == "message":
        role = p.get("role")
        text = _texts(p.get("content"))
        if role == "user":
            return [Event(kind="user", actor="user", text=text, **sysbase)]
        if role == "assistant":
            return [Event(kind="assistant", model=model, text=text, **base)]
        return [Event(kind="system", actor="system", subkind=f"{role}_message", text=text, **sysbase)]
    if pt == "reasoning":
        summary = "\n".join(s.get("text", "") for s in p.get("summary") or [] if isinstance(s, dict))
        return [Event(kind="assistant", subkind="reasoning", model=model, text=summary or "[reasoning, not stored]",
                      **base)]
    if pt in ("function_call", "custom_tool_call"):
        name = str(p.get("name") or "?")
        args = _args(p.get("arguments") if pt == "function_call" else p.get("input"))
        # shell / shell_command: "command"; exec_command (unified exec): "cmd"
        cmd = _command(args.get("command", args.get("cmd"))) if isinstance(args, dict) else None
        text = args if isinstance(args, str) else short_json(args)
        files = PATCH_FILE_RE.findall(args) if isinstance(args, str) and "*** " in args else []
        return [Event(kind="tool_call", tool=name, command=cmd, text=cmd or text, files=files,
                      file_op="edit" if files else None, call_id=p.get("call_id"), model=model, **base)]
    if pt in ("function_call_output", "custom_tool_call_output"):
        out = p.get("output")
        if isinstance(out, dict):
            out = out.get("content") if isinstance(out.get("content"), str) else short_json(out)
        elif isinstance(out, list):                  # content items: their text entries
            out = _texts(out) or short_json(out)
        code = _exit_code(out)
        return [Event(kind="tool_result", actor="tool", call_id=p.get("call_id"), text=str(out or ""),
                      is_error=True if code not in (0, None) else None, **sysbase)]
    if pt == "local_shell_call":
        action = p.get("action") if isinstance(p.get("action"), dict) else {}
        cmd = _command(action.get("command"))
        return [Event(kind="tool_call", tool="local_shell", command=cmd, text=cmd or "", call_id=p.get("call_id"),
                      model=model, **base)]
    if pt == "web_search_call":
        action = p.get("action") if isinstance(p.get("action"), dict) else {}
        return [Event(kind="tool_call", tool="web_search", text=str(action.get("query") or short_json(p, 2000)),
                      model=model, **base)]
    return [Event(kind="system", actor="system", subkind=str(pt), text=short_json(p, 4000), **sysbase)]


def parse(files, options=None) -> ParseResult:
    res = ParseResult(framework="codex", events=[])
    lines = bad = 0
    names = {}
    for path in files:
        recs, n, b = read_records(path)
        lines, bad = lines + n, bad + b
        state = {}
        is_rollout = any(d.get("type") in ROLLOUT_TYPES and isinstance(d.get("payload"), dict) for _, d in recs[:50])
        if is_rollout:
            info = X.summarise_rollout(path)
            res.cli_version = res.cli_version or info.get("cli_version")
        for lineno, d in recs:
            base = {"ts": iso_from_str(d.get("timestamp")), "source": src(path, lineno), "actor": "agent"}
            evs = _rollout_record(d, base, res, state) if is_rollout else _exec_event(d, X.event_type(d), base, res)
            for e in evs:
                if e.kind == "tool_call" and e.call_id:
                    names[e.call_id] = e.tool
                elif e.kind == "tool_result" and e.call_id and not e.tool:
                    e.tool = names.get(e.call_id)
            res.events += evs
    res.session_ids = [s for s in dict.fromkeys(res.session_ids) if s]
    for e in res.events:
        e.session = e.session or (res.session_ids[0] if res.session_ids else None)
    _turn_usage_deltas(res)
    res.stats = dict(res.stats, lines=lines, unparseable_lines=bad)
    return res


def _turn_usage_deltas(res: ParseResult) -> None:
    """turn.completed carries the running total: give each turn event the difference to the previous total, so the
    events add up to the last total (X.turn_usage_total decides; values that do not grow stay as they are)."""
    turns = [e for e in res.events if e.subkind == "turn" and e.usage]
    if not turns:
        return
    total, grows = X.turn_usage_total([e.usage for e in turns])
    if grows:
        prev: dict = {}
        for e in turns:
            cur = dict(e.usage)
            e.usage = {k: v - prev.get(k, 0) for k, v in cur.items()} or None
            prev = cur
        res.native["tokens_basis"] = ("turn.completed usage: Codex reports the thread's running total there, so the "
                                      "last total is used (each turn event shows its difference to the one before; "
                                      "input includes cached input, as Codex reports it)")
    else:
        res.native["tokens_basis"] = ("sum of turn.completed usage (the values do not grow from turn to turn, so they "
                                      "were read as per-turn usage; input includes cached input, as Codex reports it)")
    res.native["usage_turn_total"] = total


register("codex", "OpenAI Codex CLI", sniff, parse)
