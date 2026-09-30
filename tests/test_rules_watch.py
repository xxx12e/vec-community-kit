"""vec_rules_watch: normalisation, section split, JSON canonicalisation, contract / phase / scorer messages in English
and Chinese, excerpt cap, cache-missing re-baseline, fetch failures, the full-text switch and the CLI.

No network: every request goes to a stub fetcher that serves the synthetic fixtures in tests/fixtures/rules_watch/
(made-up pages and boards, not the organisers' text)."""
from __future__ import annotations

import json
import re
import socket
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vec_rules_watch import __main__ as cli
from vec_rules_watch import contract as C
from vec_rules_watch import fetch as F
from vec_rules_watch import pages as P
from vec_rules_watch import runner as R
from vec_rules_watch.messages import Joined, Message, catalogue, placeholders
from vec_rules_watch.normalize import (canonical_json, html_to_sections, page_sha, parse_json_bytes,
                                       sections_to_text, text_to_sections)

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "rules_watch"
BASE = "https://example.test/challenge"
API = "https://api.example.test"
RAW = "https://raw.example.test"


def fx(name: str) -> bytes:
    return (FIX / name).read_bytes()


def gh(key: str):
    return json.loads(fx("github_api.json"))[key]


def config(pages=("rules",)) -> dict:
    return {
        "user_agent": "test-agent",
        "min_page_chars": 50,
        "pages": [{"id": p, "url": f"{BASE}/{p}", "hint": "rules"} for p in pages],
        "contract": {"index_url": f"{BASE}/panels/index.json", "genes_base_url": f"{BASE}/panels/"},
        "phase": {"url": "https://api.example.test/challenge/phase"},
        "scorer": {"repo": "example/scorer", "api": API, "raw": RAW, "html": "https://github.test/example/scorer",
                   "pinned": "aaaaaaa (0.1.1)"},
    }


class StubFetcher:
    """Serves bytes by URL; a value may be an int (HTTP error status) or an error string."""

    def __init__(self, routes: dict):
        self.routes = dict(routes)
        self.requests = 0
        self.seen = []

    def fetch(self, url):
        self.requests += 1
        self.seen.append(url)
        v = self.routes.get(url)
        if v is None:
            return F.FetchResult(url, 404, b"", "HTTP 404")
        if isinstance(v, int):
            return F.FetchResult(url, v, b"", f"HTTP {v}")
        if isinstance(v, str):
            return F.FetchResult(url, 0, b"", v)
        return F.FetchResult(url, 200, v)


def routes(version: int, page: str = None) -> dict:
    v = version
    r = {
        f"{BASE}/rules": fx(page or f"page_v{v}.html"),
        f"{BASE}/panels/index.json": fx(f"index_v{v}.json"),
        "https://api.example.test/challenge/phase": fx(f"phase_v{v}.json"),
        f"{API}/repos/example/scorer": json.dumps(gh("repo")).encode(),
        f"{API}/repos/example/scorer/branches?per_page=100": json.dumps(gh(f"branches_v{v}")).encode(),
        f"{API}/repos/example/scorer/tags?per_page=100": json.dumps(gh(f"tags_v{v}")).encode(),
        f"{API}/repos/example/scorer/releases?per_page=30": json.dumps(gh(f"releases_v{v}")).encode(),
        f"{API}/repos/example/scorer/commits/main": json.dumps(gh(f"commit_v{v}")).encode(),
        f"{RAW}/example/scorer/{gh(f'commit_v{v}')['sha']}/pyproject.toml": gh(f"pyproject_v{v}").encode(),
    }
    if v == 1:
        r[f"{BASE}/panels/TX__alpha.genes.txt"] = fx("alpha.genes.txt")
        r[f"{BASE}/panels/TX__beta.genes.txt"] = fx("beta_v1.genes.txt")
    else:
        r[f"{BASE}/panels/TX__beta.genes.txt"] = fx("beta_v2.genes.txt")
        r[f"{BASE}/panels/TX__gamma.genes.txt"] = fx("gamma.genes.txt")
    return r


def day(n: int) -> datetime:
    return datetime(2026, 10, n, 7, 17, tzinfo=timezone.utc)


