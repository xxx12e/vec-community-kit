"""vec_agent_evidence end to end with the stand-in agent (tests/fake_agent.py): lock -> launch -> postrun -> package.
Nothing here calls a real agent CLI or any API."""
from __future__ import annotations

import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

from vec_agent_evidence import common as C
from vec_agent_evidence import evidence, launch as launch_mod, lock as lock_mod, package as package_mod
from vec_agent_evidence.__main__ import main as cli_main

ROOT = Path(__file__).resolve().parents[1]
FAKE_AGENT = Path(__file__).resolve().parent / "fake_agent.py"
EXAMPLE_PROMPT = ROOT / "vec_agent_evidence" / "example_prompt.md"


def detach_links(runs_root: Path) -> None:
    """Remove workspace/data junctions / symlinks and make everything writable before pytest cleans up."""
    if not runs_root.exists():
        return
    for run in runs_root.iterdir():
        link = run / "workspace" / "data"
        if C.is_junction_or_link(link):
            try:
                os.rmdir(link)
            except OSError:
                try:
                    os.unlink(link)
                except OSError:
                    pass
    C.set_writable(runs_root)


@pytest.fixture
def runs_root(tmp_path):
    root = tmp_path / "runs"
    yield root
    detach_links(root)


def do_lock(tiny_data_root, runs_root, projects, hours=0.05, **kw):
    return lock_mod.lock("T3", None, EXAMPLE_PROMPT, "fake-model-1", hours, tiny_data_root, runs_root=runs_root,
                         projects_dir=projects, claude_exe=sys.executable, max_turns=5, **kw)


def fake_cmd(cfg, run):
    cmd = launch_mod.build_command(cfg, run)
    return [sys.executable, str(FAKE_AGENT)] + cmd[1:]


