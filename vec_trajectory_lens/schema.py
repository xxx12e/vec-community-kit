"""The unified event schema every parser writes (stdlib only, ASCII only).

One Event per thing that happened in an agent run, whatever the framework:

  kind      user | assistant | tool_call | tool_result | system
  ts        ISO 8601 UTC timestamp ("2026-09-30T01:02:03.456Z") or None when the log has none
  actor     user | agent | subagent | tool | system
  tool      tool name for tool_call / tool_result (as the framework names it: Bash, bash, shell, ...)
  command   the shell command of a shell tool call
  files     paths a tool call names; file_op says what it does with them (read / write / edit)
  model     the model string that produced an assistant event
  usage     token usage attached to this event: any of input, output, cache_read, cache_write, reasoning
  text      the readable content (message text, tool input or output); may be truncated in the HTML report
  call_id   links a tool_result to its tool_call
  is_error  a failed tool call, a non-zero exit code, an error event
  subkind   finer label: thinking, reasoning, init, result, turn, step, error, meta, attachment, patch, ...
  session   session / thread id the event belongs to
  source    "<file name>:<line>" (or "<file name>#<index>") where it was read
  flags     e.g. "network" (network-shaped command), "redacted" (a credential-shaped string was replaced)
  msg_id    the model response an assistant event belongs to (one response can span several events)

Serialised with to_dict() (fields that are None / empty are left out) and read back with Event.from_dict().
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields

SCHEMA = "vec-trajectory-lens/1"
KINDS = ("user", "assistant", "tool_call", "tool_result", "system")
ACTORS = ("user", "agent", "subagent", "tool", "system")
USAGE_KEYS = ("input", "output", "cache_read", "cache_write", "reasoning")
FILE_OPS = ("read", "write", "edit")


@dataclass
class Event:
    kind: str
    ts: str | None = None
    actor: str = "agent"
    tool: str | None = None
    command: str | None = None
    files: list = field(default_factory=list)
    file_op: str | None = None
    model: str | None = None
    usage: dict | None = None
    text: str = ""
    call_id: str | None = None
    is_error: bool | None = None
    subkind: str | None = None
    session: str | None = None
    source: str | None = None
    flags: list = field(default_factory=list)
    msg_id: str | None = None

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown event kind {self.kind!r}; one of {KINDS}")
        if self.actor not in ACTORS:
            raise ValueError(f"unknown actor {self.actor!r}; one of {ACTORS}")
        if self.file_op is not None and self.file_op not in FILE_OPS:
            raise ValueError(f"unknown file_op {self.file_op!r}; one of {FILE_OPS}")
        if self.usage is not None:
            self.usage = {k: self.usage[k] for k in USAGE_KEYS if isinstance(self.usage.get(k), (int, float))} or None
        self.files = [str(f) for f in self.files or [] if f]
        self.text = "" if self.text is None else str(self.text)

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", [], {})}

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        names = {f.name for f in fields(cls)}
        unknown = set(d) - names
        if unknown:
            raise ValueError(f"unknown event field(s) {sorted(unknown)}")
        return cls(**d)


def usage_from(mapping: dict | None, **names) -> dict | None:
    """Pick token counts out of a framework's usage object: usage_from(u, input="input_tokens", output=...)."""
    if not isinstance(mapping, dict):
        return None
    out = {}
    for key, src in names.items():
        v = mapping
        for part in src.split("."):
            v = v.get(part) if isinstance(v, dict) else None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = v
    return out or None
