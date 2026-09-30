"""SYNTHETIC OpenCode files, laid out as the OpenCode source (github.com/anomalyco/opencode, tag v1.18.33) describes
them: the `opencode run --format json` event stream, the SQLite tables session / message / part / todo (next to
account / credential tables that hold tokens), the JSON storage of versions up to v1.1.x, and auth.json. Nothing here
was captured from a live OpenCode run; the token values are fake and assembled from fragments."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SID = "ses_0a1b2c3d4e5fSyntheticRun01"
CHILD = "ses_0a1b2c3d4e60SyntheticSub01"
T0 = 1790000000000                                   # ms since the epoch (2026-09-21)
MODEL = {"providerID": "anthropic", "modelID": "claude-test-model"}
FAKE_ACCOUNT_TOKEN = "acct" + "-access-" + "Zq9" * 12
FAKE_CREDENTIAL_VALUE = "cred" + "-value-" + "Wx7" * 12


def jl(path: Path, records) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def auth_json() -> str:
    """OpenCode's <data>/auth.json: one entry per provider (opencode/src/auth/index.ts)."""
    return json.dumps({
        "anthropic": {"type": "api", "key": "sk-" + "ant-" + "api03-" + "F" * 40},
        "openai": {"type": "oauth", "refresh": "rt-" + "R" * 30, "access": "at-" + "A" * 30, "expires": 1790000000},
    }, indent=2)


def tool_part(pid, mid, sid, tool, inp, output="ok", status="completed", t=0, metadata=None):
    state = {"status": status, "input": inp, "time": {"start": T0 + t, "end": T0 + t + 500}}
    if status == "completed":
        state.update(output=output, title=tool, metadata=metadata or {})
    else:
        state.update(error=output)
    return {"id": pid, "sessionID": sid, "messageID": mid, "type": "tool", "callID": "call_" + pid, "tool": tool,
            "state": state}


def session_messages(sid=SID, prompt="Predict the Gata4 knockout board. Write out/pred_T3_gata4.h5ad.", model=MODEL,
                     extra_parts=()):
    """[(message info, [parts])] of a short run: the user prompt, then two assistant steps with tools."""
    u, a1, a2 = "msg_u01", "msg_a01", "msg_a02"
    user = {"id": u, "sessionID": sid, "role": "user", "time": {"created": T0}, "agent": "build", "model": model}
    asst = {"sessionID": sid, "role": "assistant", "parentID": u, "modelID": model["modelID"],
            "providerID": model["providerID"], "mode": "build", "agent": "build", "path": {"cwd": "/ws", "root": "/ws"},
            "cost": 0.01, "tokens": {"input": 900, "output": 60, "reasoning": 0, "cache": {"read": 100, "write": 0}}}
    step_tokens = {"input": 1000, "output": 50, "reasoning": 5, "cache": {"read": 200, "write": 10}}
    return [
        (user, [{"id": "prt_u01", "sessionID": sid, "messageID": u, "type": "text", "text": prompt}]),
        (dict(asst, id=a1, time={"created": T0 + 1000, "completed": T0 + 5000}), [
            {"id": "prt_a01", "sessionID": sid, "messageID": a1, "type": "step-start"},
            {"id": "prt_a02", "sessionID": sid, "messageID": a1, "type": "reasoning", "text": "Plan: floor first.",
             "time": {"start": T0 + 1100, "end": T0 + 1200}},
            tool_part("prt_a03", a1, sid, "bash", {"command": "ls data", "description": "list data"}, "raw panels", t=1300),
            tool_part("prt_a04", a1, sid, "write", {"filePath": "/ws/src/model.py", "content": "print('fit')\n"}, t=2000),
            {"id": "prt_a05", "sessionID": sid, "messageID": a1, "type": "step-finish", "reason": "tool-calls",
             "cost": 0.005, "tokens": step_tokens},
        ]),
        (dict(asst, id=a2, time={"created": T0 + 6000, "completed": T0 + 9000}), [
            {"id": "prt_b01", "sessionID": sid, "messageID": a2, "type": "step-start"},
            tool_part("prt_b02", a2, sid, "bash", {"command": "python src/model.py --out out/pred_T3_gata4.h5ad"},
                      "wrote out/pred_T3_gata4.h5ad", t=6100),
            tool_part("prt_b03", a2, sid, "edit", {"filePath": "/ws/NOTES.md", "oldString": "a", "newString": "b"},
                      "no match", status="error", t=7000),
            {"id": "prt_b04", "sessionID": sid, "messageID": a2, "type": "text", "text": "Wrote out/pred_T3_gata4.h5ad.",
             "time": {"start": T0 + 8000, "end": T0 + 8100}},
            {"id": "prt_b05", "sessionID": sid, "messageID": a2, "type": "patch", "hash": "abc123",
             "files": ["/ws/src/model.py"]},
            {"id": "prt_b06", "sessionID": sid, "messageID": a2, "type": "step-finish", "reason": "stop", "cost": 0.004,
             "tokens": step_tokens},
        ] + list(extra_parts)),
    ]


