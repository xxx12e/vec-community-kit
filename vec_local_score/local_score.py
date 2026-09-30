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

DEFAULT OUTPUT = THE MULTI-SEED BAND. One call scores the prediction under several subsample seeds (default
0 1 2 3 4) and prints mean, sd and the band (min..max over the seeds) of the task score, with a per-metric table
of means. The organisers, in their review of this kit (2026-09), said the subsample seed will depend on each
submission; a single-seed number hides how much the score moves with the subsample. --single-seed [--seed N]
restores the old one-seed table (faster; for quick checks). The JSON of the band carries task_score_mean (and
task_score_sd / _min / _max, band, task_scores); task_score is the key of the single-seed JSON only.

PAIRED COMPARISON (--pred A --pred B). Both predictions are scored under the same seeds, and in each seed against
the same draw - reference and target subsamples, target halves, probe, floor and ceiling - so the per-seed
difference B - A removes the subsampling noise the two files share. Output: each file's band, per-metric point
differences, B - A per seed and its mean, sd and min..max over the seeds. Seed s of either file is exactly its
--single-seed --seed s result.

Usage:
  python -m vec_local_score --task T1 --pred pred.h5ad --target E9.5_RNA.h5ad --reference E8.5_RNA.h5ad
  python -m vec_local_score --task T2 --setting heart --pred pred.h5ad --target E8.75.h5ad --reference E8.25_late.h5ad
  python -m vec_local_score --task T3 --pred pred.h5ad --target Mab21l2_KO_E9.5.h5ad --wt WT_E9.5.h5ad
  python -m vec_local_score ... --single-seed --seed 3        (one seed, full per-metric table)
  python -m vec_local_score --task T2 --setting heart --pred a.h5ad --pred b.h5ad --target E8.75.h5ad
      --reference E8.25_late.h5ad                              (one command line; paired: B - A per seed, seeds 0-4)
Options: --seeds 0 1 2 3 4 (default), --single-seed / --seed N (given alone, --seed implies --single-seed),
         --frac 0.1 (stage subsample), --max-cells 4000 (reference cap; target 2x),
         --pred-max-cells 0 (0 = score every submitted cell, as the server does; a cap draws the prediction's
         cells with a generator of its own, so it never changes the draw of the target, reference or the other
         prediction), --verbose, --json out.json

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
def read_stage(path):
    """Read a RAW stage .h5ad (var_names as str). Files exported by make_pseudo_split are refused (they are already
    subsampled and split)."""
    import anndata as ad

    path = Path(path)
    a = ad.read_h5ad(path)
    if PSEUDO_SPLIT_MARKER in a.uns:
        raise ValueError(f"{path.name} was exported by vec_local_score.make_pseudo_split (uns[{PSEUDO_SPLIT_MARKER!r}]). "
                         "The wrapper takes the RAW released stage files and subsamples / splits them itself; the exported "
                         "files are for inspection and for the veckit CLI only")
    a.var_names = a.var_names.astype(str)
    return a


def _stage(path, cache):
    """read_stage(path), memoised in `cache` (a dict) when one is given: a multi-seed run reads each file once."""
    if cache is None:
        return read_stage(path)
    key = str(Path(path).resolve())
    if key not in cache:
        cache[key] = read_stage(path)
    return cache[key]


def load_arrays(path, need_coords: bool, rng: np.random.Generator, frac: float, max_cells: int, genes=None,
                cache=None):
    """Read a RAW stage .h5ad (or take it from `cache`), subsample rows (sparse-aware) BEFORE densifying, return
    (X, C, celltypes, genes). Files exported by make_pseudo_split are refused. The stage read from disk is never
    modified, so a cached copy serves every seed."""
    import scipy.sparse as sp

    path = Path(path)
    a = _stage(path, cache)
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


