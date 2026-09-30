"""vec_trajectory_lens on SYNTHETIC logs. The Claude Code records follow the field names the CLI writes (stream-json of
`claude -p --output-format stream-json --verbose`, and the session JSONL under ~/.claude/projects); the Codex and
OpenCode records are the ones the evidence adapters' tests use. No real transcript, key or run is in this file; the
key-shaped strings are fake and assembled from fragments."""
from __future__ import annotations

import json
import re
import sqlite3
import zipfile
from pathlib import Path

import pytest

import oc_fixtures as F
from test_codex_adapter import THREAD, exec_json_stream, rollout
from vec_agent_evidence import codex as X
from vec_agent_evidence import opencode as O
from vec_trajectory_lens.parsers import opencode as OCP
from vec_trajectory_lens import core, inputs, parsers as P
from vec_trajectory_lens.__main__ import main as lens_main
from vec_trajectory_lens.redact import Redactor, scan_bytes
from vec_trajectory_lens.schema import KINDS, SCHEMA, Event

SID = "6f1c2d3e-0000-4000-8000-00000000abcd"
ANTHROPIC_KEY = "sk-" + "ant-" + "api03-" + "Zz9_" * 10
OPENAI_KEY = "sk-" + "proj-" + "Qq8-" * 10
GATEWAY_KEY = "gw-" + "plainvalue-" + "7" * 12


def jl(path: Path, records) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def use(mid, blocks, usage=None, model="claude-test-model", **extra):
    msg = {"id": mid, "type": "message", "role": "assistant", "model": model, "content": blocks,
           "usage": usage or {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 1000,
                              "cache_creation_input_tokens": 50}}
    return dict({"type": "assistant", "message": msg, "session_id": SID, "parent_tool_use_id": None,
                 "uuid": "u-" + mid}, **extra)


def result_block(tid, content, is_error=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": content, "is_error": is_error}]}, "session_id": SID}


def claude_stream(extra_blocks=()):
    """What `claude -p --output-format stream-json --verbose` prints for a short run: one response split over two
    lines (same message id and usage), a network-shaped Bash call, a Write, a failed Edit, a final answer."""
    return [
        {"type": "system", "subtype": "init", "session_id": SID, "model": "claude-test-model", "cwd": "/ws",
         "tools": ["Bash", "Read", "Write", "Edit"], "permissionMode": "bypassPermissions",
         "claude_code_version": "9.9.9-synthetic"},
        use("msg_01", [{"type": "thinking", "thinking": "Plan first.", "signature": "x"}]),
        use("msg_01", [{"type": "tool_use", "id": "toolu_1", "name": "Bash",
                        "input": {"command": "curl -s https://example.org/data.h5ad -o data/x.h5ad"}}]),
        result_block("toolu_1", "harness guard: network access is forbidden", True),
        use("msg_02", [{"type": "tool_use", "id": "toolu_2", "name": "Write",
                        "input": {"file_path": "/ws/src/model.py", "content": "print('fit')\n"}}]),
        result_block("toolu_2", [{"type": "text", "text": "File created"}]),
        use("msg_03", [{"type": "tool_use", "id": "toolu_3", "name": "Edit",
                        "input": {"file_path": "/ws/NOTES.md", "old_string": "a", "new_string": "b"}}]),
        result_block("toolu_3", "String not found", True),
        use("msg_04", [{"type": "tool_use", "id": "toolu_4", "name": "Read", "input": {"file_path": "/ws/README.md"}}]
            + list(extra_blocks)),
        use("msg_05", [{"type": "text", "text": "Finalized out/pred_T3_gata4.h5ad."}]),
        {"type": "result", "subtype": "success", "is_error": False, "num_turns": 5, "duration_ms": 125000,
         "total_cost_usd": 0.42, "session_id": SID, "result": "Finalized.",
         "usage": {"input_tokens": 500, "output_tokens": 100, "cache_read_input_tokens": 5000},
         "modelUsage": {"claude-test-model": {"inputTokens": 500}}},
    ]


def claude_session(ts0="2026-09-30T01:00:00.000Z"):
    """The session JSONL the CLI writes: timestamps, CLI version, bookkeeping records."""
    base = {"sessionId": SID, "version": "9.9.9-synthetic", "cwd": "/ws", "userType": "external", "isSidechain": False}
    return [
        {"type": "queue-operation", "operation": "enqueue", "sessionId": SID, "timestamp": ts0},
        dict(base, type="user", uuid="u1", parentUuid=None, timestamp=ts0,
             message={"role": "user", "content": "Predict the Gata4 board. Write out/pred_T3_gata4.h5ad."}),
        dict(base, type="assistant", uuid="a1", timestamp="2026-09-30T01:00:05.000Z",
             message=use("msg_01", [{"type": "tool_use", "id": "toolu_1", "name": "Bash",
                                     "input": {"command": "pip install scanpy"}}])["message"]),
        dict(base, type="user", uuid="u2", timestamp="2026-09-30T01:00:09.000Z",
             message={"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1",
                                                   "content": "denied"}]}),
        dict(base, type="system", subtype="api_error", level="error", uuid="s1", timestamp="2026-09-30T01:00:10.000Z",
             content="API error, retrying"),
        dict(base, type="user", uuid="u3", isMeta=True, timestamp="2026-09-30T01:00:11.000Z",
             message={"role": "user", "content": "<local-command-caveat>meta</local-command-caveat>"}),
        dict(base, type="assistant", uuid="a2", timestamp="2026-09-30T01:30:00.000Z",
             message=use("msg_02", [{"type": "text", "text": "Done."}])["message"]),
        {"type": "custom-title", "customTitle": "t", "sessionId": SID},
        {"type": "file-history-snapshot", "messageId": "m", "snapshot": {}, "isSnapshotUpdate": False},
    ]