def do_run(tmp_path, version=1, n=1, full_text=False, extra=None, page=None, state="state"):
    r = routes(version, page)
    r.update(extra or {})
    return R.run(tmp_path / state, tmp_path / "out", fetcher=StubFetcher(r), now=day(n), full_text=full_text,
                 config=config(), log=lambda *a: None)


def snapshot(d: Path) -> dict:
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


# -- normalisation --

def test_section_split_reads_main_only_and_drops_chrome():
    secs, used_main = html_to_sections(fx("page_v1.html").decode())
    assert used_main
    heads = [s["heading"] for s in secs]
    assert heads == ["", "Example Rules", "1. Agreement", "2. Submissions", "3. Boards", "Notes", "Notes (2)",
                     "4. Old heading", "5. Removed later"]
    assert secs[0]["lines"] == ["Synthetic Challenge"]
    text = sections_to_text(secs)
    for gone in ("window.__NUXT__", "color:red", "Copy", "svg label", "On this page", "Footer text", "late script",
                 "Overview"):
        assert gone not in text, gone
    boards = next(s for s in secs if s["heading"] == "3. Boards")["lines"]
    assert boards[:3] == ["board | cells", "TX:alpha | 1000-5000", "TX:beta:val | 500-2000"]
    assert boards[3:] == ["python -m tool --board TX:alpha", "python -m tool --check"]
    assert "[email protected]" in text                           # entity + NBSP collapsed to one space
    last = secs[-1]["lines"]
    assert last == ["This section disappears in the second version.", "Question one?", "Answer one."]


def test_section_split_without_main_falls_back_to_body():
    secs, used_main = html_to_sections(fx("page_nomain.html").decode())
    assert not used_main
    assert [s["heading"] for s in secs] == ["Plain page", "Second"]
    text = sections_to_text(secs)
    assert "Site header" not in text and "Menu" not in text and "Footer" not in text


def test_text_form_round_trips():
    secs = [{"heading": "", "level": 0, "lines": ["top line"]},
            {"heading": "A", "level": 2, "lines": ["# not a heading", "\\ backslash", "plain"]},
            {"heading": "B", "level": 3, "lines": []}]
    assert text_to_sections(sections_to_text(secs)) == secs
    real, _ = html_to_sections(fx("page_v2.html").decode())
    assert text_to_sections(sections_to_text(real)) == real
    assert page_sha(text_to_sections(sections_to_text(real))) == page_sha(real)


def test_json_canonicalisation_is_stable():
    a = parse_json_bytes(b'\xef\xbb\xbf{"b": 1, "a": {"y": [2, 1], "x": "\\u00b7"}}')
    b = json.loads('{"a": {"x": "\\u00b7", "y": [2, 1]}, "b": 1}')
    ca, cb = canonical_json(a), canonical_json(b)
    assert ca == cb and ca.endswith("\n") and ca.isascii()
    assert ca.index('"a"') < ca.index('"b"') and ca.index('"x"') < ca.index('"y"')
    assert '"y": [\n      2,\n      1\n    ]' in ca                 # list order is data, not sorted


# -- excerpts --

def test_excerpt_cap_and_centering():
    long_old = "word " * 100 + "limit is 2 per board" + " tail" * 100
    long_new = long_old.replace("limit is 2", "limit is 3")
    lines = P.excerpt_pair(long_old, long_new)
    assert len(lines) == 2
    for line in lines:
        assert len(line[2:]) <= P.EXCERPT_CAP
    assert "limit is 2" in lines[0] and "limit is 3" in lines[1]
    assert lines[0].startswith("- ...") and lines[0].endswith("...")
    only_added = P.excerpt_pair(None, "x" * 5000)
    assert len(only_added[0][2:]) <= P.EXCERPT_CAP
    assert P.excerpt("short") == "short"
    for start in (0, 10, 400, 999):
        assert len(P.excerpt("y" * 1000, start, start + 1)) <= P.EXCERPT_CAP
    assert len(P.excerpt("z" * 1000, 0, 1000)) <= P.EXCERPT_CAP


