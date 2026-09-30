#!/usr/bin/env python
"""Seed summary - kept as an alias. The multi-seed band is now the DEFAULT output of `python -m vec_local_score`
(mean, sd and band min..max of the task score over subsample seeds 0 1 2 3 4), so this module adds nothing:

    python -m vec_local_score.seed_summary --task T2 --setting heart --pred pred.h5ad \
        --target E8.75.h5ad --reference E8.25_late.h5ad --seeds 0 1 2 3 4 [--json out.json] [--verbose]

is the same as `python -m vec_local_score` with the same arguments. Inputs are the RAW released stage files (see
local_score.py).

Python: summarise("T2", "pred.h5ad", "E8.75.h5ad", "E8.25_late.h5ad", seeds=(0, 1, 2, 3, 4)) -> dict with
task_score_mean, task_score_sd, task_score_min, task_score_max, band, task_scores, metrics{name: raw_mean, raw_sd,
skill_mean, skill_sd, points_mean, floor_mean, ceiling_mean, ...}, per_seed [local_score result dicts]. The
functions live in local_score.py and are re-exported here.
"""
from __future__ import annotations

import sys

from .local_score import DEFAULT_SEEDS, SEED_NOTE, format_summary, summarise, summary_line  # noqa: F401
from .local_score import main as _main


def main(argv=None) -> int:
    return _main(argv, prog="python -m vec_local_score.seed_summary")


if __name__ == "__main__":
    sys.exit(main())