def test_lock_creates_all_files_and_hashes(tiny_data_root, runs_root, tmp_path):
    run, cfg = do_lock(tiny_data_root, runs_root, tmp_path / "projects", note="test note")
    for rel in ("config.lock.json", "config.lock.sha256", "initial_prompt.md", "prompts.manifest.json",
                "claude_settings.json", "harness_snapshot.zip", "LOCK_TIMESTAMP", "hooks/guard.py", "hooks/audit.py",
                "env/pip_freeze.txt", "env/platform.txt", "env/git_head.txt", "env/claude_version.txt",
                "env/claude_exe.sha256", "workspace/README_WORKSPACE.md", "workspace/DEADLINE.txt", "workspace/NOTES.md",
                "workspace/tools/finalize_submission.py", "workspace/tools/vec_submit_check/checker.py",
                "workspace/tools/vec_baselines/io.py", "workspace/tools/vec_local_score/local_score.py",
                "workspace/data/panels/index.json"):
        assert (run / rel).exists(), rel
    assert not (run / "system_prompt_appendix.md").exists()
    # hash chain
    blob = (run / "config.lock.json").read_bytes()
    assert C.sha256_bytes(blob) == (run / "config.lock.sha256").read_text(encoding="utf-8").strip()
    assert C.RUN_ID_RE.fullmatch(cfg["run_id"]) and cfg["run_id"].startswith(cfg["created_utc"][:4])
    ip = (run / "initial_prompt.md").read_bytes()
    assert C.sha256_bytes(ip) == cfg["prompts"]["initial_prompt_sha256"] and len(ip) == cfg["prompts"]["initial_prompt_bytes"]
    assert b"{{" not in ip and cfg["run_id"].encode() in ip and cfg["deadline_utc"].encode() in ip
    assert b"tiny_wt.h5ad" in ip and b"T3:gata4" in ip
    assert (run / "workspace" / "README_WORKSPACE.md").read_bytes() == ip
    assert C.sha256_file(run / "claude_settings.json") == cfg["prompts"]["claude_settings_sha256"]
    settings = C.read_json(run / "claude_settings.json")
    assert settings["hooks"]["PreToolUse"][0]["matcher"] == "Bash|Write|Edit|Read|Glob|Grep"
    assert (run / "hooks" / "guard.py").as_posix() in settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "WebFetch" in settings["permissions"]["deny"]
    assert not any("{{" in json.dumps(v) for v in settings.values())
    # frozen policy and data manifest
    assert cfg["tools"] == C.DEFAULT_TOOLS and cfg["permission_mode"] == "bypassPermissions" and cfg["model"] == "fake-model-1"
    assert cfg["boards"] == ["T3:gata4"] and cfg["note"] == "test note" and cfg["dry_run"] is False
    assert list(cfg["data_manifest"]) == ["raw/tiny_wt.h5ad"]
    assert cfg["data_manifest"]["raw/tiny_wt.h5ad"]["sha256"] == C.sha256_file(tiny_data_root / "raw" / "tiny_wt.h5ad")
    assert cfg["panels_dir"] == str(tiny_data_root / "panels")
    assert cfg["hooks"]["guard.py"] == C.sha256_file(ROOT / "vec_agent_evidence" / "hooks" / "guard.py")
    assert cfg["claude_exe_sha256"] == C.sha256_file(Path(sys.executable)) and cfg["claude_version"]
    # snapshot contents
    names = zipfile.ZipFile(run / "harness_snapshot.zip").namelist()
    for n in ("vec_agent_evidence/lock.py", "vec_agent_evidence/hooks/guard.py", "vec_submit_check/checker.py",
              "vec_baselines/io.py", "vec_local_score/local_score.py", "templates_used/example_prompt.md",
              "templates_used/example_settings.json"):
        assert n in names, n
    assert not any(n.endswith(".pyc") for n in names)
    assert C.sha256_file(run / "harness_snapshot.zip") == cfg["harness_snapshot_sha256"]
    # workspace: tools copy read-only, data access documented
    assert not os.access(run / "workspace" / "tools" / "finalize_submission.py", os.W_OK)
    assert cfg["workspace"]["data_access"]["kind"] in ("junction", "symlink", "fallback_copy_panels_only")
    # the suggested launch command pins everything from the lock
    cmd = launch_mod.build_command(cfg, run)
    assert cmd[1] == "-p" and cmd[cmd.index("--model") + 1] == "fake-model-1"
    assert cmd[cmd.index("--session-id") + 1] == cfg["session_id"] and "--append-system-prompt-file" not in cmd
    env = launch_mod.child_env(cfg, run)
    assert env["VEC_RUN_DIR"] == str(run) and env["PYTHONPATH"] == str(run / "workspace" / "tools")
    assert env["VEC_PANELS_DIR"] == cfg["panels_dir"] and env["PIP_NO_INDEX"] == "1"
    assert not any(k.startswith("CLAUDE") and k not in cfg["env_overrides"] for k in env)


def test_lock_rejects_bad_inputs(tiny_data_root, runs_root, tmp_path):
    with pytest.raises(SystemExit):
        lock_mod.lock("T1", ["T3:gata4"], EXAMPLE_PROMPT, "m", 1, tiny_data_root, runs_root=runs_root)
    with pytest.raises(SystemExit):
        lock_mod.lock("T3", None, tmp_path / "missing_prompt.md", "m", 1, tiny_data_root, runs_root=runs_root)
    bad = tmp_path / "bad_prompt.md"
    bad.write_text("hello {{NOT_A_PLACEHOLDER}}", encoding="utf-8")
    with pytest.raises(KeyError):
        lock_mod.lock("T3", None, bad, "m", 1, tiny_data_root, runs_root=runs_root)
    assert not list(runs_root.glob("*_T3_*")) or all(not (r / "config.lock.json").exists() for r in runs_root.glob("*_T3_*"))


