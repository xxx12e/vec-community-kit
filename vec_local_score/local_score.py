#!/usr/bin/env python
"""Local scoreboard: turn veckit raw metrics into the official 0-100 skill scale on a pseudo-validation split.

The official scorer (virtualembryo.ai/challenge/evaluation):
  * subsamples every stage to 10 % and splits the target in half: half A is scored against, half B estimates
    the attainable ceiling (B scored against A);
  * floor = copy_last (T1/T2: resubmit the reference stage) or wt_identity (T3: resubmit the matched WT);
  * skill(m) = min(d_floor / (d_floor + d(m)), 1), where d = distance from the ceiling in raw units
    (floor -> 0.5, ceiling -> 1.0, worse than floor -> below 0.5, unbounded);
  * task score = 100 * sum_g w_g * sum_{m in g} w_m skill(m); a missing / NaN metric counts as skill 0.

This tool reproduces that pipeline on data YOU hold (e.g. hold out a released stage and predict it from the
earlier ones), using veckit's metric code in-process. Floor and ceiling are computed from your local split, so a
prediction equal to the reference scores exactly 50 and the other half of the target scores 100. It is NOT a
preview of the real score: the real target is a stage you do not have.

Usage:
  python -m vec_local_score --task T1 --pred pred.h5ad --target E9.5_RNA.h5ad --reference E8.5_RNA.h5ad
  python -m vec_local_score --task T2 --setting heart --pred pred.h5ad --target E8.75.h5ad --reference E8.25_late.h5ad
  python -m vec_local_score --task T3 --pred pred.h5ad --target Mab21l2_KO_E9.5.h5ad --wt WT_E9.5.h5ad
Options: --frac 0.1 (stage subsample), --seed 0, --max-cells 4000 (reference cap; target 2x),
         --pred-max-cells 0 (0 = score every submitted cell, as the server does), --json out.json

veckit must be installed or pointed to with VECKIT_PATH (see veckit_loader.py).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

from .veckit_loader import load_veckit

# ---- official weights (challenge evaluation pages) -------------------------------------------------
WEIGHTS = {
    "T1": {"de_score": 0.25, "de_direction": 0.25, "mmd_u": 0.30, "variogram": 0.20},
    "T2": {"de_score": 0.125, "de_direction": 0.125, "mmd_u": 0.15, "variogram": 0.10,
           "d2_shape": 0.25 / 3, "occupancy_dice": 0.25 / 3, "scale_log_ratio": 0.25 / 3, "neighborhood_mmd": 0.25},
    "T3": {"de_score": 0.30, "de_direction": 0.25, "severity_slope": 0.25, "mmd_u": 0.12, "variogram": 0.08},
}
# direction: +1 higher is better, -1 lower is better, 0 target value (ceiling) with symmetric distance
DIRECTION = {"de_score": +1, "de_direction": +1, "mmd_u": -1, "variogram": -1, "d2_shape": -1,
             "occupancy_dice": +1, "scale_log_ratio": 0, "neighborhood_mmd": -1, "severity_slope": +1}
GROUPS = {
    "T1": {"DE recovery": ["de_score"], "Change direction": ["de_direction"],
           "Cell-state distribution": ["mmd_u"], "Gene-gene co-variation": ["variogram"]},
    "T2": {"Expression change": ["de_score", "de_direction"], "Cell-state distribution": ["mmd_u", "variogram"],
           "Tissue shape and growth": ["d2_shape", "occupancy_dice", "scale_log_ratio"],
           "Local spatial organisation": ["neighborhood_mmd"]},
    "T3": {"Response gene recovery": ["de_score"], "Response direction": ["de_direction"],
           "Response magnitude": ["severity_slope"], "Cell-state distribution": ["mmd_u", "variogram"]},
}


def skill(m, floor, ceiling, direction):
    """Official hyperbolic rescale. Returns a float in (-inf, 1]; 0.0 for a missing metric."""
    if m is None or not np.isfinite(m):
        return 0.0
    if direction == 0:
        d, d_floor = abs(m - ceiling), abs(floor - ceiling)
    elif direction > 0:
        d, d_floor = max(ceiling - m, 0.0), max(ceiling - floor, 0.0)
    else:
        d, d_floor = max(m - ceiling, 0.0), max(floor - ceiling, 0.0)
    if d_floor <= 0:
        # degenerate split: the ceiling half is not better than the floor; the metric cannot discriminate
        return 1.0 if d <= 0 else 0.0
    return min(d_floor / (d_floor + d), 1.0)


def load_arrays(path, need_coords: bool, rng: np.random.Generator, frac: float, max_cells: int, genes=None):
    """Read an .h5ad, subsample rows (sparse-aware) BEFORE densifying, return (X, C, celltypes, genes)."""
    import anndata as ad
    import scipy.sparse as sp

    path = Path(path)
    a = ad.read_h5ad(path)
    a.var_names = a.var_names.astype(str)
    names = list(a.var_names)
    if genes is not None and names != genes:
        # the reference file defines the panel; a target/prediction with extra genes is subset by name
        have = set(names)
        missing = [g for g in genes if g not in have]
        if missing:
            raise ValueError(f"{path.name}: {len(missing)} panel genes missing (e.g. {missing[:5]}); cannot align to the reference")
        a = a[:, genes].copy()
    n = a.n_obs
    k = int(min(max(round(n * frac), 1), max_cells, n)) if frac < 1 else min(n, max_cells)
    idx = np.sort(rng.choice(n, size=k, replace=False)) if k < n else np.arange(n)
    a = a[idx].copy()
    X = a.X.toarray() if sp.issparse(a.X) else np.asarray(a.X)
    X = X.astype(np.float32, copy=False)
    ct = np.asarray(a.obs["celltype"]).astype(str) if "celltype" in a.obs else np.array(["NA"] * a.n_obs)
    C = None
    if need_coords:
        if "spatial_3D" not in a.obsm:
            raise KeyError(f"{path.name}: obsm['spatial_3D'] required")
        C = np.asarray(a.obsm["spatial_3D"], dtype=np.float32)[:, :3]
    return X, C, ct, names


def run_panel(task, m2, pred, truth, ref, seed):
    """Run veckit's metrics_v2 panel with in-memory arrays. pred/truth/ref = (X, C, celltypes)."""
    if task == "T1":
        return m2.score_task1_v2(pred[0], pred[2], truth[0], truth[2], ref[0], seed=seed)
    if task == "T2":
        return m2.score_task2_v2(pred[0], pred[1], pred[2], truth[0], truth[1], truth[2], ref[0], seed=seed)
    return m2.score_task3_v2(pred[0], pred[1], pred[2], truth[0], truth[1], truth[2], ref[0], seed=seed)


