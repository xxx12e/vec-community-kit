"""vec_agent_evidence.opencode on SYNTHETIC OpenCode files (tests/oc_fixtures.py). The layout follows the OpenCode source
(github.com/anomalyco/opencode, tag v1.18.33); nothing here was captured from a live OpenCode run, so these tests show
that the adapter handles that layout, not that your OpenCode version writes exactly this."""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

import oc_fixtures as F
from conftest import make_adata
from vec_agent_evidence import common as C
from vec_agent_evidence import opencode as oc
from vec_agent_evidence.__main__ import main as cli_main

PKG = Path(oc.__file__).resolve().parent


@pytest.fixture
def oc_run(tmp_path, heart_panel, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(oc, "home_dir", lambda: home)
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)                    # the upward config search stops at the repository root
    ws = proj / "ws"
    (ws / "out").mkdir(parents=True)
    (ws / "src").mkdir()
    (ws / "opencode.jsonc").write_text(
        '{\n  // project config\n  "share": "disabled",\n  "permission": {"webfetch": "deny", "websearch": "deny",\n'
        '    "external_directory": "deny", "bash": {"*": "allow", "curl *": "deny",},},\n}\n', encoding="utf-8")
    (ws / "AGENTS.md").write_text("Work only inside this directory.\n", encoding="utf-8")
    (ws / ".opencode" / "command").mkdir(parents=True)
    (ws / ".opencode" / "command" / "fit.md").write_text("Fit the model.\n", encoding="utf-8")
    (ws / ".opencode" / "agent").mkdir(parents=True)
    (ws / ".opencode" / "agent" / ".env").write_text("OPENAI_API_KEY=placeholder\n", encoding="utf-8")
    (ws / "data").mkdir()
    (ws / "data" / "AGENTS.md").write_text("not collected: data dirs are skipped\n", encoding="utf-8")
    make_adata(heart_panel, 1000, seed=7).write_h5ad(ws / "out" / "pred_T3_gata4.h5ad")
    cfg = tmp_path / "oc_config"
    (cfg / "agent").mkdir(parents=True)
    (cfg / "opencode.json").write_text(json.dumps({"model": "anthropic/claude-test-model", "autoupdate": False}),
                                       encoding="utf-8")
    (cfg / "AGENTS.md").write_text("Global instructions.\n", encoding="utf-8")
    (cfg / "agent" / "reviewer.md").write_text("---\nmode: subagent\n---\nReview.\n", encoding="utf-8")
    data = tmp_path / "oc_data"
    data.mkdir()
    (data / "auth.json").write_text(F.auth_json(), encoding="utf-8")
    (data / "mcp-auth.json").write_text(json.dumps({"srv": {"tokens": {"accessToken": "m" * 20}}}), encoding="utf-8")
    F.make_db(data / "opencode.db")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Predict the Gata4 knockout board. Write out/pred_T3_gata4.h5ad.\n", encoding="utf-8")
    stream = F.jl(tmp_path / "opencode_stream.jsonl", F.stream_events())
    loop = tmp_path / "my_loop.py"
    loop.write_text("print('orchestration')\n", encoding="utf-8")
    env = {"OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_CLAUDE_CODE": "1", "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
           "OPENCODE_AUTH_CONTENT": F.auth_json()}
    return {"ws": ws, "cfg": cfg, "data": data, "prompt": prompt, "stream": stream, "loop": loop, "env": env,
            "tmp": tmp_path, "home": home}


def lock(r, out=None, **kw):
    return oc.lock_opencode(r["prompt"], r["ws"], out or r["tmp"] / "lock", "anthropic/claude-test-model",
                            cfg_dir=r["cfg"], ddir=r["data"], env=r["env"], exe=str(r["tmp"] / "no-such-opencode"), **kw)


def package(r, out, **kw):
    kw.setdefault("workspace", r["ws"])
    kw.setdefault("ddir", r["data"])
    kw.setdefault("cfg_dir", r["cfg"])
    kw.setdefault("env", r["env"])
    return oc.package_opencode(r["stream"], r["prompt"], out, **kw)