def test_schema_round_trip(tmp_path):
    evs = [Event(kind=k, ts="2026-09-30T01:00:00.000Z", actor="agent", tool="Bash" if "tool" in k else None,
                 command="ls" if k == "tool_call" else None, files=["a.py"] if k == "tool_call" else [],
                 file_op="edit" if k == "tool_call" else None, model="m", usage={"input": 3, "output": 4, "junk": 1},
                 text="x", call_id="c1", is_error=False, subkind="s", session="s1", source="f:1", flags=["network"],
                 msg_id="m1") for k in KINDS] + [Event(kind="user")]
    for e in evs:
        assert Event.from_dict(json.loads(json.dumps(e.to_dict()))) == e
    assert evs[0].usage == {"input": 3, "output": 4} and Event(kind="user").to_dict() == {"kind": "user", "actor": "agent"}
    with pytest.raises(ValueError):
        Event(kind="tool")
    with pytest.raises(ValueError):
        Event.from_dict({"kind": "user", "surprise": 1})
    stream = jl(tmp_path / "stream.jsonl", claude_stream())
    summ, events = core.analyse(stream)
    core.write_outputs(summ, events, out_events=tmp_path / "ev.jsonl")
    assert json.loads((tmp_path / "ev.jsonl").read_text(encoding="utf-8").splitlines()[0])["schema"] == SCHEMA
    assert core.read_events(tmp_path / "ev.jsonl") == events


def test_claude_stream_json(tmp_path):
    summ, events = core.analyse(jl(tmp_path / "stream.jsonl", claude_stream()))
    assert summ["framework"] == "claude" and summ["cli_version"] == "9.9.9-synthetic"
    assert summ["session_ids"] == [SID] and summ["models"][0]["model"] == "claude-test-model"
    assert not summ["multiple_models"]
    assert summ["turns"] == 5                                   # msg_01 spans two lines: counted once
    assert summ["tokens"] == {"input": 500, "output": 100, "cache_read": 5000, "cache_write": 250, "reasoning": None}
    assert summ["tokens_reported_by_cli"] == {"input": 500, "output": 100, "cache_read": 5000}
    assert summ["tool_calls_by_tool"] == {"Bash": 1, "Write": 1, "Edit": 1, "Read": 1} and summ["tool_errors"] == 2
    assert summ["files_written"] == ["/ws/src/model.py"] and summ["files_edited"] == ["/ws/NOTES.md"]
    assert summ["files_read"] == 1 and summ["cost_usd"] == 0.42
    assert summ["wall_time"]["seconds"] == 125.0 and "duration_ms" in summ["wall_time"]["basis"]
    assert [r["tool"] for r in summ["network_flags"]] == ["Bash"]
    results = [e for e in events if e.kind == "tool_result"]
    assert [e.tool for e in results] == ["Bash", "Write", "Edit"] and results[0].is_error
    assert events[0].subkind == "init" and events[-1].subkind == "result"
    assert sum(1 for e in events if e.usage) == 5


