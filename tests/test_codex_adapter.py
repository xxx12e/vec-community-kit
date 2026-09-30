"""vec_agent_evidence.codex on SYNTHETIC Codex transcripts. The event names follow the Codex CLI's documented
`codex exec --json` output (and the older {"id", "msg"} shape) as the kit authors understand it; nothing here was
captured from a live Codex run, so these tests show that the adapter handles that format, not that the format is
what your Codex version writes."""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

from vec_agent_evidence import codex
from vec_agent_evidence import common as C
from vec_agent_evidence.__main__ import main as cli_main

from conftest import make_adata

THREAD = "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"


def jl(path: Path, records) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def exec_json_stream(pred_rel="out/pred_T3_gata4.h5ad", extra=()):
    """A two-turn run in the current `codex exec --json` shape. turn.completed carries the thread's running total
    (codex-rs/exec/src/event_processor_with_jsonl_output.rs, usage_from_last_total)."""
    return [
        {"type": "thread.started", "thread_id": THREAD},
        {"type": "turn.started"},
        {"type": "item.started", "item": {"id": "item_0", "type": "command_execution", "command": "ls data",
                                          "aggregated_output": "", "status": "in_progress"}},
        {"type": "item.completed", "item": {"id": "item_0", "type": "command_execution", "command": "ls data",
                                            "aggregated_output": "raw panels\n", "exit_code": 0, "status": "completed"}},
        {"type": "item.completed", "item": {"id": "item_1", "type": "reasoning", "text": "Plan: floor first."}},
        {"type": "item.completed", "item": {"id": "item_2", "type": "file_change", "status": "completed",
                                            "changes": [{"path": "src/model.py", "kind": "add"}]}},
        {"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 200, "output_tokens": 300}},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_3", "type": "command_execution",
                                            "command": f"python src/model.py --out {pred_rel}", "aggregated_output": "ok",
                                            "exit_code": 0, "status": "completed"}},
        {"type": "item.completed", "item": {"id": "item_4", "type": "command_execution", "command": "python broken.py",
                                            "aggregated_output": "Traceback", "exit_code": 1, "status": "failed"}},
        {"type": "item.completed", "item": {"id": "item_5", "type": "agent_message", "text": f"Wrote {pred_rel}."}},
        {"type": "future.event", "payload": {"anything": 1}},
        {"type": "turn.completed", "usage": {"input_tokens": 1500, "cached_input_tokens": 300, "output_tokens": 350}},
    ] + list(extra)


