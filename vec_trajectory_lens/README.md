# vec_trajectory_lens - Trajectory Lens: one readable offline report of an agent run

An Agent-track run leaves a log of thousands of JSON lines: model messages, tool calls, tool outputs, token counts.
The rules ask for that trajectory as evidence, and the organisers may audit it. Trajectory Lens turns such a log into
**one self-contained HTML file** (a summary card and a timeline you can filter) and a **summary JSON**, so a team can
check its own run before choosing which completed run to submit, and a reviewer can read a run without installing the
agent's CLI. It works offline: the HTML loads nothing, not even a font.

Chinese: [`docs/trajectory_lens_zh.md`](../docs/trajectory_lens_zh.md).

```
python -m vec_trajectory_lens <log file | run or package directory | .zip> --out report.html --json summary.json
    [--framework auto|claude|codex|opencode] [--session ID] [--events events.jsonl] [--redact-env NAME] [--max-text 3000]
```

(`vec-community-lens` is the same command after `pip install -e .`.) Exit code 0 when written, 2 when the input
cannot be read, 3 when an output was refused (see "Secrets").

## What it reads

| framework | input | status |
|---|---|---|
| Claude Code | stdout of `claude -p --output-format stream-json --verbose`; the session JSONL the CLI writes (`~/.claude/projects/<project>/<session>.jsonl`, with `<session>/subagents/*.jsonl` added when present); this kit's run directory (`transcript/` first, else `stream.jsonl`) | field names checked against the kit's own launcher and against a session file written by the CLI (structure only; no content was copied); tests use synthetic logs |
| Codex CLI | stdout of `codex exec --json` (current and older event shapes); the session rollout (turns from its `task_complete` records, failed tool calls from the exit code in each tool output); an unzipped `codex-package` (a full rollout is read on its own; a `--rollout dedup` copy is read together with the stream, which carries what it dropped) | the parsing of `vec_agent_evidence/codex.py` (written from the Codex documentation), plus record names checked in the Codex source (openai/codex main, read 2026-09-30); synthetic logs only, not a live run |
| OpenCode | stdout of `opencode run --format json`; an `opencode export <sessionID>` document (also the `session_export.json` of `opencode-package`); OpenCode's database (`opencode.db`, read-only, session tables only; `--session` or the most recent session); a data directory (its database first; the JSON `storage/` of OpenCode up to v1.1.x only when there is no database or the session is not in it); `storage/` itself | the reading code of `vec_agent_evidence/opencode.py` (checked against the OpenCode source, tag v1.18.33); synthetic files only, not a live run |
| PantheonOS | - | **not yet**: its documentation says where sessions are stored (`.pantheon/memory/<id>_<name>.jsonl`, one JSON object per turn) but not the fields of a line, so a parser would be a guess |

**OpenCode data directory.** OpenCode v1.2.0 copied the old `storage/` files into the database and left them in
place, so an upgraded data directory holds both: the database is read, and the report says that `storage/` was not.
With several databases (`opencode.db`, `opencode-<channel>.db` of another install channel, or a relative
`OPENCODE_DB` name) the one that holds `--session` - without `--session`, the one with the most recently updated
session - is read and named in the report. An absolute `OPENCODE_DB` is not followed: pass that database file itself.
The database is opened read-only and never changed. When OpenCode has exited (no `-wal` file next to it) it is opened
immutable, so SQLite creates no side files either; while a `-wal` file exists (OpenCode still running, or not shut
down cleanly) SQLite may create a `-shm` file next to it. Run the lens after OpenCode has exited.

A `.zip` (e.g. `trajectory.zip` or `evidence_bundle.zip` as uploaded) is extracted into a temporary directory first
(at most 1 GB; entries that would land outside it are skipped). Parsers are pluggable: a new framework is one module
in `parsers/` that calls `register(name, label, sniff, parse)`; `--framework auto` picks the parser whose sniffer
scores the first lines highest.

## The unified event schema (`schema.py`, `vec-trajectory-lens/1`)

Every parser writes the same events: `kind` (user / assistant / tool_call / tool_result / system), `ts` (UTC ISO
8601, when the log has it), `actor` (user / agent / subagent / tool / system), `tool`, `command` (shell calls),
`files` + `file_op` (read / write / edit), `model`, `usage` (input / output / cache_read / cache_write / reasoning,
when present), `text`, `call_id` (links a result to its call), `is_error`, `subkind` (thinking, reasoning, init,
result, turn, step, meta, patch, ...), `session`, `source` (file and line), `flags` (network, redacted), `msg_id`.
`--events out.jsonl` writes them (redacted, not shortened further; the parsers already cap a written file's content
at 4000 characters and a JSON tool input at 20000) after a header line; `Event.from_dict` reads them back.