def test_claude_session_jsonl_with_subagents(tmp_path):
    proj = tmp_path / "projects" / "C--ws"
    main = jl(proj / f"{SID}.jsonl", claude_session())
    jl(proj / SID / "subagents" / "agent-1.jsonl", [
        {"type": "assistant", "sessionId": SID, "isSidechain": True, "timestamp": "2026-09-30T01:10:00.000Z",
         "message": use("msg_s1", [{"type": "text", "text": "subagent says hi"}], model="claude-small-model")["message"]}])
    jl(proj / "other-session.jsonl", claude_session())
    with pytest.raises(inputs.InputError, match="pass one file, or --session"):
        core.analyse(proj)
    for summ, events in (core.analyse(proj, session=SID), core.analyse(main)):
        assert summ["framework"] == "claude" and summ["parse_stats"]["shape"] == "session-jsonl"
        assert summ["multiple_models"] and {m["model"] for m in summ["models"]} == {"claude-test-model",
                                                                                   "claude-small-model"}
        assert summ["wall_time"]["seconds"] == 1800.0 and summ["cli_version"] == "9.9.9-synthetic"
        assert summ["parse_stats"]["skipped_records_by_type"] == {"queue-operation": 1, "custom-title": 1,
                                                                   "file-history-snapshot": 1}
        assert [e.actor for e in events if e.kind == "user"] == ["user", "system"]
        assert any(e.actor == "subagent" for e in events)
        assert any(e.kind == "system" and e.is_error for e in events)
        assert summ["network_flags"][0]["reason"] == "matched 'pip install'"
    summ, _ = core.analyse(main, subagents=False)
    assert not summ["multiple_models"]


def test_codex_stream_and_rollout(tmp_path):
    stream = jl(tmp_path / "codex_stream.jsonl", exec_json_stream())
    summ, events = core.analyse(stream)
    assert summ["framework"] == "codex" and summ["session_ids"] == [THREAD]
    assert summ["tokens"]["input"] == 1500 and summ["tokens"]["cache_read"] == 300 and summ["turns"] == 2
    assert summ["tool_calls_by_tool"] == {"shell": 3, "file_change": 1} and summ["tool_errors"] == 1
    assert summ["files_written"] == ["src/model.py"] and "no model string in these logs" in summ["warnings"]
    home = tmp_path / "home"
    ro = rollout(home, "Predict the Gata4 knockout board.")
    summ, events = core.analyse(ro)
    assert summ["cli_version"] == "0.0.0-synthetic" and summ["models"][0]["model"] == "gpt-test-model"
    assert [e.kind for e in events if e.kind in ("user", "assistant")] == ["user", "assistant"]
    # an unzipped codex-package with a dedup rollout: the stream and the rollout are read together
    pkg = tmp_path / "pkg" / "evidence" / "trajectory"
    (pkg / "rollout").mkdir(parents=True)
    (pkg / "codex_stream.jsonl").write_bytes(stream.read_bytes())
    (pkg / "rollout" / (ro.stem + ".dedup.jsonl")).write_bytes(ro.read_bytes())
    fw, files = inputs.resolve(tmp_path / "pkg")
    assert fw == "codex" and [f.name for f in files] == ["codex_stream.jsonl", ro.stem + ".dedup.jsonl"]
    summ, _ = core.analyse(tmp_path / "pkg")
    assert summ["tool_calls"] == 4 and summ["models"][0]["model"] == "gpt-test-model"


