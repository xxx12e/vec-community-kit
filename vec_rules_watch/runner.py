"""One watch run: fetch every source, compare with the previous snapshot, write the public snapshot and the changelog.

Two directories:
  --out    the public output, committed by the Action (default layout below). Everything in it is derived from
           content only - no run timestamps - so a run that finds nothing writes nothing and there is no commit.
  --state  private working state (the GitHub Actions cache): the full normalised text of every page, used for the
           next run's line-level diff. If it is missing, pages are compared by the public per-section hashes and
           re-baselined, and the changelog says so.

Public layout (out):
  CHANGES.md, CHANGES.zh.md          changelog, newest first
  status.json                        sources and their fetch status (an error is recorded with the date it began)
  pages/<id>.json                    per page: url, page sha256, per-section heading + sha256 + line count
  pages/<id>.txt                     full normalised text, ONLY with --full-text (off by default)
  contract/panels/index.json         the board contract, canonical JSON (a drop-in VEC_PANELS_DIR together with...)
  contract/panels/<genes_file>       ...the gene lists index.json names
  contract/phase.json                the phase endpoint, canonical JSON
  scorer/<repo name>.json            the scorer repository: default-branch head, version, branches, tags, releases
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from . import contract as C
from . import pages as P
from .fetch import Fetcher
from .messages import Message
from .normalize import canonical_json, page_sha, sections_to_text, text_to_sections
from .sources import fetch_contract, fetch_json, fetch_page, fetch_scorer

WATCHLIST = Path(__file__).resolve().parent / "watchlist.json"
MARKER = "<!-- entries below, newest first -->"
SCHEMA = 1


def load_watchlist(path=None) -> dict:
    with open(path or WATCHLIST, encoding="utf-8") as f:
        return json.load(f)


def make_fetcher(cfg: dict, delay=None) -> Fetcher:
    return Fetcher(cfg["user_agent"], delay=cfg.get("delay_seconds", 1.5) if delay is None else delay,
                   timeout=cfg.get("timeout_seconds", 30), robots_hosts=cfg.get("robots_hosts", ()))


# -- small file helpers: UTF-8, LF, write only when the bytes change --

def _read_text(path: Path):
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return None


def _read_json(path: Path):
    t = _read_text(path)
    if t is None:
        return None
    try:
        return json.loads(t)
    except ValueError:
        return None


def _write(path: Path, text: str) -> bool:
    if _read_text(path) == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return True


def _remove(path: Path) -> bool:
    if path.exists():
        path.unlink()
        return True
    return False


def _display_path(p: Path) -> str:
    try:
        return Path(os.path.relpath(p.resolve(), Path.cwd().resolve())).as_posix()
    except ValueError:
        return p.as_posix()


class Entry:
    """Collects one run's findings; renders them in English and Chinese."""

    def __init__(self):
        self.contract: list = []
        self.phase: list = []
        self.scorer: list = []
        self.page_baselines: list = []       # Messages
        self.page_changes: list = []         # (page id, title Message, url, hint key, diff)
        self.links: list = []                # Messages: links added to / removed from the site
        self.errors: list = []               # (source label Message or str, error)
        self.baselines: set = set()          # sources whose items are a first snapshot, not a change
        self.first_run = False
        self.rebaselined = False
        self.urls: dict = {}
        self.out_rel = "rules-watch"

    def has_content(self) -> bool:
        return bool(self.contract or self.phase or self.scorer or self.page_baselines or self.page_changes
                    or self.links)

    def high_signal(self) -> bool:
        """A change (not a first snapshot) of the contract, the phase endpoint or the scorer."""
        return any(items and name not in self.baselines
                   for name, items in (("contract", self.contract), ("phase", self.phase), ("scorer", self.scorer)))

    def headline(self) -> str:
        if self.first_run:
            return "baseline"
        parts = [name + (" baseline" if name in self.baselines else "")
                 for name, items in (("contract", self.contract), ("phase", self.phase), ("scorer", self.scorer))
                 if items]
        if self.page_changes:
            parts.append(f"{len(self.page_changes)} page{'s' if len(self.page_changes) != 1 else ''}")
        if self.links:
            parts.append("site links")
        if self.page_baselines:
            parts.append(f"{len(self.page_baselines)} new page baseline(s)")
        return ", ".join(parts) or "no change"

    # rendering
    @staticmethod
    def _items(items, lang) -> list:
        out = []
        for it in items:
            out.append("- " + it["msg"].render(lang))
            for m in it["impact"]:
                out.append("  - " + Message("entry.impact", text=m).render(lang))
        return out

    def render_sections(self, lang: str, which=("contract", "phase", "scorer", "pages")) -> list:
        out = []
        if "contract" in which and self.contract:
            out += [Message("head.contract", url=self.urls.get("contract", "")).render(lang), ""]
            out += self._items(self.contract, lang) + [""]
        if "phase" in which and self.phase:
            out += [Message("head.phase", url=self.urls.get("phase", "")).render(lang), ""]
            out += self._items(self.phase, lang) + [""]
        if "scorer" in which and self.scorer:
            out += [Message("head.scorer", url=self.urls.get("scorer", "")).render(lang), ""]
            out += self._items(self.scorer, lang) + [""]
        if "pages" in which and self.links:
            out += [Message("head.site").render(lang), ""]
            out += ["- " + m.render(lang) for m in self.links] + [""]
        if "pages" in which and (self.page_baselines or self.page_changes):
            out += [Message("head.pages").render(lang), ""]
            if self.page_baselines:
                out += ["- " + m.render(lang) for m in self.page_baselines] + [""]
            for _pid, title, url, hint, diff in self.page_changes:
                out.append("#### " + title.render(lang))
                out.append("")
                out.append(Message("page.changed", title=title, url=url, summary=P.summary_message(diff)).render(lang))
                hint_text = Message(f"hint.{hint}").render(lang) if hint else ""
                if hint_text:
                    out.append(hint_text)
                out.append("")
                out += ["- " + m.render(lang) for m in P.detail_messages(diff)]
                out.append("")
                if diff["blocks"]:
                    out.append(Message("page.excerpt_label").render(lang))
                    out.append("")
                    out.append("```diff")
                    for heading, lines in diff["blocks"]:
                        label = heading or Message("page.top").render(lang)
                        out.append("@@ " + label.replace("```", "'''"))
                        out += [x.replace("```", "'''") for x in lines]
                    out.append("```")
                    if diff["not_quoted"]:
                        out.append(Message("page.more_lines", n=diff["not_quoted"]).render(lang))
                    out.append("")
        return out

    def render(self, lang: str, date: str, time: str) -> str:
        out = [Message("entry.title", date=date, time=time).render(lang), ""]
        if self.first_run:
            out += [Message("entry.first_run").render(lang), ""]
        if self.rebaselined:
            out += [Message("entry.rebaseline").render(lang), ""]
        if self.errors:
            out += [Message("entry.fetch_errors", sources=_error_list(self.errors, lang)).render(lang), ""]
        out += self.render_sections(lang)
        while out and out[-1] == "":
            out.pop()
        return "\n".join(out) + "\n"