def test_page_diff_full_mode_names_sections_and_quotes_short_lines():
    old, _ = html_to_sections(fx("page_v1.html").decode())
    new, _ = html_to_sections(fx("page_v2.html").decode())
    d = P.compare_full(old, new)
    assert [c["heading"] for c in d["changed"]] == ["2. Submissions"]
    assert [a["heading"] for a in d["added"]] == ["6. Appeals"]
    assert [r["heading"] for r in d["removed"]] == ["5. Removed later"]
    assert d["renamed"] == [{"old": "4. Old heading", "new": "4. Renamed heading"}]
    quoted = [x for _, lines in d["blocks"] for x in lines]
    assert any(x.startswith("- ") and "two" in x for x in quoted)
    assert any(x.startswith("+ ") and "three" in x for x in quoted)
    assert any(x == "+ Coordinates go in obsm." for x in quoted)
    assert all(len(x) - 2 <= P.EXCERPT_CAP for x in quoted)
    en = " ".join(m.render("en") for m in P.detail_messages(d))
    zh_text = " ".join(m.render("zh") for m in P.detail_messages(d))
    assert 'Renamed: "4. Old heading" -> "4. Renamed heading"' in en
    assert zh("page.section_renamed", old="4. Old heading", new="4. Renamed heading") in zh_text
    assert zh("page.section_added", heading="6. Appeals", lines=3) in zh_text
    assert zh("page.section_removed", heading="5. Removed later", lines=3) in zh_text


# -- contract, phase, scorer messages --

CJK = re.compile("[\u4e00-\u9fff]")


def zh(key, **params) -> str:
    """The Chinese template, filled: the tests stay ASCII (tests/test_ascii.py) and still check the zh output."""
    return Message(key, **params).render("zh")


def _render(items, lang):
    out = []
    for it in items:
        out.append(it["msg"].render(lang))
        out += [m.render(lang) for m in it["impact"]]
    return "\n".join(out)


def test_contract_diff_messages_en_and_zh():
    v1, v2 = json.loads(fx("index_v1.json")), json.loads(fx("index_v2.json"))
    g1 = {"TX__alpha.genes.txt": C.parse_genes(fx("alpha.genes.txt").decode()),
          "TX__beta.genes.txt": C.parse_genes(fx("beta_v1.genes.txt").decode())}
    g2 = {"TX__beta.genes.txt": C.parse_genes(fx("beta_v2.genes.txt").decode()),
          "TX__gamma.genes.txt": C.parse_genes(fx("gamma.genes.txt").decode())}
    items = C.diff_index(v1, v2, g1, g2, "rules-watch/contract/panels")
    en, zh_text = _render(items, "en"), _render(items, "zh")
    assert "Board TX:alpha (TX alpha, validation (E10.5)) is no longer in index.json." in en
    assert "New board TX:gamma:test (TX gamma, test (E12.5)): task TX, split test, 2 genes" in en
    assert "VEC_PANELS_DIR=rules-watch/contract/panels" in en
    assert "TX:beta:val: gene panel changed: 3 -> 4 genes, 1 added, 0 removed, the order of the kept genes changed" in en
    assert "Added: Beta4. Removed: none." in en
    assert "TX:beta:val: cell bounds [500, 2000] -> [500, 1500]." in en
    assert "must now have between 500 and 1500 cells" in en
    assert "TX:beta:val: required .obsm keys [] -> [spatial_3D]." in en
    assert "Your TX:beta:val file must carry [spatial_3D] in .obsm." in en
    assert "TX:beta:val now needs 3D coordinates" in en
    assert "anchors of mmd_u: floor 0.08 -> 0.09" in en
    assert "variogram added to the anchors" in en
    assert "stage in the label E8.5 -> E8.75" in en
    assert "TX:beta:val: new field new_field = x." in en
    # the same changes from the Chinese templates
    for s in (zh("contract.board_removed", board="TX:alpha", label="TX alpha, validation (E10.5)"),
              zh("contract.genes_changed", board="TX:beta:val", old_n=3, new_n=4, added=1, removed=0,
                 order_note=Message("genes.order_changed"), old_sha="191dea8b1f28b577", new_sha="9b35cb4224dc3e7d"),
              zh("contract.cells_changed", board="TX:beta:val", old_min=500, old_max=2000, new_min=500, new_max=1500),
              zh("impact.obsm_required", board="TX:beta:val", keys=["spatial_3D"]),
              zh("contract.stage_changed", board="TX:beta:val", old=Joined(["E8.5"]), new=Joined(["E8.75"])),
              zh("contract.field_added", board="TX:beta:val", field="new_field", new="x"),
              zh("contract.genes_examples", added_list=Joined(["Beta4"]), removed_list=Joined([]))):
        assert s in zh_text, s
    assert en.isascii() and len(CJK.findall(zh_text)) > 100


