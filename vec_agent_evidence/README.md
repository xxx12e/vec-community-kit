# vec_agent_evidence - Agent-track evidence skeleton

The Agent track of the Virtual Embryo Challenge is scored on the same hidden tests as the Human track; what
distinguishes an Agent entry is **autonomy after the configuration lock** and the **evidence** uploaded with the
prediction. The rules (challenge site, Agent Team section):

* The lock is the moment a run starts. Before it, anything goes: write the harness, choose the model, draft the
  prompts, set budgets, run as many times as you like. After it, no human reads intermediate results or steers,
  no configuration changes mid-run, no picking among a run's intermediate outputs. Choosing WHICH COMPLETED RUN
  to submit is allowed.
* The submitted file must be unedited agent output. Any human edit (by hand, script or substitution) makes it a
  non-Agent entry.
* At least TWO distinct kinds of evidence from {trajectory, prompts (every prompt including the initial one),
  harness (orchestration code, tools, evaluation loop)} must be uploaded against a submission before it is
  scored. The evidence must come from the exact run that produced the file. Organisers may audit and ask you to
  re-run the harness. Limits: 200 MB per evidence file, 600 MB per team in total.

This package makes producing that evidence mechanical. What it produces is an auditable evidence bundle -
configuration snapshots, integrity checks (hashes re-verified after the run), best-effort guard hooks and an audit
log. It does not independently attest that a run complied with the rules; the organisers' audit decides that, and
this bundle is what you hand them. The current implementation targets the Claude Code CLI
in headless mode (`claude -p --output-format stream-json`) because it exposes everything needed: a transcript per
session id, hooks that can deny and log tool calls, a settings file for deny rules, and an init event that echoes
the model and tool set actually used. The same layout works for any agent CLI that can be started from a command
line and writes a machine-readable trajectory, but you must adapt `launch.build_command` (and the stream-event
parsing in `launch.launch` if the CLI's output differs).

What the hooks are and are not: `hooks/guard.py` and `hooks/audit.py` are **regex hooks** over the tool input.
They reject recognised network commands and restricted file operations, and they log every tool call; the audit
log and the hashes in `config.lock.json` / `run_manifest.json` support post-run verification. They are not a
network sandbox (see "The hooks" and "Limitations").

## What a run directory contains

```
runs/<YYYYMMDD-HHMM>_<task>_<8hex>/
  config.lock.json + config.lock.sha256   everything frozen at lock time (see below)
  initial_prompt.md                        rendered initial prompt (byte-exact, hashed)
  system_prompt_appendix.md                optional appendix (hashed)
  claude_settings.json                     hooks + deny rules (hashed)
  prompts.manifest.json                    hashes and sizes of the prompt files
  hooks/guard.py, hooks/audit.py           run-local copies of the hooks (hashed)
  hooks/tool_audit.jsonl                   one line per tool call (PostToolUse / SessionStart / Stop ...)
  hooks/guard_denials.jsonl                every denied tool call with the reason
  harness_snapshot.zip                     the kit code + the templates used
  workspace/                               what the agent sees (tools/ read-only, data link, NOTES.md, src/, out/)
  submission/pred_<board>.h5ad + MANIFEST.json   written only by tools/finalize_submission.py
  stream.jsonl, stderr.log                 the agent CLI's stdout (stream-json) and stderr, byte for byte
  launch_command.json, launch_state.json   exact argv + redacted env; init assertion, deadline / stall / kill state
  transcript/<session-id>.jsonl            the CLI transcript, copied by session id after the run
  artifacts/                               small agent outputs copied from the workspace (src/, NOTES.md, ...)
  env/                                     pip freeze, platform, kit git head, CLI version + sha256
  run_manifest.json                        written by postrun: hashes of every evidence file, lock re-verification,
                                           secret scan, sizes vs the portal limits, result / usage of the run
```

`config.lock.json` records: run id, session UUID, task and boards, model / effort / max turns / budget, wall clock
and deadline, tool policy (allowed + disallowed tools, permission mode), seed, child environment overrides, the
sha256 of every data file under the data root, sha256 of the prompt / appendix / settings bytes, hook hashes, the
snapshot hash, the kit's git commit and dirty state, and the CLI binary path / version / sha256.

Transcript coverage: `postrun` copies the CLI transcript located by the run's session UUID
(`transcript/<id>.jsonl`) plus the CLI's `tool-results/` and `subagents/` side directories when they exist. The
kit's default tool policy disallows the `Task` / `Agent` tools, so a default run is one session with one
transcript; if you enable subagents, check that their transcripts landed under `transcript/subagents/` before you
rely on them. A resumed or continued session is outside what the lock covers: never resume a run (see below), and
do not package a resumed run as Agent-track evidence.

## Commands

```
# 1. dry run with a stand-in agent (no API calls): exercises lock -> launch -> postrun -> package
python -m pytest tests/test_evidence.py -q

# 2. lock only (inspect the run directory and the exact launch command, nothing is launched)
python -m vec_agent_evidence lock --task T3 --prompt vec_agent_evidence/example_prompt.md --model <model-id> \
    --data-root ./data --hours 8

# 3. a real run: lock -> claude -p -> postrun; from the lock message on, the human walks away
python -m vec_agent_evidence run --task T2 --boards T2:heart:val_extrap --prompt my_prompt.md \
    --model <model-id> --data-root ./data --hours 10 --max-turns 600

# 4. recovery only (harness crashed after the agent exited)
python -m vec_agent_evidence postrun --run-dir runs/<run_id>

# 5. upload package: predictions/ + trajectory.zip + prompts.zip + harness.zip + evidence_bundle.zip + README.md
python -m vec_agent_evidence package --run-dir runs/<run_id> --team-uploaded-mb 120   # 120 = what your team already uploaded
```

`--data-root` is a directory holding the released .h5ad files (any layout; every `*.h5ad` under it is hashed into
the lock) and optionally `panels/` (index.json + genes files; the kit's own `data/panels` is used otherwise).
Prompt and settings templates may use the placeholders listed in `lock.template_values` (`{{RUN_ID}}`,
`{{DEADLINE_UTC}}`, `{{BOARD_CONTRACT_TABLE}}`, `{{DATA_FILES_TABLE}}`, `{{PYTHON_POSIX}}`, ...); an unknown or
unrendered placeholder fails the lock.

## Codex CLI runs: `codex-package` (minimal adapter, untested against a live Codex run)

The Codex CLI is the second most declared agent framework on the portal. `codex.py` packages a **finished**
`codex exec --json` run into the same three evidence kinds, so a Codex team can attach trajectory + prompts (+
harness) the same way. It is deliberately minimal:

* **Untested against a live Codex run.** It was written from the Codex CLI's documentation
  (https://developers.openai.com/codex/noninteractive, read 2026-09-30, which lists the event types and shows a
  sample stream) and our understanding of Codex's session ("rollout") files, which that page does not describe. It
  is tested only on synthetic transcripts written from those names (`tests/test_codex_adapter.py`):
  `thread.started`, `turn.started` / `turn.completed` (usage) / `turn.failed`, `item.started` / `item.completed`
  with `command_execution`, `file_change`, `agent_message`, `reasoning`, ... items, and the older
  `{"id", "msg": {"type": ...}}` shape. The trajectory is always a byte copy of what Codex wrote; only the summary
  depends on those names, and an unknown format yields an empty summary plus a warning, never a dropped line.
  Please report a real transcript that it misreads.
* **After the fact only.** No configuration lock, launcher, wall clock or guard / audit hooks (the Claude Code path
  above has them). Codex's own sandbox (`--sandbox workspace-write`) is the enforcement layer; lock your prompt and
  harness yourself before the run (a commit hash is enough) and keep the exact command.

Run Codex with its JSON event stream on stdout (check `codex exec --help` for your version; `codex exec -` reads
the whole prompt from stdin). Do not pass `--ephemeral`: it suppresses the rollout file. `--ignore-user-config`
keeps `$CODEX_HOME/config.toml` out of the run; if you do rely on that file, pass it with `--harness` so the
evidence shows the configuration that ran (the credential scan applies). Then package:

```
codex exec --json --model <model> --sandbox workspace-write --skip-git-repo-check --cd <workspace> - \
    < prompt.md > codex_stream.jsonl 2> codex_stderr.log

python -m vec_agent_evidence codex-package --stream codex_stream.jsonl --stderr codex_stderr.log \
    --prompt prompt.md --workspace <workspace> --prediction T3:gata4=<workspace>/out/pred.h5ad \
    --command-file cmd.txt --harness my_loop.py --model <model> --out runs/_upload_codex/run1 [--rollout dedup]
```

| kind | what goes in |
|---|---|
| trajectory | `codex_stream.jsonl` (byte copy), `codex_stderr.log`, the session rollout(s) found by thread id under `$CODEX_HOME/sessions` (default `~/.codex`) as chosen by `--rollout` (below), `trajectory_summary.json` (turns, usage, commands, files changed, errors) |
| prompts | `initial_prompt.md` (byte copy of `--prompt`), every `AGENTS.md` / `AGENTS.override.md` Codex reads from the workspace and from `$CODEX_HOME` (global instructions), `user_messages.jsonl` (every user-role message found in the rollout) |
| harness | the `--harness` files, `command.txt` (`--command-file`), `codex_manifest.json` (framework and model string, hashes of every evidence file, the summary, warnings) |

`predictions/` holds byte-identical copies of the `--prediction` files after the board-contract check. The packager
**refuses** on a credential-shaped string anywhere in the evidence (including OpenAI-style keys and auth-file token
fields), a file or zip over 200 MB, a stream with no JSON events, or a prediction that fails its board contract.
It **warns** (in `README.md` and the manifest) when no rollout is found, the model string is unknown or differs from
what Codex recorded, no turn completed, the prediction's file name never appears in the stream (no visible
provenance), the prompt is not among the rollout's user messages, or the copied rollout(s) add more than 10 MB.

**The session rollout and the 600 MB team cap.** The rollout largely repeats the stream (the same commands, outputs
and messages in another format), so a long run can pay for its trajectory twice. `--rollout` chooses:

| `--rollout` | what goes into the trajectory |
|---|---|
| `copy` (default) | a byte copy of every rollout file |
| `dedup` | `rollout/<name>.dedup.jsonl`: only the records the stream does not carry - session metadata, turn context, user / developer messages and any record type the adapter does not know - each an unchanged line of the original; `event_msg` records and the `response_item` records of assistant messages, reasoning and tool calls with their output are dropped |
| `omit` | nothing |

In every mode the manifest and the package README record each rollout's name, size and sha256 (and, for `dedup`,
the records kept and dropped by type), the rollout's model, CLI version and user messages still reach the manifest
and `prompts/user_messages.jsonl`, and the same bytes are never packaged twice. Keep the original rollout file: it is
what the recorded sha256 verifies if the full session is asked for.