def _error_list(errors, lang) -> str:
    sep = Message("word.sep").render(lang)
    return sep.join(Message("entry.error_item", source=lab, error=err).render(lang) for lab, err in errors)


def prepend_entry(path: Path, entry_text: str, lang: str) -> None:
    current = _read_text(path)
    if current is None or MARKER not in current:
        head = "\n".join([Message("changes.title").render(lang), "", Message("changes.intro").render(lang), "",
                          MARKER, ""])
        rest = "" if current is None else "\n" + current
        _write(path, head + "\n" + entry_text + rest)
        return
    before, after = current.split(MARKER, 1)
    _write(path, before + MARKER + "\n\n" + entry_text + ("\n" + after.lstrip("\n") if after.strip() else ""))


def run(state_dir, out_dir, *, fetcher=None, now=None, full_text: bool = False, config=None, only=None,
        log=print) -> dict:
    """Run every source once. Returns a dict: changed (files under out_dir changed), entry (a changelog entry was
    written), high_signal (contract / phase / scorer changed, not on the first run), headline, errors, entry_en,
    entry_zh, issue_body (or "")."""
    cfg = config or load_watchlist()
    state, out = Path(state_dir), Path(out_dir)
    now = now or datetime.now(timezone.utc)
    date, hhmm = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    fetcher = fetcher or make_fetcher(cfg)
    wanted = None if not only else set(only)

    def want(source_id: str) -> bool:
        return wanted is None or source_id in wanted or source_id.split(":")[0] in wanted

    old_status = _read_json(out / "status.json") or {}
    old_sources = old_status.get("sources", {}) if isinstance(old_status, dict) else {}
    sources: dict = {}
    entry = Entry()
    entry.first_run = not (out / "status.json").exists()
    entry.out_rel = _display_path(out)
    changed = False
    state_present = (state / "state.json").exists()

    def ok(source_id, url):
        sources[source_id] = {"url": url, "ok": True}

    def fail(source_id, url, label, err):
        prev = old_sources.get(source_id) or {}
        since = prev.get("failing_since") if (not prev.get("ok", True) and prev.get("error")) else None
        sources[source_id] = {"url": url, "ok": False, "error": err, "failing_since": since or date}
        entry.errors.append((label, err))
        log(f"[error] {source_id}: {err}")

    # -- board contract --
    ccfg = cfg.get("contract") or {}
    if ccfg and want("contract"):
        url = ccfg["index_url"]
        entry.urls["contract"] = url
        snap, err = fetch_contract(fetcher, url, ccfg["genes_base_url"])
        if err:
            fail("contract", url, Message("title.contract"), err)
        else:
            ok("contract", url)
            pdir = out / "contract" / "panels"
            old_index = _read_json(pdir / "index.json")
            old_genes = {}
            if isinstance(old_index, dict):
                for spec in old_index.values():
                    if isinstance(spec, dict) and spec.get("genes_file"):
                        t = _read_text(pdir / str(spec["genes_file"]))
                        if t is not None:
                            old_genes[spec["genes_file"]] = C.parse_genes(t)
            if not isinstance(old_index, dict):
                old_index = None
                entry.baselines.add("contract")
            items = C.diff_index(old_index, snap["index"], old_genes, snap["genes"], _display_path(pdir))
            changed |= _write(pdir / "index.json", canonical_json(snap["index"]))
            for name, genes in snap["genes"].items():
                ok("genes:" + name, ccfg["genes_base_url"] + name)
                changed |= _write(pdir / name, "\n".join(genes) + "\n")
            for name, gerr in snap["genes_errors"].items():
                # the previous copy (if any) is kept; the validator refuses it if index.json moved on
                fail("genes:" + name, ccfg["genes_base_url"] + name, name, gerr)
            referenced = set(snap["genes"]) | set(snap["genes_errors"])
            for p in (pdir.glob("*.genes.txt") if pdir.exists() else []):
                if p.name not in referenced:
                    changed |= _remove(p)
            entry.contract = items

    # -- phase endpoint --
    phcfg = cfg.get("phase") or {}
    if phcfg and want("phase"):
        url = phcfg["url"]
        entry.urls["phase"] = url
        obj, err = fetch_json(fetcher, url)
        if err:
            fail("phase", url, Message("title.phase"), err)
        else:
            ok("phase", url)
            path = out / "contract" / "phase.json"
            old = _read_json(path)
            text = canonical_json(obj)
            if _read_text(path) != text:
                if old is None:
                    entry.baselines.add("phase")
                entry.phase = C.diff_phase(old, obj)
                changed |= _write(path, text)

    # -- scorer --
    scfg = cfg.get("scorer") or {}
    if scfg and want("scorer"):
        repo = scfg["repo"]
        url = scfg.get("html") or f"https://github.com/{repo}"
        entry.urls["scorer"] = url
        snap, err = fetch_scorer(fetcher, repo, scfg.get("api", "https://api.github.com"),
                                 scfg.get("raw", "https://raw.githubusercontent.com"))
        if err:
            fail("scorer", url, Message("title.scorer"), err)
        else:
            ok("scorer", url)
            path = out / "scorer" / (repo.split("/")[-1] + ".json")
            old = _read_json(path)
            text = canonical_json(snap)
            if _read_text(path) != text:
                if old is None:
                    entry.baselines.add("scorer")
                entry.scorer = C.diff_scorer(old, snap, scfg.get("pinned", "?"))
                changed |= _write(path, text)

    # -- pages --
    min_chars = int(cfg.get("min_page_chars", 300))
    for page in cfg.get("pages", []):
        pid, url = page["id"], page["url"]
        sid = "page:" + pid
        if not want(sid):
            continue
        title = Message(f"title.{pid}")
        got, err = fetch_page(fetcher, url, min_chars)
        if err:
            fail(sid, url, title, err)
            continue
        ok(sid, url)
        sections = got["sections"]
        meta_path = out / "pages" / f"{pid}.json"
        txt_path = out / "pages" / f"{pid}.txt"
        state_path = state / "pages" / f"{pid}.json"
        old_meta = _read_json(meta_path)
        new_sha = page_sha(sections)
        prev = None
        st = _read_json(state_path)
        if isinstance(old_meta, dict):
            if isinstance(st, dict) and st.get("sha256") == old_meta.get("sha256"):
                prev = st.get("sections")
            else:
                t = _read_text(txt_path)
                if t is not None and page_sha(text_to_sections(t)) == old_meta.get("sha256"):
                    prev = text_to_sections(t)
        last_changed = old_meta.get("last_changed") if isinstance(old_meta, dict) else None
        if not isinstance(old_meta, dict):
            entry.page_baselines.append(Message("page.baseline", title=title, url=url, n=len(sections)))
            last_changed = date
        elif old_meta.get("sha256") != new_sha:
            if prev is not None:
                diff = P.compare_full(prev, sections)
            else:
                diff = P.compare_hashes(old_meta.get("sections") or [], sections)
                entry.rebaselined = True
            if not P.is_empty(diff):
                entry.page_changes.append((pid, title, url, page.get("hint", "none"), diff))
            last_changed = date
        meta = {"id": pid, "url": url, "sha256": new_sha, "last_changed": last_changed,
                "full_text_in_repo": bool(full_text), "links": got["links"],
                "sections": P.section_meta(sections)}
        changed |= _write(meta_path, canonical_json(meta))
        _write(state_path, canonical_json({"sha256": new_sha, "url": url, "sections": sections}))
        if full_text:
            changed |= _write(txt_path, sections_to_text(sections))
        else:
            changed |= _remove(txt_path)
    if entry.first_run and entry.page_baselines:
        n = len(entry.page_baselines)
        entry.page_baselines.insert(0, Message("pages.baseline", n=n))
    if wanted is None and (out / "pages").is_dir():
        # a page dropped from the watch list: drop its public record too (git history keeps it)
        ids = {page["id"] for page in cfg.get("pages", [])}
        for p in sorted((out / "pages").iterdir()):
            if p.suffix in (".json", ".txt") and p.stem not in ids:
                changed |= _remove(p)
    if wanted is None:
        changed |= _site_links(cfg, out, entry)

    # -- status: sources not run this time (--only) keep their previous record --
    for sid, rec in old_sources.items():
        if sid not in sources and wanted is not None:
            sources[sid] = rec
    status = {"schema": SCHEMA, "tool": "vec_rules_watch", "full_text_in_repo": bool(full_text),
              "sources": dict(sorted(sources.items()))}
    changed |= _write(out / "status.json", canonical_json(status))

    entry_en = entry_zh = ""
    if entry.has_content():
        entry_en = entry.render("en", date, hhmm)
        entry_zh = entry.render("zh", date, hhmm)
        prepend_entry(out / "CHANGES.md", entry_en, "en")
        prepend_entry(out / "CHANGES.zh.md", entry_zh, "zh")
        changed = True

    issue_body = ""
    if entry.high_signal():
        issue_body = render_issue(entry, date, hhmm)

    _write(state / "state.json", canonical_json({"schema": SCHEMA, "saved_at": now.isoformat(timespec="seconds"),
                                                 "state_was_present": state_present}))
    return {"changed": changed, "entry": bool(entry_en), "high_signal": entry.high_signal(),
            "headline": entry.headline(), "errors": [(sid, rec["error"]) for sid, rec in sources.items()
                                                      if not rec.get("ok", True)],
            "first_run": entry.first_run, "rebaselined": entry.rebaselined, "entry_en": entry_en,
            "entry_zh": entry_zh, "issue_body": issue_body, "date": date,
            "requests": getattr(fetcher, "requests", None)}