def test_dry_run_end_to_end_and_package(tiny_data_root, runs_root, tmp_path):
    projects = tmp_path / "projects"
    run, cfg = do_lock(tiny_data_root, runs_root, projects)
    env = launch_mod.child_env(cfg, run)
    state = launch_mod.launch(run, cfg, fake_cmd(cfg, run), env, poll_seconds=0.5)
    assert state["init"]["model"] == "fake-model-1" and state["init_problems"] == [] and state["abort"] is None
    assert state["init_tool_extras"] == ["StructuredOutput"] and state["returncode"] == 0
    assert state["result"]["subtype"] == "success" and state["assistant_events"] == 1
    assert not (run / "RUNNING").exists() and (run / "launch_state.json").exists()
    lc = C.read_json(run / "launch_command.json")
    assert lc["argv"][1].endswith("fake_agent.py") and lc["env"]["VEC_SESSION_ID"] == cfg["session_id"]

    m = evidence.postrun(run, projects, state=state)
    assert m["lock_integrity"]["ok"], m["lock_integrity"]
    assert m["secret_scan"]["clean"], m["secret_scan"]
    assert m["result_subtype"] == "success" and m["is_error"] is False and m["abort"] is None and m["deadline_hit"] is False
    sub = m["submission"]
    assert sub["status"] == "ok", sub
    b = sub["boards"]["T3:gata4"]
    f = run / "submission" / "pred_T3_gata4.h5ad"
    assert f.exists() and b["sha256"] == C.sha256_file(f) == C.sha256_file(tiny_data_root / "raw" / "tiny_wt.h5ad")
    assert b["uploadable"] is True and b["relaxed_min_cells"] is False and b["format"]["ok"]
    assert b["agent_manifest_entries"][-1]["candidate"] == "c1" and b["agent_manifest_entries"][-1]["sha256"] == b["sha256"]
    assert b["writer_tool_uses"] and b["writer_tool_uses"][0]["tool"] == "Bash"
    # trajectory: transcript copied by session id (+ tool-results), audit log, guard denial of curl
    tr = list((run / "transcript").glob("*.jsonl"))
    assert len(tr) == 1 and tr[0].stem == cfg["session_id"] and (run / "transcript" / "tool-results").is_dir()
    audit_lines = [json.loads(x) for x in (run / "hooks" / "tool_audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(x["event"] == "PostToolUse" and x["tool_name"] == "Bash" for x in audit_lines)
    denials = [json.loads(x) for x in (run / "hooks" / "guard_denials.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any("curl" in d["tool_input"] for d in denials)
    assert m["permission_denials"] and "curl" in m["permission_denials"][0]["tool_input"]["command"]
    # evidence hashes present and correct; scratch and the manifest itself excluded
    ev = m["evidence"]
    for rel in ("config.lock.json", "initial_prompt.md", "claude_settings.json", "harness_snapshot.zip", "stream.jsonl",
                "hooks/tool_audit.jsonl", "hooks/guard_denials.jsonl", "submission/MANIFEST.json",
                "submission/pred_T3_gata4.h5ad", "launch_command.json", "launch_state.json", f"transcript/{cfg['session_id']}.jsonl"):
        assert rel in ev, rel
        assert ev[rel]["sha256"] == C.sha256_file(run / rel) and ev[rel]["bytes"] == (run / rel).stat().st_size
    assert not any(rel.startswith("workspace/scratch") or rel.startswith("workspace/data") for rel in ev)
    assert "run_manifest.json" not in ev and m["upload_set_bytes"] > 0 and m["sizes"]["files_over_per_file_limit"] == []
    assert (run / "artifacts" / "NOTES.md").exists() and (run / "artifacts" / "candidates" / "c1" / "notes.md").exists()
    stream = [json.loads(x) for x in (run / "stream.jsonl").read_text(encoding="utf-8").splitlines()]
    assert stream[0]["type"] == "system" and stream[-1]["type"] == "result" and m["stream_events"] == len(stream)
    assert not os.access(run / "config.lock.json", os.W_OK) and not os.access(run / "run_manifest.json", os.W_OK)
    with pytest.raises(SystemExit):
        evidence.postrun(run, projects)                    # not repeatable

    # upload package
    out = package_mod.package(run, tmp_path / "upload")
    assert (out / "predictions" / "pred_T3_gata4.h5ad").exists()
    assert C.sha256_file(out / "predictions" / "pred_T3_gata4.h5ad") == b["sha256"]
    for z in ("trajectory.zip", "prompts.zip", "harness.zip", "evidence_bundle.zip"):
        assert (out / z).exists(), z
    traj = zipfile.ZipFile(out / "trajectory.zip").namelist()
    assert f"transcript/{cfg['session_id']}.jsonl" in traj and "stream.jsonl" in traj and "hooks/tool_audit.jsonl" in traj
    prompts = zipfile.ZipFile(out / "prompts.zip").namelist()
    assert prompts == ["initial_prompt.md", "prompts.manifest.json"]
    harness = zipfile.ZipFile(out / "harness.zip").namelist()
    assert "harness_snapshot.zip" in harness and "config.lock.json" in harness and "claude_settings.json" in harness
    assert "run_manifest.json" in harness and "submission/MANIFEST.json" in harness
    assert not any(n.startswith("workspace/") or n.endswith(".h5ad") for n in zipfile.ZipFile(out / "evidence_bundle.zip").namelist())
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "pred_T3_gata4.h5ad" in readme and b["sha256"] in readme and "trajectory.zip" in readme
    # a tampered prediction is refused
    (out.parent / "tamper").mkdir()
    C.set_writable(run)
    with open(f, "ab") as fh:
        fh.write(b"x")
    with pytest.raises(SystemExit, match="REFUSED"):
        package_mod.package(run, tmp_path / "upload2")


def test_relaxed_dry_run_is_never_packaged(tiny_data_root, runs_root, tmp_path, heart_panel):
    """A dry run finalizing a file below min_cells is recorded but package() refuses to upload it."""
    from conftest import make_adata
    small_root = tmp_path / "small_data"
    (small_root / "raw").mkdir(parents=True)
    make_adata(heart_panel, 60, seed=3).write_h5ad(small_root / "raw" / "tiny_wt.h5ad")
    projects = tmp_path / "projects"
    run, cfg = lock_mod.lock("T3", None, EXAMPLE_PROMPT, "fake-model-1", 0.05, small_root, runs_root=runs_root,
                             projects_dir=projects, claude_exe=sys.executable, dry_run=True)
    assert cfg["env_overrides"]["VEC_ALLOW_RELAX"] == "1" and cfg["panels_dir"].endswith("panels")
    env = launch_mod.child_env(cfg, run)
    state = launch_mod.launch(run, cfg, fake_cmd(cfg, run), env, poll_seconds=0.5)
    m = evidence.postrun(run, projects, state=state)
    b = m["submission"]["boards"]["T3:gata4"]
    assert m["submission"]["status"] == "ok" and b["relaxed_min_cells"] is True and b["uploadable"] is False
    with pytest.raises(SystemExit, match="not uploadable"):
        package_mod.package(run, tmp_path / "upload")


def test_init_mismatch_voids_the_run(tiny_data_root, runs_root, tmp_path):
    projects = tmp_path / "projects"
    run, cfg = do_lock(tiny_data_root, runs_root, projects, grace_minutes=0.05)
    env = launch_mod.child_env(cfg, run)
    env["VEC_FAKE_MODE"] = "model_mismatch"
    state = launch_mod.launch(run, cfg, fake_cmd(cfg, run), env, poll_seconds=0.5)
    assert state["abort"] and "init mismatch" in state["abort"] and state["init_problems"]
    assert state["kill"] is not None
    m = evidence.postrun(run, projects, state=state)
    assert m["abort"] and m["submission"]["status"] == "no_submission"
    with pytest.raises(SystemExit, match="REFUSED"):
        package_mod.package(run, tmp_path / "upload")


def test_deadline_kill(tiny_data_root, runs_root, tmp_path):
    projects = tmp_path / "projects"
    run, cfg = do_lock(tiny_data_root, runs_root, projects, hours=0.0006, grace_minutes=0.05)
    env = launch_mod.child_env(cfg, run)
    env["VEC_FAKE_MODE"] = "hang"
    state = launch_mod.launch(run, cfg, fake_cmd(cfg, run), env, poll_seconds=0.5)
    assert state["deadline_hit"] is True and state["returncode"] not in (None, 0)
    assert state["init"] is not None and state["result"] is None
    m = evidence.postrun(run, projects, state=state)
    assert m["deadline_hit"] is True and m["submission"]["status"] == "no_submission"


def test_secret_scan_precision(tmp_path):
    run = tmp_path / "run"
    (run / "artifacts").mkdir(parents=True)
    # a scanner that merely lists the marker words is NOT a hit
    (run / "artifacts" / "scanner.py").write_text(
        "MARKERS = (\"sk-\" + \"ant-\", '\"access' + 'Token\"', '\"refresh' + 'Token\"', \"claudeAi\" + \"Oauth\")\n", encoding="utf-8")
    leak = {"claudeAi" + "Oauth": {"access" + "Token": "x", "refresh" + "Token": "y"}, "k": "sk-" + "ant-api03-ABCDEFGHIJKLMNOP"}
    (run / "artifacts" / "leak.json").write_text(json.dumps(leak) + "\n", encoding="utf-8")
    (run / "artifacts" / "keyleak.txt").write_text("token=zai-test-1234567890abcdef\n", encoding="utf-8")
    (run / "artifacts" / "model.h5ad").write_bytes(b"sk-" + b"ant-not-scanned-binary-suffix-0123456789")
    rep = evidence.secret_scan(run, extra_values=["zai-test-1234567890abcdef", ""])
    by_file = {h["file"]: h["patterns"] for h in rep["hits"]}
    assert "artifacts/scanner.py" not in by_file and "artifacts/model.h5ad" not in by_file
    assert set(by_file["artifacts/leak.json"]) == {"anthropic_api_key_shape", "oauth_access_token_field",
                                                  "oauth_refresh_token_field", "oauth_credentials_block"}
    assert by_file["artifacts/keyleak.txt"] == ["extra_value_0"]
    assert rep["clean"] is False and "zai-test" not in json.dumps(rep["patterns"])
    # the kit's own source never trips the scan
    kit_rep = evidence.secret_scan(ROOT / "vec_agent_evidence")
    assert kit_rep["clean"], kit_rep


def test_cli_lock_subcommand(tiny_data_root, runs_root, tmp_path, capsys):
    rc = cli_main(["lock", "--task", "T2", "--boards", "T2:heart:val_interp", "--prompt", str(EXAMPLE_PROMPT), "--model", "m-1",
                   "--data-root", str(tiny_data_root), "--runs-root", str(runs_root), "--hours", "2", "--claude-exe", sys.executable])
    assert rc == 0
    captured = capsys.readouterr().out                 # a log line precedes the JSON block
    out = json.loads(captured[captured.index("{"):])
    assert C.RUN_ID_RE.fullmatch(out["run_id"]) and "_T2_" in out["run_id"]
    assert out["launch_command"][cli_index(out["launch_command"], "--model") + 1] == "m-1"
    cfg = C.read_json(Path(out["run_dir"]) / "config.lock.json")
    assert cfg["boards"] == ["T2:heart:val_interp"] and cfg["wall_clock_hours"] == 2.0
    with pytest.raises(SystemExit):
        cli_main(["lock", "--task", "T2", "--boards", "T3:gata4", "--prompt", str(EXAMPLE_PROMPT), "--model", "m-1",
                  "--data-root", str(tiny_data_root), "--runs-root", str(runs_root)])


def cli_index(argv, flag):
    return argv.index(flag)