def score(task: str, pred, target, reference, setting: str = "heart", frac: float = 0.1, seed: int = 0,
          max_cells: int = 4000, pred_max_cells: int = 0) -> dict:
    """Score `pred` on the pseudo board (target, reference) with local floor/ceiling. Returns a result dict:
    task_score, rows [{group, metric, raw, floor, ceiling, skill, weight, points}], raw_pred, raw_floor,
    raw_ceiling, cells, seconds."""
    if task not in WEIGHTS:
        raise ValueError("task must be T1, T2 or T3")
    need_coords = task in ("T2", "T3")
    rng = np.random.default_rng(seed)
    sh = load_veckit()
    _, m2 = sh._load_task_metrics(task)

    t0 = time.time()
    ref_X, ref_C, ref_ct, genes = load_arrays(reference, need_coords, rng, frac, max_cells)
    tgt_X, tgt_C, tgt_ct, _ = load_arrays(target, need_coords, rng, frac, 2 * max_cells, genes)
    prd_X, prd_C, prd_ct, _ = load_arrays(pred, need_coords, rng, 1.0, pred_max_cells or 10 ** 9, genes)
    if (prd_X < 0).any():
        raise ValueError("prediction .X has negative values; the official scorer rejects this")

    # half split of the target: A = scored against, B = ceiling estimate
    perm = rng.permutation(tgt_X.shape[0])
    ia, ib = np.sort(perm[: len(perm) // 2]), np.sort(perm[len(perm) // 2:])
    A = (tgt_X[ia], None if tgt_C is None else tgt_C[ia], tgt_ct[ia])
    B = (tgt_X[ib], None if tgt_C is None else tgt_C[ib], tgt_ct[ib])
    REF = (ref_X, ref_C, ref_ct)
    PRED = (prd_X, prd_C, prd_ct)

    raw_pred = run_panel(task, m2, PRED, A, REF, seed)
    raw_floor = run_panel(task, m2, REF, A, REF, seed)       # copy_last / wt_identity
    raw_ceiling = run_panel(task, m2, B, A, REF, seed)       # other half of the truth

    rows, task_score = [], 0.0
    for group, members in GROUPS[task].items():
        for k in members:
            fl, ce = raw_floor.get(k), raw_ceiling.get(k)
            if fl is None or ce is None or not (np.isfinite(fl) and np.isfinite(ce)):
                s = 0.0
            else:
                s = skill(raw_pred.get(k), fl, ce, DIRECTION[k])
            w = WEIGHTS[task][k]
            task_score += 100 * w * s
            rows.append({"group": group, "metric": k, "raw": raw_pred.get(k), "floor": fl, "ceiling": ce,
                         "skill": round(s, 4), "weight": round(w, 4), "points": round(100 * w * s, 2)})

    return {"task": task, "setting": setting if task == "T2" else None, "pred": str(pred), "target": str(target),
            "reference": str(reference), "frac": frac, "seed": seed,
            "cells": {"pred": int(prd_X.shape[0]), "target_A": int(len(ia)), "target_B": int(len(ib)),
                      "reference": int(ref_X.shape[0])},
            "task_score": round(task_score, 2), "rows": rows, "raw_pred": raw_pred, "raw_floor": raw_floor,
            "raw_ceiling": raw_ceiling, "seconds": round(time.time() - t0, 1)}


def format_table(res: dict) -> str:
    c = res["cells"]
    head = (f"{res['task']}{' ' + res['setting'] if res['setting'] else ''}  pred={Path(res['pred']).name}  "
            f"target={Path(res['target']).name}  ref={Path(res['reference']).name}  "
            f"cells pred/A/B/ref = {c['pred']}/{c['target_A']}/{c['target_B']}/{c['reference']}  frac={res['frac']} seed={res['seed']}")
    lines = [head, f"{'group':28s} {'metric':18s} {'raw':>10s} {'floor':>10s} {'ceiling':>10s} {'skill':>7s} {'pts':>6s}"]

    def f(v):
        return "       n/a" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{v:10.4f}"

    for r in res["rows"]:
        lines.append(f"{r['group']:28s} {r['metric']:18s} {f(r['raw'])} {f(r['floor'])} {f(r['ceiling'])} "
                     f"{r['skill']:7.3f} {r['points']:6.2f}")
    lines.append(f"{'TASK SCORE (0-100; floor=50, ceiling=100)':>77s} {res['task_score']:6.2f}   [{res['seconds']}s]")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m vec_local_score", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--task", required=True, choices=["T1", "T2", "T3"])
    p.add_argument("--setting", default="heart", choices=["heart", "embryo"], help="T2 only, recorded in the output")
    p.add_argument("--pred", required=True, type=Path)
    p.add_argument("--target", required=True, type=Path, help="local pseudo-target stage (you hold its answers)")
    p.add_argument("--reference", type=Path, help="T1/T2: preceding stage = DE reference and copy_last floor")
    p.add_argument("--wt", type=Path, help="T3: matched wild type = DE reference and wt_identity floor")
    p.add_argument("--frac", type=float, default=0.1, help="stage subsample fraction (official: 0.1)")
    p.add_argument("--max-cells", type=int, default=4000, help="cap for the reference (target: 2x) after the --frac subsample")
    p.add_argument("--pred-max-cells", type=int, default=0,
                   help="cap for the PREDICTION (0 = score every submitted cell, as the server does)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--json", type=Path)
    args = p.parse_args(argv)

    ref_path = args.wt if args.task == "T3" else args.reference
    if ref_path is None:
        p.error("--reference (T1/T2) or --wt (T3) is required for a meaningful score")
    try:
        res = score(args.task, args.pred, args.target, ref_path, setting=args.setting, frac=args.frac, seed=args.seed,
                    max_cells=args.max_cells, pred_max_cells=args.pred_max_cells)
    except ImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(res, indent=2, default=str) + "\n", encoding="utf-8")
    print()
    print(format_table(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