def _path_of(url: str) -> str:
    u = urlsplit(url)
    return u.path.rstrip("/") + (("?" + u.query) if u.query else "")


def _site_links(cfg: dict, out: Path, entry: Entry) -> bool:
    """The union of the links under /challenge on every watched page (a page that failed today contributes its
    previous links): a link that appears is a page the watch list may not cover yet."""
    links = set()
    for page in cfg.get("pages", []):
        meta = _read_json(out / "pages" / f"{page['id']}.json")
        if isinstance(meta, dict):
            links.update(meta.get("links") or [])
    path = out / "site-links.json"
    old = _read_json(path)
    pages = cfg.get("pages", [])
    watched = {_path_of(p["url"]) for p in pages}
    genes_base = _path_of(cfg["contract"]["genes_base_url"]) if cfg.get("contract") else None
    host = "{0.scheme}://{0.netloc}".format(urlsplit(pages[0]["url"])) if pages else ""
    if isinstance(old, dict) and isinstance(old.get("links"), list):
        before = set(old["links"])
        for link in sorted(links - before):
            is_watched = link in watched or bool(genes_base and link.startswith(genes_base))
            entry.links.append(Message("site.link_added", url=host + link,
                                       note=Message("site.watched" if is_watched else "site.not_watched")))
        for link in sorted(before - links):
            entry.links.append(Message("site.link_removed", url=host + link))
    return _write(path, canonical_json({"links": sorted(links),
                                        "note": "links under /challenge found on the watched pages"}))


def render_issue(entry: Entry, date: str, hhmm: str) -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    base = f"{server}/{repo}/blob/{branch}/" if repo else ""
    lines = [Message("issue.intro", link=base + entry.out_rel + "/CHANGES.md").render("en"), ""]
    lines += entry.render_sections("en", which=("contract", "phase", "scorer"))
    lines += ["---", "", Message("issue.intro", link=base + entry.out_rel + "/CHANGES.zh.md").render("zh"), ""]
    lines += entry.render_sections("zh", which=("contract", "phase", "scorer"))
    return "\n".join(lines).rstrip() + "\n"