def test_contract_baseline_and_sha_mismatch():
    v1 = json.loads(fx("index_v1.json"))
    genes = {"TX__alpha.genes.txt": C.parse_genes(fx("alpha.genes.txt").decode()),
             "TX__beta.genes.txt": ["Beta1", "Beta2"]}                          # does not match genes_sha256
    items = C.diff_index(None, v1, {}, genes, "p")
    en = _render(items, "en")
    assert en.startswith("Baseline: 2 boards in index.json.")
    assert "TX:alpha: 5 genes (TX__alpha.genes.txt, genes_sha256 9dfbb9b6441994c6), cells 1000-5000" in en
    assert "TX:beta:val: the published TX__beta.genes.txt does not match index.json" in en
    assert "TX:alpha: the published" not in en
    assert C.panel_sha256(C.parse_genes(fx("alpha.genes.txt").decode())) == v1["TX:alpha"]["genes_sha256"]


def test_phase_diff_en_and_zh():
    p1, p2 = json.loads(fx("phase_v1.json")), json.loads(fx("phase_v2.json"))
    items = C.diff_phase(p1, p2)
    en, zh_text = _render(items, "en"), _render(items, "zh")
    assert "Phase p2 -> p3 (P3 - Test phase)." in en
    assert "Scored board validation -> test." in en
    assert "daily_quota 8 -> 2." in en
    assert "Nominations are open" in en
    assert "split val -> test." in en
    assert "Note on the phase endpoint: Two official submissions per board." in en
    assert zh("phase.phase_changed", old="p2", new="p3", label="P3 - Test phase") in zh_text
    assert zh("phase.board_changed", old="validation", new="test") in zh_text
    assert zh("phase.nominations_open.true") in zh_text and CJK.search(zh_text)
    assert C.diff_phase(p1, dict(p1)) == []
    assert "Baseline: phase p2" in _render(C.diff_phase(None, p1), "en")
    extra = _render(C.diff_phase(p1, dict(p1, deadline="2026-12-02")), "en")
    assert extra == "deadline null -> 2026-12-02."


def test_scorer_diff():
    old = {"repo": "r", "default_branch": "main", "head": {"sha": "a" * 40, "date": "2026-08-10", "subject": "s"},
           "version": "0.1.1", "branches": {"main": "a" * 40, "feat/x": "b" * 40}, "tags": {}, "releases": {}}
    new = {"repo": "r", "default_branch": "main", "head": {"sha": "c" * 40, "date": "2026-10-19", "subject": "Bump"},
           "version": "0.2.0", "branches": {"main": "c" * 40}, "tags": {"v0.2.0": "c" * 40},
           "releases": {"v0.2.0": {"name": "Scorer 0.2.0", "published": "2026-10-19", "prerelease": True,
                                   "draft": False}}}
    items = C.diff_scorer(old, new, "aaaaaaa (0.1.1)")
    en, zh_text = _render(items, "en"), _render(items, "zh")
    assert 'main moved aaaaaaa -> ccccccc (2026-10-19: "Bump").' in en
    assert "pins veckit aaaaaaa (0.1.1)" in en
    assert "Version on main: 0.1.1 -> 0.2.0." in en
    assert "New tag v0.2.0 at ccccccc." in en
    assert "New release v0.2.0: Scorer 0.2.0 (2026-10-19, pre-release)." in en
    assert "Branch feat/x removed (was at bbbbbbb)." in en
    assert zh("impact.head_moved", pinned="aaaaaaa (0.1.1)") in zh_text
    assert zh("word.prerelease") in zh_text


# -- whole runs --