def members(path) -> dict:
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_command_and_locations(tmp_path):
    cmd = oc.build_command("anthropic/claude-x", "/ws", agent="build", variant="high", title="t1")
    assert cmd == ["opencode", "run", "--format", "json", "--model", "anthropic/claude-x", "--dir", "/ws", "--agent",
                   "build", "--variant", "high", "--title", "t1"]
    assert "--auto" in oc.build_command("a/b", "/ws", auto=True)
    assert oc.data_dir(env={"XDG_DATA_HOME": str(tmp_path)}) == tmp_path / "opencode"
    assert oc.config_dir(env={"XDG_CONFIG_HOME": str(tmp_path)}) == tmp_path / "opencode"
    F.make_db(tmp_path / "opencode.db")
    F.make_db(tmp_path / "opencode-beta.db")
    assert [p.name for p in oc.db_candidates(tmp_path, env={})] == ["opencode.db", "opencode-beta.db"]
    assert [p.name for p in oc.db_candidates(tmp_path, env={"OPENCODE_DB": "opencode-beta.db"})] == ["opencode-beta.db"]
    assert oc.db_candidates(tmp_path, env={"OPENCODE_DB": ":memory:"}) == []
    assert oc.parse_jsonc('{"a": 1, // c\n "b": "x//y", /* z */ "c": [1, 2,],}') == {"a": 1, "b": "x//y", "c": [1, 2]}
    assert oc.parse_jsonc("{nope") is None


def test_summarise_stream(oc_run):
    s = oc.summarise_stream(oc_run["stream"])
    assert s["shape"] == "opencode-run-json" and s["session_id"] == F.SID and s["unparseable_lines"] == 0
    assert s["steps"] == 2 and s["tools_by_name"] == {"bash": 2, "write": 1, "edit": 1} and s["tool_errors"] == 1
    assert s["tokens"] == {"input": 2000, "output": 100, "reasoning": 10, "cache_read": 400, "cache_write": 20}
    assert s["files_changed"] == ["/ws/src/model.py", "/ws/NOTES.md"] and s["last_text"].startswith("Wrote out/")
    junk = oc_run["tmp"] / "junk.jsonl"
    junk.write_text("plain text\n[1]\n", encoding="utf-8")
    assert oc.summarise_stream(junk)["shape"] == "unknown"


@pytest.mark.parametrize("wal", [False, True])
def test_export_from_db_reads_only_the_session_tables(tmp_path, wal):
    db = F.make_db(tmp_path / "opencode.db", wal=wal)
    exp = oc.export_from_db(db, F.SID)
    text = json.dumps(exp)
    assert F.FAKE_ACCOUNT_TOKEN not in text and F.FAKE_ACCOUNT_TOKEN[::-1] not in text
    assert F.FAKE_CREDENTIAL_VALUE not in text and "ses_other" not in text
    info = exp["info"]
    assert info["id"] == F.SID and info["version"] == "1.18.33" and info["projectID"] == "prj_1"
    assert info["permission"][0]["action"] == "deny" and info["tokens"]["input"] == 2000
    assert [m["info"]["role"] for m in exp["messages"]] == ["user", "assistant", "assistant"]
    assert exp["messages"][1]["parts"][2]["tool"] == "bash" and exp["messages"][1]["parts"][2]["messageID"] == "msg_a01"
    assert exp["todo"][0]["content"] == "write the prediction"
    assert [c["info"]["id"] for c in exp["children"]] == [F.CHILD]
    s = oc.summarise_export(exp)
    assert s["models"] == ["anthropic/claude-test-model", "openai/gpt-sub-model"] and s["sessions"] == 2
    assert s["steps"] == 3 and s["tokens"]["input"] == 3000 and s["cli_version"] == "1.18.33"
    assert [m["text"][:7] for m in s["user_messages"]] == ["Predict", "Check t"]
    assert oc.export_from_db(db, "ses_missing") is None
    assert not (tmp_path / "opencode.db-wal").exists() or wal      # read-only: nothing written next to a rollback db


