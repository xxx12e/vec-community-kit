"""Source files are ASCII-only (the docs/ tutorials and the top-level README may contain Chinese)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "runs", "third_party", ".venv", "data"}
SUFFIXES = {".py", ".json", ".txt", ".ini", ".cfg", ".toml", ".md"}
ALLOWED_NON_ASCII = {ROOT / "README.md"}


def source_files():
    for p in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        if p.is_file() and p.suffix in SUFFIXES and not (p.parent == ROOT / "docs") and p not in ALLOWED_NON_ASCII:
            yield p


def test_sources_are_ascii():
    bad = []
    for p in source_files():
        data = p.read_bytes()
        if not data.isascii():
            bad.append(str(p.relative_to(ROOT)))
    assert bad == [], bad


def test_no_tabs_or_crlf_in_python():
    bad = []
    for p in source_files():
        if p.suffix == ".py":
            data = p.read_bytes()
            if b"\r\n" in data or b"\t" in data:
                bad.append(str(p.relative_to(ROOT)))
    assert bad == [], bad
