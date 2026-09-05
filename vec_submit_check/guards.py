"""Generic numeric sanity guards for a prediction matrix. None of these is an official metric.

They catch the classic failure modes before a file is validated or scored: NaN / negative / count-scale entries
(the board contracts require finite, non-negative expression; a metric that comes back missing is scored 0, not
floor), a normalisation convention that
differs from the reference stage (library_size_ratio far from 1), mean collapse (variance_ratio near 0),
duplicated cells (they bias the unbiased distribution estimators), and cell counts outside the board bounds.

All functions accept dense or scipy.sparse matrices.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from .checker import load_index


def to_dense_f32(X) -> np.ndarray:
    X = X.toarray() if sp.issparse(X) else np.asarray(X)
    return np.ascontiguousarray(X, dtype=np.float32)


def pseudobulk(X) -> np.ndarray:
    """Mean expression per gene over all cells (float64)."""
    if sp.issparse(X):
        return np.asarray(X.mean(axis=0), dtype=np.float64).ravel()
    return np.asarray(X, dtype=np.float64).mean(axis=0)


def _jsonable(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, (np.integer,)):
            out[k] = int(v)
        elif isinstance(v, (np.floating,)):
            out[k] = float(v)
        elif isinstance(v, np.bool_):
            out[k] = bool(v)
        else:
            out[k] = v
    return out


def library_size_ratio(X_pred, X_ref) -> float:
    """Median implied library size expm1(x).sum() of pred over ref. 1.0 = same normalisation convention.

    The released data is log1p-normalised; a prediction normalised to a different target sum shows up here as a
    ratio far from 1 even when everything else looks plausible.
    """
    a, b = to_dense_f32(X_pred), to_dense_f32(X_ref)
    la = float(np.median(np.expm1(np.clip(a, 0, 50)).sum(1)))
    lb = float(np.median(np.expm1(np.clip(b, 0, 50)).sum(1)))
    return float(la / lb) if lb > 0 else float("nan")


def variance_ratio(X_pred, X_ref) -> float:
    """Mean per-gene variance of pred over ref: about 1 for a real population, about 0 for one cell broadcast."""
    va = float(to_dense_f32(X_pred).var(0).mean())
    vb = float(to_dense_f32(X_ref).var(0).mean())
    return float(va / vb) if vb > 0 else float("nan")


def zero_fraction_match(X_pred, X_ref) -> dict:
    """Per-gene zero-fraction agreement between pred and ref (sparsity structure)."""
    a, b = to_dense_f32(X_pred), to_dense_f32(X_ref)
    za, zb = (a == 0).mean(0), (b == 0).mean(0)
    d = za - zb
    return _jsonable({"zero_frac_pred": float(za.mean()), "zero_frac_ref": float(zb.mean()),
                      "per_gene_mean_abs_diff": float(np.abs(d).mean()), "per_gene_max_abs_diff": float(np.abs(d).max()),
                      "n_genes_pred_denser_by_5pct": int(np.count_nonzero(d < -0.05)),
                      "n_genes_pred_sparser_by_5pct": int(np.count_nonzero(d > 0.05))})


def duplicate_rows(X, C=None) -> dict:
    """Count exactly duplicated expression rows (and duplicated coordinate rows when C is given)."""
    A = np.ascontiguousarray(to_dense_f32(X))
    key = A.view(np.dtype((np.void, A.dtype.itemsize * A.shape[1]))).ravel()
    n_unique = len(np.unique(key))
    out = {"n_rows": int(A.shape[0]), "n_unique_expression_rows": int(n_unique),
           "n_duplicate_expression_rows": int(A.shape[0] - n_unique)}
    if C is not None:
        Cc = np.ascontiguousarray(np.asarray(C, dtype=np.float32)[:, :3])
        key_c = Cc.view(np.dtype((np.void, Cc.dtype.itemsize * 3))).ravel()
        out["n_unique_coordinate_rows"] = int(len(np.unique(key_c)))
        out["n_duplicate_coordinate_rows"] = int(A.shape[0] - out["n_unique_coordinate_rows"])
    return _jsonable(out)


def finite_nonneg(X, C=None, x_max_warn: float = 30.0) -> dict:
    """Finite, non-negative, float32-castable expression (and finite coordinates): the contract's hard requirements."""
    A = to_dense_f32(X)
    out = {"finite": bool(np.all(np.isfinite(A))), "n_nonfinite": int(np.count_nonzero(~np.isfinite(A))),
           "nonneg": bool(np.all(A >= 0)), "n_negative": int(np.count_nonzero(A < 0)),
           "x_max": float(np.nanmax(A)) if A.size else 0.0,
           "looks_like_counts": bool(A.size and float(np.nanmax(A)) > x_max_warn)}
    if C is not None:
        Cc = np.asarray(C)
        out["coords_shape_ok"] = bool(Cc.ndim == 2 and Cc.shape[0] == A.shape[0] and Cc.shape[1] >= 3)
        out["coords_finite"] = bool(np.all(np.isfinite(Cc)))
    out["ok"] = bool(out["finite"] and out["nonneg"] and not out["looks_like_counts"]
                     and out.get("coords_shape_ok", True) and out.get("coords_finite", True))
    return _jsonable(out)