**Credential files are never collected.** `$CODEX_HOME/auth.json` holds your login tokens. The adapter only reads
rollouts under `$CODEX_HOME/sessions` and `AGENTS.md` / `AGENTS.override.md` from `$CODEX_HOME`, and it refuses,
before anything is written, any input - `--stream`, `--prompt`, `--stderr`, `--command-file`, `--harness` - that is a
credential file by name (`auth.json*`, `.env`, `.env.*`, `*credential*.json`, `.credentials*`, `.netrc`, `.pypirc`,
`.npmrc`, `id_rsa` / `id_ed25519` / ..., `*.pem`, `*.key`, `*.p12`, `*.pfx`), by the name of the file a link points to,
or that has the same bytes as a credential file in `$CODEX_HOME` (a renamed copy). The finished evidence set is
checked the same way once more, and the credential-shaped content scan below applies on top.

## OpenCode runs: `opencode-lock` and `opencode-package` (checked against the source, untested live)

OpenCode is the third most declared agent framework on the portal. `opencode.py` gives an OpenCode team the same
three evidence kinds, plus a configuration lock before the run:

* **Supported version and what was checked.** Everything was read from the public OpenCode source,
  github.com/anomalyco/opencode (the repository formerly at sst/opencode), tag **v1.18.33**, commit
  `51ef4be1d3c122f18fefb510dca8d778571f4f18`, on 2026-09-30: the `run` and `export` commands, the session storage,
  the auth and MCP-auth files, the config and permission loading, the instruction files. The session layout of
  OpenCode up to v1.1.x (JSON files) was read from tags v1.1.40 and v1.2.0. **It is not yet tested live with a real
  OpenCode login**: no OpenCode binary was installed and no model was called; the tests
  (`tests/test_opencode_adapter.py`, synthetic files laid out as the source describes) show that the adapter handles
  that layout, not that your OpenCode version writes exactly that. Please report a run it misreads.