def rollout(home: Path, prompt_text: str, model="gpt-test-model"):
    return jl(home / "sessions" / "2026" / "09" / "30" / f"rollout-2026-09-30T01-02-03-{THREAD}.jsonl", [
        {"timestamp": "2026-09-30T01:02:03Z", "type": "session_meta",
         "payload": {"id": THREAD, "cwd": "/ws", "cli_version": "0.0.0-synthetic", "originator": "codex_exec"}},
        {"timestamp": "2026-09-30T01:02:04Z", "type": "turn_context",
         "payload": {"model": model, "approval_policy": "never", "sandbox_policy": {"mode": "workspace-write"}}},
        {"timestamp": "2026-09-30T01:02:05Z", "type": "response_item",
         "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt_text}]}},
        {"timestamp": "2026-09-30T01:02:06Z", "type": "response_item",
         "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]}},
    ])


@pytest.fixture
def codex_run(tmp_path, heart_panel):
    ws = tmp_path / "ws"
    (ws / "out").mkdir(parents=True)
    (ws / "AGENTS.md").write_text("Work only inside this directory.\n", encoding="utf-8")
    (ws / "data").mkdir()
    (ws / "data" / "AGENTS.md").write_text("not collected: data dirs are skipped\n", encoding="utf-8")
    make_adata(heart_panel, 1000, seed=7).write_h5ad(ws / "out" / "pred_T3_gata4.h5ad")
    home = tmp_path / "codex_home"
    (home).mkdir()
    (home / "AGENTS.md").write_text("Global instructions.\n", encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Predict the Gata4 knockout board. Write out/pred_T3_gata4.h5ad.\n", encoding="utf-8")
    rollout(home, prompt.read_text(encoding="utf-8"))
    stream = jl(tmp_path / "codex_stream.jsonl", exec_json_stream())
    (tmp_path / "codex_stderr.log").write_text("", encoding="utf-8")
    loop = tmp_path / "my_loop.py"
    loop.write_text("print('orchestration')\n", encoding="utf-8")
    cmd = tmp_path / "cmd.txt"
    cmd.write_text("codex exec --json --model gpt-test-model --sandbox workspace-write --cd ws - < prompt.md\n",
                   encoding="utf-8")
    return {"ws": ws, "home": home, "prompt": prompt, "stream": stream, "loop": loop, "cmd": cmd, "tmp": tmp_path}


def test_summarise_current_shape(codex_run):
    s = codex.summarise_stream(codex_run["stream"])
    assert s["shape"] == "exec-json" and s["thread_id"] == THREAD and s["unparseable_lines"] == 0
    assert s["turns_started"] == 2 and s["turns_completed"] == 2 and s["turns_failed"] == 0
    assert s["usage"] == {"input_tokens": 1500, "cached_input_tokens": 300, "output_tokens": 350}
    assert s["commands"] == 3 and s["commands_nonzero_exit"] == 1
    assert s["items_by_type"] == {"command_execution": 3, "reasoning": 1, "file_change": 1, "agent_message": 1}
    assert s["files_changed"] == [{"path": "src/model.py", "kind": "add"}]
    assert s["events_by_type"]["future.event"] == 1 and s["last_agent_message"].startswith("Wrote out/")
    r = codex.summarise_rollout(codex.find_rollouts(codex_run["home"], THREAD)[0])
    assert r["cli_version"] == "0.0.0-synthetic" and r["models"] == ["gpt-test-model"] and r["session_id"] == THREAD
    assert len(r["user_messages"]) == 1 and "Gata4" in r["user_messages"][0]["text"]
    assert codex.find_rollouts(codex_run["home"], None) == [] and codex.find_rollouts(codex_run["home"], "../x") == []


def test_turn_usage_is_a_running_total():
    # the running total of the last turn is the run's usage; summing the turns would count turn 1 twice
    grow = [{"input_tokens": 1000, "output_tokens": 300}, {"input_tokens": 1500, "output_tokens": 350}]
    assert codex.turn_usage_total(grow) == ({"input_tokens": 1500, "output_tokens": 350}, True)
    # values that do not grow are per-turn values: summed
    flat = [{"input_tokens": 1000, "output_tokens": 300}, {"input_tokens": 500, "output_tokens": 50}]
    assert codex.turn_usage_total(flat) == ({"input_tokens": 1500, "output_tokens": 350}, False)
    assert codex.turn_usage_total([]) == ({}, True)


def test_summarise_legacy_shape(tmp_path):
    stream = jl(tmp_path / "legacy.jsonl", [
        {"id": "0", "msg": {"type": "session_configured", "session_id": THREAD, "model": "legacy-model"}},
        {"id": "1", "msg": {"type": "task_started"}},
        {"id": "1", "msg": {"type": "exec_command_begin", "command": ["ls"]}},
        {"id": "1", "msg": {"type": "exec_command_end", "exit_code": 2}},
        {"id": "1", "msg": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 7, "output_tokens": 3}}}},
        {"id": "1", "msg": {"type": "agent_message", "message": "done"}},
        {"id": "1", "msg": {"type": "task_complete"}},
    ])
    (tmp_path / "junk.jsonl").write_text("not json\n[1, 2]\n", encoding="utf-8")
    s = codex.summarise_stream(stream)
    assert s["shape"] == "legacy" and s["thread_id"] == THREAD and s["model"] == "legacy-model"
    assert s["turns_completed"] == 1 and s["commands"] == 1 and s["commands_nonzero_exit"] == 1
    assert s["usage"] == {"input_tokens": 7, "output_tokens": 3} and s["last_agent_message"] == "done"
    junk = codex.summarise_stream(tmp_path / "junk.jsonl")
    assert junk["events"] == 0 and junk["unparseable_lines"] == 2 and junk["shape"] == "unknown"


