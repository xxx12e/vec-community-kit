"""Section-level page diffs and short excerpts.

Two ways to compare a page with its previous version:
  * full: the previous full normalised text is available (the Actions cache, or --full-text in the repository):
    per section, lines added / removed and short excerpts of the changed lines (each at most EXCERPT_CAP characters,
    cut around the part of the line that changed);
  * by hash: only the public per-section sha256 is available (the cache was lost): the changed sections are named,
    no line is quoted.
"""
from __future__ import annotations

import difflib

from .messages import Joined, Message
from .normalize import section_sha

EXCERPT_CAP = 200
MAX_EXCERPTS_PER_SECTION = 6
MAX_EXCERPTS_PER_PAGE = 24


def excerpt(text: str, start: int = 0, end=None, cap: int = EXCERPT_CAP) -> str:
    """At most `cap` characters of `text`, centred on text[start:end] (the changed part), with '...' where cut."""
    if len(text) <= cap:
        return text
    end = len(text) if end is None else max(end, start)
    room = cap - 6                                   # two '...' at most
    if end - start >= room:
        s, e = start, start + room
    else:
        pad = (room - (end - start)) // 2
        s = max(0, start - pad)
        e = min(len(text), s + room)
        s = max(0, e - room)
    out = text[s:e]
    if s > 0:
        out = "..." + out
    if e < len(text):
        out = out + "..."
    return out


def _changed_span(a: str, b: str) -> tuple:
    """(start, end_a, end_b): the common prefix and suffix of a and b removed."""
    p = 0
    n = min(len(a), len(b))
    while p < n and a[p] == b[p]:
        p += 1
    s = 0
    while s < n - p and a[len(a) - 1 - s] == b[len(b) - 1 - s]:
        s += 1
    return p, len(a) - s, len(b) - s


def line_diff(old_lines, new_lines) -> tuple:
    """(added, removed, pairs): pairs are (old line or None, new line or None) for each changed line."""
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    added = removed = 0
    pairs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        olds, news = old_lines[i1:i2], new_lines[j1:j2]
        removed += len(olds)
        added += len(news)
        for k in range(max(len(olds), len(news))):
            pairs.append((olds[k] if k < len(olds) else None, news[k] if k < len(news) else None))
    return added, removed, pairs


def excerpt_pair(old, new) -> list:
    """Diff lines ('- ...', '+ ...') for one changed pair, each excerpt at most EXCERPT_CAP characters."""
    out = []
    if old is not None and new is not None:
        start, end_old, end_new = _changed_span(old, new)
        out.append("- " + excerpt(old, start, end_old))
        out.append("+ " + excerpt(new, start, end_new))
    elif old is not None:
        out.append("- " + excerpt(old))
    else:
        out.append("+ " + excerpt(new))
    return out


def _by_key(sections):
    return {s["heading"]: s for s in sections}


def _heading_label(heading: str):
    return heading if heading else Message("page.top")


def compare_full(old_sections, new_sections) -> dict:
    """Section-level diff with line detail. Returns a dict with lists changed/added/removed/renamed, totals,
    order_changed and excerpt blocks [(heading, [diff lines])]."""
    old, new = _by_key(old_sections), _by_key(new_sections)
    changed, added, removed, renamed, blocks = [], [], [], [], []
    plus = minus = 0
    quoted = 0
    not_quoted = 0
    for s in new_sections:
        h = s["heading"]
        if h in old:
            if old[h]["lines"] != s["lines"]:
                a, r, pairs = line_diff(old[h]["lines"], s["lines"])
                plus, minus = plus + a, minus + r
                changed.append({"heading": h, "added": a, "removed": r})
                lines = []
                in_section = 0
                for pair in pairs:
                    if in_section >= MAX_EXCERPTS_PER_SECTION or quoted >= MAX_EXCERPTS_PER_PAGE:
                        not_quoted += 1
                        continue
                    lines.extend(excerpt_pair(*pair))
                    in_section += 1
                    quoted += 1
                if lines:
                    blocks.append((h, lines))
    added_keys = [s["heading"] for s in new_sections if s["heading"] not in old]
    removed_keys = [s["heading"] for s in old_sections if s["heading"] not in new]
    # a removed and an added section with the same body: a renamed heading
    old_sha = {k: section_sha(old[k]) for k in removed_keys}
    for k in list(added_keys):
        sha = section_sha(new[k])
        match = next((o for o in removed_keys if old_sha[o] == sha), None)
        if match is not None:
            renamed.append({"old": match, "new": k})
            added_keys.remove(k)
            removed_keys.remove(match)
    for k in added_keys:
        n = len(new[k]["lines"])
        plus += n
        added.append({"heading": k, "lines": n})
        lines = []
        for line in new[k]["lines"]:
            if quoted >= MAX_EXCERPTS_PER_PAGE or len(lines) >= MAX_EXCERPTS_PER_SECTION:
                not_quoted += 1
                continue
            lines.append("+ " + excerpt(line))
            quoted += 1
        if lines:
            blocks.append((k, lines))
    for k in removed_keys:
        n = len(old[k]["lines"])
        minus += n
        removed.append({"heading": k, "lines": n})
        lines = []
        for line in old[k]["lines"]:
            if quoted >= MAX_EXCERPTS_PER_PAGE or len(lines) >= MAX_EXCERPTS_PER_SECTION:
                not_quoted += 1
                continue
            lines.append("- " + excerpt(line))
            quoted += 1
        if lines:
            blocks.append((k, lines))
    common_old = [s["heading"] for s in old_sections if s["heading"] in new]
    common_new = [s["heading"] for s in new_sections if s["heading"] in old]
    return {"mode": "full", "changed": changed, "added": added, "removed": removed, "renamed": renamed,
            "plus": plus, "minus": minus, "order_changed": common_old != common_new, "blocks": blocks,
            "not_quoted": not_quoted}