* **Before the run: `opencode-lock`.** Snapshots the prompt, every config and permission file OpenCode would read
  (the global config directory, `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR`, `opencode.json(c)` and `.opencode/`
  directories from the workspace up to the repository root, `~/.opencode`), the instruction files (`AGENTS.md`,
  `CLAUDE.md`, `CONTEXT.md` in the workspace tree and its parents, the global `AGENTS.md`), the relevant `OPENCODE_*`
  environment variables and the CLI path / sha256 / `--version`, and writes `opencode.lock.json` +
  `opencode.lock.sha256` and `command.txt` with the exact headless command. It warns in plain words when `share` is
  not `"disabled"`, `webfetch` / `websearch` / `external_directory` are not denied, there is no permission block,
  `--auto` is used, an MCP server is remote, an instruction file comes from a URL, or `~/.claude/CLAUDE.md` would be
  pulled in. It refuses (writing nothing) when a config file holds a credential-shaped string: put keys in
  `{env:VAR}` references instead. It does not launch OpenCode, keep a wall clock or hook tool calls; OpenCode's own
  permission rules are the enforcement layer.
* **The run.** `opencode run --format json` prints one JSON event per line (`step_start`, `step_finish` with tokens
  and cost, `text`, `reasoning`, `tool_use`, `error`), each with the session id. The prompt goes in on stdin. In
  `opencode run` a permission that resolves to "ask" is rejected automatically unless `--auto` is passed, so a run
  never waits for a human. The stream carries no user message and no model string; those are in the stored session.