def cell_count_bounds(n: int, board: str, panels=None) -> dict:
    """Is n inside [min_cells, max_cells] of the board? Also reports the board's truth_cells for context."""
    idx = load_index(panels)
    if board not in idx:
        raise KeyError(f"unknown board {board!r}; known: {sorted(idx)}")
    spec = idx[board]
    lo, hi = int(spec["min_cells"]), int(spec["max_cells"])
    return {"n": int(n), "min_cells": lo, "max_cells": hi, "truth_cells": int(spec["truth_cells"]),
            "ok": bool(lo <= int(n) <= hi)}


def check_all(X, C, X_ref, board=None, lib_band=(0.9, 1.1), var_band=(0.5, 2.0), panels=None) -> dict:
    """Run every guard. Returns a dict with "ok" (hard failures) and "warnings" (soft bands).

    Hard: finite / non-negative / not count-scale, cell-count bounds (when board is given), no duplicate rows.
    Soft: library_size_ratio inside lib_band, variance_ratio inside var_band (adjust the bands to your data).
    """
    rep = {"finite_nonneg": finite_nonneg(X, C), "duplicates": duplicate_rows(X, C),
           "library_size_ratio": library_size_ratio(X, X_ref), "variance_ratio": variance_ratio(X, X_ref),
           "zero_fraction": zero_fraction_match(X, X_ref)}
    hard, warn = [], []
    if not rep["finite_nonneg"]["ok"]:
        hard.append("expression/coords not finite, non-negative and log-scale")
    if rep["duplicates"]["n_duplicate_expression_rows"] > 0:
        hard.append(f"{rep['duplicates']['n_duplicate_expression_rows']} duplicated expression rows")
    if board is not None:
        rep["cell_count"] = cell_count_bounds(to_dense_f32(X).shape[0], board, panels)
        if not rep["cell_count"]["ok"]:
            hard.append(f"n_cells {rep['cell_count']['n']} outside [{rep['cell_count']['min_cells']}, "
                        f"{rep['cell_count']['max_cells']}]")
    if not (lib_band[0] <= rep["library_size_ratio"] <= lib_band[1]):
        warn.append(f"library_size_ratio {rep['library_size_ratio']:.3f} outside {lib_band}")
    if not (var_band[0] <= rep["variance_ratio"] <= var_band[1]):
        warn.append(f"variance_ratio {rep['variance_ratio']:.3f} outside {var_band}")
    rep["ok"] = not hard
    rep["hard_failures"] = hard
    rep["warnings"] = warn
    return rep