**Order.** Inside one file (and one session) the events keep the order of the log. Several files of one run (a
Claude Code session and its subagent files, a Codex rollout and stream) and several sessions in one export (OpenCode
subagents) are merged by time. The Codex `exec --json` stream has no timestamps, so its events are placed after the
dedup rollout records it was read with (session, turn context, user prompt).

## The summary card (HTML) and summary JSON

Framework and CLI version (as the log records it), every model string seen (flagged when there is more than one - a
subagent on a smaller model shows up here), turns (with what a turn means for that framework), tool calls by tool and
how many failed, token totals (input / output / cache read / cache write / reasoning, counted once per model
response: Claude Code repeats a response's usage on every line of that response, OpenCode keeps only the last step's
usage on a message), the CLI's own totals when it reports them, wall time (first to last timestamp, or the CLI's
duration), files written and edited by the file tools (see Limits), network-shaped commands, the secret-scan result,
the input files with sha256,
and a "what this report does not show" box. The timeline filters by kind, tool, actor, free text, flagged and
failed events; each event opens to its full text (shortened in the HTML after `--max-text` characters).

**Network-shaped commands** are flagged with the same patterns as the evidence skeleton's guard hook
(`vec_agent_evidence/hooks/guard.py`: curl, wget, pip / conda install, git clone / fetch / pull / push, ssh, scp,
requests / httpx / urllib / socket, huggingface_hub, any http(s) URL, ...) applied to shell commands, plus the web
tools by name (WebFetch, WebSearch, webfetch, web_search, ...). A flag means "looks like network access", not that it
happened or that a rule was broken; in a guarded run, the tool result usually shows the denial.

## Secrets

The input files are scanned with the evidence skeleton's credential patterns (`vec_agent_evidence/common.py`: key
prefixes, OAuth and auth-file token fields, OpenCode `auth.json` entries); the result is in the summary. Every string
that goes into an output is redacted with the same patterns - `[REDACTED:<pattern>]`, and for a token field the value
after it too - plus the literal value of each `--redact-env NAME` variable (for a gateway key that has no recognisable
shape; the value is read from the environment, never typed on the command line). Before anything is written, every
output is scanned once more; if a credential-shaped string survived, nothing is written and the exit code is 3. When
the input holds credential-shaped strings, the report says so: redacting the report does not clean the original
log, which must not be uploaded as it is.

## Limits (read this)

* It reads logs. It does not prove that a run was autonomous, that its configuration was locked, that nobody
  intervened, or that the rules were followed; a log can be incomplete or edited, and this tool cannot tell.
* Network flags are regular expressions over command text: obfuscated or indirect network access (Python code that
  opens a socket from a file) is not seen, and a harmless command can be flagged.
* The secret scan and the redaction find credential-SHAPED strings and the values you pass; a secret without a
  recognisable shape is not found.
* Hidden reasoning that the framework did not store is not in the log, so it is not in the report.
* "Files written / edited" lists only the files named by file-tool calls (Claude Code Write / Edit, Codex
  file_change / apply_patch, OpenCode write / edit / patch). A file that a shell command writes (for example
  `python predict.py --out out/pred.h5ad`, which is how predictions are usually written) is not listed: read the
  shell commands in the timeline. An empty list does not mean that the agent wrote nothing.
* Codex token totals: `turn.completed` carries the thread's running total, so the last total is shown, not a sum;
  if the values do not grow from turn to turn they are summed, and the summary says which was done.
* Only the Claude Code field names were checked against a file the CLI wrote; the Codex and OpenCode readers were
  written from documentation / source and tested on synthetic files. Please report a log it misreads.
* Large logs: a synthetic 22 MB log with 12,000 events gave a 30 MB report in about 6 seconds; the timeline
  draws 400 events at a time.

## Related work

**VEC Evidence Check** (Alex Solonsky, already filed) hashes and seals a run package offline so it can be verified
later. Trajectory Lens is complementary: it does not hash or seal anything, it makes the log readable. Use both - seal
the package, then read the report. Within this kit, `vec_agent_evidence` produces the evidence (lock, hooks,
packagers); the lens reads the trajectories those packagers collect and the logs of runs made without them.
