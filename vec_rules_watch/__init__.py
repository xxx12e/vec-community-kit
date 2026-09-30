"""vec_rules_watch - a daily watch of the Virtual Embryo Challenge's public rules, pages and machine-readable contract.

Watches the challenge pages (rules, terms, FAQ, timeline, prizes, data, tasks, evaluation, reference rows, ...), the
board contract (panels/index.json and the gene lists it names), the phase endpoint the site itself calls, and the
organisers' scorer veckit on GitHub (default-branch head, version, branches, tags, releases). Writes a dated
changelog in English and Chinese with rule-based "what this changes for your file" lines for the contract.

Standard library only (no anndata, no numpy), so the GitHub Action needs no install step.

    python -m vec_rules_watch run --state .rules-watch-state --out rules-watch [--full-text]
    python -m vec_rules_watch diff old.html new.html
    python -m vec_rules_watch diff old_index.json new_index.json
    python -m vec_rules_watch diff old_out_dir new_out_dir

By default the public output holds per-section hashes, headings and short excerpts (<= 200 characters) of changed
lines, not the organisers' full page text; the full text for the next day's diff lives in the --state directory
(the Actions cache). See README.md for what is and is not checked.
"""
__version__ = "2026.10.0"