* **After the run: `opencode-package`.** The trajectory is the stream (byte copy), the stderr log if you kept it,
  and the stored session, found by the session id of the stream, in this order: the file you made with
  `opencode export <sessionID> > session_export.json` and passed with `--export` (best: OpenCode's own export); else
  the rows of that session and its child sessions (subagents) from OpenCode's database, opened read-only, written as
  `session_export.json` in the export's shape; else, for OpenCode up to v1.1.x, byte copies of
  `storage/session/<project>/<id>.json`, `storage/message/<id>/*.json` and `storage/part/<message>/*.json`. The
  prompts kind holds the prompt, the instruction files and every user message of the session; the harness kind the
  lock (verified: a config or instruction file that changed after the lock, or a config file that appeared after it -
  e.g. one the agent wrote into the workspace - is a warning in the README and the manifest, and its current copy is
  packaged next to the locked one), or a config snapshot taken now when there is no lock, your harness files, the command and
  `opencode_manifest.json` (framework and CLI version, model string, hashes of every evidence file, warnings).
  Predictions are format-checked byte copies, as for Codex.

Where OpenCode keeps things (from the source): data in `$XDG_DATA_HOME/opencode`, by default
`~/.local/share/opencode` on every platform (`opencode db path` prints the database path); config in
`$XDG_CONFIG_HOME/opencode`, by default `~/.config/opencode`. Since v1.2.0 sessions live in the SQLite database
`opencode.db` (tables `session`, `message`, `part`, `todo`); up to v1.1.x they were JSON files under `storage/`.

**Credential files are never collected.** OpenCode keeps provider keys and OAuth tokens in `<data>/auth.json`,
MCP OAuth tokens in `<data>/mcp-auth.json`, and account tokens in the `account`, `control_account` and `credential`
tables of the same database that holds the sessions. So the database file is never copied: only the session,
message, part and todo rows of the run's session are selected, read-only (after OpenCode has exited, with no `-wal`
file next to the database, it is opened immutable, so SQLite creates no `-wal` / `-shm` side files either). Any input that is a credential file by name
(`auth.json`, `mcp-auth.json`, `*.db`, `*.db-wal`, `*.sqlite`, `.env`, `*.pem`, ...), by the name of a link's target,
by the SQLite header (a renamed database), or by the bytes of a credential file in the data directory (a renamed
`auth.json`) is refused before anything is written, and the finished set is checked the same way again. The
`OPENCODE_AUTH_CONTENT` variable is recorded as set / not set, never its value. On top, the content scan refuses an
OpenCode auth entry (`"type"` oauth / api / wellknown followed by `"refresh"` / `"key"`) and every pattern listed
under "Secret scan".