def score_many(task: str, preds, target, reference, setting: str = "heart", frac: float = 0.1, seed: int = 0,
               max_cells: int = 4000, pred_max_cells: int = 0, cache=None) -> list:
    """Score one or more predictions under ONE subsample seed against the SAME draw: the reference and target
    subsamples, the target halves A / B, the frozen cell-type probe, the floor row and the ceiling are computed once
    and shared, so the predictions differ only in themselves. Result i is exactly score(preds[i], ..., seed=seed):
    the draw does not depend on the predictions (each prediction's own subsample, used only when --pred-max-cells
    caps it, has its own generator seeded by `seed`)."""
    if task not in WEIGHTS:
        raise ValueError("task must be T1, T2 or T3")
    preds = list(preds)
    if not preds:
        raise ValueError("at least one prediction is required")
    need_coords = task in ("T2", "T3")
    rng = np.random.default_rng(seed)
    sh = load_veckit()
    metrics, m2 = sh._load_task_metrics(task)
    base_skill = veckit_skill_fn()
    vk = veckit_info()

    t0 = time.time()
    ref_X, ref_C, ref_ct, genes = load_arrays(reference, need_coords, rng, frac, max_cells, cache=cache)
    tgt_X, tgt_C, tgt_ct, _ = load_arrays(target, need_coords, rng, frac, 2 * max_cells, genes, cache=cache)

    # half split of the target: A = scored against, B = ceiling estimate
    perm = rng.permutation(tgt_X.shape[0])
    ia, ib = np.sort(perm[: len(perm) // 2]), np.sort(perm[len(perm) // 2:])
    A = (tgt_X[ia], None if tgt_C is None else tgt_C[ia], tgt_ct[ia])
    B = (tgt_X[ib], None if tgt_C is None else tgt_C[ib], tgt_ct[ib])
    REF = (ref_X, ref_C, ref_ct)

    loaded = []
    for pred in preds:
        prd_X, prd_C, prd_ct, _ = load_arrays(pred, need_coords, np.random.default_rng([seed, 1]), 1.0,
                                              pred_max_cells or 10 ** 9, genes, cache=cache)
        if (prd_X < 0).any():
            raise ValueError(f"{Path(pred).name}: prediction .X has negative values; the veckit scorer rejects negative "
                             "expression")
        loaded.append((prd_X, prd_C, prd_ct))

    # the frozen cell-type probe is trained once on the scored half and shared by every panel run
    probe = metrics.train_frozen_probe(A[0], A[2])
    raw_preds = [run_panel(task, m2, PRED, A, REF, seed, probe) for PRED in loaded]
    raw_floor = run_panel(task, m2, REF, A, REF, seed, probe)       # copy_last / wt_identity
    raw_ceiling = run_panel(task, m2, B, A, REF, seed, probe)       # other half of the truth

    results = []
    for pred, PRED, raw_pred in zip(preds, loaded, raw_preds):
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
        results.append({
            "mode": "single_seed", "task": task, "setting": setting if task == "T2" else None, "pred": str(pred),
            "target": str(target), "reference": str(reference), "frac": frac, "seed": seed,
            "cells": {"pred": int(PRED[0].shape[0]), "target_A": int(len(ia)), "target_B": int(len(ib)),
                      "reference": int(ref_X.shape[0])},
            "task_score": round(task_score, 2), "rows": rows, "raw_pred": raw_pred, "raw_floor": raw_floor,
            "raw_ceiling": raw_ceiling,
            "veckit": dict(vk, skill_source="veckit common.core_metrics.skill" if base_skill else "kit transcription",
                           tested_against=TESTED_VECKIT_VERSION),
            "seconds": round(time.time() - t0, 1)})
    return results


def score(task: str, pred, target, reference, setting: str = "heart", frac: float = 0.1, seed: int = 0,
          max_cells: int = 4000, pred_max_cells: int = 0, cache=None) -> dict:
    """Score `pred` on the pseudo board (target, reference) with local floor / ceiling under ONE subsample seed.
    Returns a result dict: task_score, rows [{group, metric, raw, floor, ceiling, skill, weight, points, folded,
    degenerate, undefined}], raw_pred, raw_floor, raw_ceiling, cells, veckit, seconds. `cache` (a dict) keeps the
    stages read from disk for the next call; summarise() uses it so that every seed reads each file once.
    For the default multi-seed band use summarise(); to compare two predictions, compare()."""
    return score_many(task, [pred], target, reference, setting=setting, frac=frac, seed=seed, max_cells=max_cells,
                      pred_max_cells=pred_max_cells, cache=cache)[0]


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


# ---- the multi-seed band (default output) ------------------------------------------------------------
DEFAULT_SEEDS = (0, 1, 2, 3, 4)
SEED_NOTE = ("the organisers, in their review of this kit, said the subsample seed will depend on each submission; "
             "this band shows how much the score moves with the subsample seed on YOUR pseudo split, not on the "
             "hidden target")


def summarise(task: str, pred, target, reference, seeds=DEFAULT_SEEDS, setting: str = "heart", frac: float = 0.1,
              max_cells: int = 4000, pred_max_cells: int = 0) -> dict:
    """Score over several subsample seeds (each file read once) and summarise. Returns a dict with task_score_mean,
    task_score_sd (ddof=1), task_score_min / task_score_max and band [min, max] over the seeds, task_scores,
    metrics{name: group, weight, folded, raw_mean, raw_sd, skill_mean, skill_sd, points_mean, floor_mean,
    ceiling_mean, degenerate_seeds, undefined_seeds}, per_seed [score() result dicts]. Seed s gives exactly
    score(..., seed=s)."""
    import warnings

    seeds = [int(s) for s in seeds]
    if not seeds:
        raise ValueError("seeds must not be empty")
    cache: dict = {}
    per = []
    for s in seeds:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            per.append(score(task, pred, target, reference, setting=setting, frac=frac, seed=s, max_cells=max_cells,
                             pred_max_cells=pred_max_cells, cache=cache))
    cache.clear()
    return _aggregate(task, pred, target, reference, seeds, setting, frac, per)


def _sd(v) -> float:
    return float(np.nanstd(v, ddof=1)) if len(v) > 1 else 0.0


def _aggregate(task, pred, target, reference, seeds, setting, frac, per) -> dict:
    """The multi-seed summary of per-seed score() results (see summarise())."""
    scores = np.array([r["task_score"] for r in per], dtype=float)

    sd = _sd
    metrics = {}
    for row in per[0]["rows"]:
        m = row["metric"]
        mine = [[rr for rr in r["rows"] if rr["metric"] == m][0] for r in per]
        vals = {k: np.array([np.nan if x[k] is None else float(x[k]) for x in mine], dtype=float)
                for k in ("raw", "skill", "points", "floor", "ceiling")}
        metrics[m] = {"group": row["group"], "weight": row["weight"], "folded": row["folded"],
                      "raw_mean": float(np.nanmean(vals["raw"])), "raw_sd": sd(vals["raw"]),
                      "skill_mean": float(np.mean(vals["skill"])), "skill_sd": sd(vals["skill"]),
                      "points_mean": float(np.mean(vals["points"])),
                      "floor_mean": float(np.nanmean(vals["floor"])), "ceiling_mean": float(np.nanmean(vals["ceiling"])),
                      "degenerate_seeds": int(sum(bool(x["degenerate"]) for x in mine)),
                      "undefined_seeds": int(sum(bool(x["undefined"]) for x in mine))}
    return {"mode": "multi_seed", "task": task, "setting": setting if task == "T2" else None, "pred": str(pred),
            "target": str(target), "reference": str(reference), "seeds": seeds, "frac": frac,
            "cells": per[0]["cells"],
            "task_score_mean": float(scores.mean()), "task_score_sd": sd(scores),
            "task_score_min": float(scores.min()), "task_score_max": float(scores.max()),
            "band": [float(scores.min()), float(scores.max())], "task_scores": scores.tolist(),
            "metrics": metrics, "veckit": per[0].get("veckit"), "seed_note": SEED_NOTE,
            "seconds": round(sum(r["seconds"] for r in per), 1), "per_seed": per}


def summary_line(res: dict) -> str:
    lo, hi = res["band"]
    return (f"{Path(res['pred']).name} on {Path(res['target']).name}: {res['task_score_mean']:.2f} +- "
            f"{res['task_score_sd']:.2f} (sd), band {lo:.2f}..{hi:.2f} (min..max over seeds {res['seeds']})")


def format_summary(res: dict) -> str:
    c = res["cells"]
    head = (f"{res['task']}{' ' + res['setting'] if res['setting'] else ''}  pred={Path(res['pred']).name}  "
            f"target={Path(res['target']).name}  ref={Path(res['reference']).name}  "
            f"cells pred/A/B/ref = {c['pred']}/{c['target_A']}/{c['target_B']}/{c['reference']}  frac={res['frac']}  "
            f"seeds={res['seeds']}")
    lines = [head, f"{'metric':18s} {'raw_mean':>10s} {'raw_sd':>9s} {'floor':>10s} {'ceiling':>10s} {'skill':>7s} "
                   f"{'sd':>6s} {'pts':>6s}"]
    flags = False
    for m, v in res["metrics"].items():
        name = m + ("*" if v.get("folded") else "")
        mark = ""
        if v.get("degenerate_seeds") or v.get("undefined_seeds"):
            mark = f" (degenerate/undefined on {v['degenerate_seeds'] + v['undefined_seeds']} seed(s))"
            flags = True
        lines.append(f"{name:18s} {v['raw_mean']:10.4f} {v['raw_sd']:9.4f} {v['floor_mean']:10.4f} "
                     f"{v['ceiling_mean']:10.4f} {v['skill_mean']:7.3f} {v['skill_sd']:6.3f} {v['points_mean']:6.2f}{mark}")
    lo, hi = res["band"]
    lines.append(f"TASK SCORE (0-100; floor=50, ceiling=100): mean {res['task_score_mean']:.2f}  sd "
                 f"{res['task_score_sd']:.2f}  band {lo:.2f}..{hi:.2f} (min..max over {len(res['seeds'])} seeds)  "
                 f"[{res['seconds']}s]")
    lines.append(summary_line(res))
    if any(v.get("folded") for v in res["metrics"].values()):
        lines.append("* target-0 metric: skill computed on |value| (prediction, floor and ceiling), lower is better")
    if flags:
        lines.append("degenerate / undefined: floor and ceiling coincide or are missing on some seeds; the metric cannot "
                     "discriminate there")
    lines.append("note: " + SEED_NOTE)
    vk = res.get("veckit") or {}
    ver = vk.get("version") or "unknown version"
    note = "" if ver == TESTED_VECKIT_VERSION else f" (kit tested against {TESTED_VECKIT_VERSION})"
    lines.append(f"veckit {ver}{note}; the organisers' scorer is the source of truth and this wrapper may lag it")
    return "\n".join(lines)


# ---- paired comparison of two predictions ---------------------------------------------------------------
PAIRED_NOTE = ("paired: in every seed both files are scored against the same subsample, target halves, floor and "
               "ceiling, so the per-seed B - A removes the subsampling noise the two share; if its min..max straddles 0 "
               "the seeds disagree on which file is better. This compares two of your methods on this pseudo split, "
               "not on the hidden target")


def _metric_values(res: dict, key: str) -> dict:
    return {r["metric"]: r[key] for r in res["rows"]}


def compare(task: str, pred_a, pred_b, target, reference, seeds=DEFAULT_SEEDS, setting: str = "heart",
            frac: float = 0.1, max_cells: int = 4000, pred_max_cells: int = 0) -> dict:
    """Paired comparison: score predictions A and B under the same seeds, each seed with ONE shared draw (score_many),
    and summarise the per-seed differences B - A. Returns mode "paired", pred_a, pred_b, seeds, diff_scores (B - A
    per seed), diff_mean, diff_sd (ddof=1), diff_min, diff_max, b_higher_seeds / a_higher_seeds / tied_seeds,
    metric_diffs{name: points_diff_mean, points_diff_sd, skill_diff_mean, raw_diff_mean}, and a / b: the
    summarise()-style band of each file (task_score_mean, ..., per_seed). Seed s of a / b is exactly score(..., s)."""
    import warnings

    seeds = [int(s) for s in seeds]
    if not seeds:
        raise ValueError("seeds must not be empty")
    cache: dict = {}
    per_a, per_b = [], []
    for s in seeds:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ra, rb = score_many(task, [pred_a, pred_b], target, reference, setting=setting, frac=frac, seed=s,
                                max_cells=max_cells, pred_max_cells=pred_max_cells, cache=cache)
        per_a.append(ra)
        per_b.append(rb)
    cache.clear()
    a = _aggregate(task, pred_a, target, reference, seeds, setting, frac, per_a)
    b = _aggregate(task, pred_b, target, reference, seeds, setting, frac, per_b)
    diffs = np.array([round(rb["task_score"] - ra["task_score"], 2) for ra, rb in zip(per_a, per_b)], dtype=float)
    metric_diffs = {}
    for m in a["metrics"]:
        d = {}
        for k in ("points", "skill", "raw"):
            vals = []
            for ra, rb in zip(per_a, per_b):
                va, vb = _metric_values(ra, k)[m], _metric_values(rb, k)[m]
                vals.append(np.nan if va is None or vb is None else float(vb) - float(va))
            d[k] = np.array(vals, dtype=float)
        metric_diffs[m] = {"points_diff_mean": float(np.nanmean(d["points"])), "points_diff_sd": _sd(d["points"]),
                           "skill_diff_mean": float(np.nanmean(d["skill"])), "raw_diff_mean": float(np.nanmean(d["raw"]))}
    return {"mode": "paired", "task": task, "setting": setting if task == "T2" else None, "pred_a": str(pred_a),
            "pred_b": str(pred_b), "target": str(target), "reference": str(reference), "seeds": seeds, "frac": frac,
            "diff_scores": diffs.tolist(), "diff_mean": float(diffs.mean()), "diff_sd": _sd(diffs),
            "diff_min": float(diffs.min()), "diff_max": float(diffs.max()),
            "b_higher_seeds": int((diffs > 0).sum()), "a_higher_seeds": int((diffs < 0).sum()),
            "tied_seeds": int((diffs == 0).sum()), "metric_diffs": metric_diffs, "a": a, "b": b,
            "veckit": a.get("veckit"), "paired_note": PAIRED_NOTE, "seed_note": SEED_NOTE,
            "seconds": round(sum(r["seconds"] for r in per_b), 1)}


def paired_line(res: dict) -> str:
    n = len(res["seeds"])
    return (f"B - A ({Path(res['pred_b']).name} - {Path(res['pred_a']).name}) on {Path(res['target']).name}: "
            f"{res['diff_mean']:+.2f} +- {res['diff_sd']:.2f} (sd), min..max {res['diff_min']:+.2f}..{res['diff_max']:+.2f} "
            f"over seeds {res['seeds']}; B higher on {res['b_higher_seeds']} of {n} seeds")


def format_paired(res: dict) -> str:
    a, b = res["a"], res["b"]
    head = (f"{res['task']}{' ' + res['setting'] if res['setting'] else ''}  target={Path(res['target']).name}  "
            f"ref={Path(res['reference']).name}  frac={res['frac']}  seeds={res['seeds']}  (paired comparison)")
    lines = [head,
             f"A = {Path(res['pred_a']).name}: mean {a['task_score_mean']:.2f}  sd {a['task_score_sd']:.2f}  band "
             f"{a['band'][0]:.2f}..{a['band'][1]:.2f}",
             f"B = {Path(res['pred_b']).name}: mean {b['task_score_mean']:.2f}  sd {b['task_score_sd']:.2f}  band "
             f"{b['band'][0]:.2f}..{b['band'][1]:.2f}",
             f"{'metric':18s} {'A pts':>7s} {'B pts':>7s} {'B-A pts':>8s} {'sd':>6s}"]
    for m, d in res["metric_diffs"].items():
        name = m + ("*" if a["metrics"][m].get("folded") else "")
        lines.append(f"{name:18s} {a['metrics'][m]['points_mean']:7.2f} {b['metrics'][m]['points_mean']:7.2f} "
                     f"{d['points_diff_mean']:+8.2f} {d['points_diff_sd']:6.2f}")
    per_seed = "  ".join(f"{s}: {d:+.2f}" for s, d in zip(res["seeds"], res["diff_scores"]))
    lines.append(f"TASK SCORE B - A per seed: {per_seed}")
    lines.append(f"TASK SCORE B - A: mean {res['diff_mean']:+.2f}  sd {res['diff_sd']:.2f}  min..max "
                 f"{res['diff_min']:+.2f}..{res['diff_max']:+.2f} over {len(res['seeds'])} seeds  [{res['seconds']}s]")
    lines.append(paired_line(res))
    if any(v.get("folded") for v in a["metrics"].values()):
        lines.append("* target-0 metric: skill computed on |value| (prediction, floor and ceiling), lower is better")
    lines.append("note: " + PAIRED_NOTE)
    vk = res.get("veckit") or {}
    ver = vk.get("version") or "unknown version"
    note = "" if ver == TESTED_VECKIT_VERSION else f" (kit tested against {TESTED_VECKIT_VERSION})"
    lines.append(f"veckit {ver}{note}; the organisers' scorer is the source of truth and this wrapper may lag it")
    return "\n".join(lines)


def main(argv=None, prog: str = "python -m vec_local_score") -> int:
    p = argparse.ArgumentParser(prog=prog, description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--task", required=True, choices=["T1", "T2", "T3"])
    p.add_argument("--setting", default="heart", choices=["heart", "embryo"], help="T2 only, recorded in the output")
    p.add_argument("--pred", required=True, type=Path, action="append",
                   help="the prediction for the held-out stage; give it twice (--pred A --pred B) for the paired "
                        "comparison B - A over the same seeds")
    p.add_argument("--target", required=True, type=Path,
                   help="RAW released stage held out as the pseudo-target (the wrapper subsamples and splits it)")
    p.add_argument("--reference", type=Path, help="T1/T2: RAW preceding stage = DE reference and copy_last floor")
    p.add_argument("--wt", type=Path, help="T3: RAW matched wild type = DE reference and wt_identity floor")
    p.add_argument("--frac", type=float, default=0.1,
                   help="subsample fraction applied to the raw target and reference stages (veckit protocol: 0.1)")
    p.add_argument("--max-cells", type=int, default=4000, help="cap for the reference (target: 2x) after the --frac subsample")
    p.add_argument("--pred-max-cells", type=int, default=0,
                   help="cap for the PREDICTION (0 = score every submitted cell, as the server does)")
    p.add_argument("--seeds", type=int, nargs="+", default=None,
                   help="subsample seeds of the multi-seed band, the default output (default: 0 1 2 3 4)")
    p.add_argument("--single-seed", action="store_true",
                   help="the old behaviour: one seed (--seed, default 0) and its full per-metric table")
    p.add_argument("--seed", type=int, default=None,
                   help="the seed of --single-seed (given alone, it implies --single-seed)")
    p.add_argument("--verbose", action="store_true", help="multi-seed: also print every per-seed table")
    p.add_argument("--json", type=Path)
    args = p.parse_args(argv)

    ref_path = args.wt if args.task == "T3" else args.reference
    if ref_path is None:
        p.error("--reference (T1/T2) or --wt (T3) is required for a meaningful score")
    if args.seeds is not None and (args.single_seed or args.seed is not None):
        p.error("--seeds (multi-seed band) cannot be combined with --single-seed / --seed")
    single = args.single_seed or args.seed is not None
    if len(args.pred) > 2:
        p.error("at most two --pred: A and B of the paired comparison")
    paired = len(args.pred) == 2
    if paired and single:
        p.error("--single-seed / --seed take one --pred; the paired comparison runs over --seeds (default 0 1 2 3 4)")
    try:
        if paired:
            res = compare(args.task, args.pred[0], args.pred[1], args.target, ref_path,
                          seeds=args.seeds or DEFAULT_SEEDS, setting=args.setting, frac=args.frac,
                          max_cells=args.max_cells, pred_max_cells=args.pred_max_cells)
        elif single:
            res = score(args.task, args.pred[0], args.target, ref_path, setting=args.setting, frac=args.frac,
                        seed=0 if args.seed is None else args.seed, max_cells=args.max_cells,
                        pred_max_cells=args.pred_max_cells)
        else:
            res = summarise(args.task, args.pred[0], args.target, ref_path, seeds=args.seeds or DEFAULT_SEEDS,
                            setting=args.setting, frac=args.frac, max_cells=args.max_cells,
                            pred_max_cells=args.pred_max_cells)
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
    if paired:
        if args.verbose:
            for r in (res["a"], res["b"]):
                print(format_summary(r))
                print()
        print(format_paired(res))
    elif single:
        print(format_table(res))
        print("single seed: the organisers, in their review of this kit, said the subsample seed will depend on each "
              "submission; drop --single-seed / --seed to see how much the score moves with the seed "
              "(the band, default)")
    else:
        if args.verbose:
            for r in res["per_seed"]:
                print(format_table(r))
                print()
        print(format_summary(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