def test_package_three_kinds(codex_run):
    r = codex_run
    out = codex.package_codex(r["stream"], r["prompt"], r["tmp"] / "pkg", workspace=r["ws"], home=r["home"],
                              stderr=r["tmp"] / "codex_stderr.log",
                              predictions={"T3:gata4": r["ws"] / "out" / "pred_T3_gata4.h5ad"},
                              harness=[r["loop"]], command_file=r["cmd"], model="gpt-test-model", team_uploaded_mb=10)
    pred = out / "predictions" / "pred_T3_gata4.h5ad"
    assert C.sha256_file(pred) == C.sha256_file(r["ws"] / "out" / "pred_T3_gata4.h5ad")
    assert C.sha256_file(out / "evidence" / "trajectory" / "codex_stream.jsonl") == C.sha256_file(r["stream"])
    traj = zipfile.ZipFile(out / "trajectory.zip").namelist()
    assert "trajectory/codex_stream.jsonl" in traj and "trajectory/codex_stderr.log" in traj
    assert f"trajectory/rollout/rollout-2026-09-30T01-02-03-{THREAD}.jsonl" in traj
    assert "trajectory/trajectory_summary.json" in traj
    prompts = zipfile.ZipFile(out / "prompts.zip").namelist()
    assert sorted(prompts) == ["prompts/initial_prompt.md", "prompts/instructions/codex_home/AGENTS.md",
                               "prompts/instructions/workspace/AGENTS.md", "prompts/user_messages.jsonl"]
    harness = zipfile.ZipFile(out / "harness.zip").namelist()
    assert sorted(harness) == ["harness/codex_manifest.json", "harness/command.txt", "harness/files/my_loop.py"]
    bundle = zipfile.ZipFile(out / "evidence_bundle.zip").namelist()
    assert sorted(bundle) == sorted(traj + prompts + harness) and not any(n.endswith(".h5ad") for n in bundle)
    man = json.loads((out / "evidence" / "harness" / "codex_manifest.json").read_text(encoding="utf-8"))
    assert man["model_string"] == "gpt-test-model" and "0.0.0-synthetic" in man["framework"]
    assert "untested against a live Codex run" in man["status"]
    assert man["predictions"][0]["stream_mentions"] == 2 and man["predictions"][0]["n_obs"] == 1000
    assert man["warnings"] == [], man["warnings"]
    for rel, v in man["evidence"].items():
        assert v["sha256"] == C.sha256_file(out / "evidence" / rel), rel
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "MINIMAL ADAPTER" in readme and "untested against a live Codex run" in readme
    assert "Model string: gpt-test-model" in readme and "per-team cap" in readme and "Warnings:" not in readme
    with pytest.raises(SystemExit, match="not empty"):          # never overwrites a package
        codex.package_codex(r["stream"], r["prompt"], out)


def test_package_warns_without_rollout_model_or_provenance(codex_run, tmp_path):
    r = codex_run
    empty_home = tmp_path / "empty_home"
    empty_home.mkdir()
    other = r["ws"] / "out" / "other.h5ad"
    other.write_bytes((r["ws"] / "out" / "pred_T3_gata4.h5ad").read_bytes())
    out = codex.package_codex(r["stream"], r["prompt"], tmp_path / "pkg2", workspace=r["ws"], home=empty_home,
                              predictions={"T3:gata4": other})
    man = json.loads((out / "evidence" / "harness" / "codex_manifest.json").read_text(encoding="utf-8"))
    text = " | ".join(man["warnings"])
    assert "no rollout file" in text and "model string unknown" in text and "never appears in the stream" in text
    assert "no --command-file" in text and man["model_string"] is None
    assert "Warnings:" in (out / "README.md").read_text(encoding="utf-8")