def test_first_run_baseline_then_changes_then_no_change(tmp_path):
    res = do_run(tmp_path, 1, 1)
    out = tmp_path / "out"
    assert res["first_run"] and res["entry"] and not res["high_signal"] and res["errors"] == []
    en = (out / "CHANGES.md").read_text(encoding="utf-8")
    zh_text = (out / "CHANGES.zh.md").read_text(encoding="utf-8")
    assert zh("changes.title") in zh_text
    assert "First run" in en and zh("entry.first_run") in zh_text
    assert (out / "contract" / "panels" / "index.json").read_text() == canonical_json(json.loads(fx("index_v1.json")))
    assert (out / "contract" / "panels" / "TX__alpha.genes.txt").read_bytes() == fx("alpha.genes.txt")
    meta = json.loads((out / "pages" / "rules.json").read_text())
    assert meta["url"] == f"{BASE}/rules" and meta["last_changed"] == "2026-10-01"
    assert [s["heading"] for s in meta["sections"]][:3] == ["", "Example Rules", "1. Agreement"]
    assert all(p.name.endswith(".genes.txt") for p in out.rglob("*.txt"))         # no page text by default
    assert "Each team may make up to" not in "".join(p.read_text(encoding="utf-8") for p in out.rglob("*")
                                                     if p.is_file())
    assert (tmp_path / "state" / "pages" / "rules.json").exists()

    res2 = do_run(tmp_path, 2, 2)
    assert res2["high_signal"] and res2["entry"] and not res2["first_run"]
    assert res2["headline"] == "contract, phase, scorer, 1 page"
    en2 = (out / "CHANGES.md").read_text(encoding="utf-8")
    assert en2.index("## 2026-10-02") < en2.index("## 2026-10-01")                # newest first
    assert en2.count("<!-- entries below, newest first -->") == 1
    assert "```diff" in en2 and "+ Each team may make up to three official" in en2
    assert "What this changes for your file: A TX:beta:val file must now have between 500 and 1500 cells" in en2
    assert not (out / "contract" / "panels" / "TX__alpha.genes.txt").exists()      # board gone: its list removed
    assert "TX:gamma:test" in res2["issue_body"]
    assert zh("head.contract", url=f"{BASE}/panels/index.json") in res2["issue_body"]
    zh2 = (out / "CHANGES.zh.md").read_text(encoding="utf-8")
    impact = Message("impact.cells_changed", board="TX:beta:val", new_min=500, new_max=1500)
    assert zh("entry.impact", text=impact) in zh2
    assert zh("page.excerpt_label") in zh2 and "+ Each team may make up to three official" in zh2

    before = snapshot(out)
    res3 = do_run(tmp_path, 2, 3)
    assert not res3["changed"] and not res3["entry"] and res3["headline"] == "no change"
    assert snapshot(out) == before


def test_contract_copy_is_a_drop_in_panels_dir_for_the_validator(tmp_path):
    from vec_submit_check import panel_for_board

    do_run(tmp_path, 2, 1)
    panels = tmp_path / "out" / "contract" / "panels"
    spec, genes = panel_for_board("TX:beta:val", panels=panels)       # verifies genes_sha256 and n_genes
    assert genes == ["Beta2", "Beta1", "Beta3", "Beta4"] and spec["max_cells"] == 1500
    assert panel_for_board("TX:gamma:test", panels=panels)[0]["obsm_required"] == ["spatial_3D"]


def test_page_dropped_from_the_watch_list_is_removed(tmp_path):
    do_run(tmp_path, 1, 1)
    extra = tmp_path / "out" / "pages" / "old-page.json"
    extra.write_text("{}", encoding="utf-8")
    res = do_run(tmp_path, 1, 2)
    assert not extra.exists() and res["changed"] and not res["entry"]


def test_cache_missing_rebaselines_by_section_hash(tmp_path):
    do_run(tmp_path, 1, 1)
    res = do_run(tmp_path, 1, 2, page="page_v2.html", state="fresh_state")        # the Actions cache was lost
    assert res["rebaselined"] and res["entry"]
    en = res["entry_en"]
    assert "compared by section hash only" in en
    assert 'Changed (by hash, no line detail): "2. Submissions"' in en
    assert 'Renamed: "4. Old heading" -> "4. Renamed heading"' in en
    assert "```diff" not in en and "three" not in en
    assert zh("entry.rebaseline") in res["entry_zh"]
    # the fresh state is now the baseline: the next change is quoted again
    res2 = do_run(tmp_path, 1, 3, page="page_v1.html", state="fresh_state")
    assert not res2["rebaselined"] and "```diff" in res2["entry_en"]