def test_opencode_stream_export_database_and_storage(tmp_path):
    summ, _ = core.analyse(F.jl(tmp_path / "opencode_stream.jsonl", F.stream_events()))
    assert summ["framework"] == "opencode" and summ["turns"] == 2 and summ["tokens"]["input"] == 2000
    assert summ["tool_calls_by_tool"] == {"bash": 2, "write": 1, "edit": 1} and summ["files_written"] == ["/ws/src/model.py"]
    exp = tmp_path / "session_export.json"
    exp.write_text(json.dumps(F.export_doc()), encoding="utf-8")
    summ, events = core.analyse(exp)
    assert summ["cli_version"] == "1.18.33" and summ["models"][0]["model"] == "anthropic/claude-test-model"
    assert events[0].kind == "user" and events[0].text.startswith("Predict")
    db = F.make_db(tmp_path / "data" / "opencode.db")
    summ, events = core.analyse(db, session=F.SID)
    assert summ["multiple_models"] and any(e.actor == "subagent" for e in events)
    text = json.dumps([e.to_dict() for e in events]) + json.dumps(summ)
    assert F.FAKE_ACCOUNT_TOKEN not in text and F.FAKE_CREDENTIAL_VALUE not in text
    # only the rows that were read are listed and scanned: not the database file (its account table holds tokens)
    assert summ["sources"][0]["file"].startswith("opencode.db: session") and summ["secret_scan"]["clean"]
    (tmp_path / "data" / "auth.json").write_text(F.auth_json(), encoding="utf-8")
    summ, _ = core.analyse(tmp_path / "data")                  # data directory, no --session: the latest session
    assert any("most recently updated" in w for w in summ["warnings"]) and summ["secret_scan"]["clean"]
    legacy = tmp_path / "legacy"
    F.make_storage(legacy)
    (legacy / "auth.json").write_text(F.auth_json(), encoding="utf-8")
    summ, _ = core.analyse(legacy, session=F.SID)
    assert summ["cli_version"] == "1.1.40" and summ["tool_calls"] == 4 and summ["secret_scan"]["clean"]
    assert all(s["file"].startswith("storage/") for s in summ["sources"]) and len(summ["sources"]) > 10


def test_opencode_data_dir_reads_the_database_before_old_storage(tmp_path, monkeypatch, capsys):
    # an upgraded install: v1.2.0 copied storage/ into opencode.db and left the old files in place
    data = tmp_path / "data"
    F.make_storage(data, sid="ses_OLDlegacySession0001")
    F.make_db(data / "opencode.db")
    for session in (None, F.SID):
        summ, _ = core.analyse(data, session=session)
        assert summ["session_ids"][0] == F.SID and summ["cli_version"] == "1.18.33"
        assert any("storage/ directory" in w and "was not read" in w for w in summ["warnings"])
    # a session that only the old storage holds is still found there, and the report says why
    summ, _ = core.analyse(data, session="ses_OLDlegacySession0001")
    assert summ["cli_version"] == "1.1.40" and any("is not in opencode.db" in w for w in summ["warnings"])
    # storage/ given on its own is read on its own
    summ, _ = core.analyse(data / "storage")
    assert summ["session_ids"] == ["ses_OLDlegacySession0001"]
    # two install channels: the database that holds the session (or the most recent one) is read and named
    chan = tmp_path / "chan"
    F.make_db(chan / "opencode.db")
    F.make_db(chan / "opencode-beta.db")
    con = sqlite3.connect(str(chan / "opencode-beta.db"))
    con.execute("UPDATE session SET id = 'ses_betaChannelRun01', time_updated = ? WHERE id = ?", (F.T0 + 99000, F.SID))
    con.execute("UPDATE message SET session_id = 'ses_betaChannelRun01' WHERE session_id = ?", (F.SID,))
    con.execute("UPDATE part SET session_id = 'ses_betaChannelRun01' WHERE session_id = ?", (F.SID,))
    con.execute("UPDATE session SET parent_id = 'ses_betaChannelRun01' WHERE parent_id = ?", (F.SID,))
    con.commit()
    con.close()
    summ, _ = core.analyse(chan)
    assert summ["session_ids"][0] == "ses_betaChannelRun01"
    assert any("2 OpenCode databases" in w and "opencode-beta.db was read" in w for w in summ["warnings"])
    summ, _ = core.analyse(chan, session=F.SID)
    assert summ["session_ids"][0] == F.SID and any("opencode.db was read" in w for w in summ["warnings"])
    monkeypatch.setenv("OPENCODE_DB", "custom.db")                      # a relative OPENCODE_DB is looked up here
    F.make_db(chan / "custom.db")
    assert [p.name for p in OCP.data_dir_dbs(chan)] == ["opencode.db", "opencode-beta.db", "custom.db"]
    # a database that is not OpenCode's: a readable refusal (exit 2), not a traceback
    other = tmp_path / "other.db"
    con = sqlite3.connect(str(other))
    con.execute("CREATE TABLE x (a)")
    con.commit()
    con.close()
    assert lens_main([str(other)]) == 2
    assert "cannot be read as an OpenCode database" in capsys.readouterr().out
    with pytest.raises(inputs.InputError, match="no OpenCode session ses_missing"):
        core.analyse(data / "opencode.db", session="ses_missing")