def test_package_refusals(codex_run, tmp_path, heart_panel):
    r = codex_run
    # 1. a credential-shaped string anywhere in the evidence (here: a key printed by a command) -> refused, no zips
    key = "sk-" + "proj-" + "Q" * 40
    leaky = jl(tmp_path / "leaky.jsonl", exec_json_stream(extra=[
        {"type": "item.completed", "item": {"id": "x", "type": "command_execution", "command": "env",
                                            "aggregated_output": f"OPENAI_API_KEY={key}", "exit_code": 0}}]))
    with pytest.raises(SystemExit, match="REFUSED: credential-shaped.*openai_api_key_shape"):
        codex.package_codex(leaky, r["prompt"], tmp_path / "p1", workspace=r["ws"], home=r["home"])
    assert not (tmp_path / "p1" / "trajectory.zip").exists()
    # an auth-file token field inside a harness file is refused as well
    auth = tmp_path / "auth_copy.json"
    auth.write_text(json.dumps({"tokens": {"refresh" + "_token": "abc"}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="auth_token_field"):
        codex.package_codex(r["stream"], r["prompt"], tmp_path / "p2", home=r["home"], harness=[auth])
    # identifiers that merely contain "sk-" are not keys
    fine = jl(tmp_path / "fine.jsonl", exec_json_stream(extra=[{"type": "note", "text": "task-completion-handler-" + "9" * 30}]))
    codex.package_codex(fine, r["prompt"], tmp_path / "p3", home=r["home"])
    # 2. not a Codex JSON stream
    junk = tmp_path / "junk.jsonl"
    junk.write_text("plain text output\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no JSON events"):
        codex.package_codex(junk, r["prompt"], tmp_path / "p4")
    # 3. a prediction that fails the board contract (genes out of order)
    bad = make_adata(list(reversed(heart_panel)), 1000, seed=8)
    bad.write_h5ad(tmp_path / "bad.h5ad")
    with pytest.raises(SystemExit, match="fails the T3:gata4 contract"):
        codex.package_codex(r["stream"], r["prompt"], tmp_path / "p5", predictions={"T3:gata4": tmp_path / "bad.h5ad"})
    with pytest.raises(SystemExit, match="BOARD=PATH"):
        codex.parse_prediction_args(["pred.h5ad"])


def _long_rollout(home: Path, prompt_text: str) -> Path:
    """A rollout with the records that repeat the stream (event_msg, tool calls and output, reasoning, assistant
    messages) next to the ones it lacks (session metadata, turn context, user message, an unknown record)."""
    path = rollout(home, prompt_text)
    extra = [
        {"type": "response_item", "payload": {"type": "reasoning", "summary": [{"text": "Plan: floor first."}]}},
        {"type": "response_item", "payload": {"type": "function_call", "name": "shell", "arguments": "{\"command\": [\"ls\"]}"}},
        {"type": "response_item", "payload": {"type": "function_call_output", "output": "raw panels\n" * 50}},
        {"type": "event_msg", "payload": {"type": "exec_command_end", "exit_code": 0, "stdout": "raw panels\n" * 50}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 9}}}},
        {"type": "compacted", "payload": {"message": "unknown record kinds are kept"}},
    ]
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write("".join(json.dumps(r) + "\n" for r in extra))
    return path