def test_unchanged_page_with_missing_cache_is_silent(tmp_path):
    do_run(tmp_path, 1, 1)
    before = snapshot(tmp_path / "out")
    res = do_run(tmp_path, 1, 2, state="fresh_state")
    assert not res["entry"] and not res["changed"] and not res["rebaselined"]
    assert snapshot(tmp_path / "out") == before
    assert (tmp_path / "fresh_state" / "pages" / "rules.json").exists()


def test_fetch_failure_is_recorded_not_fatal(tmp_path):
    do_run(tmp_path, 1, 1)
    out = tmp_path / "out"
    before = snapshot(out)
    down = {f"{BASE}/rules": 503, "https://api.example.test/challenge/phase": "timeout",
            f"{BASE}/panels/TX__beta.genes.txt": 500}
    res = do_run(tmp_path, 2, 2, extra=down)
    ids = dict(res["errors"])
    assert ids == {"page:rules": "HTTP 503", "phase": "timeout", "contract": "TX__beta.genes.txt: HTTP 500"}
    status = json.loads((out / "status.json").read_text())["sources"]
    assert status["page:rules"] == {"url": f"{BASE}/rules", "ok": False, "error": "HTTP 503",
                                    "failing_since": "2026-10-02"}
    # contract is all-or-nothing: index.json v2 was fetched, but not written because a gene list failed
    for keep in ("contract/panels/index.json", "contract/panels/TX__alpha.genes.txt", "contract/phase.json",
                 "pages/rules.json"):
        assert snapshot(out)[keep] == before[keep], keep
    assert "Could not fetch in this run" in res["entry_en"]                        # the scorer did change
    assert zh("entry.fetch_errors", sources="X").split("X")[0] in res["entry_zh"]
    assert "Removed" not in res["entry_en"]
    # still failing the next day: failing_since does not move, status.json does not change
    status_bytes = (out / "status.json").read_bytes()
    res2 = do_run(tmp_path, 2, 3, extra=down)
    assert (out / "status.json").read_bytes() == status_bytes and not res2["entry"]
    # recovered: the changes show up
    res3 = do_run(tmp_path, 2, 4)
    assert res3["errors"] == [] and res3["high_signal"]
    assert json.loads((out / "status.json").read_text())["sources"]["page:rules"]["ok"] is True
    assert "three official" in res3["entry_en"]


def test_empty_shell_page_is_an_error_not_a_baseline(tmp_path):
    res = do_run(tmp_path, 1, 1, page="page_shell.html")
    assert dict(res["errors"])["page:rules"].startswith("page text too short")
    assert not (tmp_path / "out" / "pages" / "rules.json").exists()


def test_full_text_switch(tmp_path):
    do_run(tmp_path, 1, 1)
    assert not (tmp_path / "out" / "pages" / "rules.txt").exists()
    res = do_run(tmp_path, 1, 2, full_text=True)
    txt = tmp_path / "out" / "pages" / "rules.txt"
    assert txt.exists() and res["changed"]
    assert json.loads((tmp_path / "out" / "status.json").read_text())["full_text_in_repo"] is True
    assert page_sha(text_to_sections(txt.read_text(encoding="utf-8"))) == json.loads(
        (tmp_path / "out" / "pages" / "rules.json").read_text())["sha256"]
    # with the text in the repository, a lost cache still gives line detail
    res2 = do_run(tmp_path, 1, 3, full_text=True, page="page_v2.html", state="fresh_state")
    assert not res2["rebaselined"] and "three official" in res2["entry_en"]
    do_run(tmp_path, 1, 4, full_text=False, page="page_v2.html", state="fresh_state")
    assert not txt.exists()


def test_only_runs_the_named_sources(tmp_path):
    do_run(tmp_path, 1, 1)
    r = routes(2)
    res = R.run(tmp_path / "state", tmp_path / "out", fetcher=StubFetcher(r), now=day(2), config=config(),
                only=["phase"], log=lambda *a: None)
    assert res["headline"] == "phase"
    status = json.loads((tmp_path / "out" / "status.json").read_text())["sources"]
    assert set(status) == {"contract", "phase", "scorer", "page:rules"}


