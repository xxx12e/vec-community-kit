"""Configuration lock: freeze everything a run depends on BEFORE the agent process exists.

The Agent-track rule is autonomy after the "configuration lock", the moment a run starts. This module writes a
run directory runs/<YYYYMMDD-HHMM>_<task>_<8hex>/ holding

  config.lock.json (+ .sha256)  run id, session UUID, model / effort / turn / wall-clock limits, tool policy, seed,
                                child environment, sha256 of every data file the agent may read, sha256 of the
                                prompt / appendix / settings bytes, hook hashes, snapshot hash, CLI version + sha256
  initial_prompt.md             the initial prompt, rendered byte-exact from the template (placeholders filled)
  system_prompt_appendix.md     optional --append-system-prompt-file content
  claude_settings.json          the settings file that wires the hooks and the deny rules
  prompts.manifest.json         hashes and sizes of the three files above
  hooks/guard.py, hooks/audit.py  run-local copies (editing the kit mid-run cannot change a running run)
  harness_snapshot.zip          the kit code that produced the run + the templates used
  workspace/                    what the agent sees: read-only tools/, data link, README_WORKSPACE.md, DEADLINE.txt
  env/                          pip freeze, platform, git head of the kit
  LOCK_TIMESTAMP

run_manifest.json (written by evidence.postrun) re-verifies every hash after the run.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path

from vec_submit_check import checker as vcheck

from . import common as C

PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


# ------------------------------------------------------------------------------------------ rendering
def render(text: str, values: dict, name: str = "template") -> str:
    def sub(m):
        key = m.group(1)
        if key not in values:
            raise KeyError(f"{name}: no value for placeholder {{{{{key}}}}}; known: {sorted(values)}")
        return str(values[key])

    out = PLACEHOLDER.sub(sub, text)
    left = PLACEHOLDER.findall(out)
    if left:
        raise ValueError(f"{name}: unrendered placeholders {left}")
    return out


def board_table(index: dict, boards) -> str:
    rows = ["| board | genes | genes file | cells min-max | coords | floor model |", "|---|---|---|---|---|---|"]
    for b in boards:
        s = index[b]
        rows.append(f"| {b} | {s['n_genes']} | panels/{s['genes_file']} | {s['min_cells']}-{s['max_cells']} | "
                    f"{'yes: obsm[spatial_3D]' if s['needs_coords'] else 'no'} | {s['floor_model']} |")
    return "\n".join(rows)


def data_table(manifest: dict) -> str:
    if not manifest:
        return "(no data files found under the data root; the lock recorded an empty manifest)"
    rows = ["| file (under data/) | MB | sha256 (first 16) |", "|---|---|---|"]
    for rel, v in manifest.items():
        rows.append(f"| {rel} | {v['bytes'] / 1e6:.1f} | {v['sha256'][:16]} |")
    return "\n".join(rows)


def template_values(cfg: dict, run: Path, index: dict) -> dict:
    ws = run / "workspace"
    try:
        from vec_local_score.veckit_loader import veckit_dir
        vk = veckit_dir()
        veckit_posix = C.posix(vk) if vk else "(veckit not found: install it or set VECKIT_PATH)"
    except ImportError:
        veckit_posix = "(veckit not found)"
    return {
        "RUN_ID": cfg["run_id"], "SESSION_ID": cfg["session_id"], "TASK": cfg["task"],
        "BOARDS": ", ".join(cfg["boards"]), "PRIMARY_BOARD": cfg["boards"][0],
        "BOARDS_BULLETS": "\n".join(f"- `{b}`" for b in cfg["boards"]),
        "MODEL": cfg["model"], "EFFORT": cfg.get("effort") or "default", "MAX_TURNS": cfg["max_turns"],
        "WALL_CLOCK_HOURS": cfg["wall_clock_hours"], "DEADLINE_UTC": cfg["deadline_utc"],
        "CREATED_UTC": cfg["created_utc"], "SEED": cfg["seed"],
        "TOOLS": ", ".join(cfg["tools"]), "PERMISSION_MODE": cfg["permission_mode"],
        "RUN_DIR": str(run), "RUN_DIR_POSIX": C.posix(run), "RUNS_ROOT_POSIX": C.posix(cfg["runs_root"]),
        "WORKSPACE": str(ws), "WORKSPACE_POSIX": C.posix(ws),
        "DATA_DIR_POSIX": C.posix(cfg["data_root"]), "PANELS_DIR_POSIX": C.posix(cfg["panels_dir"]),
        "KIT_ROOT_POSIX": C.posix(C.KIT_ROOT), "PYTHON": str(C.PY), "PYTHON_POSIX": C.posix(C.PY),
        "VECKIT_DIR_POSIX": veckit_posix,
        "GUARD_POSIX": C.posix(run / "hooks" / "guard.py"), "AUDIT_POSIX": C.posix(run / "hooks" / "audit.py"),
        "HOME_CLAUDE_POSIX": C.posix(Path.home() / ".claude"),
        "BOARD_CONTRACT_TABLE": board_table(index, cfg["boards"]),
        "DATA_FILES_TABLE": data_table(cfg["data_manifest"]),
        "CLI_VERSION": cfg["claude_version"],
    }


# ------------------------------------------------------------------------------------------ git / data / cli
def git_state(root: Path):
    rc, out, err = C.run_cmd(["git", "-C", root, "rev-parse", "HEAD"])
    commit = out.strip() if rc == 0 else f"unavailable ({(err or out).strip()[:120]})"
    rc2, out2, _ = C.run_cmd(["git", "-C", root, "status", "--porcelain"])
    porcelain = out2 if rc2 == 0 else ""
    return commit, bool(porcelain.strip()), porcelain


def data_manifest(data_root: Path, patterns=("**/*.h5ad",)) -> dict:
    """sha256 + bytes of every data file the agent may read (default: every .h5ad under the data root)."""
    data_root = Path(data_root)
    files = set()
    for g in patterns:
        files.update(p for p in data_root.glob(g) if p.is_file())
    return {p.relative_to(data_root).as_posix(): {"bytes": p.stat().st_size, "sha256": C.sha256_file(p)}
            for p in sorted(files)}


def claude_info(exe) -> dict:
    """Pin the agent CLI binary: path, version string, sha256. Records the absence instead of failing."""
    if not exe:
        found = shutil.which("claude")
        exe = found or "claude"
    p = Path(exe)
    if p.exists():
        rc, out, err = C.run_cmd([p, "--version"], timeout=120)
        return {"claude_exe": str(p.resolve()), "claude_exe_sha256": C.sha256_file(p),
                "claude_version": out.strip() if rc == 0 else f"version check failed: {(err or out).strip()[:200]}"}
    return {"claude_exe": str(exe), "claude_exe_sha256": "missing", "claude_version": "missing (binary not found at lock time)"}


# ------------------------------------------------------------------------------------------ workspace
def make_data_link(link: Path, target: Path) -> dict:
    """workspace/data -> data root. Junction on Windows (no admin needed), symlink elsewhere; falls back to copying
    only the panels so the tools keep working, and documents which route was taken."""
    note = {"link": str(link), "target": str(target)}
    try:
        if os.name == "nt":
            import _winapi  # CPython internal, present on Windows builds
            _winapi.CreateJunction(str(target), str(link))
            note.update(kind="junction", how="_winapi.CreateJunction")
        else:
            os.symlink(str(target), str(link), target_is_directory=True)
            note.update(kind="symlink", how="os.symlink")
        if link.exists():
            return note
    except Exception as e:  # noqa: BLE001 - any failure falls through to the documented fallback
        note["link_error"] = repr(e)
    link.mkdir(parents=True, exist_ok=True)
    src_panels = target / "panels"
    if src_panels.is_dir():
        shutil.copytree(src_panels, link / "panels", dirs_exist_ok=True)
    note.update(kind="fallback_copy_panels_only",
                how="link creation failed; copied panels only, raw data NOT available inside the workspace")
    return note


def make_workspace(run: Path, cfg: dict, prompt_text: str) -> dict:
    ws = run / "workspace"
    for d in ("src", "scratch", "out/candidates"):
        (ws / d).mkdir(parents=True, exist_ok=True)
    tools = ws / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    for pkg in C.TOOL_PACKAGES:
        shutil.copytree(C.KIT_ROOT / pkg, tools / pkg, ignore=ignore)
    shutil.copy2(C.PKG_DIR / "finalize_submission.py", tools / "finalize_submission.py")
    n_ro = C.set_read_only(tools)
    C.write_text(ws / "README_WORKSPACE.md", prompt_text)
    C.write_text(ws / "DEADLINE.txt", cfg["deadline_utc"] + "\n")
    C.write_text(ws / "NOTES.md", f"# NOTES for run {cfg['run_id']}\n\n(agent-maintained; keep it current)\n")
    for f in ("README_WORKSPACE.md", "DEADLINE.txt"):
        os.chmod(ws / f, 0o444)
    data_note = make_data_link(ws / "data", Path(cfg["data_root"]))
    return {"tools_files_read_only": n_ro, "data_access": data_note}


def snapshot_code(run: Path, extra_files: dict) -> Path:
    """Zip the kit packages that produced this run plus the template files used (prompt, settings, appendix)."""
    zpath = run / "harness_snapshot.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for top in ("vec_agent_evidence",) + C.TOOL_PACKAGES:
            for f in sorted((C.KIT_ROOT / top).rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                    z.write(f, f.relative_to(C.KIT_ROOT).as_posix())
        for arcname, path in extra_files.items():
            if path and Path(path).exists():
                z.write(path, f"templates_used/{arcname}")
    return zpath


def record_env(run: Path, cfg: dict) -> None:
    env_dir = run / "env"
    rc, out, err = C.run_cmd([C.PY, "-m", "pip", "freeze"], timeout=300)
    C.write_text(env_dir / "pip_freeze.txt", out if rc == 0 else f"pip freeze failed (rc={rc}): {err}\n")
    C.write_text(env_dir / "platform.txt", json.dumps(platform.uname()._asdict()) + "\n" + platform.python_version() + "\n")
    C.write_text(env_dir / "git_head.txt", cfg["kit_git_commit"] + "\n" + cfg["kit_git_porcelain"])
    C.write_text(env_dir / "claude_version.txt", cfg["claude_version"] + "\n")
    C.write_text(env_dir / "claude_exe.sha256", f"{cfg['claude_exe_sha256']}  {cfg['claude_exe']}\n")


# ------------------------------------------------------------------------------------------ lock
def lock(task: str, boards, prompt, model: str, hours: float, data_root, runs_root=None, settings=None,
         appendix=None, max_turns: int = 400, effort=None, tools=None, disallowed_tools=None, seed: int = 0,
         claude_exe=None, projects_dir=None, permission_mode: str = C.PERMISSION_MODE, max_budget_usd=None,
         grace_minutes: float = 10.0, stall_hours: float = 3.0, data_globs=("**/*.h5ad",), dry_run: bool = False,
         note: str = ""):
    """Create and freeze a run directory. Returns (run_dir, cfg). Nothing is launched."""
    if task not in C.TASK_BOARDS:
        raise SystemExit(f"task must be one of {sorted(C.TASK_BOARDS)}")
    boards = [b.strip() for b in (boards or C.TASK_BOARDS[task]) if b.strip()]
    bad = [b for b in boards if b not in C.TASK_BOARDS[task]]
    if bad:
        raise SystemExit(f"boards {bad} do not belong to task {task}; valid: {C.TASK_BOARDS[task]}")
    prompt = Path(prompt)
    settings = Path(settings) if settings else C.DEFAULT_SETTINGS_TEMPLATE
    appendix = Path(appendix) if appendix else None
    for p in (prompt, settings) + ((appendix,) if appendix else ()):
        if not p.exists():
            raise SystemExit(f"template not found: {p}")
    data_root = Path(data_root).resolve()
    if not data_root.is_dir():
        raise SystemExit(f"data root not found: {data_root}")
    panels_dir = data_root / "panels" if (data_root / "panels" / "index.json").exists() else vcheck.panels_dir()
    index = vcheck.load_index(panels_dir)
    runs_root = Path(runs_root).resolve() if runs_root else C.DEFAULT_RUNS_ROOT
    runs_root.mkdir(parents=True, exist_ok=True)

    commit, dirty, porcelain = git_state(C.KIT_ROOT)
    cli = claude_info(claude_exe)
    created = C.now_utc()
    run_id = f"{created:%Y%m%d-%H%M}_{task}_{uuid.uuid4().hex[:8]}"
    run = runs_root / run_id
    run.mkdir(parents=True, exist_ok=False)
    for d in ("env", "hooks", "transcript", "artifacts", "submission", "workspace"):
        (run / d).mkdir(parents=True, exist_ok=True)
    session_id = str(uuid.uuid4())
    deadline = created + timedelta(hours=float(hours))

    env_overrides = dict(C.ENV_OVERRIDES)
    if dry_run:
        env_overrides["VEC_ALLOW_RELAX"] = "1"      # lets a dry run finalize a tiny sample file
    cfg = {
        "run_id": run_id, "session_id": session_id, "task": task, "boards": boards,
        "model": model, "effort": effort, "max_turns": int(max_turns), "max_budget_usd": max_budget_usd,
        "wall_clock_hours": float(hours), "deadline_utc": C.iso(deadline), "grace_minutes": float(grace_minutes),
        "stall_hours": float(stall_hours),
        "tools": list(tools or C.DEFAULT_TOOLS), "disallowed_tools": list(disallowed_tools or C.DEFAULT_DISALLOWED_TOOLS),
        "permission_mode": permission_mode, "seed": int(seed), "env_overrides": env_overrides,
        "python": str(C.PY), "kit_git_commit": commit, "kit_git_dirty": dirty, "kit_git_porcelain": porcelain,
        "data_root": str(data_root), "panels_dir": str(panels_dir), "data_globs": list(data_globs),
        "data_manifest": data_manifest(data_root, data_globs),
        "panels_index_sha256": C.sha256_file(Path(panels_dir) / "index.json"),
        "prompt_template": str(prompt), "settings_template": str(settings),
        "appendix_template": str(appendix) if appendix else None,
        "created_utc": C.iso(created), "dry_run": bool(dry_run), "runs_root": str(runs_root),
        "claude_projects_dir": str(Path(projects_dir).resolve()) if projects_dir else None,
        "note": note,
    }
    cfg.update(cli)

    values = template_values(cfg, run, index)
    prompt_text = render(prompt.read_text(encoding="utf-8"), values, prompt.name)
    ip = prompt_text.encode("utf-8")
    settings_obj = json.loads(render(settings.read_text(encoding="utf-8"), values, settings.name))
    st = (json.dumps(settings_obj, indent=2) + "\n").encode("utf-8")
    (run / "initial_prompt.md").write_bytes(ip)
    (run / "claude_settings.json").write_bytes(st)
    cfg["prompts"] = {"initial_prompt_sha256": C.sha256_bytes(ip), "initial_prompt_bytes": len(ip),
                      "claude_settings_sha256": C.sha256_bytes(st),
                      "base_system_prompt": f"agent CLI {cfg['claude_version']} default system prompt (reproducible from "
                                            "the pinned binary sha256)",
                      "prompt_delivery": "initial_prompt.md fed byte-exact on stdin"}
    if appendix:
        sp = render(appendix.read_text(encoding="utf-8"), values, appendix.name).encode("utf-8")
        (run / "system_prompt_appendix.md").write_bytes(sp)
        cfg["prompts"]["system_prompt_appendix_sha256"] = C.sha256_bytes(sp)
        cfg["prompts"]["system_prompt_appendix_bytes"] = len(sp)
        cfg["prompts"]["prompt_delivery"] += "; appendix via --append-system-prompt-file"
    C.write_json(run / "prompts.manifest.json", cfg["prompts"])

    hooks = {}
    for name in ("guard.py", "audit.py"):
        shutil.copy2(C.PKG_DIR / "hooks" / name, run / "hooks" / name)
        hooks[name] = C.sha256_file(run / "hooks" / name)
    cfg["hooks"] = hooks
    zpath = snapshot_code(run, {prompt.name: prompt, settings.name: settings,
                                (appendix.name if appendix else "no_appendix"): appendix})
    cfg["harness_snapshot_sha256"] = C.sha256_file(zpath)
    cfg["workspace"] = make_workspace(run, cfg, prompt_text)
    record_env(run, cfg)

    blob = (json.dumps(cfg, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (run / "config.lock.json").write_bytes(blob)
    C.write_text(run / "config.lock.sha256", C.sha256_bytes(blob) + "\n")
    C.write_text(run / "LOCK_TIMESTAMP", C.iso(C.now_utc()) + "\n")
    C.log(f"locked {run_id}: model={model} boards={boards} deadline={cfg['deadline_utc']} "
          f"data_files={len(cfg['data_manifest'])} dirty={dirty} dry_run={dry_run}")
    return run, cfg