def test_rollout_modes(codex_run, tmp_path, monkeypatch):
    r = codex_run
    home = tmp_path / "home_long"
    home.mkdir()
    full = _long_rollout(home, r["prompt"].read_text(encoding="utf-8"))
    full_lines = full.read_bytes().splitlines(keepends=True)
    rel = f"trajectory/rollout/{full.name}"

    def pkg(name, mode):
        return codex.package_codex(r["stream"], r["prompt"], tmp_path / name, workspace=r["ws"], home=home,
                                   rollout_mode=mode)

    def manifest(out):
        return json.loads((out / "evidence" / "harness" / "codex_manifest.json").read_text(encoding="utf-8"))

    # copy (default): byte copy; a large rollout warns and names the alternatives
    monkeypatch.setattr(codex, "ROLLOUT_WARN_MB", 0.0)
    out = pkg("copy", "copy")
    assert zipfile.ZipFile(out / "trajectory.zip").read(rel) == full.read_bytes()
    ro = manifest(out)["rollouts"][0]
    assert ro["included"] == "copy" and ro["sha256"] == C.sha256_file(full) and ro["bytes"] == full.stat().st_size
    assert any("--rollout dedup" in w for w in manifest(out)["warnings"])
    # dedup: only the records the stream lacks, each an unchanged line of the original; no size warning
    out = pkg("dedup", "dedup")
    names = zipfile.ZipFile(out / "trajectory.zip").namelist()
    dedup_rel = f"trajectory/rollout/{full.stem}.dedup.jsonl"
    assert rel not in names and dedup_rel in names
    kept = zipfile.ZipFile(out / "trajectory.zip").read(dedup_rel).splitlines(keepends=True)
    assert kept and all(line in full_lines for line in kept)
    kinds = sorted((json.loads(x)["type"], json.loads(x)["payload"].get("role")) for x in kept)
    assert kinds == [("compacted", None), ("response_item", "user"), ("session_meta", None), ("turn_context", None)]
    m = manifest(out)
    ro = m["rollouts"][0]
    assert ro["included"] == "dedup" and ro["sha256"] == C.sha256_file(full)
    assert ro["dedup"]["kept_lines"] == 4 and ro["dedup"]["dropped_lines"] == 6
    assert ro["dedup"]["dropped_by_type"]["event_msg:exec_command_end"] == 1
    assert not any("--rollout" in w for w in m["warnings"]) and m["model_string"] == "gpt-test-model"
    assert "records kept" in (out / "README.md").read_text(encoding="utf-8")
    # omit: nothing of the rollout in the trajectory, its hash in the manifest, its user messages still in prompts
    out = pkg("omit", "omit")
    assert not any(n.startswith("trajectory/rollout/") for n in zipfile.ZipFile(out / "trajectory.zip").namelist())
    assert manifest(out)["rollouts"][0]["sha256"] == C.sha256_file(full)
    assert "prompts/user_messages.jsonl" in zipfile.ZipFile(out / "prompts.zip").namelist()
    # the same bytes are never packaged twice (a second copy of the rollout found for the same thread)
    twin = full.parent / full.name.replace("rollout-", "rollout-copy-")
    twin.write_bytes(full.read_bytes())
    out = pkg("twin", "copy")
    ros = manifest(out)["rollouts"]
    assert sorted(x["included"] for x in ros)[0] == "copy" and "same bytes as rollout/" in sorted(x["included"] for x in ros)[1]
    assert len([n for n in zipfile.ZipFile(out / "trajectory.zip").namelist() if n.startswith("trajectory/rollout/")]) == 1
    with pytest.raises(SystemExit, match="rollout mode must be one of"):
        pkg("bad", "slim")


def test_cli_rollout_option(codex_run, tmp_path):
    r = codex_run
    rc = cli_main(["codex-package", "--stream", str(r["stream"]), "--prompt", str(r["prompt"]), "--out",
                   str(tmp_path / "cli_omit"), "--codex-home", str(r["home"]), "--rollout", "omit"])
    assert rc == 0
    names = zipfile.ZipFile(tmp_path / "cli_omit" / "trajectory.zip").namelist()
    assert not any(n.startswith("trajectory/rollout/") for n in names)