def test_opencode_database_is_read_without_creating_side_files(tmp_path):
    ddir = tmp_path / "data"
    db = F.make_db(ddir / "opencode.db", wal=True)
    before = sorted(p.name for p in ddir.iterdir())
    assert before == ["opencode.db"]
    core.analyse(db)
    core.analyse(ddir, session=F.SID)
    assert O.export_from_db(db, F.SID)["info"]["id"] == F.SID
    assert sorted(p.name for p in ddir.iterdir()) == before              # no -wal / -shm next to it
    # while OpenCode still has it open (a -wal file exists), the pages in the -wal are read too
    live = sqlite3.connect(str(db))
    try:
        live.execute("INSERT INTO todo VALUES (?,?,?,?,?,?,?)", (F.SID, "only in the wal", "pending", "low", 1, F.T0, F.T0))
        live.commit()
        assert (ddir / "opencode.db-wal").exists()
        assert [t["content"] for t in O.export_from_db(db, F.SID)["todo"]] == ["write the prediction", "only in the wal"]
    finally:
        live.close()


def test_redaction_everywhere(tmp_path, monkeypatch):
    leak = [{"type": "tool_use", "id": "toolu_9", "name": "Bash",
             "input": {"command": f"OPENAI_API_KEY={OPENAI_KEY} python run.py --key {GATEWAY_KEY}"}}]
    recs = claude_stream(extra_blocks=leak) + [
        result_block("toolu_9", "cat ~/.local/share/opencode/auth.json\n" + F.auth_json()),
        result_block("toolu_1", json.dumps({"claudeAiOauth": {"accessToken": "tok-" + "A" * 30,
                                                              "refreshToken": "ref-" + "B" * 30}})),
        use("msg_06", [{"type": "text", "text": f"The key is {ANTHROPIC_KEY} ok"}]),
    ]
    stream = jl(tmp_path / "leaky.jsonl", recs)
    monkeypatch.setenv("MY_GATEWAY_KEY", GATEWAY_KEY)
    rc = lens_main([str(stream), "--out", str(tmp_path / "r.html"), "--json", str(tmp_path / "s.json"),
                    "--events", str(tmp_path / "e.jsonl"), "--redact-env", "MY_GATEWAY_KEY"])
    assert rc == 0
    secrets = [ANTHROPIC_KEY, OPENAI_KEY, GATEWAY_KEY, "tok-" + "A" * 30, "ref-" + "B" * 30, "api03-" + "F" * 40,
               "rt-" + "R" * 30]
    for name in ("r.html", "s.json", "e.jsonl"):
        data = (tmp_path / name).read_text(encoding="utf-8")
        for s in secrets:
            assert s not in data and json.dumps(s)[1:-1] not in data, (name, s[:8])
        assert scan_bytes(data.encode("utf-8")) == [], name
    summ = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))["summary"]
    assert not summ["secret_scan"]["clean"]
    labels = set(summ["secret_scan"]["hits"][0]["patterns"])            # the raw bytes, as the packagers scan them
    assert {"anthropic_api_key_shape", "openai_api_key_shape", "opencode_auth_entry", "extra_value_0"} <= labels
    red = summ["secret_scan"]["redactions"]                             # the parsed (unescaped) text
    assert red["extra_value_0"] >= 1 and red["openai_api_key_shape"] >= 1 and red["opencode_auth_entry"] >= 1
    assert red["oauth_access_token_field"] >= 1 and red["oauth_refresh_token_field"] >= 1
    assert any("do not upload them as they are" in w for w in summ["warnings"])
    events = core.read_events(tmp_path / "e.jsonl")
    assert any("redacted" in e.flags for e in events)
    cmd = next(e.command for e in events if e.command and "run.py" in e.command)
    assert "[REDACTED:openai_api_key_shape]" in cmd and "[REDACTED:extra_value_0]" in cmd
    r = Redactor()
    out, changed = r.text('{"access_token": "abc.def-ghi", "keep": 1}')
    assert changed and "abc.def-ghi" not in out and '"keep": 1' in out


def test_output_guard_refuses_when_redaction_misses(tmp_path, monkeypatch):
    stream = jl(tmp_path / "leaky.jsonl", claude_stream() + [use("msg_9", [{"type": "text", "text": ANTHROPIC_KEY}])])
    monkeypatch.setattr(Redactor, "event", lambda self, ev: False)
    summ, events = core.analyse(stream)
    with pytest.raises(core.OutputRefused, match="anthropic_api_key_shape"):
        core.write_outputs(summ, events, tmp_path / "r.html", tmp_path / "s.json")
    assert not (tmp_path / "r.html").exists() and not (tmp_path / "s.json").exists()
    assert lens_main([str(stream), "--out", str(tmp_path / "r2.html")]) == 3