def child_messages():
    """A subagent session (task tool) under SID, on a different model."""
    m = {"providerID": "openai", "modelID": "gpt-sub-model"}
    return [(dict(info, sessionID=CHILD, id=info["id"] + "c"), [dict(p, sessionID=CHILD, messageID=info["id"] + "c",
                                                                     id=p["id"] + "c") for p in parts])
            for info, parts in session_messages(CHILD, prompt="Check the panel order.", model=m)[:2]]


def stream_events(sid=SID, extra=()):
    """What `opencode run --format json` prints for the run above (opencode/src/cli/cmd/run.ts: emit())."""
    out = []
    for info, parts in session_messages(sid)[1:]:
        for p in parts:
            t = {"step-start": "step_start", "step-finish": "step_finish", "text": "text", "reasoning": "reasoning",
                 "tool": "tool_use"}.get(p["type"])
            if t:
                out.append({"type": t, "timestamp": info["time"]["created"], "sessionID": sid, "part": p})
    return out + list(extra)


SESSION_SQL = """
CREATE TABLE project (id TEXT PRIMARY KEY, worktree TEXT, time_created INTEGER, time_updated INTEGER);
CREATE TABLE session (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, workspace_id TEXT, parent_id TEXT, slug TEXT NOT NULL,
  directory TEXT NOT NULL, path TEXT, title TEXT NOT NULL, version TEXT NOT NULL, share_url TEXT, summary_additions INTEGER,
  summary_deletions INTEGER, summary_files INTEGER, summary_diffs TEXT, metadata TEXT, cost REAL NOT NULL DEFAULT 0,
  tokens_input INTEGER NOT NULL DEFAULT 0, tokens_output INTEGER NOT NULL DEFAULT 0, tokens_reasoning INTEGER NOT NULL
  DEFAULT 0, tokens_cache_read INTEGER NOT NULL DEFAULT 0, tokens_cache_write INTEGER NOT NULL DEFAULT 0, revert TEXT,
  permission TEXT, agent TEXT, model TEXT, time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL,
  time_compacting INTEGER, time_archived INTEGER);
CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, time_created INTEGER NOT NULL,
  time_updated INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT NOT NULL, session_id TEXT NOT NULL, time_created INTEGER NOT NULL,
  time_updated INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE todo (session_id TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL, priority TEXT NOT NULL,
  position INTEGER NOT NULL, time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL);
CREATE TABLE account (id TEXT PRIMARY KEY, email TEXT NOT NULL, url TEXT NOT NULL, access_token TEXT NOT NULL,
  refresh_token TEXT NOT NULL, token_expiry INTEGER, time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL);
CREATE TABLE credential (id TEXT PRIMARY KEY, integration_id TEXT, label TEXT NOT NULL, value TEXT NOT NULL,
  connector_id TEXT, method_id TEXT, active INTEGER, time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL);
"""


