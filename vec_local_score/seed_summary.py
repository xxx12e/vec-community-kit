#!/usr/bin/env python
"""Seed summary: run the local scoreboard over several subsample seeds and report mean +- sd.

The 10 % subsample and the half split make a single local score noisy. Two predictions can only be compared on
the same target/reference pair, the same seeds, and with the spread in view: a difference inside one standard
deviation is not a result. Inputs are the RAW released stage files (see local_score.py).

    python -m vec_local_score.seed_summary --task T2 --setting heart --pred pred.h5ad \
        --target E8.75.h5ad --reference E8.25_late.h5ad --seeds 0 1 2 3 4 [--json out.json]

Python: summarise("T2", "pred.h5ad", "E8.75.h5ad", "E8.25_late.h5ad", seeds=(0, 1, 2)) -> dict with
task_score_mean, task_score_sd, task_scores, metrics{name: raw_mean, raw_sd, skill_mean, skill_sd, points_mean,
floor_mean, ceiling_mean}, per_seed [local_score result dicts].
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np

from .local_score import format_table, score


def summarise(task: str, pred, target, reference, seeds=(0, 1, 2), setting: str = "heart", frac: float = 0.1,
              max_cells: int = 4000, pred_max_cells: int = 0) -> dict:
    per = []
    for s in seeds:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            per.append(score(task, pred, target, reference, setting=setting, frac=frac, seed=int(s),
                             max_cells=max_cells, pred_max_cells=pred_max_cells))
    scores = np.array([r["task_score"] for r in per], dtype=float)
    metrics = {}
    for row in per[0]["rows"]:
        m = row["metric"]
        vals = {}
        for k in ("raw", "skill", "points", "floor", "ceiling"):
            col = []
            for r in per:
                x = [rr[k] for rr in r["rows"] if rr["metric"] == m][0]
                col.append(np.nan if x is None else float(x))
            vals[k] = np.array(col, dtype=float)
        sd = (lambda v: float(np.nanstd(v, ddof=1)) if len(per) > 1 else 0.0)
        metrics[m] = {"group": row["group"], "weight": row["weight"],
                      "raw_mean": float(np.nanmean(vals["raw"])), "raw_sd": sd(vals["raw"]),
                      "skill_mean": float(np.mean(vals["skill"])), "skill_sd": sd(vals["skill"]),
                      "points_mean": float(np.mean(vals["points"])),
                      "floor_mean": float(np.nanmean(vals["floor"])), "ceiling_mean": float(np.nanmean(vals["ceiling"]))}
    return {"task": task, "setting": setting if task == "T2" else None, "pred": str(pred), "target": str(target),
            "reference": str(reference), "seeds": [int(s) for s in seeds], "frac": frac,
            "task_score_mean": float(scores.mean()),
            "task_score_sd": float(scores.std(ddof=1)) if len(scores) > 1 else 0.0,
            "task_scores": scores.tolist(), "metrics": metrics, "veckit": per[0].get("veckit"), "per_seed": per}


def summary_line(res: dict) -> str:
    parts = [f"{Path(res['pred']).name} on {Path(res['target']).name}: {res['task_score_mean']:.2f} +- "
             f"{res['task_score_sd']:.2f} (seeds {res['seeds']})"]
    for m, v in res["metrics"].items():
        parts.append(f"{m}={v['raw_mean']:.4f}/{v['skill_mean']:.3f}")
    return "  ".join(parts)


def format_summary(res: dict) -> str:
    lines = [summary_line(res),
             f"{'metric':18s} {'raw_mean':>10s} {'raw_sd':>9s} {'floor':>10s} {'ceiling':>10s} {'skill':>7s} {'pts':>6s}"]
    for m, v in res["metrics"].items():
        lines.append(f"{m:18s} {v['raw_mean']:10.4f} {v['raw_sd']:9.4f} {v['floor_mean']:10.4f} {v['ceiling_mean']:10.4f} "
                     f"{v['skill_mean']:7.3f} {v['points_mean']:6.2f}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m vec_local_score.seed_summary", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", required=True, choices=["T1", "T2", "T3"])
    ap.add_argument("--setting", default="heart", choices=["heart", "embryo"])
    ap.add_argument("--pred", required=True, type=Path)
    ap.add_argument("--target", required=True, type=Path)
    ap.add_argument("--reference", type=Path, help="T1/T2 reference stage")
    ap.add_argument("--wt", type=Path, help="T3 matched wild type")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--frac", type=float, default=0.1)
    ap.add_argument("--max-cells", type=int, default=4000)
    ap.add_argument("--pred-max-cells", type=int, default=0)
    ap.add_argument("--json", type=Path, help="write the aggregated result here")
    ap.add_argument("--verbose", action="store_true", help="also print every per-seed table")
    args = ap.parse_args(argv)
    ref = args.wt if args.task == "T3" else args.reference
    if ref is None:
        ap.error("--reference (T1/T2) or --wt (T3) is required")
    try:
        res = summarise(args.task, args.pred, args.target, ref, seeds=tuple(args.seeds), setting=args.setting,
                        frac=args.frac, max_cells=args.max_cells, pred_max_cells=args.pred_max_cells)
    except ImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if args.verbose:
        for r in res["per_seed"]:
            print(format_table(r))
            print()
    print(format_summary(res))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(res, indent=2, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
