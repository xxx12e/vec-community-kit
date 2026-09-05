#!/usr/bin/env python
"""Local scoreboard: run the organisers' veckit metric panels on a pseudo-validation split built from RAW released
stages and turn the raw metrics into the 0-100 skill scale.

The wrapper follows the veckit scorer's protocol as of veckit 0.1.1: 10 % subsample, split-half ceiling, floor row,
skill scale. Concretely:
  * the reference stage and the target stage are subsampled to --frac (default 0.1) of their cells; the target
    subsample is split in half - half A is scored against, half B is scored as a prediction to estimate the
    attainable ceiling (veckit: common.core_metrics.split_half);
  * floor = the reference stage resubmitted (copy_last on T1/T2, wt_identity on T3), scored against half A;
  * skill = veckit's own common.core_metrics.skill(value, floor, ceiling, lower_is_better): hyperbolic, floor -> 0.5,
    ceiling -> 1.0, clipped above at 1.0, worse than the floor -> below 0.5 towards 0;
  * task score = 100 * sum_g w_g * sum_{m in g} w_m skill(m) with the task weights published on the evaluation
    pages; a missing / NaN metric counts as skill 0.
The organisers' portal scorer is the source of truth; this wrapper may lag it. It is NOT a preview of the real
score: the real target is a stage you do not have. It ranks your own methods against each other on one split.

INPUTS ARE THE RAW RELEASED STAGE FILES. The wrapper subsamples and splits them itself. Files exported by
vec_local_score.make_pseudo_split (target_score / target_ceiling / reference) are for inspection and for the veckit
CLI only; they carry a marker in uns and are refused here, because feeding them back would subsample twice.

Conventions this wrapper adds on top of veckit (veckit itself only returns raw metrics):
  * a direction per metric: higher is better (de_score, de_direction, occupancy_dice), lower is better (mmd_u,
    variogram, d2_shape, neighborhood_mmd), or target 0 (scale_log_ratio, severity_slope);
  * target-0 metrics are folded to their distance from 0 - |value| for the prediction, the floor and the ceiling -
    and then scored as lower-is-better with veckit's skill(). veckit 0.1.1 reports both as SIGNED values
    (scale_log_ratio = log of the RMS-radius ratio prediction/truth; severity_slope = log of the regression slope of
    predicted on observed log fold change, with a finite worst case log(1e-3) for a no / inverted / unrelated
    response) and its skill() has no symmetric mode, so the fold is the wrapper's choice. It matches the published
    definitions (0 = the right size; severity = min(beta, 1/beta) in log space): an overshoot is penalised, not
    credited. The table marks folded metrics with '*'.
  * degenerate local reference values (|floor - ceiling| < 1e-12 after folding, where veckit's skill() returns NaN):
    the metric cannot discriminate on this split; the wrapper assigns 1.0 when the prediction is at least as good
    as the ceiling and 0.0 otherwise and flags the row (`degenerate`). Treat such a metric as uninformative.

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

from .veckit_loader import TESTED_VECKIT_VERSION, load_veckit, veckit_info

# ---- task weights (challenge evaluation pages) -----------------------------------------------------
WEIGHTS = {
    "T1": {"de_score": 0.25, "de_direction": 0.25, "mmd_u": 0.30, "variogram": 0.20},
    "T2": {"de_score": 0.125, "de_direction": 0.125, "mmd_u": 0.15, "variogram": 0.10,
           "d2_shape": 0.25 / 3, "occupancy_dice": 0.25 / 3, "scale_log_ratio": 0.25 / 3, "neighborhood_mmd": 0.25},
    "T3": {"de_score": 0.30, "de_direction": 0.25, "severity_slope": 0.25, "mmd_u": 0.12, "variogram": 0.08},
}
# direction: +1 higher is better, -1 lower is better, 0 target 0 (folded to |value|, then lower is better)
DIRECTION = {"de_score": +1, "de_direction": +1, "mmd_u": -1, "variogram": -1, "d2_shape": -1,
             "occupancy_dice": +1, "scale_log_ratio": 0, "neighborhood_mmd": -1, "severity_slope": 0}
GROUPS = {
    "T1": {"DE recovery": ["de_score"], "Change direction": ["de_direction"],
           "Cell-state distribution": ["mmd_u"], "Gene-gene co-variation": ["variogram"]},
    "T2": {"Expression change": ["de_score", "de_direction"], "Cell-state distribution": ["mmd_u", "variogram"],
           "Tissue shape and growth": ["d2_shape", "occupancy_dice", "scale_log_ratio"],
           "Local spatial organisation": ["neighborhood_mmd"]},
    "T3": {"Response gene recovery": ["de_score"], "Response direction": ["de_direction"],
           "Response magnitude": ["severity_slope"], "Cell-state distribution": ["mmd_u", "variogram"]},
}
PSEUDO_SPLIT_MARKER = "vec_pseudo_split"


# ---- skill --------------------------------------------------------------------------------------------
def veckit_skill_fn():
    """veckit's own skill(): common.core_metrics.skill, available once a task's metric modules are loaded."""
    mod = sys.modules.get("common.core_metrics")
    return getattr(mod, "skill", None)


def skill_hyperbolic(value, floor, ceiling, lower_is_better=False):
    """Transcription of veckit 0.1.1 common.core_metrics.skill (fallback when veckit's own is not importable).
    NaN for non-finite inputs or a degenerate floor == ceiling; 1.0 at or beyond the ceiling; 0.5 at the floor."""
    if not all(np.isfinite([value, floor, ceiling])):
        return float("nan")
    d_floor = abs(ceiling - floor)
    if d_floor < 1e-12:
        return float("nan")
    d = (value - ceiling) if lower_is_better else (ceiling - value)
    denom = d_floor + d
    if denom <= 1e-9:
        return 1.0
    return float(min(d_floor / denom, 1.0))


def fold(value, direction):
    """A target-0 metric enters the skill map as its distance from 0."""
    return abs(value) if direction == 0 else value


def skill(m, floor, ceiling, direction, base=None):
    """Skill of raw metric `m` against the local floor and ceiling, following veckit's skill() (module docstring).

    direction: +1 higher is better, -1 lower is better, 0 target 0 (|value| of all three, then lower is better).
    base: the skill function to use - veckit's own when loaded (veckit_skill_fn()), else skill_hyperbolic.
    Returns 0.0 for a missing / NaN raw metric or missing reference values (the portal counts it as 0);
    degenerate reference values -> 1.0 if the prediction is at least as good as the ceiling, else 0.0.
    """
    if m is None or floor is None or ceiling is None or not all(np.isfinite([m, floor, ceiling])):
        return 0.0
    base = base or skill_hyperbolic
    if direction == 0:
        m, floor, ceiling, lower = abs(m), abs(floor), abs(ceiling), True
    else:
        lower = direction < 0
    s = base(m, floor, ceiling, lower)
    if s is None or not np.isfinite(s):
        d = (m - ceiling) if lower else (ceiling - m)
        return 1.0 if d <= 0 else 0.0
    return float(s)


def is_degenerate(floor, ceiling, direction) -> bool:
    if floor is None or ceiling is None or not (np.isfinite(floor) and np.isfinite(ceiling)):
        return False
    return abs(fold(ceiling, direction) - fold(floor, direction)) < 1e-12


# ---- data -------------------------------------------------------------------------------------------
def load_arrays(path, need_coords: bool, rng: np.random.Generator, frac: float, max_cells: int, genes=None):
    """Read a RAW stage .h5ad, subsample rows (sparse-aware) BEFORE densifying, return (X, C, celltypes, genes).
    Files exported by make_pseudo_split are refused (they are already subsampled and split)."""
    import anndata as ad
    import scipy.sparse as sp

    path = Path(path)
    a = ad.read_h5ad(path)
    if PSEUDO_SPLIT_MARKER in a.uns:
        raise ValueError(f"{path.name} was exported by vec_local_score.make_pseudo_split (uns[{PSEUDO_SPLIT_MARKER!r}]). "
                         "The wrapper takes the RAW released stage files and subsamples / splits them itself; the exported "
                         "files are for inspection and for the veckit CLI only")
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


def run_panel(task, m2, pred, truth, ref, seed, probe=None):
    """Run veckit's metrics_v2 panel with in-memory arrays. pred/truth/ref = (X, C, celltypes)."""
    if task == "T1":
        return m2.score_task1_v2(pred[0], pred[2], truth[0], truth[2], ref[0], probe=probe, seed=seed)
    if task == "T2":
        return m2.score_task2_v2(pred[0], pred[1], pred[2], truth[0], truth[1], truth[2], ref[0], probe=probe, seed=seed)
    return m2.score_task3_v2(pred[0], pred[1], pred[2], truth[0], truth[1], truth[2], ref[0], probe=probe, seed=seed)


def score(task: str, pred, target, reference, setting: str = "heart", frac: float = 0.1, seed: int = 0,
          max_cells: int = 4000, pred_max_cells: int = 0) -> dict:
    """Score `pred` on the pseudo board (target, reference) with local floor / ceiling. Returns a result dict:
    task_score, rows [{group, metric, raw, floor, ceiling, skill, weight, points, folded, degenerate, undefined}],
    raw_pred, raw_floor, raw_ceiling, cells, veckit, seconds."""
    if task not in WEIGHTS:
        raise ValueError("task must be T1, T2 or T3")
    need_coords = task in ("T2", "T3")
    rng = np.random.default_rng(seed)
    sh = load_veckit()
    metrics, m2 = sh._load_task_metrics(task)
    base_skill = veckit_skill_fn()
    vk = veckit_info()

    t0 = time.time()
    ref_X, ref_C, ref_ct, genes = load_arrays(reference, need_coords, rng, frac, max_cells)
    tgt_X, tgt_C, tgt_ct, _ = load_arrays(target, need_coords, rng, frac, 2 * max_cells, genes)
    prd_X, prd_C, prd_ct, _ = load_arrays(pred, need_coords, rng, 1.0, pred_max_cells or 10 ** 9, genes)
    if (prd_X < 0).any():
        raise ValueError("prediction .X has negative values; the veckit scorer rejects negative expression")

    # half split of the target: A = scored against, B = ceiling estimate
    perm = rng.permutation(tgt_X.shape[0])
    ia, ib = np.sort(perm[: len(perm) // 2]), np.sort(perm[len(perm) // 2:])
    A = (tgt_X[ia], None if tgt_C is None else tgt_C[ia], tgt_ct[ia])
    B = (tgt_X[ib], None if tgt_C is None else tgt_C[ib], tgt_ct[ib])
    REF = (ref_X, ref_C, ref_ct)
    PRED = (prd_X, prd_C, prd_ct)

    # the frozen cell-type probe is trained once on the scored half and shared by the three panel runs
    probe = metrics.train_frozen_probe(A[0], A[2])
    raw_pred = run_panel(task, m2, PRED, A, REF, seed, probe)
    raw_floor = run_panel(task, m2, REF, A, REF, seed, probe)       # copy_last / wt_identity
    raw_ceiling = run_panel(task, m2, B, A, REF, seed, probe)       # other half of the truth

    rows, task_score = [], 0.0
    for group, members in GROUPS[task].items():
        for k in members:
            fl, ce, raw = raw_floor.get(k), raw_ceiling.get(k), raw_pred.get(k)
            refs_ok = fl is not None and ce is not None and bool(np.isfinite(fl) and np.isfinite(ce))
            s = skill(raw, fl, ce, DIRECTION[k], base_skill) if refs_ok else 0.0
            w = WEIGHTS[task][k]
            task_score += 100 * w * s
            rows.append({"group": group, "metric": k, "raw": raw, "floor": fl, "ceiling": ce,
                         "skill": round(s, 4), "weight": round(w, 4), "points": round(100 * w * s, 2),
                         "folded": DIRECTION[k] == 0, "degenerate": is_degenerate(fl, ce, DIRECTION[k]),
                         "undefined": not refs_ok})

    return {"task": task, "setting": setting if task == "T2" else None, "pred": str(pred), "target": str(target),
            "reference": str(reference), "frac": frac, "seed": seed,
            "cells": {"pred": int(prd_X.shape[0]), "target_A": int(len(ia)), "target_B": int(len(ib)),
                      "reference": int(ref_X.shape[0])},
            "task_score": round(task_score, 2), "rows": rows, "raw_pred": raw_pred, "raw_floor": raw_floor,
            "raw_ceiling": raw_ceiling,
            "veckit": dict(vk, skill_source="veckit common.core_metrics.skill" if base_skill else "kit transcription",
                           tested_against=TESTED_VECKIT_VERSION),
            "seconds": round(time.time() - t0, 1)}


def format_table(res: dict) -> str:
    c = res["cells"]
    head = (f"{res['task']}{' ' + res['setting'] if res['setting'] else ''}  pred={Path(res['pred']).name}  "
            f"target={Path(res['target']).name}  ref={Path(res['reference']).name}  "
            f"cells pred/A/B/ref = {c['pred']}/{c['target_A']}/{c['target_B']}/{c['reference']}  frac={res['frac']} seed={res['seed']}")
    lines = [head, f"{'group':28s} {'metric':18s} {'raw':>10s} {'floor':>10s} {'ceiling':>10s} {'skill':>7s} {'pts':>6s}"]

    def f(v):
        return "       n/a" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{v:10.4f}"

    flags = False
    for r in res["rows"]:
        name = r["metric"] + ("*" if r.get("folded") else "")
        mark = " (degenerate split)" if r.get("degenerate") else (" (undefined)" if r.get("undefined") else "")
        flags = flags or bool(mark)
        lines.append(f"{r['group']:28s} {name:18s} {f(r['raw'])} {f(r['floor'])} {f(r['ceiling'])} "
                     f"{r['skill']:7.3f} {r['points']:6.2f}{mark}")
    lines.append(f"{'TASK SCORE (0-100; floor=50, ceiling=100)':>77s} {res['task_score']:6.2f}   [{res['seconds']}s]")
    if any(r.get("folded") for r in res["rows"]):
        lines.append("* target-0 metric: skill computed on |value| (prediction, floor and ceiling), lower is better")
    if flags:
        lines.append("degenerate split / undefined: floor and ceiling coincide or are missing on this split; the metric "
                     "cannot discriminate here")
    vk = res.get("veckit") or {}
    ver = vk.get("version") or "unknown version"
    note = "" if ver == TESTED_VECKIT_VERSION else f" (kit tested against {TESTED_VECKIT_VERSION})"
    lines.append(f"veckit {ver}{note}; the organisers' scorer is the source of truth and this wrapper may lag it")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m vec_local_score", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--task", required=True, choices=["T1", "T2", "T3"])
    p.add_argument("--setting", default="heart", choices=["heart", "embryo"], help="T2 only, recorded in the output")
    p.add_argument("--pred", required=True, type=Path)
    p.add_argument("--target", required=True, type=Path,
                   help="RAW released stage held out as the pseudo-target (the wrapper subsamples and splits it)")
    p.add_argument("--reference", type=Path, help="T1/T2: RAW preceding stage = DE reference and copy_last floor")
    p.add_argument("--wt", type=Path, help="T3: RAW matched wild type = DE reference and wt_identity floor")
    p.add_argument("--frac", type=float, default=0.1,
                   help="subsample fraction applied to the raw target and reference stages (veckit protocol: 0.1)")
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
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(res, indent=2, default=str) + "\n", encoding="utf-8")
    print()
    print(format_table(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
