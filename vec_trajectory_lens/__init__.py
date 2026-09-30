"""vec_trajectory_lens - one readable, offline report of an agent run's log, for Agent-track teams and for the
evidence audit.

Reads the log of a Claude Code, Codex CLI or OpenCode run (pluggable parsers, one unified event schema), and writes a
single self-contained HTML file (a summary card and a filterable timeline; no network, no CDN) and a summary JSON.
Credential-shaped strings are redacted before anything is written. It reads logs; it does not prove autonomy or
rule compliance. See README.md in this directory.

    python -m vec_trajectory_lens <log file, run directory or zip> --out report.html --json summary.json
"""
__version__ = "2026.10.0"
