"""Credential-shaped strings are replaced before anything is written (stdlib only, ASCII only).

The patterns are the evidence skeleton's own (vec_agent_evidence/common.py SECRET_PATTERNS: key prefixes followed by
key characters, OAuth / auth-file token fields, OpenCode auth.json entries), so the lens and the packagers agree on
what counts as a credential. A key-shaped match is replaced by [REDACTED:<label>]; for a token FIELD the value that
follows the field name is replaced too. Literal values (e.g. a gateway key read from an environment variable) can be
added. This is best effort: a secret that has no recognisable shape and was not passed in is not found.
"""
from __future__ import annotations

import re

from vec_agent_evidence import common as C

# patterns that match a field NAME; the value after it is redacted as well
FIELD_LABELS = {"oauth_access_token_field", "oauth_refresh_token_field", "oauth_credentials_block", "auth_token_field",
                "opencode_auth_entry"}
_VALUE_TAIL = r'(?:\s|\\[nrt])*(?:\\?"(?:[^"\\\n]|\\.){0,4096}?\\?"|[^\s,}\]]{1,4096})?'


def _as_str_regex(rx) -> str:
    p = rx.pattern
    return p.decode("ascii") if isinstance(p, bytes) else p


class Redactor:
    def __init__(self, extra_values=()):
        self.patterns = []
        for label, rx in C.SECRET_PATTERNS:
            pat = _as_str_regex(rx)
            if label in FIELD_LABELS:
                pat = "(?:" + pat + ")" + _VALUE_TAIL
            self.patterns.append((label, re.compile(pat)))
        self.extra = [(f"extra_value_{i}", re.compile(re.escape(str(v)))) for i, v in enumerate(extra_values) if v]
        self.counts: dict = {}

    @property
    def labels(self) -> list:
        return [label for label, _ in self.patterns + self.extra]

    def text(self, s):
        """(redacted string, changed?) for a string; anything else is returned unchanged."""
        if not isinstance(s, str) or not s:
            return s, False
        changed = False
        for label, rx in self.extra + self.patterns:
            s2, n = rx.subn(f"[REDACTED:{label}]", s)
            if n:
                self.counts[label] = self.counts.get(label, 0) + n
                s, changed = s2, True
        return s, changed

    def obj(self, o):
        """Deep copy of a JSON-like object with every string redacted; returns (object, changed?)."""
        if isinstance(o, str):
            return self.text(o)
        if isinstance(o, list):
            out, ch = [], False
            for x in o:
                y, c = self.obj(x)
                out.append(y)
                ch = ch or c
            return out, ch
        if isinstance(o, dict):
            out, ch = {}, False
            for k, v in o.items():
                k2, c1 = self.text(k) if isinstance(k, str) else (k, False)
                v2, c2 = self.obj(v)
                out[k2] = v2
                ch = ch or c1 or c2
            return out, ch
        return o, False

    def event(self, ev) -> bool:
        """Redact every string field of an Event in place; flag it "redacted" when something was replaced."""
        changed = False
        for name in ("text", "command", "tool", "model", "call_id", "session", "source", "msg_id"):
            v, c = self.text(getattr(ev, name))
            if c:
                setattr(ev, name, v)
                changed = True
        files, c = self.obj(ev.files)
        if c:
            ev.files, changed = files, True
        if changed and "redacted" not in ev.flags:
            ev.flags.append("redacted")
        return changed


def scan_bytes(data: bytes, extra_values=()) -> list:
    """Labels of the credential patterns (plus literal values) found in raw bytes."""
    found = [label for label, rx in C.SECRET_PATTERNS if rx.search(data)]
    found += [f"extra_value_{i}" for i, v in enumerate(extra_values) if v and str(v).encode("utf-8") in data]
    return found
