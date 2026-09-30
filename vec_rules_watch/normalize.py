"""Turn a fetched page into stable text split into sections by heading, and JSON into a canonical form.

HTML: only the page's <main> element is read (the site navigation, header and footer are outside it); inside it,
scripts, styles, inline SVG, <nav>, <aside> (the "On this page" box), <button> and <template> are dropped. Block
elements end a line, table cells are joined with " | ", whitespace is collapsed, text is NFC-normalised. Headings
h1-h4 start a new section; h5/h6 stay inside the section as a line starting with "#####". Text before the first
heading goes into a section with an empty heading (shown as "(top)").

Nothing here is specific to one page: a page whose layout moves text out of <main> shows up as a change, not as a
crash, and a page with no <main> at all falls back to the whole <body> minus header, footer and nav.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

SECTION_LEVELS = (1, 2, 3, 4)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
DROP = {"script", "style", "noscript", "svg", "template", "nav", "aside", "button", "iframe", "canvas", "select",
        "head", "title", "math"}
FALLBACK_DROP = {"header", "footer"}
BLOCK = {"address", "article", "blockquote", "caption", "dd", "details", "dialog", "div", "dl", "dt", "fieldset",
         "figcaption", "figure", "form", "li", "main", "ol", "p", "section", "summary", "table", "tbody", "tfoot",
         "thead", "tr", "ul", "label", "legend", "time"}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
CELLS = {"td", "th"}
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)
_SPACES = re.compile(r"\s+")


def clean_line(text: str) -> str:
    """NFC, zero-width characters removed, every run of whitespace (NBSP included) collapsed to one space."""
    text = unicodedata.normalize("NFC", text).translate(_ZERO_WIDTH)
    return _SPACES.sub(" ", text).strip()


class _Extractor(HTMLParser):
    def __init__(self, main_only: bool):
        super().__init__(convert_charrefs=True)
        self.main_only = main_only
        self.blocks: list = []          # (level, text); level 0 = ordinary line
        self._stack: list = []
        self._drop = 0
        self._main = 0
        self._pre = 0
        self._heading = 0
        self._cur: list = []

    # -- tag bookkeeping (a stack, so a stray or omitted end tag cannot derail the drop / main counters) --
    def _dropping(self) -> bool:
        return self._drop > 0 or (self.main_only and self._main == 0)

    def _enter(self, tag):
        if tag in DROP or (not self.main_only and tag in FALLBACK_DROP):
            self._drop += 1
        if tag == "main":
            self._main += 1
        if self._dropping() and tag != "main":
            return
        if tag in HEADINGS:
            self._flush()
            self._heading = HEADINGS[tag]
        elif tag == "pre":
            self._flush()
            self._pre += 1
        elif tag in BLOCK or tag == "tr":
            self._flush()
        elif tag in CELLS:
            if "".join(self._cur).strip():
                self._cur.append(" | ")

    def _leave(self, tag):
        if not self._dropping() or tag == "main":
            if tag in HEADINGS:
                self._flush()
                self._heading = 0
            elif tag == "pre":
                self._flush()
                self._pre = max(0, self._pre - 1)
            elif tag in BLOCK:
                self._flush()
        if tag in DROP or (not self.main_only and tag in FALLBACK_DROP):
            self._drop = max(0, self._drop - 1)
        if tag == "main":
            self._flush()
            self._main = max(0, self._main - 1)

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            if tag in ("br", "hr") and not self._dropping():
                self._flush()
            return
        self._stack.append(tag)
        self._enter(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in ("br", "hr") and not self._dropping():
            self._flush()

    def handle_endtag(self, tag):
        if tag in VOID or tag not in self._stack:
            return
        while self._stack:
            t = self._stack.pop()
            self._leave(t)
            if t == tag:
                break

    def handle_data(self, data):
        if self._dropping():
            return
        if self._pre:
            parts = data.split("\n")
            for i, part in enumerate(parts):
                if i:
                    self._flush()
                self._cur.append(part)
        else:
            self._cur.append(data)

    def _flush(self):
        raw = "".join(self._cur)
        self._cur = []
        text = clean_line(raw)
        if text:
            self.blocks.append((self._heading, text))

    def close(self):
        super().close()
        self._flush()


def html_blocks(html: str) -> tuple:
    """(blocks, used_main): blocks is a list of (heading level or 0, text)."""
    has_main = re.search(r"<main[\s>]", html, flags=re.IGNORECASE) is not None
    p = _Extractor(main_only=has_main)
    p.feed(html)
    p.close()
    return p.blocks, has_main


def blocks_to_sections(blocks) -> list:
    """Group (level, text) blocks into sections [{heading, level, lines}]; duplicate headings get " (2)", " (3)"."""
    sections = []
    cur = {"heading": "", "level": 0, "lines": []}
    seen: dict = {}
    for level, text in blocks:
        if level in SECTION_LEVELS:
            if cur["lines"] or cur["heading"]:
                sections.append(cur)
            n = seen.get(text, 0) + 1
            seen[text] = n
            cur = {"heading": text if n == 1 else f"{text} ({n})", "level": level, "lines": []}
        elif level:
            cur["lines"].append("#" * level + " " + text)
        else:
            cur["lines"].append(text)
    if cur["lines"] or cur["heading"]:
        sections.append(cur)
    return sections


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs: list = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def site_links(html: str, page_url: str, prefix: str = "/challenge") -> list:
    """Sorted paths (with query, without fragment) of every <a href> on the page - navigation and footer included -
    that stays on the page's host under `prefix`. Used to notice a page the watch list does not cover yet."""
    p = _Links()
    p.feed(html)
    p.close()
    base = urlsplit(page_url)
    out = set()
    for href in p.hrefs:
        u = urlsplit(urljoin(page_url, href))
        if u.scheme not in ("http", "https") or u.netloc != base.netloc:
            continue
        if not (u.path == prefix or u.path.startswith(prefix + "/")):
            continue
        out.add(u.path.rstrip("/") + (("?" + u.query) if u.query else ""))
    return sorted(out)


