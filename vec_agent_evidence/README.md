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

This package makes producing that evidence mechanical. The current implementation targets the Claude Code CLI
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
python -m vec_agent_evidence package --run-dir runs/<run_id>
```

`--data-root` is a directory holding the released .h5ad files (any layout; every `*.h5ad` under it is hashed into
the lock) and optionally `panels/` (index.json + genes files; the kit's own `data/panels` is used otherwise).
Prompt and settings templates may use the placeholders listed in `lock.template_values` (`{{RUN_ID}}`,
`{{DEADLINE_UTC}}`, `{{BOARD_CONTRACT_TABLE}}`, `{{DATA_FILES_TABLE}}`, `{{PYTHON_POSIX}}`, ...); an unknown or
unrendered placeholder fails the lock.

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

Evidence must never carry credentials. `evidence.secret_scan` and `package` scan every text-like evidence file for
credential-shaped byte patterns (an Anthropic key prefix followed by key characters; OAuth token fields as JSON
keys) and refuse to package on a hit. Pass any literal gateway key you used to `secret_scan(run, extra_values=[...])`
to scan for its value as well. The patterns are assembled from fragments so the kit's own source never trips the scan.

## Sizes

`run_manifest.json.sizes` lists files over the 200 MB per-file cap and the upload-set total; `package` refuses to
build a zip over the cap. A typical multi-hour run produces tens of MB of evidence uncompressed.

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
* Only the Claude Code CLI is implemented (`claude -p --output-format stream-json`, headless, hooks via a settings
  file). Another agent CLI needs `launch.build_command` adapted and its trajectory located by `evidence.collect_transcript`.
* Thinking blocks may be stored without their text by the CLI; the trajectory proves the tool calls and messages.
* `total_cost_usd` in the manifest is the CLI's own estimate.
