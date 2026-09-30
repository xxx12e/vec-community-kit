"""OpenCode adapter: lock the OpenCode configuration before a headless `opencode run --format json` run, then package
the finished run as the three Agent-track evidence kinds (trajectory, prompts, harness), plus byte-identical,
format-checked prediction copies.

STATUS: CHECKED AGAINST THE OPENCODE SOURCE ONLY, UNTESTED AGAINST A LIVE OPENCODE RUN. Everything below was read
from the public source of OpenCode (github.com/anomalyco/opencode, formerly sst/opencode; tag v1.18.33, commit
51ef4be1d3c122f18fefb510dca8d778571f4f18, read 2026-09-30) and is tested only on synthetic files laid out like that
source describes (tests/test_opencode_adapter.py). No OpenCode binary and no OpenCode login were used.

What the source says (file names relative to packages/ in that commit):

  * `opencode run [message..] --format json` (opencode/src/cli/cmd/run.ts) prints one JSON object per line on
    stdout: {"type", "timestamp" (ms), "sessionID", ...} with type step_start / step_finish / text / reasoning /
    tool_use ({"part": ...}) or error ({"error": ...}). A message piped on stdin is used as the prompt. Without
    --auto, a permission that resolves to "ask" is rejected automatically (the run never waits for a human).
    The stream carries no user message and no model string: those live in the stored session.
  * Sessions are stored in SQLite since v1.2.0: <data>/opencode.db (core/src/database/database.ts; another
    install channel uses opencode-<channel>.db; OPENCODE_DB overrides it), tables session / message / part / todo
    (core/src/session/sql.ts). The SAME database holds the tables account and control_account (access and refresh
    tokens) and credential (core/src/account/sql.ts, core/src/credential/sql.ts). This adapter therefore never
    copies the database file: it opens it read-only and selects the rows of the run's session (and its child
    sessions) from the four session tables only, and writes them in the shape of `opencode export <sessionID>`
    (opencode/src/cli/cmd/export.ts: {"info", "messages": [{"info", "parts"}]}). Up to v1.1.x sessions were JSON
    files: <data>/storage/session/<projectID>/<sessionID>.json, storage/message/<sessionID>/<messageID>.json,
    storage/part/<messageID>/<partID>.json (opencode/src/storage/storage.ts); those are byte-copied when found.
    Best of all, run `opencode export <sessionID> > session_export.json` yourself and pass it with --export.
  * <data> is $XDG_DATA_HOME/opencode, by default ~/.local/share/opencode on every platform (core/src/global.ts;
    `opencode db path` prints the database path). Credentials: <data>/auth.json (opencode/src/auth/index.ts),
    <data>/mcp-auth.json (opencode/src/mcp/auth.ts), the database tables above, and the OPENCODE_AUTH_CONTENT
    environment variable. None of them is ever collected (see "Credential files" below).
  * Configuration (opencode/src/config/config.ts, config/paths.ts): $XDG_CONFIG_HOME/opencode (default
    ~/.config/opencode) with config.json / opencode.json / opencode.jsonc, the file named by OPENCODE_CONFIG,
    opencode.json / opencode.jsonc found from the working directory upwards, .opencode/ directories (agents,
    commands, modes, plugins, skills), OPENCODE_CONFIG_DIR, OPENCODE_CONFIG_CONTENT and OPENCODE_PERMISSION. The
    "permission" block maps tools (read, edit, glob, grep, list, bash, task, external_directory, webfetch,
    websearch, ...) to allow / ask / deny, optionally per pattern; the last matching rule wins
    (opencode/src/permission/index.ts). "share": "disabled" stops sessions from being shared.
  * Instruction files (opencode/src/session/instruction.ts): AGENTS.md, CLAUDE.md, CONTEXT.md found from the
    working directory upwards (the first name that exists wins), <config>/AGENTS.md, and ~/.claude/CLAUDE.md unless
    OPENCODE_DISABLE_CLAUDE_CODE(_PROMPT) is set; AGENTS.md files next to files the agent reads are attached too.

Sub-commands (python -m vec_agent_evidence ...):
  opencode-lock     BEFORE the run: snapshot prompt, config and permission files, instruction files, the
                    OPENCODE_* environment and the CLI version; write opencode.lock.json + .sha256 and print the
                    exact command to run. Refuses on a credential-shaped string or a credential file.
  opencode-package  AFTER the run: stream + session (export file, database rows or legacy JSON files) + prompts +
                    config snapshot + lock -> trajectory.zip / prompts.zip / harness.zip / evidence_bundle.zip.

What this adapter does NOT do (the Claude Code path of this package does): launch the agent, enforce a wall clock,
or hook tool calls. OpenCode's own permission rules are the enforcement layer; see example_opencode.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import uuid
from collections import Counter
from pathlib import Path

from . import codex as X
from . import common as C

ADAPTER = "vec_agent_evidence.opencode (checked against the OpenCode source only; untested against a live OpenCode run)"
SOURCE_CHECKED = {"repository": "github.com/anomalyco/opencode (formerly sst/opencode)", "tag": "v1.18.33",
                  "commit": "51ef4be1d3c122f18fefb510dca8d778571f4f18", "read": "2026-09-30"}
PER_FILE_LIMIT = X.PER_FILE_LIMIT
STREAM_TYPES = ("step_start", "step_finish", "text", "reasoning", "tool_use", "error")
INSTRUCTION_NAMES = ("AGENTS.md", "CLAUDE.md", "CONTEXT.md")
PROJECT_CONFIG_NAMES = ("opencode.json", "opencode.jsonc")
GLOBAL_CONFIG_NAMES = ("config.json", "opencode.json", "opencode.jsonc")
CONFIG_SUBDIRS = ("agent", "agents", "command", "commands", "mode", "modes", "plugin", "plugins", "skill", "skills",
                  "tool", "tools")
CONFIG_SUFFIXES = (".md", ".json", ".jsonc", ".ts", ".js", ".mjs", ".txt")
CONFIG_SKIP_DIRS = {"node_modules", ".git", "__pycache__"}
CONFIG_FILE_LIMIT = 1024 * 1024
ANCESTOR_LEVELS = 8
# the only tables of opencode.db that are ever read; account / control_account / credential hold tokens
SESSION_TABLES = ("session", "message", "part", "todo")
SESSION_JSON_COLUMNS = ("summary_diffs", "metadata", "revert", "permission", "model")
SQLITE_MAGIC = b"SQLite format 3\x00"
# OpenCode's own credential stores, on top of the generic credential names of the Codex adapter (auth.json, .env, ...)
OPENCODE_CREDENTIAL_RE = re.compile(r"(?i)^(?:mcp-auth\.json(?:\..*)?|.*\.(?:db|sqlite|sqlite3)(?:-wal|-shm|-journal)?)$")
ENV_RECORDED = ("OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG_CONTENT", "OPENCODE_PERMISSION",
                "OPENCODE_DISABLE_PROJECT_CONFIG", "OPENCODE_DISABLE_CLAUDE_CODE", "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT",
                "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS", "OPENCODE_DISABLE_AUTOUPDATE", "OPENCODE_DISABLE_MODELS_FETCH",
                "OPENCODE_DISABLE_LSP_DOWNLOAD", "OPENCODE_DISABLE_DEFAULT_PLUGINS", "OPENCODE_DISABLE_EXTERNAL_SKILLS",
                "OPENCODE_DISABLE_AUTOCOMPACT", "OPENCODE_PURE", "OPENCODE_AUTO_SHARE", "OPENCODE_DB",
                "OPENCODE_ENABLE_EXA", "OPENCODE_EXPERIMENTAL", "XDG_DATA_HOME", "XDG_CONFIG_HOME")
ENV_NEVER_RECORDED = ("OPENCODE_AUTH_CONTENT", "OPENCODE_SERVER_PASSWORD", "OPENCODE_CONSOLE_TOKEN")
# suggested for an unattended run: no self-update, no ~/.claude/CLAUDE.md or Claude skills pulled in, no LSP downloads
RECOMMENDED_ENV = {"OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_CLAUDE_CODE": "1",
                   "OPENCODE_DISABLE_LSP_DOWNLOAD": "1"}
EDIT_TOOLS = ("write", "edit", "apply_patch", "patch", "multiedit")


# ------------------------------------------------------------------------------------------ locations
def home_dir() -> Path:
    """The user's home directory (a function so that tests can point it at a scratch directory)."""
    return Path.home()