def test_credential_files_are_never_collected(codex_run, tmp_path):
    r = codex_run
    auth = r["home"] / "auth.json"
    auth.write_text(json.dumps({"OPENAI_API_KEY": None, "tokens": {"id" + "_token": "eyJ.a.b", "access" + "_token": "x",
                                                                   "refresh" + "_token": "y", "account_id": "z"},
                                "last_refresh": "2026-09-30T00:00:00Z"}), encoding="utf-8")
    (r["ws"] / "auth.json").write_bytes(auth.read_bytes())               # stray copies in the workspace
    (r["ws"] / ".codex").mkdir()
    (r["ws"] / ".codex" / "auth.json").write_bytes(auth.read_bytes())
    (r["ws"] / ".env").write_text("OPENAI_API_KEY=placeholder\n", encoding="utf-8")
    secret = auth.read_bytes()
    # 1. a normal package: nothing from CODEX_HOME but rollouts and AGENTS.md, no member with auth.json's bytes
    out = codex.package_codex(r["stream"], r["prompt"], tmp_path / "ok", workspace=r["ws"], home=r["home"],
                              harness=[r["loop"]], command_file=r["cmd"])
    for z in ("trajectory", "prompts", "harness", "evidence_bundle"):
        with zipfile.ZipFile(out / f"{z}.zip") as zf:
            for n in zf.namelist():
                assert not codex.CREDENTIAL_FILE_RE.match(n.rsplit("/", 1)[-1]), n
                assert zf.read(n) != secret, n
    assert not any(p.name in ("auth.json", ".env") for p in out.rglob("*"))
    # 2. named on the command line, under any route: refused before anything is written
    routes = [dict(harness=[auth]), dict(stderr=auth), dict(command_file=r["ws"] / ".env"),
              dict(harness=[r["ws"] / ".codex" / "auth.json"])]
    for i, kw in enumerate(routes):
        with pytest.raises(SystemExit, match="is a credential file"):
            codex.package_codex(r["stream"], r["prompt"], tmp_path / f"no{i}", home=r["home"], **kw)
        assert not (tmp_path / f"no{i}").exists()
    # 3. a renamed copy of CODEX_HOME/auth.json is refused by its bytes
    renamed = tmp_path / "notes.txt"
    renamed.write_bytes(secret)
    with pytest.raises(SystemExit, match="same bytes as a credential file"):
        codex.package_codex(r["stream"], r["prompt"], tmp_path / "renamed", home=r["home"], harness=[renamed])
    # 4. a link to it, under a harmless name, is refused by the target's name (where links can be made)
    link = tmp_path / "settings_link.json"
    try:
        os.symlink(auth, link)
    except (OSError, NotImplementedError):
        link = None
    if link is not None:
        with pytest.raises(SystemExit, match="is a credential file"):
            codex.package_codex(r["stream"], r["prompt"], tmp_path / "link", home=r["home"], harness=[link])
    # the name rule itself
    for name in ("auth.json", "AUTH.JSON", "auth.json.bak", "credentials.json", ".credentials.json", "gcp-credentials.json",
                 ".env", ".env.local", ".netrc", ".pypirc", "id_rsa", "id_ed25519", "server.pem", "api.key"):
        assert codex.is_credential_file(tmp_path / name), name
    for name in ("config.toml", "my_loop.py", "tokenizer.py", "AGENTS.md", "id_rsa.pub", "authors.json",
                 f"rollout-2026-09-30T01-02-03-{THREAD}.jsonl", "codex_stream.jsonl", "keys.txt"):
        assert not codex.is_credential_file(tmp_path / name), name


def _secret_hits(data: bytes) -> list:
    return [label for label, rx in C.SECRET_PATTERNS if rx.search(data)]


