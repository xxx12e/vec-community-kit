"""`python -m vec_rules_watch diff OLD NEW` for local use: no network, nothing written.

OLD and NEW may be
  * two saved pages (.html / .htm): normalised and compared section by section, with excerpts;
  * two normalised texts (.txt, the --full-text format);
  * two JSON files: an index.json (gene lists are read from the same directory when present), a phase response,
    a scorer snapshot, or any other JSON (compared as canonical text);
  * two output directories of `run` (--out): contract, phase, scorer and pages; pages are compared line by line
    when both sides carry pages/<id>.txt, else by the per-section hashes (names only).

A file that is not valid JSON where JSON is expected, or JSON of the wrong shape, raises BadInput (the CLI prints
it and exits 2).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import contract as C
from . import pages as P
from .messages import Message
from .normalize import canonical_json, html_to_sections, text_to_sections
from .runner import Entry


class BadInput(ValueError):
    """An input file the local diff cannot read (not JSON, or JSON of the wrong shape)."""


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _load_json(p: Path):
    try:
        return json.loads(_read(p))
    except ValueError:
        raise BadInput(f"not JSON: {p.as_posix()}") from None


def _load_object(p: Path, what: str) -> dict:
    obj = _load_json(p)
    if not isinstance(obj, dict):
        raise BadInput(f"not {what} (a JSON object was expected): {p.as_posix()}")
    return obj


def _sections(p: Path):
    if p.suffix.lower() in (".html", ".htm"):
        return html_to_sections(_read(p))[0]
    return text_to_sections(_read(p))


def _json_kind(obj) -> str:
    if isinstance(obj, dict):
        if "phase" in obj and ("board" in obj or "label" in obj):
            return "phase"
        if "default_branch" in obj and "head" in obj:
            return "scorer"
        if obj and all(isinstance(v, dict) and "genes_file" in v for v in obj.values()):
            return "index"
    return "json"


def _genes_near(index_path: Path, index: dict) -> dict:
    out = {}
    for spec in index.values():
        name = spec.get("genes_file") if isinstance(spec, dict) else None
        if name and (index_path.parent / name).is_file():
            out[name] = C.parse_genes(_read(index_path.parent / name))
    return out


class _Literal(Message):
    """A title that is not in the catalogue (a local file name): same text in both languages."""

    def __init__(self, text: str):  # noqa: D401 - deliberately bypasses the catalogue check
        self.key = "_literal"
        self.params = {"text": text}

    def render(self, lang: str) -> str:
        return self.params["text"]


def _page_entry(entry: Entry, label: str, url: str, diff: dict) -> None:
    if not P.is_empty(diff):
        entry.page_changes.append((label, _Literal(label), url, "none", diff))


def diff_files(old: Path, new: Path, pinned: str = "?") -> Entry:
    entry = Entry()
    if old.suffix.lower() == ".json" and new.suffix.lower() == ".json":
        a, b = _load_json(old), _load_json(new)
        kind_a, kind_b = _json_kind(a), _json_kind(b)
        kind = kind_b if kind_a == kind_b else "json"
        if kind == "index":
            entry.urls["contract"] = new.as_posix()
            entry.contract = C.diff_index(a, b, _genes_near(old, a), _genes_near(new, b), new.parent.as_posix())
        elif kind == "phase":
            entry.urls["phase"] = new.as_posix()
            entry.phase = C.diff_phase(a, b)
        elif kind == "scorer":
            entry.urls["scorer"] = new.as_posix()
            entry.scorer = C.diff_scorer(a, b, pinned)
        else:
            sa = [{"heading": "", "level": 0, "lines": canonical_json(a).splitlines()}]
            sb = [{"heading": "", "level": 0, "lines": canonical_json(b).splitlines()}]
            _page_entry(entry, new.name, new.as_posix(), P.compare_full(sa, sb))
        return entry
    _page_entry(entry, new.name, new.as_posix(), P.compare_full(_sections(old), _sections(new)))
    return entry


def diff_dirs(old: Path, new: Path, pinned: str = "?") -> Entry:
    entry = Entry()
    oi, ni = old / "contract" / "panels" / "index.json", new / "contract" / "panels" / "index.json"
    if oi.is_file() and ni.is_file():
        a, b = _load_object(oi, "a board contract"), _load_object(ni, "a board contract")
        entry.urls["contract"] = ni.as_posix()
        entry.contract = C.diff_index(a, b, _genes_near(oi, a), _genes_near(ni, b), ni.parent.as_posix())
    op, np_ = old / "contract" / "phase.json", new / "contract" / "phase.json"
    if op.is_file() and np_.is_file():
        entry.urls["phase"] = np_.as_posix()
        entry.phase = C.diff_phase(_load_json(op), _load_json(np_))
    for ns in sorted((new / "scorer").glob("*.json")) if (new / "scorer").is_dir() else []:
        os_ = old / "scorer" / ns.name
        if os_.is_file():
            entry.urls["scorer"] = ns.as_posix()
            entry.scorer += C.diff_scorer(_load_object(os_, "a scorer snapshot"),
                                          _load_object(ns, "a scorer snapshot"), pinned)
    for nm in sorted((new / "pages").glob("*.json")) if (new / "pages").is_dir() else []:
        om = old / "pages" / nm.name
        if not om.is_file():
            continue
        a, b = _load_object(om, "a page record"), _load_object(nm, "a page record")
        if a.get("sha256") == b.get("sha256"):
            continue
        ot, nt = om.with_suffix(".txt"), nm.with_suffix(".txt")
        if ot.is_file() and nt.is_file():
            diff = P.compare_full(text_to_sections(_read(ot)), text_to_sections(_read(nt)))
        else:
            diff = P.compare_meta(a.get("sections") or [], b.get("sections") or [])
        _page_entry(entry, b.get("id") or nm.stem, b.get("url") or "", diff)
    return entry


def render(entry: Entry, lang: str) -> str:
    lines = entry.render_sections(lang)
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return Message("summary.no_difference").render(lang) + "\n"
    return "\n".join(lines) + "\n"