def data_dir(explicit=None, env=None) -> Path:
    env = os.environ if env is None else env
    if explicit:
        return Path(explicit)
    base = env.get("XDG_DATA_HOME") or str(home_dir() / ".local" / "share")
    return Path(base) / "opencode"


def config_dir(explicit=None, env=None) -> Path:
    env = os.environ if env is None else env
    if explicit:
        return Path(explicit)
    base = env.get("XDG_CONFIG_HOME") or str(home_dir() / ".config")
    return Path(base) / "opencode"


def db_candidates(ddir, env=None) -> list:
    """The database file(s) OpenCode may have written this session to (opencode.db, opencode-<channel>.db, or
    OPENCODE_DB); only existing files are returned."""
    env = os.environ if env is None else env
    ddir = Path(ddir)
    override = env.get("OPENCODE_DB")
    if override:
        if override == ":memory:":
            return []
        p = Path(override) if Path(override).is_absolute() else ddir / override
        return [p] if p.is_file() else []
    out = [ddir / "opencode.db"] + sorted(ddir.glob("opencode-*.db"))
    return [p for p in out if p.is_file()]


def build_command(model, workspace, agent=None, variant=None, title=None, auto=False, exe="opencode") -> list:
    """The headless command: the prompt comes on stdin, the JSON event stream goes to stdout."""
    cmd = [str(exe or "opencode"), "run", "--format", "json", "--model", str(model), "--dir", str(workspace)]
    if agent:
        cmd += ["--agent", str(agent)]
    if variant:
        cmd += ["--variant", str(variant)]
    if title:
        cmd += ["--title", str(title)]
    if auto:
        cmd.append("--auto")
    return cmd


def command_line(cmd: list) -> str:
    def q(a):
        return a if re.fullmatch(r"[A-Za-z0-9_./:=@+,-]+", a) else '"' + a.replace('"', '\\"') + '"'
    return " ".join(q(str(a)) for a in cmd)


def cli_info(exe=None) -> dict:
    """Path, sha256 and `--version` of the OpenCode binary, best effort (None when it is not installed)."""
    path = shutil.which(exe or "opencode") if not (exe and Path(exe).is_file()) else str(exe)
    info = {"path": path, "sha256": None, "version": None}
    if not path:
        return info
    try:
        info["sha256"] = C.sha256_file(path)
    except OSError:
        pass
    rc, out, err = C.run_cmd([path, "--version"], timeout=60)
    if rc == 0:
        info["version"] = (out.strip() or err.strip()).splitlines()[-1] if (out.strip() or err.strip()) else None
    return info


# ------------------------------------------------------------------------------------------ credentials
def is_credential_file(path) -> bool:
    """A credential store by its name or by the name of the file a link points to: auth.json, mcp-auth.json, any
    SQLite database (opencode.db holds account tokens), plus the generic names (.env, *.pem, ...)."""
    p = Path(path)
    if X.is_credential_file(p):
        return True
    names = [p.name]
    try:
        names.append(p.resolve().name)
    except OSError:
        pass
    return any(OPENCODE_CREDENTIAL_RE.match(n) for n in names)


def is_sqlite(path=None, data=None) -> bool:
    if data is not None:
        return bytes(data[:16]) == SQLITE_MAGIC
    try:
        with open(path, "rb") as f:
            return f.read(16) == SQLITE_MAGIC
    except OSError:
        return False


def credential_fingerprints(ddir) -> dict:
    """{size: {sha256, ...}} of the credential files directly inside OpenCode's data directory (auth.json,
    mcp-auth.json, ...), so that a renamed copy is recognised by its bytes. Databases are recognised by their header
    instead (hashing a large opencode.db is not needed)."""
    out: dict = {}
    try:
        entries = list(os.scandir(ddir))
    except OSError:
        return out
    for e in entries:
        name = e.name.lower()
        is_json_cred = X.CREDENTIAL_FILE_RE.match(e.name) or name.startswith("mcp-auth")
        if not e.is_file() or not is_json_cred or re.search(r"\.(?:db|sqlite3?)(?:-wal|-shm|-journal)?$", name):
            continue
        try:
            out.setdefault(e.stat().st_size, set()).add(C.sha256_file(e.path))
        except OSError:
            continue
    return out


def refuse_credential(src, fingerprints=None, data=None) -> None:
    """SystemExit("REFUSED: ...") if `src` is a credential file by name, an SQLite database, or has the bytes of a
    credential file in OpenCode's data directory (a renamed copy)."""
    src, fingerprints = Path(src), fingerprints or {}
    if is_credential_file(src):
        raise SystemExit(f"REFUSED: {src} is a credential file ({src.name}); credential files are never collected")
    if is_sqlite(src, data):
        raise SystemExit(f"REFUSED: {src} is an SQLite database; OpenCode's database also holds account tokens and is "
                         "never collected (the session rows are exported instead)")
    size = len(data) if data is not None else src.stat().st_size
    if size in fingerprints:
        sha = C.sha256_bytes(data) if data is not None else C.sha256_file(src)
        if sha in fingerprints[size]:
            raise SystemExit(f"REFUSED: {src} has the same bytes as a credential file in OpenCode's data directory "
                             "(e.g. auth.json); credential files are never collected")


def scan_blobs(blobs: dict, extra_values=()) -> list:
    """[(name, [labels])] for in-memory evidence {name: bytes} that holds credential-shaped content."""
    patterns = list(C.SECRET_PATTERNS)
    for i, v in enumerate(extra_values):
        if v:
            patterns.append((f"extra_value_{i}", re.compile(re.escape(str(v).encode("utf-8")))))
    hits = []
    for name, data in blobs.items():
        found = [label for label, rx in patterns if rx.search(data)]
        if found:
            hits.append((name, found))
    return hits


# ------------------------------------------------------------------------------------------ configuration
_CLOSING_RE = re.compile(r"\s*[}\]]")