def html_to_sections(html: str) -> tuple:
    """(sections, used_main)."""
    blocks, used_main = html_blocks(html)
    return blocks_to_sections(blocks), used_main


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def section_sha(section: dict) -> str:
    """Hash of a section's body lines (the heading is its key; a renamed heading with the same body keeps its hash)."""
    return sha256_text("\n".join(section["lines"]))


def page_sha(sections) -> str:
    return sha256_text(sections_to_text(sections))


def text_chars(sections) -> int:
    return sum(len(s["heading"]) + sum(len(x) for x in s["lines"]) for s in sections)


# -- readable text form (used for --full-text and for the local diff command) --

def sections_to_text(sections) -> str:
    """Headings as '#' * level + ' ' + heading; a body line that starts with '#' or '\\' is escaped with '\\'."""
    out = []
    for s in sections:
        if s["level"]:
            out.append("#" * s["level"] + " " + s["heading"])
        for line in s["lines"]:
            out.append("\\" + line if line.startswith(("#", "\\")) else line)
    return "\n".join(out) + "\n"


def text_to_sections(text: str) -> list:
    """Inverse of sections_to_text."""
    blocks = []
    for line in text.splitlines():
        if not line.strip():
            continue
        m = re.match(r"^(#{1,6}) (.*)$", line)
        if m and len(m.group(1)) in SECTION_LEVELS:
            blocks.append((len(m.group(1)), m.group(2)))
        elif line.startswith("\\"):
            blocks.append((0, line[1:]))
        else:
            blocks.append((0, line))
    sections = []
    cur = {"heading": "", "level": 0, "lines": []}
    for level, t in blocks:
        if level:
            if cur["lines"] or cur["heading"]:
                sections.append(cur)
            cur = {"heading": t, "level": level, "lines": []}
        else:
            cur["lines"].append(t)
    if cur["lines"] or cur["heading"]:
        sections.append(cur)
    return sections


# -- JSON --

def canonical_json(obj) -> str:
    """Sorted keys, two-space indent, ASCII-escaped, trailing newline: the same object always gives the same bytes."""
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def parse_json_bytes(data: bytes):
    return json.loads(data.decode("utf-8-sig"))