def test_legacy_json_storage(tmp_path):
    F.make_storage(tmp_path)
    files = oc.storage_session_files(tmp_path, F.SID)
    rels = [rel for rel, _ in files]
    assert rels[0] == f"session/prj_1/{F.SID}.json" and f"session_diff/{F.SID}.json" in rels
    assert f"message/{F.SID}/msg_a01.json" in rels and "part/msg_a01/prt_a03.json" in rels
    assert not any("ses_unrelated" in r for r in rels)
    exp = oc.export_from_storage(files)
    assert exp["info"]["version"] == "1.1.40" and len(exp["messages"]) == 3
    assert oc.summarise_export(exp)["tools_by_name"] == {"bash": 2, "write": 1, "edit": 1}
    assert oc.storage_session_files(tmp_path, "../x") == []


def test_lock_snapshots_config_and_never_records_credentials(oc_run):
    r = oc_run
    out = lock(r, note="v3 prompt")
    names = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert names == ["command.txt", "config/global_config/agent/reviewer.md", "config/global_config/opencode.json",
                     "config/project/workspace/.opencode/command/fit.md", "config/project/workspace/opencode.jsonc",
                     "initial_prompt.md", "instructions/global_config/AGENTS.md", "instructions/workspace/AGENTS.md",
                     "opencode.lock.json", "opencode.lock.sha256"]
    raw = (out / "opencode.lock.json").read_bytes()
    assert C.sha256_bytes(raw) == (out / "opencode.lock.sha256").read_text(encoding="utf-8").strip()
    lk = json.loads(raw)
    assert lk["command"][1:4] == ["run", "--format", "json"] and lk["model"] == "anthropic/claude-test-model"
    assert lk["env"]["OPENCODE_AUTH_CONTENT"] == "<set; value not recorded>" and lk["note"] == "v3 prompt"
    assert lk["skipped_credential_files"] == ["project/workspace/.opencode/agent/.env"]
    assert lk["config_digest"]["project/workspace/opencode.jsonc"]["share"] == "disabled"
    assert lk["source_checked"]["commit"].startswith("51ef4be1")
    text = " | ".join(lk["warnings"])
    assert "share" not in text and "webfetch" not in text and "not set: OPENCODE" not in text
    assert "was not found on PATH" in text and ".env" in text
    everything = b"".join(p.read_bytes() for p in out.rglob("*") if p.is_file())
    assert b"api03-" not in everything and b"placeholder" not in everything
    assert "--format json" in (out / "command.txt").read_text(encoding="utf-8")
    assert oc.verify_lock(out)[1] == []
    # a config change after the lock is reported
    cfg = r["ws"] / "opencode.jsonc"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace('"deny"', '"allow"'), encoding="utf-8")
    assert any("changed after the lock" in p for p in oc.verify_lock(out)[1])
    with pytest.raises(SystemExit, match="not empty"):
        lock(r, out=out)


