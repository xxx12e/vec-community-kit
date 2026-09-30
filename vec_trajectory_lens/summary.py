"""The summary card: what a reader (a team, or an auditor) wants to know before reading the timeline. Stdlib only.

Network-shaped commands are flagged with the evidence skeleton's own guard patterns (vec_agent_evidence/hooks/guard.py
NETWORK_RE: curl, wget, pip install, git clone / fetch / pull / push, ssh, requests / httpx / urllib / socket,
huggingface_hub, any http(s) URL, ...), applied to the command text of shell tool calls, plus the web tools by name.
A flag says the command LOOKS like network access; it does not say it happened or that it broke a rule.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime

from vec_agent_evidence.hooks.guard import NETWORK_RE

from .schema import USAGE_KEYS

NETWORK_TOOLS = {"webfetch", "websearch", "web_fetch", "web_search", "codesearch"}
FRAMEWORK_LABELS = {"claude": "Claude Code", "codex": "OpenAI Codex CLI", "opencode": "OpenCode"}
TURNS_BASIS = {
    "claude": "distinct assistant message ids (one per model response)",
    "codex": "completed turns (turn.completed / task_complete; one per prompt, not per model call)",
    "opencode": "step-finish parts (one per model call)",
}
NOT_SHOWN = [
    "This report reads logs; it does not prove that a run was autonomous, that the configuration was locked, or that "
    "the rules were followed. It only shows what the log files say.",
    "Network flags come from regular expressions over command text: a flag is not proof of network access, and "
    "obfuscated or indirect network access (for example Python code that opens a socket from a file) is not seen.",
    "The secret scan and the redaction match credential-SHAPED strings (and values you pass with --redact-env); a "
    "secret with no recognisable shape is not found.",
    "Hidden reasoning that the framework did not store is not in the log, so it is not here.",
]


def flag_network(events) -> list:
    """Mark tool calls that look like network access (flags += ["network"]); returns the flag rows."""
    rows = []
    for i, e in enumerate(events):
        if e.kind != "tool_call":
            continue
        reason = None
        if e.tool and e.tool.lower() in NETWORK_TOOLS:
            reason = f"network tool {e.tool}"
        elif e.command:
            m = NETWORK_RE.search(e.command)
            if m:
                reason = f"matched {m.group(0)!r}"
        if reason:
            if "network" not in e.flags:
                e.flags.append("network")
            rows.append({"event": i, "tool": e.tool, "reason": reason, "ts": e.ts, "command": e.command or e.text})
    return rows


def _seconds(a, b):
    try:
        return (datetime.fromisoformat(b.replace("Z", "+00:00")) - datetime.fromisoformat(a.replace("Z", "+00:00"))).total_seconds()
    except (AttributeError, ValueError):
        return None


def build(result, events, sources: list, network: list, scan: dict, redactions: dict, redaction_labels: list) -> dict:
    fw = result.framework
    kinds = Counter(e.kind for e in events)
    tools = Counter(e.tool or "?" for e in events if e.kind == "tool_call")
    tool_errors = sum(1 for e in events if e.kind == "tool_result" and e.is_error)
    # Claude Code writes "<synthetic>" as the model of messages it makes up itself (e.g. an API error shown as a reply).
    # Besides the model responses, the session / turn records name the model: Claude Code's init, Codex's
    # turn_context and session_configured (a Codex dedup package keeps only those, its stream names no model)
    models = Counter(e.model for e in events if e.model and e.model != "<synthetic>" and (
        e.kind in ("assistant", "tool_call") or (e.kind == "system" and e.subkind in ("init", "turn"))))
    for m in result.native.get("models") or []:                 # e.g. modelUsage keys of a Claude Code result
        models.setdefault(m, 0)
    if result.native.get("init_model"):
        models.setdefault(result.native["init_model"], 0)
    tokens = {k: 0 for k in USAGE_KEYS}
    seen = set()
    for e in events:
        for k, v in (e.usage or {}).items():
            tokens[k] += v
            seen.add(k)
    tokens = {k: (tokens[k] if k in seen else None) for k in USAGE_KEYS}
    ts = sorted(e.ts for e in events if e.ts)
    wall = {"first": ts[0] if ts else None, "last": ts[-1] if ts else None,
            "seconds": _seconds(ts[0], ts[-1]) if len(ts) > 1 else None, "basis": "first and last event timestamps"}
    if wall["seconds"] is None and isinstance(result.native.get("duration_ms"), (int, float)):
        wall.update(seconds=result.native["duration_ms"] / 1000.0, basis="duration_ms of the CLI's result event")
    written, edited, read = [], [], set()
    for e in events:
        if e.kind not in ("tool_call", "system") or not e.files:
            continue
        if e.file_op == "write":
            written += e.files
        elif e.file_op == "edit":
            edited += e.files
        elif e.file_op == "read":
            read.update(e.files)
    if fw == "claude":
        turns = result.native.get("assistant_messages") or 0
    elif fw == "codex":
        turns = result.native.get("turns_completed") or 0
    else:
        turns = sum(1 for e in events if e.kind == "system" and e.subkind == "step")
    usage_basis = result.native.get("tokens_basis") or {
        "claude": "sum of each model response's usage (counted once per message id)",
        "codex": "turn.completed usage (input includes cached input, as Codex reports it)",
        "opencode": "sum of step-finish tokens (one per model call)"}[fw]
    if fw == "codex" and not seen and result.native.get("usage_last_total"):
        tokens = {k: result.native["usage_last_total"].get(k) for k in USAGE_KEYS}
        usage_basis = "last token_count total reported by Codex"
    warnings = []
    distinct = [m for m in models if m]
    if len(distinct) > 1:
        warnings.append(f"more than one model string appears: {', '.join(distinct)} (a subagent, a fallback, or a small "
                        "model the CLI uses for background work such as titles; the timeline shows which events each "
                        "one produced)")
    if not distinct:
        warnings.append("no model string in these logs")
    if network:
        warnings.append(f"{len(network)} tool call(s) look like network access (see the list)")
    if not scan["clean"]:
        warnings.append("credential-shaped content in the input log(s): redacted in this report, but the original log "
                        "files still hold it - do not upload them as they are")
    warnings += result.notes
    if result.stats.get("unparseable_lines"):
        warnings.append(f"{result.stats['unparseable_lines']} line(s) of the input were not JSON and were skipped")
    return {
        "framework": fw, "framework_label": FRAMEWORK_LABELS.get(fw, fw), "cli_version": result.cli_version,
        "session_ids": result.session_ids, "sources": sources,
        "models": [{"model": m, "events": n} for m, n in models.most_common()], "multiple_models": len(distinct) > 1,
        "events": len(events), "events_by_kind": {k: kinds.get(k, 0) for k in ("user", "assistant", "tool_call",
                                                                             "tool_result", "system")},
        "turns": turns, "turns_basis": TURNS_BASIS[fw],
        "tool_calls": sum(tools.values()), "tool_calls_by_tool": dict(tools.most_common()), "tool_errors": tool_errors,
        "tokens": tokens, "tokens_basis": usage_basis,
        "tokens_reported_by_cli": result.native.get("usage"),
        "cost_usd": result.native.get("total_cost_usd", result.native.get("cost")),
        "wall_time": wall,
        "files_written": list(dict.fromkeys(written)), "files_edited": list(dict.fromkeys(edited)),
        "files_read": len(read),
        "network_flags": network, "network_patterns": "vec_agent_evidence/hooks/guard.py NETWORK_RE + web tools by name",
        "secret_scan": dict(scan, redactions=redactions, patterns=redaction_labels),
        "parse_stats": result.stats, "warnings": warnings, "not_shown": NOT_SHOWN,
    }