`example_opencode.json` is a starting config for an unattended run: `"share": "disabled"`, no self-update, and a
permission block that allows the file tools and `bash` but denies web tools, subagents, skills, and recognised
network and process-kill commands (the same families as `hooks/guard.py`; OpenCode applies the last matching rule,
so `"*": "allow"` comes first). Like the guard, a pattern list over command text is not a sandbox. It also denies
`external_directory`: if your data lives outside the workspace, link it into the workspace or add an allow rule for
its path, e.g. `"external_directory": {"*": "deny", "/abs/path/to/data/*": "allow"}`.

```
python -m vec_agent_evidence opencode-lock --prompt prompt.md --workspace <ws> --model <provider>/<model> \
    --out runs/_opencode_lock/run1          # prints the command; also in runs/_opencode_lock/run1/command.txt

OPENCODE_DISABLE_AUTOUPDATE=1 OPENCODE_DISABLE_CLAUDE_CODE=1 OPENCODE_DISABLE_LSP_DOWNLOAD=1 \
    opencode run --format json --model <provider>/<model> --dir <ws> --title <lock id> \
    < runs/_opencode_lock/run1/initial_prompt.md > opencode_stream.jsonl 2> opencode_stderr.log
opencode export <sessionID from the stream> > session_export.json       # optional, preferred

python -m vec_agent_evidence opencode-package --stream opencode_stream.jsonl --stderr opencode_stderr.log \
    --prompt runs/_opencode_lock/run1/initial_prompt.md --workspace <ws> --lock runs/_opencode_lock/run1 \
    --export session_export.json --prediction T3:gata4=<ws>/out/pred.h5ad --out runs/_upload_opencode/run1
```

Not checked or not covered: the exact text OpenCode sends to the model (system prompts, tool definitions) is not in
any file this adapter reads; permissions are summarised per file, while OpenCode merges them (later files and
`OPENCODE_PERMISSION` win), so read the snapshot itself; npm plugins are only named, not snapshotted; OpenCode's own
logs (`<data>/log/`) and file snapshots are not collected; a session shared before the lock (`share` not disabled)
cannot be unshared by this tool.

## The hooks

`hooks/guard.py` (PreToolUse; exit 2 + JSON reason denies the call) rejects recognised network commands and
restricted file operations: network-shaped commands (curl, wget,
pip/uv/conda install, git clone/fetch/pull/push, ssh/scp, requests/httpx/urllib/socket, huggingface_hub, any URL),
any reference to `~/.claude`, any reference to another run directory, writes into `submission/` other than through
`tools/finalize_submission.py`, writes outside the workspace or into `tools/`, `data/`, `DEADLINE.txt`,
`README_WORKSPACE.md` (Write/Edit paths, mutating commands, redirections), process-kill commands (taskkill, pkill,
kill, Stop-Process), and recursive `claude -p`. It is fail-closed: an internal error denies with the error text.
`hooks/audit.py` appends one JSON line per event to `hooks/tool_audit.jsonl` and never blocks.

