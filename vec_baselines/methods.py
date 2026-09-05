"""Baseline generators for the Virtual Embryo Challenge, re-implemented from the organisers' public one-line
definitions (challenge task pages):

    copy_last(last)              T1/T2 floor row: resubmit the last observed stage verbatim
    wt_identity(wt)              T3 floor row: resubmit the matched wild type verbatim
    pseudobulk_shift(prev, last) T1/T2 baseline (not a floor row): move each cell of `last` by ITS OWN cell type's
                                 mean change prev -> last

Every function returns (X, coords, info):
    X       np.ndarray float32 [n, G], non-negative
    coords  np.ndarray float32 [n, 3] or None when the input has no obsm["spatial_3D"]
    info    dict of JSON-serialisable diagnostics

Inputs are AnnData objects (see io.load_stage); all inputs of one call must share var_names in the same order
(checked). `rows` restricts the OUTPUT cells while every statistic is computed on ALL cells of every input.

copy_last / wt_identity are the organisers' floor rows: the published floor (50 on the 0-100 skill scale) is the
organisers' own copy_last / wt_identity row scored on the hidden target. A file generated here is a resample of the
same stage, so it lands near that value, not exactly on it. It is still the right first upload: it exercises the
whole pipeline with a known reference point.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp


# ----------------------------------------------------------------------------- helpers
def _dense_rows(a, rows=None) -> np.ndarray:
    """float32 dense copy of a.X (optionally only `rows`, which may contain duplicates)."""
    X = a.X
    if rows is not None:
        X = X[rows]
    X = X.toarray() if sp.issparse(X) else np.array(X, copy=True)
    return np.ascontiguousarray(X, dtype=np.float32)


def _coords(a, rows=None):
    """float32 (n, 3) COPY of obsm['spatial_3D'] (never a view into the input AnnData)."""
    if "spatial_3D" not in a.obsm:
        return None
    C = np.asarray(a.obsm["spatial_3D"])
    if rows is not None:
        C = C[rows]
    return np.array(C[:, :3], dtype=np.float32, copy=True, order="C")


def _celltypes(a, key: str) -> np.ndarray:
    if key not in a.obs:
        raise KeyError(f"obs[{key!r}] not found; columns: {list(a.obs.columns)[:20]}")
    return np.asarray(a.obs[key]).astype(str)


def _type_means(a, key: str) -> dict:
    """{cell type: (mean vector float64, n_cells)} over all cells."""
    ct = _celltypes(a, key)
    X = a.X
    out = {}
    for t in np.unique(ct):
        mask = np.flatnonzero(ct == t)
        sub = X[mask]
        if sp.issparse(sub):
            m = np.asarray(sub.mean(axis=0), dtype=np.float64).ravel()
        else:
            m = np.asarray(sub, dtype=np.float64).mean(axis=0)
        out[str(t)] = (m, int(len(mask)))
    return out


def _same_genes(*adatas):
    names = [list(map(str, a.var_names)) for a in adatas]
    for i, nm in enumerate(names[1:], start=1):
        if nm != names[0]:
            raise ValueError(f"input {i} var_names differ from input 0 ({len(nm)} vs {len(names[0])} genes / order); "
                             "load every input with io.load_stage(path, panel)")
    return names[0]


def _base_info(method: str, X: np.ndarray, C, source) -> dict:
    return {"method": method, "n_cells": int(X.shape[0]), "n_genes": int(X.shape[1]),
            "has_coords": C is not None, "n_source_cells": int(source.n_obs)}


# ----------------------------------------------------------------------------- the organisers' rows
def copy_last(last, rows=None):
    """copy_last (T1/T2 floor row): resubmit the last observed stage verbatim (X and coords)."""
    X = _dense_rows(last, rows)
    C = _coords(last, rows)
    return X, C, _base_info("copy_last", X, C, last)


def wt_identity(wt, rows=None):
    """wt_identity (T3 floor row): resubmit the matched wild type verbatim (X and coords)."""
    X = _dense_rows(wt, rows)
    C = _coords(wt, rows)
    return X, C, _base_info("wt_identity", X, C, wt)


def pseudobulk_shift(prev, last, celltype_key: str = "celltype", rows=None):
    """pseudobulk_shift (T1/T2 reference row): move each cell of `last` by its own cell type's mean change.

        delta_c = mean_last(c) - mean_prev(c)   for every type c present in BOTH stages
        x_i     = clip(x_i + delta_{type(i)}, 0)
    Types of `last` that have no cells in `prev` get delta 0 (they are copied verbatim) and are listed in
    info["unmatched_types_in_last"] with their cell counts. Coordinates are copied from `last` unchanged.
    Cell-type label vocabularies are not necessarily harmonised across released stages, so read
    info["frac_cells_shifted"] before trusting a run of this row.
    """
    _same_genes(prev, last)
    m_prev = _type_means(prev, celltype_key)
    m_last = _type_means(last, celltype_key)
    ct = _celltypes(last, celltype_key)
    if rows is not None:
        ct = ct[rows]
    X = _dense_rows(last, rows)

    shared = sorted(set(m_prev) & set(m_last))
    only_last = sorted(set(m_last) - set(m_prev))
    only_prev = sorted(set(m_prev) - set(m_last))
    n_shifted = 0
    deltas = {}
    for t in shared:
        d = m_last[t][0] - m_prev[t][0]
        mask = ct == t
        if mask.any():
            X[mask] += d.astype(np.float32)
            n_shifted += int(mask.sum())
        deltas[t] = {"n_prev": m_prev[t][1], "n_last": m_last[t][1], "mean_abs_delta": float(np.abs(d).mean())}
    n_neg = int(np.count_nonzero(X < 0))
    np.maximum(X, 0.0, out=X)

    C = _coords(last, rows)
    info = _base_info("pseudobulk_shift", X, C, last)
    info.update({
        "celltype_key": celltype_key,
        "shared_types": shared,
        "unmatched_types_in_last": {t: int(np.count_nonzero(ct == t)) for t in only_last},
        "types_only_in_prev": only_prev,
        "n_cells_shifted": n_shifted,
        "n_cells_unshifted": int(X.shape[0] - n_shifted),
        "frac_cells_shifted": float(n_shifted / max(X.shape[0], 1)),
        "n_entries_clipped_at_zero": n_neg,
        "per_type": deltas,
    })
    return X, C, info


METHODS = {
    "copy_last": copy_last,
    "wt_identity": wt_identity,
    "pseudobulk_shift": pseudobulk_shift,
}
