"""Shared constants and helpers for the Agent-track evidence skeleton. ASCII-only source, stdlib-only.

Nothing in here talks to the agent. It holds the frozen facts (tool policy, task -> boards, child environment)
and small file / hash / process utilities used by lock.py, launch.py, evidence.py and package.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
KIT_ROOT = PKG_DIR.parent
PY = Path(sys.executable)
DEFAULT_RUNS_ROOT = KIT_ROOT / "runs"
DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_SETTINGS_TEMPLATE = PKG_DIR / "example_settings.json"
DEFAULT_PROMPT_TEMPLATE = PKG_DIR / "example_prompt.md"
# Kit packages copied read-only into every workspace/tools/ (plus finalize_submission.py) and into the snapshot zip.
TOOL_PACKAGES = ("vec_submit_check", "vec_baselines", "vec_local_score")

# Frozen tool policy. --tools restricts the built-in tool set; --disallowedTools is belt and braces.
DEFAULT_TOOLS = ["Bash", "Read", "Edit", "Write", "Glob", "Grep"]
DEFAULT_DISALLOWED_TOOLS = ["WebFetch", "WebSearch", "PowerShell", "Task", "Agent", "Skill", "NotebookEdit", "Workflow"]
PERMISSION_MODE = "bypassPermissions"
# Tools a newer CLI may list in the init event even under --tools (harmless, recorded, never abort on them).
INIT_TOOL_EXTRAS_OK = {"EndConversation", "StructuredOutput"}

TASK_BOARDS = {
    "T1": ["T1:val"],
    "T2": ["T2:heart:val_interp", "T2:heart:val_extrap", "T2:embryo:val_interp"],
    "T3": ["T3:gata4"],
}

# Child environment overrides: no memory files, no auto-update / telemetry, offline package managers, UTF-8.
ENV_OVERRIDES = {
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "DISABLE_AUTOUPDATER": "1",
    "DISABLE_TELEMETRY": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "BASH_DEFAULT_TIMEOUT_MS": "1800000",
    "BASH_MAX_TIMEOUT_MS": "7200000",
    "BASH_MAX_OUTPUT_LENGTH": "20000",
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "PIP_NO_INDEX": "1",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "NO_PROXY": "*",
}
# Inherited variables removed before the overrides are applied (cross-session leak channels, stray toolchains).
# ANTHROPIC_* is deliberately kept: it is how API-key billing reaches the CLI.
ENV_SCRUB_PREFIXES = ("CLAUDE", "CONDA", "PYTHON", "PIP_", "JUPYTER", "HF_", "VIRTUAL_ENV", "PYENV", "UV_")
# Variables whose VALUE never enters evidence (launch_command.json): matched on the name.
SECRET_ENV_MARKERS = ("TOKEN", "KEY", "SECRET", "PASSWORD")
SECRET_ENV_NAMES = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")

RUN_ID_RE = re.compile(r"\d{8}-\d{4}_T[123]_[0-9a-f]{8}")
# Portal limits for evidence uploads (challenge rules): per file and per team in total.
UPLOAD_LIMITS = {"per_file_mb": 200, "team_total_mb": 600}


def _rx(*parts: str):
    return re.compile("".join(parts).encode("ascii"))


# Evidence must never carry credentials. These are credential-SHAPED regexes over bytes (a key prefix followed
# by key characters; OAuth token fields as JSON keys), assembled from fragments so that this file - which is
# copied into every run snapshot - never contains the literal markers and cannot trip its own scan. Reports
# carry the neutral labels only.
SECRET_PATTERNS = (
    ("anthropic_api_key_shape", _rx("sk-", "ant-", r"[A-Za-z0-9_\-]{8,}")),
    ("oauth_access_token_field", _rx('"', "access", "Token", r'"\s*:')),
    ("oauth_refresh_token_field", _rx('"', "refresh", "Token", r'"\s*:')),
    ("oauth_credentials_block", _rx('"?', "claudeAi", "Oauth", r'"?\s*:')),
)
SECRET_SCAN_SUFFIXES = (".json", ".jsonl", ".md", ".txt", ".log", ".py", ".sha256", ".env", ".yaml", ".yml", ".toml", ".cfg")


# ------------------------------------------------------------------------------------------ utilities
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def sha256_file(path, buf: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write_text(path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_json(path, obj) -> None:
    # ensure_ascii stays True: the run directory must be readable on any console and by any auditor.
    write_text(path, json.dumps(obj, indent=2, default=str) + "\n")


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_cmd(cmd, cwd=None, env=None, timeout=600):
    """Run a command; return (returncode, stdout, stderr) as text. Never raises."""
    try:
        r = subprocess.run([str(c) for c in cmd], cwd=None if cwd is None else str(cwd), env=env,
                           capture_output=True, timeout=timeout, text=True, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError as e:
        return 127, "", f"not found: {e}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except OSError as e:
        return 126, "", f"os error: {e}"


def parse_json_output(text: str):
    """Parse CLI stdout that is one JSON document, possibly pretty-printed and possibly preceded by noise."""
    text = (text or "").strip()
    if not text:
        return None
    for candidate in (text, text[text.find("{"):] if "{" in text else "", text.splitlines()[-1]):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    return None


def safe_std_streams() -> None:
    """Never die printing a non-ASCII path on a legacy console."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="backslashreplace")
            except (ValueError, AttributeError):
                pass


def log(msg: str) -> None:
    print(f"[{now_utc():%H:%M:%S}Z evidence] {msg}", flush=True)


def board_sanitised(board: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", board)


def posix(path) -> str:
    return Path(path).as_posix()


def is_junction_or_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        if hasattr(os.path, "isjunction") and os.path.isjunction(str(path)):
            return True
    except OSError:
        return False
    return False


def iter_files(root: Path, skip_rel_dirs=()):
    """Yield every regular file under root WITHOUT descending into junctions/symlinks or skipped dirs."""
    root = Path(root)
    skip = {Path(s) for s in skip_rel_dirs}
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in sorted(entries, key=lambda x: x.name):
            p = Path(e.path)
            if p.relative_to(root) in skip or is_junction_or_link(p):
                continue
            if e.is_dir(follow_symlinks=False):
                stack.append(p)
            elif e.is_file(follow_symlinks=False):
                yield p


def set_read_only(root: Path, skip_rel_dirs=()) -> int:
    """Set the read-only attribute on every file under root (directories are left alone)."""
    n = 0
    for f in iter_files(root, skip_rel_dirs):
        try:
            os.chmod(f, stat.S_IREAD)
            n += 1
        except OSError:
            pass
    return n


def set_writable(root: Path) -> None:
    for f in iter_files(root):
        try:
            os.chmod(f, stat.S_IREAD | stat.S_IWRITE)
        except OSError:
            pass


def is_secret_env_name(name: str) -> bool:
    u = name.upper()
    return name in SECRET_ENV_NAMES or any(m in u for m in SECRET_ENV_MARKERS)


def redact_env(env: dict) -> dict:
    """Evidence view of an environment: secret-looking variables keep only their value length."""
    return {k: (f"<redacted:len={len(env[k])}>" if is_secret_env_name(k) else env[k]) for k in sorted(env)}