def test_secret_scan_ignores_key_shapes_inside_a_long_base64_blob(codex_run, tmp_path):
    """Random base64url data holds "-sk-" + 20 key characters about once per 14 MB. Such a substring in the middle
    of a blob (an image, a pickled array printed by a command) is data, not a key, and must not make packaging refuse
    a long run: the key pattern must not match after any base64 / base64url character."""
    import base64
    import random
    import re

    rng = random.Random(20260930)
    blob = bytearray(base64.urlsafe_b64encode(rng.randbytes(15 * 1024 * 1024)))       # 20 MiB of base64url
    assert len(blob) >= 20 * 1024 * 1024
    fake = b"sk-" + b"proj-" + base64.urlsafe_b64encode(rng.randbytes(33))              # 44 key characters
    # the pattern before this fix (not preceded by a word character only): it matched after "-", "+" and "/"
    old = re.compile(rb"(?<![A-Za-z0-9_])" + b"sk-" + rb"(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}")
    step = len(blob) // 8
    for i, before in enumerate(b"-_+/A9z"):                  # every kind of base64 / base64url character
        pos = step * (i + 1)
        blob[pos:pos + 1 + len(fake)] = bytes([before]) + fake
    blob = bytes(blob)
    assert old.search(blob), "the synthetic blob should have tripped the old pattern"
    assert _secret_hits(blob) == []
    # standard base64 cannot contain "-" at all; a blob of it is clean too
    assert _secret_hits(base64.b64encode(rng.randbytes(3 * 1024 * 1024))) == []
    # the whole path: a command printed the blob, the run is packaged, nothing is refused
    stream = jl(tmp_path / "blob.jsonl", exec_json_stream(extra=[
        {"type": "item.completed", "item": {"id": "b", "type": "command_execution", "command": "base64 -w0 img.png",
                                            "aggregated_output": blob.decode("ascii"), "exit_code": 0}}]))
    out = codex.package_codex(stream, codex_run["prompt"], tmp_path / "pkg_blob", home=codex_run["home"])
    assert (out / "trajectory.zip").exists()


def test_secret_scan_flags_a_standalone_key(codex_run, tmp_path):
    key = b"sk-" + b"proj-" + b"T3BlbkFJ" + b"a1B2c3D4e5F6g7H8i9J0kLmNoPqRsTuVwXyZ_-12"
    for context in (key, b"OPENAI_API_KEY=" + key, b"export OPENAI_API_KEY='" + key + b"'",
                    b"Authorization: Bearer " + key, b'{"api_key": "' + key + b'"}', b"line one\n" + key + b"\n",
                    json.dumps({"aggregated_output": "line one\r\n" + key.decode()}).encode(),   # escaped: ...\r\nsk-
                    b"sk-" + b"svcacct-" + b"Zz9" * 10, b"sk-" + b"Q" * 48):
        assert "openai_api_key_shape" in _secret_hits(context), context
    # a key next to (not inside) a long blob is still found
    import base64
    import random
    blob = base64.urlsafe_b64encode(random.Random(1).randbytes(3 * 1024 * 1024))
    assert "openai_api_key_shape" in _secret_hits(blob + b"\n" + key + b"\n" + blob)
    # and packaging refuses it
    stream = jl(tmp_path / "key.jsonl", exec_json_stream(extra=[
        {"type": "item.completed", "item": {"id": "k", "type": "command_execution", "command": "cat .env",
                                            "aggregated_output": "OPENAI_API_KEY=" + key.decode(), "exit_code": 0}}]))
    with pytest.raises(SystemExit, match="REFUSED: credential-shaped.*openai_api_key_shape"):
        codex.package_codex(stream, codex_run["prompt"], tmp_path / "pkg_key", home=codex_run["home"])


def test_cli_codex_package(codex_run, tmp_path, capsys):
    r = codex_run
    rc = cli_main(["codex-package", "--stream", str(r["stream"]), "--prompt", str(r["prompt"]), "--out",
                   str(tmp_path / "cli"), "--workspace", str(r["ws"]), "--codex-home", str(r["home"]),
                   "--prediction", f"T3:gata4={r['ws'] / 'out' / 'pred_T3_gata4.h5ad'}", "--harness", str(r["loop"]),
                   "--command-file", str(r["cmd"]), "--model", "gpt-test-model"])
    assert rc == 0 and (tmp_path / "cli" / "evidence_bundle.zip").exists()
    assert "OK" in capsys.readouterr().out
    rc = cli_main(["codex-package", "--stream", str(r["stream"]), "--prompt", str(r["prompt"]), "--out",
                   str(tmp_path / "cli")])
    assert rc == 2 and "REFUSED" in capsys.readouterr().out
