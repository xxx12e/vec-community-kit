"""vec_agent_evidence - the Agent-track evidence skeleton: configuration lock, guard + audit hooks, launcher,
post-run evidence collector and upload packager. See README.md in this directory.

The guard hooks are regex hooks over the tool input, not a network sandbox: they reject recognised network
commands and restricted file operations; the audit log and the hashes in config.lock.json / run_manifest.json
support post-run verification. The current implementation targets the Claude Code CLI in headless mode
(`claude -p --output-format stream-json`); another agent CLI needs `launch.build_command` adapted.

    python -m vec_agent_evidence lock|run|postrun|package ...
"""
__version__ = "0.1.0"