# -- messages --

def test_catalogue_has_both_languages_with_the_same_placeholders():
    cat = catalogue()
    for key, v in cat.items():
        assert set(v) == {"en", "zh"}, key
        assert placeholders(v["en"]) == placeholders(v["zh"]), key
        assert v["en"].isascii(), key
    watch = R.load_watchlist()
    for page in watch["pages"]:
        assert f"title.{page['id']}" in cat, page["id"]
        assert f"hint.{page['hint']}" in cat, page["hint"]
    assert len({p["id"] for p in watch["pages"]}) == len(watch["pages"])
    assert Joined([]).render("zh") == zh("word.none") and CJK.search(zh("word.none"))
    assert Joined(["a", "b"]).render("zh") == "a" + zh("word.sep") + "b"
    with pytest.raises(KeyError):
        Message("no.such.key")


def test_watchlist_urls_are_public_https():
    watch = R.load_watchlist()
    urls = [p["url"] for p in watch["pages"]] + [watch["contract"]["index_url"], watch["phase"]["url"]]
    for u in urls:
        assert re.match(r"^https://(kg\.)?virtualembryo\.ai/challenge", u), u
    assert watch["delay_seconds"] >= 1 and "github.com/xxx12e/vec-community-kit" in watch["user_agent"]


# -- fetcher --

