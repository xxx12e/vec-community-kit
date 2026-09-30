"""Turn the path the user gives into (framework, [log files of one run]) (stdlib only, ASCII only).

Accepted:
  * one log file: a Claude Code stream-json or session JSONL (its <session id>/subagents/*.jsonl are added when they
    exist), a Codex exec --json stream or rollout, an OpenCode run --format json stream, an `opencode export` JSON
    document, or OpenCode's database (with --session, else the most recent session)
  * a directory: an unzipped evidence package or run directory of this kit (evidence/trajectory/, trajectory/,
    transcript/, stream.jsonl ...), a Claude Code project directory (with --session, or when it holds one session),
    an OpenCode data directory (its database first: opencode.db, opencode-<channel>.db, or a relative OPENCODE_DB;
    the storage/ JSON files of OpenCode up to v1.1.x only when there is no database or it lacks the session), or
    storage/ itself
  * a .zip (e.g. trajectory.zip or evidence_bundle.zip): extracted into a temporary directory first (at most 1 GB)
Priorities inside an evidence package: Claude transcript/ over stream.jsonl; Codex rollout over the stream (a dedup
rollout is read together with the stream, which carries what it dropped: the rollout first, as the stream has no
timestamps); OpenCode session_export.json or storage/ over the stream.
"""
from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from vec_agent_evidence import opencode as O

from . import parsers as P

ZIP_LIMIT = 1024 ** 3


class InputError(Exception):
    pass


def extract_zip(path: Path) -> tempfile.TemporaryDirectory:
    tmp = tempfile.TemporaryDirectory(prefix="vec_lens_")
    with zipfile.ZipFile(path) as z:
        total = sum(i.file_size for i in z.infolist())
        if total > ZIP_LIMIT:
            tmp.cleanup()
            raise InputError(f"{path.name} would extract to {total / 1e9:.1f} GB (limit 1 GB); unzip it yourself")
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                continue                                   # never write outside the temporary directory
            z.extract(info, tmp.name)
    return tmp


def sniff(path: Path) -> str | None:
    scores = P.sniff_file(path)
    best = max(scores.items(), key=lambda kv: kv[1]) if scores else (None, 0)
    return best[0] if best[1] > 0 else None


def _claude_with_subagents(f: Path, subagents: bool = True) -> list:
    files = [f]
    side = f.with_suffix("") / "subagents"
    if subagents and side.is_dir():
        files += sorted(side.glob("*.jsonl"))
    return files


def _find_trajectory_dir(d: Path):
    for cand in (d / "evidence" / "trajectory", d / "trajectory", d):
        if cand.is_dir():
            yield cand


def resolve_dir(d: Path, framework: str = "auto", session=None, subagents: bool = True):
    # an OpenCode data directory (the parser reads its database first, and storage/ of OpenCode <= v1.1.x only when
    # the database is missing or does not hold the session), or storage/ itself
    if d.name == "storage" and (d / "session").is_dir():
        return "opencode", [d]
    if (d / "storage" / "session").is_dir() or (framework in ("auto", "opencode") and P.opencode.data_dir_dbs(d)):
        return "opencode", [d]
    # this kit's run directory (Claude Code path): transcript/ first, else stream.jsonl
    if (d / "transcript").is_dir() and list((d / "transcript").glob("*.jsonl")):
        main = sorted((d / "transcript").glob("*.jsonl"))
        subs = sorted((d / "transcript" / "subagents").glob("*.jsonl")) if subagents else []
        return "claude", main + subs
    for t in _find_trajectory_dir(d):
        if (t / "session_export.json").is_file():
            return "opencode", [t / "session_export.json"]
        if (t / "storage" / "session").is_dir():
            return "opencode", [t / "storage"]
        if (t / "opencode_stream.jsonl").is_file():
            return "opencode", [t / "opencode_stream.jsonl"]
        if (t / "codex_stream.jsonl").is_file():
            rollouts = sorted((t / "rollout").glob("*.jsonl")) if (t / "rollout").is_dir() else []
            full = [r for r in rollouts if not r.name.endswith(".dedup.jsonl")]
            if full:
                return "codex", full
            return "codex", rollouts + [t / "codex_stream.jsonl"]     # the stream has no timestamps: after them
        if (t / "transcript").is_dir() and list((t / "transcript").glob("*.jsonl")):
            return "claude", sorted((t / "transcript").glob("*.jsonl"))
        if (t / "stream.jsonl").is_file():
            return "claude", [t / "stream.jsonl"]
    # a Claude Code project directory: <session id>.jsonl (+ <session id>/subagents/)
    jsonl = sorted(p for p in d.glob("*.jsonl") if p.is_file())
    if session:
        f = d / f"{session}.jsonl"
        if f.is_file():
            return (sniff(f) or "claude"), _claude_with_subagents(f, subagents)
        raise InputError(f"no {session}.jsonl in {d}")
    if len(jsonl) == 1:
        fw = sniff(jsonl[0])
        if fw is None:
            raise InputError(f"{jsonl[0]} is not a log format this tool knows")
        return fw, _claude_with_subagents(jsonl[0], subagents) if fw == "claude" else [jsonl[0]]
    if len(jsonl) > 1:
        raise InputError(f"{d} holds {len(jsonl)} JSONL files; pass one file, or --session <id>")
    raise InputError(f"nothing this tool can read in {d}")


def resolve(path, framework: str = "auto", session=None, subagents: bool = True):
    """(framework, [files]) for a path (see the module docstring); InputError when it cannot be read."""
    path = Path(path)
    if not path.exists():
        raise InputError(f"{path} not found")
    if path.is_dir():
        fw, files = resolve_dir(path, framework, session, subagents)
    elif O.is_sqlite(path):
        fw, files = "opencode", [path]
    elif path.suffix.lower() == ".json":
        fw, files = "opencode", [path]                     # an `opencode export` document (checked when parsed)
    else:
        fw = sniff(path) if framework == "auto" else framework
        if fw is None:
            raise InputError(f"{path.name}: no known event format in its first lines (try --framework)")
        files = _claude_with_subagents(path, subagents) if fw == "claude" else [path]
    if framework != "auto" and fw != framework:
        raise InputError(f"{path} looks like {fw}, not {framework}")
    return fw, files
