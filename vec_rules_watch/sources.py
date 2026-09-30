"""Fetch each watched source and turn it into a snapshot, or into a short error string.

Every function returns (snapshot, error): exactly one of the two is set. A source is all-or-nothing: the board
contract is taken only when index.json and every gene list it names were fetched, the scorer only when every
GitHub call answered, so a half-fetched source never overwrites a whole previous snapshot.
"""
from __future__ import annotations

import re
from urllib.parse import quote, urljoin

from .contract import parse_genes
from .normalize import html_to_sections, parse_json_bytes, text_chars

SUBJECT_CAP = 200


def fetch_page(fetcher, url: str, min_chars: int = 300):
    res = fetcher.fetch(url)
    if not res.ok:
        return None, res.error
    try:
        html = res.body.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None, "could not decode the page"
    sections, used_main = html_to_sections(html)
    if text_chars(sections) < min_chars:
        # an empty shell (a client-side-only render, a challenge page, an error page served with 200)
        return None, "page text too short (%d characters%s)" % (text_chars(sections),
                                                               "" if used_main else ", no <main>")
    return sections, ""


def fetch_json(fetcher, url: str):
    res = fetcher.fetch(url)
    if not res.ok:
        return None, res.error
    try:
        return parse_json_bytes(res.body), ""
    except (ValueError, UnicodeDecodeError):
        return None, "not JSON"


def fetch_contract(fetcher, index_url: str, genes_base_url: str):
    """(snapshot, error); snapshot = {"index": dict, "genes": {genes_file: [genes]}}."""
    index, err = fetch_json(fetcher, index_url)
    if err:
        return None, "index.json: " + err
    if not isinstance(index, dict):
        return None, "index.json: not a JSON object"
    genes = {}
    for board in sorted(index):
        spec = index[board]
        if not isinstance(spec, dict) or not spec.get("genes_file"):
            continue
        name = str(spec["genes_file"])
        if name in genes:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", name) or name.startswith("."):
            return None, f"{board}: unexpected genes_file name"
        res = fetcher.fetch(urljoin(genes_base_url, quote(name)))
        if not res.ok:
            return None, f"{name}: {res.error}"
        genes[name] = parse_genes(res.body.decode("utf-8", "replace"))
    return {"index": index, "genes": genes}, ""


def _version_from_pyproject(text: str):
    m = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else None


def fetch_scorer(fetcher, repo: str, api: str = "https://api.github.com", raw: str = "https://raw.githubusercontent.com"):
    """Snapshot of the scorer repository: default branch head (sha, date, subject), version in pyproject.toml at that
    commit, branch heads, tags and releases. Volatile fields (stars, pushed_at, updated_at) are left out."""
    meta, err = fetch_json(fetcher, f"{api}/repos/{repo}")
    if err:
        return None, "repository: " + err
    default = meta.get("default_branch") if isinstance(meta, dict) else None
    if not default:
        return None, "repository: no default_branch"
    branches, err = fetch_json(fetcher, f"{api}/repos/{repo}/branches?per_page=100")
    if err:
        return None, "branches: " + err
    tags, err = fetch_json(fetcher, f"{api}/repos/{repo}/tags?per_page=100")
    if err:
        return None, "tags: " + err
    releases, err = fetch_json(fetcher, f"{api}/repos/{repo}/releases?per_page=30")
    if err:
        return None, "releases: " + err
    commit, err = fetch_json(fetcher, f"{api}/repos/{repo}/commits/{quote(default)}")
    if err:
        return None, "head commit: " + err
    try:
        sha = commit["sha"]
        c = commit.get("commit") or {}
        date = ((c.get("committer") or {}).get("date") or "")[:10]
        subject = (c.get("message") or "").splitlines()[0][:SUBJECT_CAP] if c.get("message") else ""
        snap = {
            "repo": repo,
            "default_branch": default,
            "head": {"sha": sha, "date": date, "subject": subject},
            "branches": {b["name"]: b["commit"]["sha"] for b in branches},
            "tags": {t["name"]: t["commit"]["sha"] for t in tags},
            "releases": {r["tag_name"]: {"name": (r.get("name") or "")[:SUBJECT_CAP],
                                         "published": (r.get("published_at") or "")[:10],
                                         "prerelease": bool(r.get("prerelease")), "draft": bool(r.get("draft"))}
                         for r in releases},
        }
    except (KeyError, TypeError, IndexError, AttributeError):
        return None, "unexpected GitHub API response"
    res = fetcher.fetch(f"{raw}/{repo}/{sha}/pyproject.toml")
    snap["version"] = _version_from_pyproject(res.body.decode("utf-8", "replace")) if res.ok else None
    if not res.ok and res.status != 404:
        return None, "pyproject.toml: " + res.error
    return snap, ""