class _Resp:
    def __init__(self, body=b"ok", status=200, headers=None):
        self._b, self.status, self.headers = body, status, headers or {}

    def read(self, n=-1):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_token_goes_to_the_github_api_only(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t0ken-for-test")
    f = F.Fetcher("ua", delay=0)
    assert f._headers_for("https://api.github.com/repos/a/b")["Authorization"] == "Bearer t0ken-for-test"
    for u in ("https://virtualembryo.ai/challenge/rules", "https://kg.virtualembryo.ai/challenge/phase",
              "https://raw.githubusercontent.com/a/b/c/pyproject.toml", "https://api.github.com.evil.test/x"):
        assert "Authorization" not in f._headers_for(u), u
    assert f._headers_for("https://virtualembryo.ai/")["User-Agent"] == "ua"


def test_fetcher_turns_failures_into_stable_errors(monkeypatch):
    calls = []

    def boom(req, timeout):
        calls.append(req.full_url)
        if "timeout" in req.full_url:
            raise urllib.error.URLError(socket.timeout("timed out"))
        if "dns" in req.full_url:
            raise urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
        if "challenge" in req.full_url:
            return _Resp(b"<html><title>Just a moment...</title></html>", 200, {"cf-mitigated": "challenge"})
        raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable", {}, None)

    monkeypatch.setattr(F.urllib.request, "urlopen", boom)
    f = F.Fetcher("ua", delay=0, retries=1, retry_wait=0)
    assert f.fetch("https://x.test/timeout").error == "timeout"
    assert f.fetch("https://x.test/dns").error == "DNS lookup failed"
    assert f.fetch("https://x.test/challenge").error == "blocked by a bot challenge"
    r = f.fetch("https://x.test/down")
    assert (r.error, r.status, r.ok) == ("HTTP 503", 503, False)
    assert calls.count("https://x.test/down") == 2                                 # one retry
    assert calls.count("https://x.test/challenge") == 1                            # a challenge is not retried


def test_fetcher_respects_robots_txt(monkeypatch):
    def fake(req, timeout):
        if req.full_url.endswith("/robots.txt"):
            return _Resp(b"User-agent: *\nDisallow: /private\n")
        return _Resp(b"page")

    monkeypatch.setattr(F.urllib.request, "urlopen", fake)
    f = F.Fetcher("ua", delay=0, robots_hosts=["site.test"])
    assert f.fetch("https://site.test/private/x").error == "disallowed by robots.txt"
    assert f.fetch("https://site.test/public").body == b"page"
    assert f.fetch("https://other.test/private/x").ok                              # not a robots-checked host


# -- CLI --

def test_cli_diff_on_saved_pages(tmp_path, capsys):
    a, b = FIX / "page_v1.html", FIX / "page_v2.html"
    assert cli.main(["diff", str(a), str(b)]) == 1
    out = capsys.readouterr().out
    assert 'Changed: "2. Submissions"' in out and "```diff" in out
    assert cli.main(["diff", str(a), str(a)]) == 0
    assert "No difference." in capsys.readouterr().out
    assert cli.main(["diff", str(FIX / "phase_v1.json"), str(FIX / "phase_v2.json"), "--lang", "zh"]) == 1
    assert zh("phase.phase_changed", old="p2", new="p3", label="P3 - Test phase") in capsys.readouterr().out


def test_cli_diff_on_index_files_reads_neighbouring_gene_lists(tmp_path, capsys):
    for v, files in ((1, {"TX__alpha.genes.txt": "alpha.genes.txt", "TX__beta.genes.txt": "beta_v1.genes.txt"}),
                     (2, {"TX__beta.genes.txt": "beta_v2.genes.txt", "TX__gamma.genes.txt": "gamma.genes.txt"})):
        d = tmp_path / f"v{v}"
        d.mkdir()
        (d / "index.json").write_bytes(fx(f"index_v{v}.json"))
        for dst, src in files.items():
            (d / dst).write_bytes(fx(src))
    assert cli.main(["diff", str(tmp_path / "v1" / "index.json"), str(tmp_path / "v2" / "index.json")]) == 1
    assert "1 added, 0 removed, the order of the kept genes changed" in capsys.readouterr().out


def test_cli_diff_on_two_output_directories(tmp_path, capsys):
    do_run(tmp_path, 1, 1, state="s1")
    import shutil
    shutil.copytree(tmp_path / "out", tmp_path / "old_out")
    do_run(tmp_path, 2, 2, state="s1")
    assert cli.main(["diff", str(tmp_path / "old_out"), str(tmp_path / "out")]) == 1
    out = capsys.readouterr().out
    assert "New board TX:gamma:test" in out and "Phase p2 -> p3" in out and "New tag v0.2.0" in out
    assert 'Changed (by hash, no line detail): "2. Submissions"' in out


def test_cli_run_writes_actions_outputs(tmp_path, monkeypatch, capsys):
    stub = StubFetcher(routes(1))
    monkeypatch.setattr(R, "make_fetcher", lambda cfg, delay=None: stub)
    monkeypatch.setattr(R, "load_watchlist", lambda path=None: config())
    monkeypatch.delenv("RULES_WATCH_FULL_TEXT", raising=False)
    gh_out, summary, issue = tmp_path / "gh_out.txt", tmp_path / "summary.md", tmp_path / "issue.md"
    args = ["run", "--state", str(tmp_path / "st"), "--out", str(tmp_path / "out"), "--github-output", str(gh_out),
            "--summary", str(summary), "--issue-file", str(issue)]
    assert cli.main(args) == 0
    text = gh_out.read_text()
    assert "changed=true" in text and "high_signal=false" in text and "headline=baseline" in text
    assert "First run" in summary.read_text(encoding="utf-8")
    assert not issue.exists()
    stub.routes = routes(2)
    stub.routes[f"{BASE}/rules"] = 503
    assert cli.main(args) == 0                                                     # a page down is not a failure
    assert issue.exists() and "Phase p2 -> p3" in issue.read_text(encoding="utf-8")
    assert "high_signal=true" in gh_out.read_text() and "errors=1" in gh_out.read_text()
    assert cli.main(args + ["--strict"]) == 3
    assert not issue.exists()                                                      # nothing new: no issue


# -- the scheduled workflow --

def test_workflow_file():
    wf = (ROOT / ".github" / "workflows" / "rules-watch.yml").read_text(encoding="utf-8")
    assert wf.isascii() and "\r\n" not in wf and "\t" not in wf
    assert re.search(r"schedule:\s*\n\s*- cron: \"\d+ \d+ \* \* \*\"", wf)
    assert "workflow_dispatch:" in wf
    assert re.search(r"permissions:\s*\n\s*contents: write", wf)
    assert "actions/cache/restore@v4" in wf and "actions/cache/save@v4" in wf
    assert "python -m vec_rules_watch run --state" in wf
    assert "git add rules-watch" in wf
    assert "RULES_WATCH_FULL_TEXT" in wf
