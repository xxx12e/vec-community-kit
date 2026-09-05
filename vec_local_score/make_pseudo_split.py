#!/usr/bin/env python
"""Build a local pseudo-validation board that mimics the official scorer's handling of the target.

Official protocol: every stage is subsampled to 10 % before comparison; the target is split in half - one half
is scored against (the "truth"), the other half is scored AS a prediction to give the attainable ceiling. veckit
itself does none of this (it scores --input against the whole --target file you give it), so this script
prepares the files; you then call veckit three times (ceiling, floor, your model) or use `vec_local_score`,
which does the split in memory.

Outputs into --out-dir:
    target_score.h5ad     the half of the 10 % target subsample to point veckit at as --target
    target_ceiling.h5ad   the other half, to be scored as --input for the ceiling row
    reference.h5ad        10 % subsample of --reference (the DE reference AND the copy_last floor prediction)
    meta.json             cell counts and panel size

Example (heart, hold out E8.75 and predict it from E8.25):
    python -m vec_local_score.make_pseudo_split --target E8.75.h5ad --reference E8.25_late.h5ad \
        --out-dir pseudo/heart_E8.25_to_E8.75 --panel data/panels/T2__heart__val_interp.genes.txt
Coordinates (obsm["spatial_3D"]) are kept when present and required with --require-coords (T2/T3).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anndata as ad
import numpy as np
from scipy import sparse


def slim(a: ad.AnnData, panel=None, require_coords: bool = False) -> ad.AnnData:
    """Keep only what the scorer reads: X, obs['celltype'], obsm['spatial_3D']; enforce panel order."""
    a.var_names = a.var_names.astype(str)
    if panel is not None:
        have = set(a.var_names)
        missing = [g for g in panel if g not in have]
        if missing:
            raise ValueError(f"{len(missing)} panel genes missing from file, head={missing[:5]}")
        a = a[:, panel].copy()
    X = a.X
    X = X.astype(np.float32) if sparse.issparse(X) else np.asarray(X, dtype=np.float32)
    obs = a.obs[["celltype"]].copy() if "celltype" in a.obs else a.obs.iloc[:, :0].copy()
    out = ad.AnnData(X=X, obs=obs, var=a.var.iloc[:, :0].copy())
    if "spatial_3D" in a.obsm:
        out.obsm["spatial_3D"] = np.asarray(a.obsm["spatial_3D"], dtype=np.float32)[:, :3]
    elif require_coords:
        raise KeyError("obsm['spatial_3D'] missing")
    return out


def make_split(target, reference, out_dir, frac: float = 0.10, seed: int = 0, panel=None,
               require_coords: bool = False, min_cells: int = 20) -> dict:
    out_dir = Path(out_dir)
    rng = np.random.default_rng(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    tgt = slim(ad.read_h5ad(target), panel, require_coords)
    ref = slim(ad.read_h5ad(reference), panel, require_coords)
    if list(tgt.var_names) != list(ref.var_names):
        raise ValueError("target and reference var_names differ in content/order; pass --panel")

    n_t = tgt.n_obs
    k_t = min(n_t, max(int(round(n_t * frac)), min_cells))
    idx_t = rng.choice(n_t, k_t, replace=False)
    perm = rng.permutation(k_t)
    score_half, ceil_half = idx_t[perm[: k_t // 2]], idx_t[perm[k_t // 2:]]
    n_r = ref.n_obs
    k_r = min(n_r, max(int(round(n_r * frac)), min_cells))
    idx_r = rng.choice(n_r, k_r, replace=False)

    t_score, t_ceil, r_sub = tgt[np.sort(score_half)].copy(), tgt[np.sort(ceil_half)].copy(), ref[np.sort(idx_r)].copy()
    t_score.write_h5ad(out_dir / "target_score.h5ad")
    t_ceil.write_h5ad(out_dir / "target_ceiling.h5ad")
    r_sub.write_h5ad(out_dir / "reference.h5ad")
    meta = {"target_file": str(target), "reference_file": str(reference), "frac": frac, "seed": seed,
            "target_full_cells": int(n_t), "target_score_cells": int(t_score.n_obs), "target_ceiling_cells": int(t_ceil.n_obs),
            "reference_full_cells": int(n_r), "reference_cells": int(r_sub.n_obs), "genes": int(tgt.n_vars),
            "has_coords": bool("spatial_3D" in tgt.obsm)}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m vec_local_score.make_pseudo_split", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", required=True, type=Path, help="stage to be predicted (held out)")
    ap.add_argument("--reference", required=True, type=Path, help="preceding stage (DE reference / copy_last)")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--frac", type=float, default=0.10, help="subsample fraction applied to every stage (official: 0.10)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--panel", type=Path, help="genes.txt from data/panels to subset + order both files to")
    ap.add_argument("--require-coords", action="store_true", help="fail if obsm['spatial_3D'] is missing (T2/T3)")
    args = ap.parse_args(argv)
    panel = None
    if args.panel:
        panel = [line.strip() for line in args.panel.read_text(encoding="utf-8").splitlines() if line.strip()]
    meta = make_split(args.target, args.reference, args.out_dir, frac=args.frac, seed=args.seed, panel=panel,
                      require_coords=args.require_coords)
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
