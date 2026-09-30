"""Fetch each watched source and turn it into a snapshot, or into a short error string.

Every function returns (snapshot, error): exactly one of the two is set. The scorer is all-or-nothing (taken only
when every GitHub call answered), so a half-fetched source never overwrites a whole previous snapshot. The board
contract is taken when index.json was fetched; a gene list that could not be fetched is reported separately (its
previous copy is kept), so a new board is announced even while its gene list is not downloadable yet.
"""
from __future__ import annotations

import re
from urllib.parse import quote, urljoin

from .contract import parse_genes
from .normalize import html_to_sections, parse_json_bytes, site_links, text_chars

SUBJECT_CAP = 200


def fetch_page(fetcher, url: str, min_chars: int = 300):
    """({"sections": [...], "links": [site paths linked from the whole page]}, error)."""
    res = fetcher.fetch(url)
    if not res.ok:
        return None, res.error
    html = res.body.decode("utf-8", "replace")
    sections, used_main = html_to_sections(html)
    if text_chars(sections) < min_chars:
        # an empty shell (a client-side-only render, a challenge page, an error page served with 200)
        return None, "page text too short (%d characters%s)" % (text_chars(sections),
                                                               "" if used_main else ", no <main>")
    return {"sections": sections, "links": site_links(html, url)}, ""


def fetch_json(fetcher, url: str):
    res = fetcher.fetch(url)
    if not res.ok:
        return None, res.error
    try:
        return parse_json_bytes(res.body), ""
    except (ValueError, UnicodeDecodeError):
        return None, "not JSON"


GENES_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.txt")


def fetch_contract(fetcher, index_url: str, genes_base_url: str):
    """(snapshot, error); snapshot = {"index": dict, "genes": {genes_file: [genes]}, "genes_errors": {genes_file:
    error}}. Only index.json failing is an error of the whole source."""
    index, err = fetch_json(fetcher, index_url)
    if err:
        return None, "index.json: " + err
    if not isinstance(index, dict):
        return None, "index.json: not a JSON object"
    genes, errors = {}, {}
    for board in sorted(index):
        spec = index[board]
        if not isinstance(spec, dict) or not spec.get("genes_file"):
            continue
        name = str(spec["genes_file"])
        if name in genes or name in errors:
            continue
        if not GENES_NAME.fullmatch(name):
            errors[name] = "unexpected genes_file name"         # never used as a path
            continue
        res = fetcher.fetch(urljoin(genes_base_url, quote(name)))
        if res.ok:
            genes[name] = parse_genes(res.body.decode("utf-8", "replace"))
        else:
            errors[name] = res.error
    return {"index": index, "genes": genes, "genes_errors": errors}, ""


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