def section_meta(sections) -> list:
    """The public per-section record: heading, level, sha256 of the body, line and character counts."""
    return [{"heading": s["heading"], "level": s["level"], "sha256": section_sha(s), "lines": len(s["lines"]),
             "chars": sum(len(x) for x in s["lines"])} for s in sections]


def compare_meta(old_meta, new_meta) -> dict:
    """Section-level diff from public metadata only (heading, sha256, lines): names, no line detail."""
    old = {s["heading"]: s for s in old_meta}
    new = {s["heading"]: s for s in new_meta}
    added = [s["heading"] for s in new_meta if s["heading"] not in old]
    removed = [s["heading"] for s in old_meta if s["heading"] not in new]
    renamed = []
    for k in list(added):
        match = next((o for o in removed if old[o].get("sha256") == new[k]["sha256"]), None)
        if match is not None:
            renamed.append({"old": match, "new": k})
            added.remove(k)
            removed.remove(match)
    common_old = [s["heading"] for s in old_meta if s["heading"] in new]
    common_new = [s["heading"] for s in new_meta if s["heading"] in old]
    return {"mode": "hash",
            "changed": [{"heading": s["heading"]} for s in new_meta
                        if s["heading"] in old and old[s["heading"]].get("sha256") != s["sha256"]],
            "added": [{"heading": k, "lines": new[k].get("lines", 0)} for k in added],
            "removed": [{"heading": k, "lines": old[k].get("lines", 0)} for k in removed],
            "renamed": renamed, "plus": None, "minus": None, "order_changed": common_old != common_new,
            "blocks": [], "not_quoted": 0}


def compare_hashes(old_meta_sections, new_sections) -> dict:
    """The previous full text is gone: compare the public per-section hashes with the new page."""
    return compare_meta(old_meta_sections, section_meta(new_sections))


def is_empty(diff: dict) -> bool:
    return not (diff["changed"] or diff["added"] or diff["removed"] or diff["renamed"] or diff["order_changed"])


def summary_message(diff: dict) -> Joined:
    parts = []
    if diff["changed"]:
        parts.append(Message("page.sum_changed", n=len(diff["changed"])))
    if diff["added"]:
        parts.append(Message("page.sum_added", n=len(diff["added"])))
    if diff["removed"]:
        parts.append(Message("page.sum_removed", n=len(diff["removed"])))
    if diff["renamed"]:
        parts.append(Message("page.sum_renamed", n=len(diff["renamed"])))
    if diff["plus"] is not None and (diff["plus"] or diff["minus"]):
        parts.append(Message("page.sum_lines", added=diff["plus"], removed=diff["minus"]))
    if not parts and diff["order_changed"]:
        parts.append(Message("page.order_changed"))
    return Joined(parts)


def detail_messages(diff: dict) -> list:
    out = []
    for c in diff["changed"]:
        if diff["mode"] == "full":
            out.append(Message("page.section_changed", heading=_heading_label(c["heading"]), added=c["added"],
                               removed=c["removed"]))
        else:
            out.append(Message("page.section_changed_hash", heading=_heading_label(c["heading"])))
    for a in diff["added"]:
        out.append(Message("page.section_added", heading=_heading_label(a["heading"]), lines=a["lines"]))
    for r in diff["removed"]:
        out.append(Message("page.section_removed", heading=_heading_label(r["heading"]), lines=r["lines"]))
    for r in diff["renamed"]:
        out.append(Message("page.section_renamed", old=_heading_label(r["old"]), new=_heading_label(r["new"])))
    if diff["order_changed"] and (diff["changed"] or diff["added"] or diff["removed"] or diff["renamed"]):
        out.append(Message("page.order_changed"))
    return out