def parse_jsonc(text: str):
    """JSON with // and /* */ comments and trailing commas (OpenCode's opencode.jsonc); None when unparseable."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    # drop trailing commas (a comma outside a string followed only by whitespace and a closing bracket)
    s, kept, in_str, esc = "".join(out), [], False, False
    for k, c in enumerate(s):
        if in_str:
            in_str = not (c == '"' and not esc)
            esc = c == "\\" and not esc
        elif c == '"':
            in_str, esc = True, False
        elif c == "," and _CLOSING_RE.match(s, k + 1):
            continue
        kept.append(c)
    try:
        return json.loads("".join(kept))
    except ValueError:
        return None


def _walk_config_dir(d: Path, label: str, with_root_configs=True) -> list:
    """(label, path) of the config files OpenCode reads from a config directory (global dir or .opencode/)."""
    found = []
    if with_root_configs:
        for name in GLOBAL_CONFIG_NAMES:
            if (d / name).is_file():
                found.append((f"{label}/{name}", d / name))
    for sub in CONFIG_SUBDIRS:
        root = d / sub
        if not root.is_dir() or C.is_junction_or_link(root):
            continue
        for p in C.iter_files(root):
            rel = p.relative_to(d)
            if any(part in CONFIG_SKIP_DIRS for part in rel.parts):
                continue
            if p.suffix.lower() not in CONFIG_SUFFIXES and not is_credential_file(p):
                continue                                # credential-named files are listed (as skipped), never read
            found.append((f"{label}/{rel.as_posix()}", p))
    return found


def _ancestors(ws: Path) -> list:
    """The workspace and its parents, as OpenCode searches them upwards: stop after the directory holding .git,
    before the home directory, and after ANCESTOR_LEVELS levels."""
    out, home = [], home_dir().resolve()
    d = ws.resolve()
    for level in range(ANCESTOR_LEVELS + 1):
        if level and d == home:
            break
        out.append((level, d))
        if (d / ".git").exists() or d.parent == d:
            break
        d = d.parent
    return out


def _level_label(level: int) -> str:
    return "workspace" if level == 0 else "up" + str(level)


def find_config_files(workspace=None, cfg_dir=None, env=None) -> tuple:
    """((label, path) of every OpenCode config file that can shape the run, [skipped credential-named files])."""
    env = os.environ if env is None else env
    found, skipped = [], []
    cfg_dir = config_dir(cfg_dir, env)
    if cfg_dir.is_dir():
        found += _walk_config_dir(cfg_dir, "global_config")
    if env.get("OPENCODE_CONFIG") and Path(env["OPENCODE_CONFIG"]).is_file():
        found.append(("env_OPENCODE_CONFIG/" + Path(env["OPENCODE_CONFIG"]).name, Path(env["OPENCODE_CONFIG"])))
    if env.get("OPENCODE_CONFIG_DIR") and Path(env["OPENCODE_CONFIG_DIR"]).is_dir():
        found += _walk_config_dir(Path(env["OPENCODE_CONFIG_DIR"]), "env_OPENCODE_CONFIG_DIR")
    if workspace:
        for level, d in _ancestors(Path(workspace)):
            for name in PROJECT_CONFIG_NAMES:
                if (d / name).is_file():
                    found.append((f"project/{_level_label(level)}/{name}", d / name))
            if (d / ".opencode").is_dir() and not C.is_junction_or_link(d / ".opencode"):
                found += _walk_config_dir(d / ".opencode", f"project/{_level_label(level)}/.opencode")
    home_oc = home_dir() / ".opencode"
    if home_oc.is_dir() and not C.is_junction_or_link(home_oc):
        found += _walk_config_dir(home_oc, "home_opencode")
    out, seen = [], set()
    for label, p in found:
        key = os.path.normcase(str(p.resolve()))
        if key in seen:
            continue
        seen.add(key)
        if is_credential_file(p) or is_sqlite(p):
            skipped.append(label)
            continue
        try:
            if p.stat().st_size > CONFIG_FILE_LIMIT:
                skipped.append(label + " (over 1 MB)")
                continue
        except OSError:
            continue
        out.append((label, p))
    return sorted(out), sorted(skipped)


def find_instruction_files(workspace=None, cfg_dir=None, env=None) -> list:
    """(label, path) of the instruction files OpenCode may put into the prompt: AGENTS.md / CLAUDE.md / CONTEXT.md in
    the workspace tree (depth <= 4, skipping data and VCS directories) and in its parents, and <config>/AGENTS.md."""
    found = []
    if workspace:
        ws = Path(workspace)
        stack = [(ws, 0)]
        while stack:
            d, depth = stack.pop()
            try:
                entries = sorted(os.scandir(d), key=lambda e: e.name)
            except OSError:
                continue
            for e in entries:
                p = Path(e.path)
                if C.is_junction_or_link(p):
                    continue
                if e.is_dir(follow_symlinks=False):
                    if depth < 4 and e.name not in X.SKIP_DIRS:
                        stack.append((p, depth + 1))
                elif e.name in INSTRUCTION_NAMES:
                    found.append(("workspace/" + p.relative_to(ws).as_posix(), p))
        for level, d in _ancestors(ws)[1:]:
            for name in INSTRUCTION_NAMES:
                if (d / name).is_file():
                    found.append((f"{_level_label(level)}/{name}", d / name))
    g = config_dir(cfg_dir, env) / "AGENTS.md"
    if g.is_file():
        found.append(("global_config/AGENTS.md", g))
    return sorted(found)


def config_instruction_files(workspace, digest: dict, limit: int = 50) -> list:
    """(label, path) of the local files named by the "instructions" entries of the config files (paths or globs,
    relative to the workspace or absolute; URLs are only warned about). OpenCode adds them to the prompt."""
    found, seen = [], set()
    ws = Path(workspace) if workspace else None
    for v in digest.values():
        for pat in v.get("instructions") or []:
            if not isinstance(pat, str) or re.match(r"(?i)^https?:", pat):
                continue
            pat = str(home_dir()) + pat[1:] if pat.startswith("~/") else pat
            if Path(pat).is_absolute():
                anchor = Path(Path(pat).anchor)
                hits = anchor.glob(str(Path(pat).relative_to(anchor)))
            elif ws is not None:
                hits = ws.glob(pat)
            else:
                continue
            for p in sorted(hits):
                key = os.path.normcase(str(p.resolve()))
                if not p.is_file() or key in seen or is_credential_file(p) or len(found) >= limit:
                    continue
                seen.add(key)
                try:
                    rel = p.resolve().relative_to(ws.resolve()).as_posix() if ws is not None else p.name
                except ValueError:
                    rel = p.name
                found.append(("config_instructions/" + rel, p))
    return found


def config_digest(named_json: dict) -> dict:
    """The settings of each config file that matter for an unattended run: permission, share, model, tools, agents
    (model / permission / tools), MCP servers (type), plugins, remote instructions."""
    out = {}
    for label, text in named_json.items():
        obj = parse_jsonc(text) if isinstance(text, str) else text
        if not isinstance(obj, dict):
            out[label] = {"parse_error": True}
            continue
        d = {k: obj[k] for k in ("permission", "share", "autoshare", "model", "small_model", "tools", "plugin",
                                  "instructions", "autoupdate") if k in obj}
        if isinstance(obj.get("agent"), dict):
            d["agent"] = {name: {k: a[k] for k in ("model", "permission", "tools", "mode") if k in a}
                          for name, a in obj["agent"].items() if isinstance(a, dict)}
        if isinstance(obj.get("mcp"), dict):
            d["mcp"] = {name: {"type": m.get("type"), "enabled": m.get("enabled")} for name, m in obj["mcp"].items()
                        if isinstance(m, dict)}
        out[label] = d
    return out


def named_configs(configs, env, blobs=None) -> dict:
    """{label: text} of the JSON / JSONC config files plus OPENCODE_CONFIG_CONTENT / OPENCODE_PERMISSION, for
    config_digest. `blobs` ({"config/<label>": bytes}) avoids reading a file twice."""
    named = {}
    for label, p in configs:
        if p.suffix.lower() in (".json", ".jsonc"):
            data = (blobs or {}).get("config/" + label)
            named[label] = (data if data is not None else p.read_bytes()).decode("utf-8", "replace")
    if env.get("OPENCODE_CONFIG_CONTENT"):
        named["env:OPENCODE_CONFIG_CONTENT"] = env["OPENCODE_CONFIG_CONTENT"]
    if env.get("OPENCODE_PERMISSION"):
        named["env:OPENCODE_PERMISSION"] = json.dumps({"permission": _loads(env["OPENCODE_PERMISSION"])})
    return named


def _perm(d: dict, key: str):
    p = d.get("permission")
    if isinstance(p, str):
        return p
    if isinstance(p, dict):
        v = p.get(key, p.get("*"))
        return v if isinstance(v, str) else ("pattern rules" if isinstance(v, dict) else None)
    return None


def config_warnings(digest: dict, env: dict, auto: bool = False) -> list:
    """Plain-language warnings about the configuration of an unattended run. Each file is read on its own; OpenCode
    merges them (later files and OPENCODE_PERMISSION win), so the snapshot itself is what counts."""
    w = []
    files = {k: v for k, v in digest.items() if not v.get("parse_error")}
    for k, v in digest.items():
        if v.get("parse_error"):
            w.append(f"{k}: could not be parsed as JSON / JSONC; its settings are not summarised")
    if not any(v.get("share") == "disabled" for v in files.values()):
        w.append('no config file sets "share": "disabled": a session can then be shared (published as a link); set it '
                 "for a competition run")
    if env.get("OPENCODE_AUTO_SHARE"):
        w.append("OPENCODE_AUTO_SHARE is set: sessions are shared automatically")
    if not any("permission" in v for v in files.values()) and not env.get("OPENCODE_PERMISSION"):
        w.append("no permission block in any config file: OpenCode's defaults apply (in `opencode run`, a permission "
                 "that resolves to ask is rejected automatically unless --auto is passed)")
    for tool in ("webfetch", "websearch"):
        if not any(_perm(v, tool) == "deny" for v in files.values()):
            w.append(f'"{tool}" is not denied in any config file: the agent can reach the network through it')
    if not any(_perm(v, "external_directory") == "deny" for v in files.values()):
        w.append('"external_directory" is not denied: the agent may be allowed to touch files outside the workspace')
    if auto:
        w.append("--auto: every permission that is not explicitly denied is approved without asking")
    for k, v in files.items():
        for name, m in (v.get("mcp") or {}).items():
            if m.get("type") == "remote" and m.get("enabled") is not False:
                w.append(f"{k}: MCP server {name!r} is remote (network)")
        for ins in v.get("instructions") or []:
            if isinstance(ins, str) and re.match(r"(?i)^https?:", ins):
                w.append(f"{k}: an instruction file is fetched from a URL at run time; it is not in the snapshot")
        if v.get("plugin"):
            w.append(f"{k}: plugins run inside OpenCode ({len(v['plugin'])} listed); local plugin files are in the "
                     "snapshot, npm plugins are only named")
    return w


def env_snapshot(env=None) -> dict:
    env = os.environ if env is None else env
    out = {k: env[k] for k in ENV_RECORDED if env.get(k)}
    for k in ENV_NEVER_RECORDED:
        if env.get(k):
            out[k] = "<set; value not recorded>"
    return out


# ------------------------------------------------------------------------------------------ the stream
def _tokens_add(total: dict, t) -> None:
    if not isinstance(t, dict):
        return
    cache = t.get("cache") if isinstance(t.get("cache"), dict) else {}
    for key, v in (("input", t.get("input")), ("output", t.get("output")), ("reasoning", t.get("reasoning")),
                   ("cache_read", cache.get("read")), ("cache_write", cache.get("write"))):
        if isinstance(v, (int, float)):
            total[key] = total.get(key, 0) + v


def tool_files(part: dict) -> list:
    """File paths a tool part wrote or edited (write / edit: filePath; apply_patch: metadata files or patch headers)."""
    if not isinstance(part, dict) or part.get("type") != "tool" or part.get("tool") not in EDIT_TOOLS:
        return []
    state = part.get("state") if isinstance(part.get("state"), dict) else {}
    inp = state.get("input") if isinstance(state.get("input"), dict) else {}
    out = []
    if isinstance(inp.get("filePath"), str):
        out.append(inp["filePath"])
    meta = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    for f in meta.get("files") or []:
        if isinstance(f, dict) and isinstance(f.get("filePath"), str):
            out.append(f["filePath"])
    if not out and isinstance(inp.get("patchText"), str):
        out += re.findall(r"(?m)^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", inp["patchText"])
    return list(dict.fromkeys(out))


def summarise_stream(path) -> dict:
    """Summary of an `opencode run --format json` stream. Never raises on content; unknown events are counted."""
    events, n_lines, bad = X.read_jsonl(path)
    by_type = Counter(str(ev.get("type")) for ev in events)
    sessions = Counter(ev.get("sessionID") for ev in events if isinstance(ev.get("sessionID"), str))
    known = any(t in STREAM_TYPES for t in by_type) and bool(sessions)
    out = {"shape": "opencode-run-json" if known else "unknown", "lines": n_lines, "unparseable_lines": bad,
           "events": len(events), "events_by_type": dict(by_type), "session_id": None, "session_ids": dict(sessions),
           "steps": 0, "tokens": {}, "cost": 0.0, "tools_by_name": {}, "tool_errors": 0, "files_changed": [],
           "errors": [], "first_timestamp_ms": None, "last_timestamp_ms": None, "last_text": None}
    if sessions:
        out["session_id"] = sessions.most_common(1)[0][0]
    tools, files = Counter(), []
    for ev in events:
        ts = ev.get("timestamp")
        if isinstance(ts, (int, float)):
            out["first_timestamp_ms"] = ts if out["first_timestamp_ms"] is None else min(out["first_timestamp_ms"], ts)
            out["last_timestamp_ms"] = ts if out["last_timestamp_ms"] is None else max(out["last_timestamp_ms"], ts)
        t = ev.get("type")
        part = ev.get("part") if isinstance(ev.get("part"), dict) else {}
        if t == "step_finish":
            out["steps"] += 1
            _tokens_add(out["tokens"], part.get("tokens"))
            if isinstance(part.get("cost"), (int, float)):
                out["cost"] += part["cost"]
        elif t == "tool_use":
            tools[str(part.get("tool"))] += 1
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            if state.get("status") == "error":
                out["tool_errors"] += 1
            files += tool_files(part)
        elif t == "text":
            out["last_text"] = X._short(part.get("text"), 500)
        elif t == "error":
            err = ev.get("error")
            msg = err.get("data", {}).get("message") if isinstance(err, dict) and isinstance(err.get("data"), dict) else None
            out["errors"].append(X._short(msg or (err.get("name") if isinstance(err, dict) else err)))
    out["tools_by_name"] = dict(tools)
    out["files_changed"] = list(dict.fromkeys(files))[:500]
    out["errors"] = out["errors"][:20]
    return out


# ------------------------------------------------------------------------------------------ the stored session
def load_export(path) -> dict:
    """An `opencode export <sessionID>` file ({"info", "messages"}); SystemExit on another shape."""
    text = Path(path).read_bytes().decode("utf-8", "replace")
    start = text.find("{")                       # tolerate a stray line before the JSON document
    try:
        obj = json.loads(text[start:] if start >= 0 else text)
    except ValueError:
        raise SystemExit(f"REFUSED: {path} is not JSON; pass the stdout of `opencode export <sessionID>`") from None
    if not (isinstance(obj, dict) and isinstance(obj.get("info"), dict) and isinstance(obj.get("messages"), list)):
        raise SystemExit(f"REFUSED: {path} is not an `opencode export` document (no info / messages)")
    return obj


def _row_dict(cur, row) -> dict:
    return {d[0]: row[i] for i, d in enumerate(cur.description)}


def _loads(v):
    if isinstance(v, (bytes, bytearray)):
        v = v.decode("utf-8", "replace")
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _session_info_from_row(row: dict) -> dict:
    """A session row in the field names of `opencode export` (id, slug, projectID, directory, title, version, ...);
    columns this adapter does not know are kept under their SQL names."""
    info = {}
    names = {"project_id": "projectID", "workspace_id": "workspaceID", "parent_id": "parentID", "share_url": None}
    time, tokens, summary = {}, {}, {}
    for k, v in row.items():
        if k in SESSION_JSON_COLUMNS:
            v = _loads(v)
        if k.startswith("time_"):
            time[k[5:]] = v
        elif k.startswith("tokens_cache_"):
            tokens.setdefault("cache", {})[k[len("tokens_cache_"):]] = v
        elif k.startswith("tokens_"):
            tokens[k[7:]] = v
        elif k.startswith("summary_"):
            summary[k[8:]] = v
        elif k == "share_url":
            if v:
                info["share"] = {"url": v}
        else:
            info[names.get(k) or k] = v
    info["time"] = time
    if tokens:
        info["tokens"] = tokens
    if summary:
        info["summary"] = summary
    return info


def export_from_db(db, session_id: str, max_depth: int = 3) -> dict:
    """The session, its messages and parts (and those of its child sessions, e.g. subagents of the task tool) from
    OpenCode's database, opened READ-ONLY, in the shape of `opencode export`. Only the tables in SESSION_TABLES are
    queried; the database file itself is never copied. None when the session is not in this database."""
    base = Path(db).resolve().as_uri()
    # a WAL-mode database whose -wal / -shm files are gone (clean shutdown) cannot always be opened with mode=ro; then
    # the main file is complete, and immutable=1 reads it without creating or locking anything (never while a -wal
    # file exists: immutable would ignore the pages still in it)
    modes = ["?mode=ro"] + ([] if Path(str(db) + "-wal").exists() else ["?mode=ro&immutable=1"])
    for i, mode in enumerate(modes):
        con = sqlite3.connect(base + mode, uri=True, timeout=10)
        try:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            break
        except sqlite3.OperationalError:
            con.close()
            if i == len(modes) - 1:
                raise
    try:
        cur = con.cursor()
        missing = [t for t in ("session", "message", "part") if t not in tables]
        if missing:
            raise SystemExit(f"REFUSED: {Path(db).name} has no table(s) {missing}; not an OpenCode database this "
                             "adapter knows (pass --export with the output of `opencode export <sessionID>`)")

        def one(sid, depth):
            cur.execute("SELECT * FROM session WHERE id = ?", (sid,))
            row = cur.fetchone()
            if row is None:
                return None
            info = _session_info_from_row(_row_dict(cur, row))
            cur.execute("SELECT * FROM message WHERE session_id = ? ORDER BY time_created, id", (sid,))
            msgs = [_row_dict(cur, r) for r in cur.fetchall()]
            cur.execute("SELECT * FROM part WHERE session_id = ? ORDER BY message_id, id", (sid,))
            parts: dict = {}
            for r in cur.fetchall():
                r = _row_dict(cur, r)
                data = _loads(r.get("data"))
                data = data if isinstance(data, dict) else {"data": data}
                parts.setdefault(r["message_id"], []).append({"id": r["id"], "sessionID": sid,
                                                              "messageID": r["message_id"], **data})
            messages = []
            for m in msgs:
                data = _loads(m.get("data"))
                data = data if isinstance(data, dict) else {"data": data}
                messages.append({"info": {"id": m["id"], "sessionID": sid, **data}, "parts": parts.get(m["id"], [])})
            exp = {"info": info, "messages": messages}
            if "todo" in tables:
                cur.execute("SELECT content, status, priority, position FROM todo WHERE session_id = ? ORDER BY position",
                            (sid,))
                exp["todo"] = [_row_dict(cur, r) for r in cur.fetchall()]
            if depth < max_depth:
                cur.execute("SELECT id FROM session WHERE parent_id = ? ORDER BY time_created, id", (sid,))
                kids = [one(r[0], depth + 1) for r in cur.fetchall()]
                exp["children"] = [k for k in kids if k]
            return exp

        return one(session_id, 0)
    finally:
        con.close()


def storage_session_files(ddir, session_id: str) -> list:
    """(relative path, path) of a session in the JSON storage of OpenCode up to v1.1.x (<data>/storage/...): the
    session file, its messages and their parts, the session diff and todo files, and the same for child sessions."""
    storage = Path(ddir) / "storage"
    if not (storage / "session").is_dir() or not re.fullmatch(r"[A-Za-z0-9_\-]{4,}", str(session_id or "")):
        return []
    infos = {}
    for p in sorted((storage / "session").glob("*/*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and isinstance(d.get("id"), str):
            infos[d["id"]] = (p, d)
    wanted, queue = [], [session_id]
    while queue:
        sid = queue.pop(0)
        if sid in wanted or sid not in infos:
            continue
        wanted.append(sid)
        queue += [k for k, (_, d) in infos.items() if d.get("parentID") == sid]
    out = []
    for sid in wanted:
        out.append(infos[sid][0])
        for m in sorted((storage / "message" / sid).glob("*.json")):
            out.append(m)
            out += sorted((storage / "part" / m.stem).glob("*.json"))
        for extra in (storage / "session_diff" / f"{sid}.json", storage / "todo" / f"{sid}.json"):
            if extra.is_file():
                out.append(extra)
    return [(p.relative_to(storage).as_posix(), p) for p in out]


def export_from_storage(files) -> dict:
    """Assemble the legacy JSON files (from storage_session_files) into the shape of `opencode export`."""
    sessions, messages, parts = {}, {}, {}
    for rel, p in files:
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        head = rel.split("/")[0]
        if head == "session" and isinstance(d, dict):
            sessions[d.get("id")] = d
        elif head == "message" and isinstance(d, dict):
            messages.setdefault(d.get("sessionID"), []).append(d)
        elif head == "part" and isinstance(d, dict):
            parts.setdefault(d.get("messageID"), []).append(d)
    if not sessions:
        return None

    def build(sid):
        msgs = sorted(messages.get(sid, []), key=lambda m: (((m.get("time") or {}).get("created")) or 0, m.get("id") or ""))
        exp = {"info": sessions[sid], "messages": [{"info": m, "parts": sorted(parts.get(m.get("id"), []),
                                                                                key=lambda x: x.get("id") or "")}
                                                   for m in msgs]}
        exp["children"] = [build(k) for k, s in sessions.items() if s.get("parentID") == sid]
        return exp

    roots = [k for k, s in sessions.items() if s.get("parentID") not in sessions]
    return build(roots[0]) if roots else None


def iter_messages(exp: dict, depth: int = 0):
    """(depth, session info, message info, parts) over an export and its child sessions."""
    if not isinstance(exp, dict):
        return
    info = exp.get("info") if isinstance(exp.get("info"), dict) else {}
    for m in exp.get("messages") or []:
        if isinstance(m, dict):
            mi = m.get("info") if isinstance(m.get("info"), dict) else {}
            yield depth, info, mi, [p for p in m.get("parts") or [] if isinstance(p, dict)]
    for child in exp.get("children") or []:
        yield from iter_messages(child, depth + 1)


def model_string(mi: dict):
    if mi.get("role") == "assistant" and mi.get("modelID"):
        return f"{mi.get('providerID')}/{mi['modelID']}" if mi.get("providerID") else str(mi["modelID"])
    m = mi.get("model")
    if isinstance(m, dict) and m.get("modelID"):
        return f"{m.get('providerID')}/{m['modelID']}" if m.get("providerID") else str(m["modelID"])
    return None


def summarise_export(exp: dict) -> dict:
    info = exp.get("info") if isinstance(exp.get("info"), dict) else {}
    out = {"session_id": info.get("id"), "cli_version": info.get("version"), "title": info.get("title"),
           "sessions": 0, "messages_by_role": {}, "models": [], "agents": [], "steps": 0, "tokens": {}, "cost": 0.0,
           "tools_by_name": {}, "files_changed": [], "user_messages": [], "permission": info.get("permission")}
    roles, tools, files, sessions = Counter(), Counter(), [], set()
    for depth, si, mi, parts in iter_messages(exp):
        sessions.add(si.get("id"))
        roles[str(mi.get("role"))] += 1
        ms = model_string(mi)
        if ms and ms not in out["models"]:
            out["models"].append(ms)
        if mi.get("agent") and mi["agent"] not in out["agents"]:
            out["agents"].append(mi["agent"])
        texts = []
        for p in parts:
            t = p.get("type")
            if t == "step-finish":
                out["steps"] += 1
                _tokens_add(out["tokens"], p.get("tokens"))
                if isinstance(p.get("cost"), (int, float)):
                    out["cost"] += p["cost"]
            elif t == "tool":
                tools[str(p.get("tool"))] += 1
                files += tool_files(p)
            elif t == "patch":
                files += [f for f in p.get("files") or [] if isinstance(f, str)]
            elif t == "text" and mi.get("role") == "user" and not p.get("synthetic") and isinstance(p.get("text"), str):
                texts.append(p["text"])
        if texts:
            out["user_messages"].append({"session_id": si.get("id"), "depth": depth, "message_id": mi.get("id"),
                                         "time_created_ms": (mi.get("time") or {}).get("created"), "text": "\n".join(texts)})
    out["sessions"] = len(sessions)
    out["messages_by_role"] = dict(roles)
    out["tools_by_name"] = dict(tools)
    out["files_changed"] = list(dict.fromkeys(files))[:500]
    return out


def locate_session(session_id, ddir, export=None, source="auto", env=None) -> dict:
    """Find the stored session of a run. Returns {"source", "export" (dict or None), "files" (legacy storage
    copies), "export_file", "notes"}; the database is only ever read, never copied."""
    res = {"source": None, "export": None, "files": [], "export_file": None, "database": None, "notes": []}
    if source == "none":
        return res
    if export and source in ("auto", "export"):
        res.update(source="export", export=load_export(export), export_file=Path(export))
        got = res["export"]["info"].get("id")
        if session_id and got != session_id:
            res["notes"].append(f"the --export file is session {got}, the stream is session {session_id}")
        return res
    if source == "export":
        raise SystemExit("REFUSED: --session-source export needs --export <file from `opencode export <sessionID>`>")
    if not session_id:
        res["notes"].append("no session id in the stream, so the stored session could not be located")
        return res
    if source in ("auto", "db"):
        for db in db_candidates(ddir, env):
            try:
                exp = export_from_db(db, session_id)
            except sqlite3.Error as e:
                res["notes"].append(f"could not read {db.name} read-only ({e}); run `opencode export {session_id}` "
                                    "and pass the file with --export")
                continue
            if exp:
                res.update(source="db", export=exp, database={"file": db.name, "bytes": db.stat().st_size})
                return res
    if source in ("auto", "storage"):
        files = storage_session_files(ddir, session_id)
        if files:
            res.update(source="storage", files=files, export=export_from_storage(files))
            return res
    res["notes"].append(f"session {session_id} not found under {ddir} (database or storage/); run `opencode export "
                        f"{session_id} > session_export.json` and pass it with --export")
    return res


# ------------------------------------------------------------------------------------------ lock
def lock_opencode(prompt, workspace, out, model, agent=None, variant=None, title=None, auto=False, cfg_dir=None,
                  ddir=None, exe=None, note="", env=None, extra_secret_values=()) -> Path:
    """Freeze what an OpenCode run will see into <out>/: initial_prompt.md, config/<label> (every config and
    permission file), instructions/<label>, opencode.lock.json (+ .sha256) with hashes, the OPENCODE_* environment,
    the CLI version and the exact command. Nothing is launched. Raises SystemExit("REFUSED: ...")."""
    env = dict(os.environ if env is None else env)
    prompt, ws, out = Path(prompt), Path(workspace), Path(out)
    if not prompt.is_file():
        raise SystemExit(f"REFUSED: --prompt {prompt} not found")
    if not ws.is_dir():
        raise SystemExit(f"REFUSED: --workspace {ws} is not a directory")
    if "/" not in str(model):
        raise SystemExit(f"REFUSED: --model {model!r} must be provider/model (the form `opencode run --model` takes)")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"REFUSED: {out} exists and is not empty; choose a new --out directory")
    ddir, cdir = data_dir(ddir, env), config_dir(cfg_dir, env)
    creds = credential_fingerprints(ddir)
    blobs = {}
    data = prompt.read_bytes()
    refuse_credential(prompt, creds, data)
    blobs["initial_prompt.md"] = data
    configs, skipped = find_config_files(ws, cdir, env)
    rows = {"config_files": {}, "instruction_files": {}}

    def take(kind, prefix, items):
        for label, p in items:
            data = p.read_bytes()
            refuse_credential(p, creds, data)
            blobs[prefix + label] = data
            rows[kind][label] = {"source": str(p), "bytes": len(data), "sha256": C.sha256_bytes(data)}

    take("config_files", "config/", configs)
    envsnap = env_snapshot(env)
    digest = config_digest(named_configs(configs, env, blobs))
    instr = find_instruction_files(ws, cdir, env) + config_instruction_files(ws, digest)
    take("instruction_files", "instructions/", instr)
    warnings = config_warnings(digest, env, auto)
    home_claude = home_dir() / ".claude" / "CLAUDE.md"
    if home_claude.is_file() and not (env.get("OPENCODE_DISABLE_CLAUDE_CODE") or env.get("OPENCODE_DISABLE_CLAUDE_CODE_PROMPT")):
        warnings.append("~/.claude/CLAUDE.md exists and OPENCODE_DISABLE_CLAUDE_CODE is not set: OpenCode adds it to the "
                        "prompt, and it is not in this snapshot (set OPENCODE_DISABLE_CLAUDE_CODE=1)")
    for k, v in RECOMMENDED_ENV.items():
        if env.get(k) != v:
            warnings.append(f"recommended for an unattended run and not set: {k}={v}")
    if skipped:
        warnings.append(f"credential-named file(s) next to the config were skipped, never read: {skipped}")
    lock_id = f"oc-{C.now_utc():%Y%m%d-%H%M}-{uuid.uuid4().hex[:8]}"
    title = title or lock_id
    cmd = build_command(model, ws, agent=agent, variant=variant, title=title, auto=auto, exe=exe or "opencode")
    cli = cli_info(exe)
    if not cli["path"]:
        warnings.append("the opencode binary was not found on PATH: CLI path, hash and version are not recorded")
    lock = {"adapter": ADAPTER, "source_checked": SOURCE_CHECKED, "lock_id": lock_id, "created_utc": C.iso(C.now_utc()),
            "model": model, "agent": agent, "variant": variant, "auto_approve": bool(auto), "title": title,
            "command": cmd, "stdin": "initial_prompt.md", "workspace": str(ws), "config_dir": str(cdir),
            "data_dir": str(ddir), "cli": cli, "env": envsnap, "recommended_env": RECOMMENDED_ENV,
            "initial_prompt": {"source": str(prompt), "bytes": len(blobs["initial_prompt.md"]),
                               "sha256": C.sha256_bytes(blobs["initial_prompt.md"])},
            **rows, "skipped_credential_files": skipped, "config_digest": digest, "warnings": warnings, "note": note}
    lock_bytes = (json.dumps(lock, indent=2, default=str) + "\n").encode("utf-8")
    hits = scan_blobs({**blobs, "opencode.lock.json": lock_bytes}, extra_secret_values)
    if hits:
        raise SystemExit("REFUSED: credential-shaped content (nothing written; move keys into {env:VAR} references or "
                         "the environment): " + ", ".join(f"{n}:{'/'.join(labels)}" for n, labels in hits[:10]))
    out.mkdir(parents=True, exist_ok=True)
    for rel, data in blobs.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(data)
    (out / "opencode.lock.json").write_bytes(lock_bytes)
    C.write_text(out / "opencode.lock.sha256", C.sha256_bytes(lock_bytes) + "\n")
    env_prefix = " ".join(f"{k}={v}" for k, v in RECOMMENDED_ENV.items())
    C.write_text(out / "command.txt", "# POSIX shell syntax; in PowerShell set the variables first ($env:NAME = '1') and "
                                      "pipe the prompt: Get-Content -Raw <prompt> | opencode run ...\n"
                                      f"{env_prefix} {command_line(cmd)} < {command_line([out / 'initial_prompt.md'])} "
                                      f"> opencode_stream.jsonl 2> opencode_stderr.log\n")
    print(f"OK {out}\n  lock id: {lock_id}; config files: {len(configs)}; instruction files: {len(instr)}; "
          f"warnings: {len(warnings)}")
    for w in warnings:
        print(f"  warn: {w}")
    print("  run exactly (see command.txt), then package with opencode-package --lock " + str(out))
    print("  CONFIGURATION LOCK IS NOW IN EFFECT - no config, prompt or instruction file changes until the run ends")
    return out


def verify_lock(lock_dir) -> tuple:
    """(lock dict, problems): the lock file against its .sha256, and every locked config / instruction file against
    its source as it is now (a change after the lock shows as a problem)."""
    lock_dir = Path(lock_dir)
    if lock_dir.is_file():
        lock_dir = lock_dir.parent
    lp = lock_dir / "opencode.lock.json"
    if not lp.is_file():
        raise SystemExit(f"REFUSED: no opencode.lock.json in {lock_dir}")
    problems = []
    data = lp.read_bytes()
    sp = lock_dir / "opencode.lock.sha256"
    if not sp.is_file() or sp.read_text(encoding="utf-8").strip() != C.sha256_bytes(data):
        problems.append("opencode.lock.json does not match opencode.lock.sha256")
    lock = json.loads(data.decode("utf-8"))
    for kind in ("config_files", "instruction_files"):
        for label, row in (lock.get(kind) or {}).items():
            src = Path(row.get("source") or "")
            if not src.is_file():
                problems.append(f"{label}: {src} no longer exists")
            elif C.sha256_file(src) != row.get("sha256"):
                problems.append(f"{label}: {src} changed after the lock")
    ip = lock.get("initial_prompt") or {}
    snap = lock_dir / "initial_prompt.md"
    if snap.is_file() and C.sha256_file(snap) != ip.get("sha256"):
        problems.append("initial_prompt.md in the lock directory changed after the lock")
    return lock, problems


# ------------------------------------------------------------------------------------------ package
def package_opencode(stream, prompt, out, workspace=None, lock=None, export=None, ddir=None, cfg_dir=None, stderr=None,
                     predictions=None, harness=(), command_file=None, model=None, team_uploaded_mb: float = 0.0,
                     extra_secret_values=(), panels=None, session_source: str = "auto", env=None) -> Path:
    """Build <out>/{predictions/, evidence/{trajectory,prompts,harness}/, trajectory.zip, prompts.zip, harness.zip,
    evidence_bundle.zip, README.md}. Raises SystemExit("REFUSED: ...") when the package must not be uploaded."""
    from vec_submit_check import check as check_file

    env = dict(os.environ if env is None else env)
    stream, prompt, out = Path(stream), Path(prompt), Path(out)
    if session_source not in ("auto", "export", "db", "storage", "none"):
        raise SystemExit(f"REFUSED: --session-source must be auto, export, db, storage or none, got {session_source!r}")
    for p, what in ((stream, "--stream"), (prompt, "--prompt")):
        if not p.is_file():
            raise SystemExit(f"REFUSED: {what} {p} not found")
    ddir, cdir = data_dir(ddir, env), config_dir(cfg_dir, env)
    creds = credential_fingerprints(ddir)
    for h, what in [(h, "--harness") for h in harness or ()] + [(stderr, "--stderr"), (command_file, "--command-file"),
                                                                 (export, "--export")]:
        if h and not Path(h).is_file():
            raise SystemExit(f"REFUSED: {what} {h} not found")
    for p in [stream, prompt] + [Path(x) for x in (stderr, command_file, export) if x] + [Path(h) for h in harness or ()]:
        refuse_credential(p, creds)
    summary = summarise_stream(stream)
    if summary["events"] == 0:
        raise SystemExit(f"REFUSED: {stream} holds no JSON events; pass the stdout of `opencode run --format json`")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"REFUSED: {out} exists and is not empty; choose a new --out directory")
    warnings = []
    if summary["shape"] == "unknown":
        warnings.append("no known OpenCode event type in the stream (the summary is empty; the trajectory is still the "
                        "byte copy)")
    if len(summary["session_ids"]) > 1:
        warnings.append(f"the stream names {len(summary['session_ids'])} session ids; the most frequent one was used")
    if summary["steps"] == 0:
        warnings.append("no step_finish event in the stream: the run may have failed before the first model call")
    if summary["errors"]:
        warnings.append(f"{len(summary['errors'])} error event(s) in the stream")
    lock_info, lock_problems = (verify_lock(lock) if lock else (None, []))
    if lock_problems:
        warnings += ["LOCK: " + p for p in lock_problems]
    if not lock:
        warnings.append("no --lock: the configuration below was snapshotted after the run, not before it")

    found = locate_session(summary["session_id"], ddir, export=export, source=session_source, env=env)
    warnings += found["notes"]
    sess = summarise_export(found["export"]) if found["export"] else None
    ev = out / "evidence"
    kinds = {"trajectory": [], "prompts": [], "harness": []}

    def put(rel: str, data: bytes, kind: str, src=None) -> Path:
        refuse_credential(src or rel, creds, data)
        dst = ev / kind / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        kinds[kind].append(dst)
        return dst

    # trajectory: the stream byte for byte, stderr, the stored session (export file, database rows, legacy files)
    put("opencode_stream.jsonl", stream.read_bytes(), "trajectory", stream)
    if stderr:
        put("opencode_stderr.log", Path(stderr).read_bytes(), "trajectory", Path(stderr))
    if found["source"] == "export":
        put("session_export.json", found["export_file"].read_bytes(), "trajectory", found["export_file"])
    elif found["source"] == "db":
        doc = dict(found["export"], vec_note="rows of the session / message / part / todo tables of "
                   f"{found['database']['file']}, read-only, in the shape of `opencode export`; the database file "
                   "itself is never collected (it also holds account tokens)")
        put("session_export.json", (json.dumps(doc, indent=2, default=str) + "\n").encode("utf-8"), "trajectory",
            "session_export.json")
    elif found["source"] == "storage":
        for rel, p in found["files"]:
            put("storage/" + rel, p.read_bytes(), "trajectory", p)

    # prompts: the initial prompt, instruction files (also those named by a config's "instructions"), every user
    # message of the stored session
    put("initial_prompt.md", prompt.read_bytes(), "prompts", prompt)
    configs, skipped = find_config_files(workspace, cdir, env)
    digest = config_digest(named_configs(configs, env))
    instr = find_instruction_files(workspace, cdir, env) + config_instruction_files(workspace, digest)
    locked = {row.get("source"): row.get("sha256") for row in ((lock_info or {}).get("instruction_files") or {}).values()}
    for label, p in instr:
        data = p.read_bytes()
        if locked.get(str(p)) == C.sha256_bytes(data):
            continue                                    # unchanged since the lock: its locked copy is in prompts/locked/
        if lock_info:
            warnings.append(f"instruction file {label} is not in the lock (it appeared or changed after the lock)")
        put("instructions/" + label, data, "prompts", p)
    user_msgs = (sess or {}).get("user_messages") or []
    if user_msgs:
        put("user_messages.jsonl", "".join(json.dumps(m) + "\n" for m in user_msgs).encode("utf-8"), "prompts",
            "user_messages.jsonl")
        head = prompt.read_bytes().decode("utf-8", "replace").strip()[:200]
        if head and not any(head in m["text"] for m in user_msgs):
            warnings.append("the --prompt text was not found among the session's user messages (check it is the prompt "
                            "the run was given)")
    elif found["source"]:
        warnings.append("no user message found in the stored session")

    # harness: the lock (and its snapshot) or a config snapshot now, the command, harness files, this manifest
    if lock:
        ldir = Path(lock) if Path(lock).is_dir() else Path(lock).parent
        prompt_sha = C.sha256_file(prompt)
        if prompt_sha != ((lock_info or {}).get("initial_prompt") or {}).get("sha256"):
            warnings.append("the --prompt file differs from the prompt in the lock; both are in the prompts evidence")
        for p in C.iter_files(ldir):
            rel = p.relative_to(ldir).as_posix()
            if rel == "initial_prompt.md" and C.sha256_file(p) == prompt_sha:
                continue                                # the same bytes as prompts/initial_prompt.md
            if rel == "initial_prompt.md" or rel.startswith("instructions/"):
                kind = "prompts"
                rel = "locked/" + rel
            else:
                kind = "harness"
                rel = "lock/" + rel
            put(rel, p.read_bytes(), kind, p)
    else:
        for label, p in configs:
            put("config/" + label, p.read_bytes(), "harness", p)
        warnings += config_warnings(digest, env)
        if skipped:
            warnings.append(f"credential-named file(s) next to the config were skipped, never read: {skipped}")
    for h in harness or ():
        put("files/" + Path(h).name, Path(h).read_bytes(), "harness", Path(h))
    if command_file:
        put("command.txt", Path(command_file).read_bytes(), "harness", Path(command_file))
    elif not lock:
        warnings.append("no --command-file and no --lock: the exact `opencode run` command is not part of the evidence")

    # predictions: byte copies, format-checked, provenance looked up in the stream
    pred_rows = []
    for board, src in sorted((predictions or {}).items()):
        if not src.is_file():
            raise SystemExit(f"REFUSED: prediction for {board} not found: {src}")
        try:
            rep = check_file(src, board, panels)
        except KeyError as e:
            raise SystemExit(f"REFUSED: {e}") from None
        if not rep["ok"]:
            raise SystemExit(f"REFUSED: {src} fails the {board} contract: {rep['errors']}")
        data = src.read_bytes()
        refuse_credential(src, creds, data)
        dst = out / "predictions" / f"pred_{C.board_sanitised(board)}.h5ad"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        sha = C.sha256_bytes(data)
        if C.sha256_file(dst) != sha:
            raise SystemExit(f"REFUSED: copy of {src} does not match its sha256")
        n_mentions = X.mentions(stream, src.name)
        if n_mentions == 0:
            warnings.append(f"{board}: the file name {src.name} never appears in the stream, so the trajectory does not "
                            "show the agent writing it")
        pred_rows.append({"board": board, "file": dst.name, "source": str(src), "sha256": sha, "bytes": len(data),
                          "n_obs": rep["info"].get("n_obs"), "stream_mentions": n_mentions})
    if not pred_rows:
        warnings.append("no --prediction given: the package holds evidence only")

    models = [m for m in [model, (lock_info or {}).get("model")] + ((sess or {}).get("models") or []) if m]
    model_str = models[0] if models else None
    recorded = (sess or {}).get("models") or []
    if not model_str:
        warnings.append("model string unknown (not given with --model, not in the lock, not found in the stored "
                        "session); the portal asks for the model string you actually ran")
    elif recorded and any(m != model_str for m in recorded):
        warnings.append(f"the model string {model_str!r} differs from the model(s) OpenCode recorded: {recorded}")
    cli_version = (sess or {}).get("cli_version") or ((lock_info or {}).get("cli") or {}).get("version")

    manifest = {"adapter": ADAPTER, "status": "checked against the OpenCode source only; untested against a live "
                "OpenCode run", "source_checked": SOURCE_CHECKED,
                "framework": f"OpenCode {cli_version or '(version unknown)'} via `opencode run --format json`",
                "model_string": model_str, "stream_summary": summary, "session_source": found["source"],
                "database": found["database"], "session_summary": dict(sess or {}, user_messages=len(user_msgs)),
                "lock": {"lock_id": lock_info.get("lock_id"), "problems": lock_problems} if lock_info else None,
                "instruction_files": [label for label, _ in instr], "predictions": pred_rows, "warnings": warnings,
                "sources": {"stream": str(stream), "prompt": str(prompt), "workspace": str(workspace) if workspace else None,
                            "data_dir": str(ddir), "config_dir": str(cdir)}}
    put("trajectory_summary.json", (json.dumps({"stream": summary, "session": manifest["session_summary"]}, indent=2,
                                               default=str) + "\n").encode("utf-8"), "trajectory", "trajectory_summary.json")
    manifest["evidence"] = {p.relative_to(ev).as_posix(): {"bytes": p.stat().st_size, "sha256": C.sha256_file(p)}
                            for paths in kinds.values() for p in paths}
    put("opencode_manifest.json", (json.dumps(manifest, indent=2, default=str) + "\n").encode("utf-8"), "harness",
        "opencode_manifest.json")
    files = [p for paths in kinds.values() for p in paths]

    # the finished set once more: no credential file by name, header or bytes, and no credential-shaped content
    for p in files + [out / "predictions" / r["file"] for r in pred_rows]:
        refuse_credential(p, creds)
    hits = X._scan(files, extra_secret_values)
    if hits:
        raise SystemExit("REFUSED: credential-shaped content in evidence (nothing to upload; review and remove it): "
                         + ", ".join(f"{p.relative_to(out).as_posix()}:{'/'.join(labels)}" for p, labels in hits[:10]))

    zips = {}
    for kind, paths in kinds.items():
        zips[kind] = out / f"{kind}.zip"
        X._zip(zips[kind], ev, paths)
    zips["evidence_bundle"] = out / "evidence_bundle.zip"
    X._zip(zips["evidence_bundle"], ev, files)
    oversize = [p for p in files + list(zips.values()) if p.stat().st_size > PER_FILE_LIMIT]
    if oversize:
        raise SystemExit(f"REFUSED: over {C.UPLOAD_LIMITS['per_file_mb']} MB: " + ", ".join(p.name for p in oversize))

    upload_mb = sum(zips[k].stat().st_size for k in ("trajectory", "prompts", "harness")) / 1e6
    team_total = float(team_uploaded_mb) + upload_mb
    cap = float(C.UPLOAD_LIMITS["team_total_mb"])
    tok = summary["tokens"]
    lines = ["# OpenCode run - upload package", "",
             "Built by `vec_agent_evidence.opencode`, an adapter checked against the OpenCode source "
             f"({SOURCE_CHECKED['tag']}) and **untested against a live OpenCode run** (its tests use synthetic files). The "
             "stream is a byte copy of what OpenCode printed; check the files before you upload.", "",
             f"Framework: {manifest['framework']}", f"Model string: {model_str or 'UNKNOWN - state the model you ran'}",
             f"Session: {summary['session_id']} (stored session from: {found['source'] or 'not found'}); steps: "
             f"{summary['steps']}; tool calls: {sum(summary['tools_by_name'].values())}; tokens: {json.dumps(tok)}",
             f"Lock: {lock_info.get('lock_id') + (' - PROBLEMS, see warnings' if lock_problems else ' - verified') if lock_info else 'none'}",
             ""]
    if pred_rows:
        lines += ["| board | file | MB | sha256 | cells | stream mentions |", "|---|---|---|---|---|---|"]
        for r in pred_rows:
            lines.append(f"| {r['board']} | predictions/{r['file']} | {r['bytes'] / 1e6:.1f} | {r['sha256']} | "
                         f"{r['n_obs']} | {r['stream_mentions']} |")
        lines.append("")
    lines += ["Evidence (three kinds; the rules require at least two, one of them the trajectory):", "",
              "| kind | zip | MB | sha256 | files |", "|---|---|---|---|---|"]
    for kind in ("trajectory", "prompts", "harness", "evidence_bundle"):
        n = len(files) if kind == "evidence_bundle" else len(kinds[kind])
        lines.append(f"| {kind} | {zips[kind].name} | {zips[kind].stat().st_size / 1e6:.1f} | "
                     f"{C.sha256_file(zips[kind])} | {n} |")
    lines += ["", f"Team evidence total: {float(team_uploaded_mb):.1f} MB already uploaded + {upload_mb:.1f} MB for this "
              f"package's three kind zips = {team_total:.1f} MB of the {cap:g} MB per-team cap."
              + (" EXCEEDS THE CAP." if team_total > cap else "")]
    if warnings:
        lines += ["", "Warnings:", ""] + [f"* {w}" for w in warnings]
    lines += ["", "Never collected: OpenCode's auth.json and mcp-auth.json, its database file (it also holds account "
              "tokens; only the session rows are exported), and any credential-named file. Not covered by this "
              "adapter: no launcher, wall clock or tool hooks (OpenCode's permission rules are the enforcement layer). "
              "The prediction files must be the agent's unedited output."]
    C.write_text(out / "README.md", "\n".join(lines) + "\n")
    print(f"OK {out}\n  predictions: {len(pred_rows)}; evidence files: {len(files)}; session from: {found['source']}; "
          f"warnings: {len(warnings)}")
    for w in warnings:
        print(f"  warn: {w}")
    return out


# ------------------------------------------------------------------------------------------ CLI
def add_lock_args(ap) -> None:
    ap.add_argument("--prompt", required=True, help="the prompt file (piped to `opencode run` on stdin)")
    ap.add_argument("--workspace", required=True, help="the directory OpenCode will run in (--dir)")
    ap.add_argument("--model", required=True, help="provider/model, exactly as passed to `opencode run --model`")
    ap.add_argument("--out", required=True, help="new, empty lock directory")
    ap.add_argument("--agent", default=None)
    ap.add_argument("--variant", default=None, help="model variant (reasoning effort), if you use one")
    ap.add_argument("--title", default=None, help="session title (default: the lock id)")
    ap.add_argument("--auto", action="store_true", help="add --auto (approve every permission not explicitly denied)")
    ap.add_argument("--config-dir", default=None, help="default: $XDG_CONFIG_HOME/opencode or ~/.config/opencode")
    ap.add_argument("--data-dir", default=None, help="default: $XDG_DATA_HOME/opencode or ~/.local/share/opencode")
    ap.add_argument("--opencode-exe", default=None, help="the opencode binary (default: `opencode` on PATH)")
    ap.add_argument("--note", default="")


def add_package_args(ap) -> None:
    ap.add_argument("--stream", required=True, help="stdout of `opencode run --format json` (JSONL)")
    ap.add_argument("--prompt", required=True, help="the prompt file the run was given")
    ap.add_argument("--out", required=True, help="new, empty output directory")
    ap.add_argument("--workspace", default=None, help="the directory OpenCode ran in (instruction files are collected)")
    ap.add_argument("--lock", default=None, help="the opencode-lock directory of this run (verified and included)")
    ap.add_argument("--export", default=None, help="output of `opencode export <sessionID>` (preferred session source)")
    ap.add_argument("--session-source", choices=("auto", "export", "db", "storage", "none"), default="auto",
                    help="auto: --export, else the database rows (read-only), else the legacy storage/ files")
    ap.add_argument("--data-dir", default=None, help="default: $XDG_DATA_HOME/opencode or ~/.local/share/opencode")
    ap.add_argument("--config-dir", default=None, help="default: $XDG_CONFIG_HOME/opencode or ~/.config/opencode")
    ap.add_argument("--stderr", default=None, help="stderr of the opencode process, if you kept it")
    ap.add_argument("--prediction", action="append", default=[], metavar="BOARD=PATH",
                    help="a prediction written by the agent, e.g. T3:gata4=ws/out/pred.h5ad (repeatable)")
    ap.add_argument("--harness", action="append", default=[], help="a harness file to include (repeatable)")
    ap.add_argument("--command-file", default=None, help="text file with the exact command line you ran")
    ap.add_argument("--model", default=None, help="the model string you ran (checked against what OpenCode recorded)")
    ap.add_argument("--team-uploaded-mb", type=float, default=0.0)
    ap.add_argument("--panels", default=None, help="directory with index.json + *.genes.txt (default: the kit's)")


def _refused(fn) -> int:
    try:
        fn()
    except SystemExit as e:
        if str(e).startswith("REFUSED"):
            print(str(e))
            return 2
        raise
    return 0


def run_lock_from_args(args) -> int:
    return _refused(lambda: lock_opencode(args.prompt, args.workspace, args.out, args.model, agent=args.agent,
                                          variant=args.variant, title=args.title, auto=args.auto,
                                          cfg_dir=args.config_dir, ddir=args.data_dir, exe=args.opencode_exe,
                                          note=args.note))


def run_package_from_args(args) -> int:
    return _refused(lambda: package_opencode(args.stream, args.prompt, args.out, workspace=args.workspace,
                                             lock=args.lock, export=args.export, ddir=args.data_dir,
                                             cfg_dir=args.config_dir, stderr=args.stderr,
                                             predictions=X.parse_prediction_args(args.prediction),
                                             harness=args.harness, command_file=args.command_file, model=args.model,
                                             team_uploaded_mb=args.team_uploaded_mb, panels=args.panels,
                                             session_source=args.session_source))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m vec_agent_evidence.opencode", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    add_lock_args(sub.add_parser("lock"))
    add_package_args(sub.add_parser("package"))
    args = ap.parse_args(argv)
    return run_lock_from_args(args) if args.cmd == "lock" else run_package_from_args(args)


if __name__ == "__main__":
    sys.exit(main())