Both are stdlib-only and copied into the run directory, so editing the kit while a run is in progress cannot change
that run. A regex guard over the command text is not a sandbox: a determined agent could obfuscate a command, and
Python code that opens files itself bypasses Read/Edit deny rules. Enforcement is layered (tool set, deny rules,
guard, offline environment, audit log); the audit log, the trajectory and the recorded hashes are what supports
post-run verification of what actually happened.

## Secret scan

Evidence must never carry credentials. `evidence.secret_scan`, `package`, `codex-package`, `opencode-lock` and
`opencode-package` scan every text-like evidence file for credential-shaped byte patterns (an Anthropic key prefix
followed by key characters; an
OpenAI-style `sk-` key not preceded by a base64 / base64url character (`A-Z a-z 0-9 + / - _`), so that an `sk-`
occurring by chance inside a long encoded blob in a transcript - about once per 14 MB of random base64url - does not
refuse a long run, while a key after a space, quote, `=`, `:` or an escaped newline is still caught; OAuth token
fields as JSON keys, camelCase or snake_case, plain or JSON-escaped inside a transcript; an entry of OpenCode's
`auth.json`, i.e. a `"type"` of oauth / api / wellknown followed by a `"refresh"` or `"key"` field, plain or
JSON-escaped once) and refuse to package on a hit. Pass any literal gateway key you used to `secret_scan(run, extra_values=[...])`
to scan for its value as well. The patterns are assembled from fragments so the kit's own source never trips the scan.

## Sizes

`run_manifest.json.sizes` lists files over the 200 MB per-file cap and the upload-set total; `package` refuses to
build a zip over the cap. The 600 MB cap is per team across every upload, which no local tool can know: pass
`package --team-uploaded-mb <MB your team has already uploaded>` (your own bookkeeping from the portal's evidence
list) and the package README states the running total and warns when this upload would exceed 600 MB. A typical
multi-hour run produces tens of MB of evidence uncompressed.

## What the human may and may not do

Pre-lock: anything. From "CONFIGURATION LOCK IS NOW IN EFFECT" until `run_manifest.json` exists: nothing - do not
open stream.jsonl, workspace/, hooks/, the transcript, or the public ranking for that run. After: read the manifest
and NOTES.md, decide WHICH COMPLETED RUN to upload, upload the unchanged prediction and the zips, and write what
you learned into the next prompt version (record it with `--note` at the next lock). Never resume a session, never
feed one run's artefacts into another's workspace, never edit a submission.

## Limitations

* Windows and POSIX are both supported for the launcher (CTRL_BREAK / SIGINT, then a process-tree kill). Network is
  not sandboxed by this kit: the guard is a regex hook that rejects recognised network commands; a firewall rule for
  the agent's Python interpreter is the hard block.
* The full lock -> launch -> postrun -> package path is implemented for the Claude Code CLI only (`claude -p
  --output-format stream-json`, headless, hooks via a settings file). For the Codex CLI there is the minimal,
  after-the-fact `codex-package` (above; untested against a live Codex run). For OpenCode there is `opencode-lock`
  before the run and `opencode-package` after it (above; checked against the OpenCode source, not yet tested live with
  a real OpenCode login); neither launches the agent. Another agent CLI needs `launch.build_command` adapted and its
  trajectory located by `evidence.collect_transcript`.
* Thinking blocks may be stored without their text by the CLI; the trajectory proves the tool calls and messages.
* The bundle documents; it does not attest. Regex hooks, hashes and a read-only directory record and detect some
  changes; by themselves they cannot prove that nobody intervened, that no restriction was bypassed, or that the
  records were not regenerated. Keep the run directory and the CLI's own project directory as they are, and expect
  the organisers to ask for a re-run.
* `total_cost_usd` in the manifest is the CLI's own estimate.