def test_lock_warnings_and_refusals(oc_run):
    r = oc_run
    (r["ws"] / "opencode.jsonc").write_text('{"permission": {"bash": "allow"}}', encoding="utf-8")
    (r["home"] / ".claude").mkdir()
    (r["home"] / ".claude" / "CLAUDE.md").write_text("personal instructions\n", encoding="utf-8")
    lk = json.loads((lock(r, out=r["tmp"] / "l2", auto=True) / "opencode.lock.json").read_text(encoding="utf-8"))
    text = " | ".join(lk["warnings"])
    assert '"share": "disabled"' in text and '"webfetch" is not denied' in text and "--auto" in text
    assert "CLAUDE.md" not in text                     # OPENCODE_DISABLE_CLAUDE_CODE is set in this environment
    env = dict(r["env"])
    del env["OPENCODE_DISABLE_CLAUDE_CODE"]
    lk = oc.lock_opencode(r["prompt"], r["ws"], r["tmp"] / "l3", "anthropic/m", cfg_dir=r["cfg"], ddir=r["data"], env=env)
    assert any("~/.claude/CLAUDE.md" in w for w in json.loads((lk / "opencode.lock.json").read_text())["warnings"])
    # a provider key written into a config file: refused, nothing written
    (r["ws"] / "opencode.jsonc").write_text(json.dumps({"provider": {"anthropic": {"options": {
        "apiKey": "sk-" + "ant-" + "api03-" + "K" * 30}}}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="REFUSED: credential-shaped.*anthropic_api_key_shape"):
        lock(r, out=r["tmp"] / "l4")
    assert not (r["tmp"] / "l4").exists()
    with pytest.raises(SystemExit, match="provider/model"):
        oc.lock_opencode(r["prompt"], r["ws"], r["tmp"] / "l5", "claude-test-model", env={})


def test_instruction_files_named_by_the_config(oc_run):
    r = oc_run
    (r["ws"] / "docs").mkdir()
    (r["ws"] / "docs" / "rules.md").write_text("Always validate before finalizing.\n", encoding="utf-8")
    (r["ws"] / "opencode.jsonc").write_text(json.dumps({"share": "disabled", "instructions": [
        "docs/*.md", "https://example.org/team-rules.md"]}), encoding="utf-8")
    lk = json.loads((lock(r, out=r["tmp"] / "li") / "opencode.lock.json").read_text(encoding="utf-8"))
    assert "config_instructions/docs/rules.md" in lk["instruction_files"]
    assert any("fetched from a URL" in w for w in lk["warnings"])
    assert (r["tmp"] / "li" / "instructions" / "config_instructions" / "docs" / "rules.md").is_file()


def test_package_three_kinds_from_database(oc_run):
    r = oc_run
    lk = lock(r)
    out = package(r, r["tmp"] / "pkg", lock=lk, stderr=None, harness=[r["loop"]],
                  predictions={"T3:gata4": r["ws"] / "out" / "pred_T3_gata4.h5ad"}, team_uploaded_mb=10)
    traj, prompts, harness = (members(out / f"{k}.zip") for k in ("trajectory", "prompts", "harness"))
    assert sorted(traj) == ["trajectory/opencode_stream.jsonl", "trajectory/session_export.json",
                            "trajectory/trajectory_summary.json"]
    assert traj["trajectory/opencode_stream.jsonl"] == r["stream"].read_bytes()
    exp = json.loads(traj["trajectory/session_export.json"])
    assert exp["info"]["id"] == F.SID and "vec_note" in exp and len(exp["children"]) == 1
    assert sorted(prompts) == ["prompts/initial_prompt.md", "prompts/locked/instructions/global_config/AGENTS.md",
                               "prompts/locked/instructions/workspace/AGENTS.md", "prompts/user_messages.jsonl"]
    assert "harness/lock/opencode.lock.json" in harness and "harness/lock/config/project/workspace/opencode.jsonc" in harness
    assert "harness/files/my_loop.py" in harness and "harness/opencode_manifest.json" in harness
    man = json.loads(harness["harness/opencode_manifest.json"])
    assert man["model_string"] == "anthropic/claude-test-model" and man["session_source"] == "db"
    assert man["database"]["file"] == "opencode.db" and "1.18.33" in man["framework"]
    assert man["lock"]["problems"] == [] and man["predictions"][0]["stream_mentions"] == 2
    assert "untested against a live OpenCode run" in man["status"]
    # the subagent ran another model: reported, not hidden
    assert [w for w in man["warnings"] if "differs from the model(s)" in w]
    for rel, v in man["evidence"].items():
        assert v["sha256"] == C.sha256_file(out / "evidence" / rel), rel
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "untested against a live OpenCode run" in readme and "verified" in readme and "per-team cap" in readme
    assert C.sha256_file(out / "predictions" / "pred_T3_gata4.h5ad") == C.sha256_file(r["ws"] / "out" / "pred_T3_gata4.h5ad")


def test_package_from_export_file_and_legacy_storage(oc_run, tmp_path):
    r = oc_run
    exp = tmp_path / "session_export.json"
    exp.write_text("Exporting session: x\n" + json.dumps(F.export_doc(), indent=2), encoding="utf-8")
    out = package(r, tmp_path / "p_export", export=exp)
    traj = members(out / "trajectory.zip")
    assert traj["trajectory/session_export.json"] == exp.read_bytes()
    man = json.loads(members(out / "harness.zip")["harness/opencode_manifest.json"])
    assert man["session_source"] == "export" and man["model_string"] == "anthropic/claude-test-model"
    text = " | ".join(man["warnings"])
    assert "no --lock" in text and "no --command-file" in text and "no --prediction" in text
    assert "harness/config/project/workspace/opencode.jsonc" in members(out / "harness.zip")
    # an OpenCode up to v1.1.x: JSON files under storage/, byte-copied
    legacy = tmp_path / "legacy_data"
    F.make_storage(legacy)
    out = package(r, tmp_path / "p_storage", ddir=legacy)
    traj = members(out / "trajectory.zip")
    assert f"trajectory/storage/session/prj_1/{F.SID}.json" in traj and "trajectory/storage/part/msg_a01/prt_a03.json" in traj
    assert json.loads(members(out / "harness.zip")["harness/opencode_manifest.json"])["session_source"] == "storage"
    # nothing found: a warning with the export command, never a failure
    empty = tmp_path / "empty_data"
    empty.mkdir()
    out = package(r, tmp_path / "p_none", ddir=empty)
    man = json.loads(members(out / "harness.zip")["harness/opencode_manifest.json"])
    assert man["session_source"] is None and any("opencode export" in w for w in man["warnings"])


def test_credentials_are_never_collected(oc_run, tmp_path):
    r = oc_run
    data = r["data"]
    auth = data / "auth.json"
    secret_bytes = [auth.read_bytes(), (data / "mcp-auth.json").read_bytes()]
    # stray copies in the workspace are not picked up either
    (r["ws"] / "auth.json").write_bytes(auth.read_bytes())
    (r["ws"] / "cache.db").write_bytes((data / "opencode.db").read_bytes())
    out = package(r, tmp_path / "ok", lock=lock(r), harness=[r["loop"]])
    for z in ("trajectory", "prompts", "harness", "evidence_bundle"):
        for name, blob in members(out / f"{z}.zip").items():
            assert not oc.is_credential_file(Path(name)), name
            assert blob not in secret_bytes and not oc.is_sqlite(data=blob), name
            assert F.FAKE_ACCOUNT_TOKEN.encode() not in blob and F.FAKE_CREDENTIAL_VALUE.encode() not in blob, name
            assert b"api03-" not in blob, name
    assert not any(p.name in ("auth.json", "mcp-auth.json", "opencode.db", "cache.db") for p in out.rglob("*"))
    # named on the command line, by any route: refused before anything is written
    routes = [dict(harness=[auth]), dict(stderr=data / "mcp-auth.json"), dict(harness=[data / "opencode.db"]),
              dict(export=auth), dict(command_file=r["ws"] / ".opencode" / "agent" / ".env"),
              dict(harness=[r["ws"] / "cache.db"])]
    for i, kw in enumerate(routes):
        with pytest.raises(SystemExit, match="is a credential file"):
            package(r, tmp_path / f"no{i}", **kw)
        assert not (tmp_path / f"no{i}").exists()
    # renamed copies: auth.json by its bytes, the database by its header
    renamed = tmp_path / "notes.txt"
    renamed.write_bytes(auth.read_bytes())
    with pytest.raises(SystemExit, match="same bytes as a credential file"):
        package(r, tmp_path / "renamed", harness=[renamed])
    db_copy = tmp_path / "results.json"
    db_copy.write_bytes((data / "opencode.db").read_bytes())
    with pytest.raises(SystemExit, match="SQLite database"):
        package(r, tmp_path / "dbcopy", harness=[db_copy])
    link = tmp_path / "settings_link.json"
    try:
        os.symlink(auth, link)
    except (OSError, NotImplementedError):
        link = None
    if link is not None:
        with pytest.raises(SystemExit, match="is a credential file"):
            package(r, tmp_path / "link", harness=[link])
    for name in ("auth.json", "mcp-auth.json", "opencode.db", "opencode-beta.db", "opencode.db-wal", "x.sqlite", ".env"):
        assert oc.is_credential_file(tmp_path / name), name
    for name in ("opencode.json", "opencode.jsonc", "AGENTS.md", "session_export.json", "opencode_stream.jsonl", "db.py"):
        assert not oc.is_credential_file(tmp_path / name), name


def test_package_refusals(oc_run, tmp_path):
    r = oc_run
    key = "sk-" + "proj-" + "Q" * 40
    leaky = F.jl(tmp_path / "leaky.jsonl", F.stream_events(extra=[
        {"type": "tool_use", "timestamp": F.T0, "sessionID": F.SID,
         "part": F.tool_part("prt_z", "msg_a02", F.SID, "bash", {"command": "env"}, f"OPENAI_API_KEY={key}")}]))
    with pytest.raises(SystemExit, match="REFUSED: credential-shaped.*openai_api_key_shape"):
        oc.package_opencode(leaky, r["prompt"], tmp_path / "p1", ddir=r["data"], env=r["env"])
    assert not (tmp_path / "p1" / "trajectory.zip").exists()
    # the agent printed auth.json: its entry shape is refused even though the key itself looks like nothing
    cat = F.jl(tmp_path / "cat.jsonl", F.stream_events(extra=[
        {"type": "tool_use", "timestamp": F.T0, "sessionID": F.SID,
         "part": F.tool_part("prt_y", "msg_a02", F.SID, "bash", {"command": "cat auth.json"},
                             json.dumps({"zai": {"type": "api", "key": "plain-looking-value"}}, indent=2))}]))
    with pytest.raises(SystemExit, match="opencode_auth_entry"):
        oc.package_opencode(cat, r["prompt"], tmp_path / "p2", ddir=r["data"], env=r["env"])
    junk = tmp_path / "junk.jsonl"
    junk.write_text("plain text output\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no JSON events"):
        oc.package_opencode(junk, r["prompt"], tmp_path / "p3", ddir=r["data"], env=r["env"])
    with pytest.raises(SystemExit, match="session-source export needs --export"):
        oc.package_opencode(r["stream"], r["prompt"], tmp_path / "p4", ddir=r["data"], env=r["env"],
                            session_source="export")


def test_example_config_passes_its_own_checks():
    cfg = json.loads((PKG / "example_opencode.json").read_text(encoding="utf-8"))
    warnings = oc.config_warnings(oc.config_digest({"example": cfg}), {})
    assert warnings == [], warnings
    rules = cfg["permission"]["bash"]
    assert list(rules)[0] == "*" and rules["*"] == "allow"          # the last matching rule wins in OpenCode
    assert all(v == "deny" for k, v in rules.items() if k != "*")


def test_cli(oc_run, capsys):
    r = oc_run
    os.environ.pop("OPENCODE_CONFIG", None)
    rc = cli_main(["opencode-lock", "--prompt", str(r["prompt"]), "--workspace", str(r["ws"]), "--model",
                   "anthropic/claude-test-model", "--out", str(r["tmp"] / "cli_lock"), "--config-dir", str(r["cfg"]),
                   "--data-dir", str(r["data"]), "--opencode-exe", str(r["tmp"] / "none")])
    assert rc == 0 and "CONFIGURATION LOCK IS NOW IN EFFECT" in capsys.readouterr().out
    rc = cli_main(["opencode-package", "--stream", str(r["stream"]), "--prompt", str(r["prompt"]), "--out",
                   str(r["tmp"] / "cli_pkg"), "--workspace", str(r["ws"]), "--lock", str(r["tmp"] / "cli_lock"),
                   "--data-dir", str(r["data"]), "--config-dir", str(r["cfg"]),
                   "--prediction", f"T3:gata4={r['ws'] / 'out' / 'pred_T3_gata4.h5ad'}"])
    assert rc == 0 and (r["tmp"] / "cli_pkg" / "evidence_bundle.zip").exists()
    rc = cli_main(["opencode-package", "--stream", str(r["stream"]), "--prompt", str(r["prompt"]), "--out",
                   str(r["tmp"] / "cli_pkg"), "--data-dir", str(r["data"])])
    assert rc == 2 and "REFUSED" in capsys.readouterr().out