def make_db(path: Path, wal: bool = False, version: str = "1.18.33") -> Path:
    """<data>/opencode.db with the run SID, its child session, and token-holding account / credential rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SESSION_SQL)
    con.execute("INSERT INTO project VALUES ('prj_1', '/ws', ?, ?)", (T0, T0))
    perm = json.dumps([{"permission": "question", "action": "deny", "pattern": "*"}])
    for sid, parent, msgs in ((SID, None, session_messages()), (CHILD, SID, child_messages())):
        con.execute("INSERT INTO session (id, project_id, parent_id, slug, directory, title, version, permission, agent, "
                    "model, tokens_input, time_created, time_updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (sid, "prj_1", parent, "slug-" + sid[-4:], "/ws", "oc-run", version, perm, "build",
                     json.dumps({"id": MODEL["modelID"], "providerID": MODEL["providerID"]}), 2000, T0, T0 + 9000))
        for info, parts in msgs:
            data = {k: v for k, v in info.items() if k not in ("id", "sessionID")}
            con.execute("INSERT INTO message VALUES (?,?,?,?,?)", (info["id"], sid, info["time"]["created"],
                                                                   info["time"]["created"], json.dumps(data)))
            for p in parts:
                pdata = {k: v for k, v in p.items() if k not in ("id", "sessionID", "messageID")}
                con.execute("INSERT INTO part VALUES (?,?,?,?,?,?)", (p["id"], info["id"], sid, info["time"]["created"],
                                                                      info["time"]["created"], json.dumps(pdata)))
    con.execute("INSERT INTO todo VALUES (?,?,?,?,?,?,?)", (SID, "write the prediction", "completed", "high", 0, T0, T0))
    con.execute("INSERT INTO session (id, project_id, slug, directory, title, version, time_created, time_updated) "
                "VALUES ('ses_other', 'prj_1', 's', '/other', 'another run', ?, ?, ?)", (version, T0, T0))
    con.execute("INSERT INTO account VALUES ('acc_1', 'someone@example.org', 'console', ?, ?, 0, ?, ?)",
                (FAKE_ACCOUNT_TOKEN, FAKE_ACCOUNT_TOKEN[::-1], T0, T0))
    con.execute("INSERT INTO credential (id, label, value, time_created, time_updated) VALUES ('crd_1', 'x', ?, ?, ?)",
                (json.dumps({"token": FAKE_CREDENTIAL_VALUE}), T0, T0))
    con.commit()
    con.close()
    return path


def make_storage(ddir: Path, sid=SID) -> Path:
    """The JSON storage of OpenCode up to v1.1.x: storage/session/<projectID>/<id>.json, storage/message/<sid>/<mid>.json,
    storage/part/<mid>/<pid>.json (opencode/src/storage/storage.ts)."""
    st = Path(ddir) / "storage"
    info = {"id": sid, "slug": "s", "projectID": "prj_1", "directory": "/ws", "title": "oc-run", "version": "1.1.40",
            "time": {"created": T0, "updated": T0 + 9000}}
    (st / "session" / "prj_1").mkdir(parents=True, exist_ok=True)
    (st / "session" / "prj_1" / f"{sid}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    for minfo, parts in session_messages(sid):
        (st / "message" / sid).mkdir(parents=True, exist_ok=True)
        (st / "message" / sid / f"{minfo['id']}.json").write_text(json.dumps(minfo, indent=2), encoding="utf-8")
        for p in parts:
            (st / "part" / minfo["id"]).mkdir(parents=True, exist_ok=True)
            (st / "part" / minfo["id"] / f"{p['id']}.json").write_text(json.dumps(p, indent=2), encoding="utf-8")
    (st / "session_diff").mkdir(parents=True, exist_ok=True)
    (st / "session_diff" / f"{sid}.json").write_text("[]", encoding="utf-8")
    (st / "session" / "prj_1" / "ses_unrelated.json").write_text(json.dumps(dict(info, id="ses_unrelated")),
                                                                 encoding="utf-8")
    return st


def export_doc(sid=SID) -> dict:
    """What `opencode export <sessionID>` prints (opencode/src/cli/cmd/export.ts)."""
    info = {"id": sid, "slug": "s", "projectID": "prj_1", "directory": "/ws", "title": "oc-run", "version": "1.18.33",
            "time": {"created": T0, "updated": T0 + 9000}}
    return {"info": info, "messages": [{"info": m, "parts": p} for m, p in session_messages(sid)]}