def test_network_flags_use_the_guard_patterns(tmp_path):
    cmds = ["ls -la", "curl -s https://example.org", "python -m pip install torch", "git push origin main",
            "python -c 'import requests'", "wget http://x", "echo hello", "cat data/panels/index.json"]
    blocks = [{"type": "tool_use", "id": f"t{i}", "name": "Bash", "input": {"command": c}} for i, c in enumerate(cmds)]
    blocks.append({"type": "tool_use", "id": "tw", "name": "WebFetch", "input": {"url": "https://example.org"}})
    summ, events = core.analyse(jl(tmp_path / "s.jsonl", [claude_stream()[0], use("m1", blocks)]))
    flagged = [r["command"] for r in summ["network_flags"]]
    assert flagged == [cmds[1], cmds[2], cmds[3], cmds[4], cmds[5], '{"url": "https://example.org"}']
    assert all("network" in e.flags for e in events if e.kind == "tool_call" and e.command in flagged[:5])
    assert not any("network" in e.flags for e in events if e.command in ("ls -la", "echo hello"))


def test_html_is_self_contained_and_offline(tmp_path):
    evil = "</script><script>alert(1)</script><img src=x onerror=alert(2)>"
    recs = claude_stream() + [use("msg_x", [{"type": "text", "text": "see https://example.org/page and " + evil}])]
    stream = jl(tmp_path / "s.jsonl", recs)
    assert lens_main([str(stream), "--out", str(tmp_path / "r.html"), "--title", "run <1>"]) == 0
    page = (tmp_path / "r.html").read_text(encoding="utf-8")
    assert page.isascii()
    assert "http://" not in page and "https://" not in page
    # the embedded data is inert JSON (no "<" at all); outside it, the only link targets are fragments (#e<n>)
    raw = re.search(r'<script type="application/json" id="lens-data">(.*?)</script>', page, re.S).group(1)
    assert "<" not in raw and ">" not in raw and "://" not in raw
    outside = page.replace(raw, "")
    assert not re.search(r"""(?i)\b(?:src|href|action|srcset|poster)\s*=\s*(?:["'](?!#)|[^"'#\s>])""", outside)
    assert "url(" not in page and "@import" not in page and "<link" not in page.lower()
    assert "default-src 'none'" in page and evil not in page and "run &lt;1&gt;" in page
    assert page.count("<script") == 2 and page.count("</script>") == 2
    data = json.loads(re.search(r'<script type="application/json" id="lens-data">(.*?)</script>', page, re.S).group(1))
    texts = [e.get("text", "") for e in data["events"]]
    assert any(evil in t for t in texts) and any("https://example.org/page" in t for t in texts)
    assert "Read this first" not in page or "network access" in page
    assert "What this report does not show" in page and "does not prove" in page


def test_cli_inputs_and_zip(tmp_path, capsys):
    stream = jl(tmp_path / "s.jsonl", claude_stream())
    assert lens_main([str(stream), "--json", str(tmp_path / "s.json")]) == 0
    assert "Claude Code 9.9.9-synthetic" in capsys.readouterr().out
    assert lens_main([str(stream), "--framework", "codex"]) == 0          # forced: parsed as codex, nothing matches
    junk = tmp_path / "junk.jsonl"
    junk.write_text("not json\n", encoding="utf-8")
    assert lens_main([str(junk)]) == 2 and "CANNOT READ" in capsys.readouterr().out
    assert lens_main([str(tmp_path / "missing.jsonl")]) == 2
    # a trajectory.zip as the portal receives it (here: from an OpenCode package layout)
    z = tmp_path / "trajectory.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("trajectory/opencode_stream.jsonl", "".join(json.dumps(r) + "\n" for r in F.stream_events()))
        zf.writestr("trajectory/session_export.json", json.dumps(F.export_doc()))
        zf.writestr("../escape.txt", "never written outside the temporary directory")
    assert lens_main([str(z), "--out", str(tmp_path / "z.html"), "--json", str(tmp_path / "z.json")]) == 0
    summ = json.loads((tmp_path / "z.json").read_text(encoding="utf-8"))["summary"]
    assert summ["framework"] == "opencode" and summ["sources"][0]["file"] == "session_export.json"
    assert not (tmp_path / "escape.txt").exists()
    assert set(P.PARSERS) == {"claude", "codex", "opencode"}
