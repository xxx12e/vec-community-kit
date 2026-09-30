"""Message catalogue: fixed English and Chinese templates in messages.json (read as UTF-8), filled with str.format.

A Message is a template key plus its parameters, so one change renders into both languages. Parameters that are
themselves language-dependent (a "none", a sub-template) are passed as Message objects and rendered in the same
language. The organisers' own text (labels, excerpts, commit subjects) passes through unchanged in both files.
"""
from __future__ import annotations

import json
import string
from functools import lru_cache
from pathlib import Path

LANGS = ("en", "zh")
CATALOGUE = Path(__file__).resolve().parent / "messages.json"


@lru_cache(maxsize=1)
def catalogue() -> dict:
    with open(CATALOGUE, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def placeholders(template: str) -> set:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


class Message:
    __slots__ = ("key", "params")

    def __init__(self, key: str, **params):
        if key not in catalogue():
            raise KeyError(f"unknown message key {key!r}")
        self.key = key
        self.params = params

    def render(self, lang: str) -> str:
        params = {k: (v.render(lang) if isinstance(v, Message) else _fmt(v, lang)) for k, v in self.params.items()}
        return catalogue()[self.key][lang].format(**params)

    def __repr__(self):
        return f"Message({self.key!r}, {self.params!r})"


class Joined:
    """A list of parts rendered in one language and joined with that language's separator (word.sep)."""

    def __init__(self, parts, empty: str = "word.none"):
        self.parts = list(parts)
        self.empty = empty

    def render(self, lang: str) -> str:
        if not self.parts:
            return catalogue()[self.empty][lang]
        sep = catalogue()["word.sep"][lang]
        return sep.join(p.render(lang) if isinstance(p, (Message, Joined)) else _fmt(p, lang) for p in self.parts)


def _fmt(value, lang: str) -> str:
    if isinstance(value, Joined):
        return value.render(lang)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(str(x) for x in value) + "]"
    return str(value)


def text(key: str, lang: str, **params) -> str:
    return Message(key, **params).render(lang)


def has(key: str) -> bool:
    return key in catalogue()
