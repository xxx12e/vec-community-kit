"""I/O for the reference baselines: stage loading, row selection, and the safe submission writer.

Everything that touches the board contract goes through vec_submit_check (index.json + the board's genes file),
and every file written by `write_submission` is validated with vec_submit_check.check before this module returns.

Public API
    panel_for_board(board)                    -> (spec dict from index.json, ordered gene list)
    load_stage(path, panel_genes=None)        -> AnnData subset/reordered to the panel (raises if genes missing)
    looks_like_counts(X) / log_normalize(a)   -> detect and fix un-logged inputs (convention log1p(1e4*c/sum c))
    select_rows(n, spec, n_cells=...)         -> row indices that land inside [min_cells, max_cells]
    write_submission(X, coords, genes, out_path, board, n_cells=...) -> vec_submit_check report

THE CELL-COUNT GOTCHA (read this once)
    write_submission(..., n_cells=None) does NOT write every row you pass. With n_cells=None it subsamples to
    min(max_cells, DEFAULT_N_CELLS) = at most 4000 cells (without replacement, seeded). This keeps T1 files
    (32,285 genes) small, and 4000 cells is more than the scorer's own draws use, but it silently changes the
    number of cells in the file. Always pass the count you mean:
        n_cells=<int>   exactly that many rows (clamped to max_cells; below min_cells raises unless relax_cells)
        n_cells="all"   every row you passed (raises if that exceeds max_cells)
    The report's write_info block records what happened (n_available, target, n_written, sampling notes).
"""
from __future__ import annotations

import os
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import scipy.sparse as sp

from vec_submit_check import checker as vcheck

# Cell count written when n_cells is not given (see THE CELL-COUNT GOTCHA above).
DEFAULT_N_CELLS = 4000
PREFERRED_CELLS = DEFAULT_N_CELLS   # backwards-compatible alias
# .X max above this is treated as raw / un-logged counts (same bound the checker warns on).
COUNTS_MAX_THRESHOLD = vcheck.COUNTS_MAX_WARN


class SubmissionError(ValueError, RuntimeError):
    """The prediction violates the board contract (pre-write checks or vec_submit_check)."""


# ----------------------------------------------------------------------------- panels / contract
def load_index(panels=None) -> dict:
    return vcheck.load_index(panels)


def panel_for_board(board: str, panels=None):
    """Return (board spec, ordered gene panel) for an index.json key such as "T1:val" or "T3:gata4"."""
    return vcheck.panel_for_board(board, panels)


# ----------------------------------------------------------------------------- loading
def load_stage(path, panel_genes=None) -> ad.AnnData:
    """Read an .h5ad; if `panel_genes` is given, subset and reorder var to exactly that list.

    Raises KeyError when any panel gene is absent from the file. var_names are cast to str. The expression
    matrix is left untouched (sparse stays sparse; see `log_normalize` for count-scale inputs).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    a = ad.read_h5ad(path)
    a.var_names = a.var_names.astype(str)
    if a.var_names.has_duplicates:
        raise ValueError(f"{path.name}: duplicate var_names")
    if panel_genes is not None:
        panel = [str(g) for g in panel_genes]
        have = set(a.var_names)
        missing = [g for g in panel if g not in have]
        if missing:
            raise KeyError(f"{path.name}: {len(missing)} panel genes missing from file, e.g. {missing[:10]}")
        if list(a.var_names) != panel:
            a = a[:, panel].copy()
    return a


def looks_like_counts(X, threshold: float = COUNTS_MAX_THRESHOLD) -> bool:
    """True when .X looks like raw or size-normalised counts rather than log1p expression."""
    data = X.data if sp.issparse(X) else np.asarray(X)
    return data.size > 0 and float(np.nanmax(data)) > threshold


def log_normalize(a: ad.AnnData, target_sum: float = 1e4) -> ad.AnnData:
    """normalize_total(target_sum) + log1p on .X: the released-data convention log1p(1e4 * c / sum c).

    Returns a new AnnData with float32 .X (dense stays dense, sparse becomes CSR). Only needed for inputs that
    are not already log-normalised; the official releases are stated to be log-normalised already.
    """
    b = a.copy()
    X = b.X
    if sp.issparse(X):
        X = sp.csr_matrix(X, dtype=np.float64)
        s = np.asarray(X.sum(axis=1)).ravel()
        s[s == 0] = 1.0
        X = sp.csr_matrix(sp.diags(target_sum / s) @ X)
        X.data = np.log1p(X.data)
        b.X = X.astype(np.float32)
    else:
        X = np.asarray(X, dtype=np.float64)
        s = X.sum(axis=1, keepdims=True)
        s[s == 0] = 1.0
        b.X = np.log1p(X * (target_sum / s)).astype(np.float32)
    b.uns["log1p"] = {"base": None}
    return b


# ----------------------------------------------------------------------------- rows
def select_rows(n_available: int, spec: dict, n_cells=None, seed: int = 0, relax_cells: bool = False):
    """Row indices for a submission that land inside [min_cells, max_cells].

    n_cells: None  -> target = min(max_cells, DEFAULT_N_CELLS)  (the default-subsample gotcha, see module doc)
             "all" -> target = n_available (raises ValueError if that exceeds max_cells)
             int   -> target = n_cells (clamped to max_cells; below min_cells raises unless relax_cells)
      n >= target             -> random subset of `target` rows, WITHOUT replacement, sorted
      min_cells <= n < target -> every row, original order (duplicating would add nothing)
      n < min_cells           -> every row + (min_cells - n) rows drawn with replacement (duplicates),
                                 unless relax_cells, in which case every row as-is
    Returns (indices, notes dict).
    """
    n_available = int(n_available)
    if n_available <= 0:
        raise ValueError("no cells to write")
    rng = np.random.default_rng(seed)
    lo, hi = int(spec["min_cells"]), int(spec["max_cells"])
    if n_cells is None:
        target = min(hi, DEFAULT_N_CELLS)
        mode = "default"
    elif isinstance(n_cells, str) and n_cells.lower() == "all":
        if n_available > hi:
            raise ValueError(f"n_cells='all' but {n_available} rows exceed max_cells={hi}; pass an explicit n_cells")
        target = n_available
        mode = "all"
    else:
        target = int(n_cells)
        mode = "explicit"
    notes: dict = {"n_available": n_available, "target": target, "n_cells_mode": mode}
    if target > hi:
        notes["n_cells_clamped_to_max_cells"] = hi
        target = hi
    if target < lo:
        if not relax_cells:
            raise ValueError(f"n_cells={target} is below min_cells={lo} for this board (relax_cells=True to allow)")
        notes["target_below_min_cells_relaxed"] = True
    if n_available >= target:
        idx = np.sort(rng.choice(n_available, size=target, replace=False))
        notes["sampled_without_replacement"] = bool(n_available > target)
    elif n_available >= lo or relax_cells:
        idx = np.arange(n_available)
        notes["kept_all_rows"] = True
        if n_available < lo:
            notes["below_min_cells_relaxed"] = True
    else:
        extra = rng.choice(n_available, size=lo - n_available, replace=True)
        idx = np.concatenate([np.arange(n_available), extra])
        notes["duplicated_rows"] = int(lo - n_available)
    notes["n_written"] = int(len(idx))
    return idx, notes


# ----------------------------------------------------------------------------- writing
def write_submission(X, coords, genes, out_path, board: str, relax_cells: bool = False, n_cells=None,
                     seed: int = 0, obs=None, compression=None, panels=None) -> dict:
    """Build a board-valid AnnData from (X, coords, genes), write it, validate it, return the report.

    * var_names become exactly the board panel: columns of `X` are mapped by gene name, so a superset or a
      differently ordered `genes` is fine; a missing panel gene raises KeyError.
    * .X float32, negatives clipped to 0 (count reported), finiteness asserted; T1 stored as CSR when sparse
      enough, T2/T3 dense.
    * obsm["spatial_3D"] float32 (n, 3) written when the board needs coordinates (required then; dropped otherwise).
    * rows selected with `select_rows` so n_obs lands inside [min_cells, max_cells] - READ the n_cells note in
      the module docstring: n_cells=None subsamples to at most 4000 cells.
    * vec_submit_check.check() runs on the written file; any error raises SubmissionError, except the
      "< min_cells" error when relax_cells=True (tiny sample data / smoke tests; such a file is NOT uploadable).
    `obs` (optional, indexed like the rows of X) is carried along for local diagnostics only: the scorer ignores
    labels and the checker warns if "celltype" is present, so leave it out of a real submission.
    """
    out_path = Path(out_path)
    spec, panel = panel_for_board(board, panels)
    genes = [str(g) for g in genes]
    if X.ndim != 2:
        raise ValueError(f"X must be 2D, got shape {X.shape}")
    if X.shape[1] != len(genes):
        raise ValueError(f"X has {X.shape[1]} columns but {len(genes)} gene names were given")
    if len(set(genes)) != len(genes):
        raise ValueError("duplicate gene names in `genes`")
    pos = {g: i for i, g in enumerate(genes)}
    missing = [g for g in panel if g not in pos]
    if missing:
        raise KeyError(f"{len(missing)} board panel genes missing from the prediction, e.g. {missing[:10]}")
    col = np.array([pos[g] for g in panel], dtype=int)
    identity_cols = len(genes) == len(panel) and bool(np.all(col == np.arange(len(panel))))

    rows, notes = select_rows(X.shape[0], spec, n_cells=n_cells, seed=seed, relax_cells=relax_cells)
    n = len(rows)
    identity_rows = n == X.shape[0] and bool(np.array_equal(rows, np.arange(X.shape[0])))

    # ---- expression: rows, columns, float32, finite, non-negative ----
    if sp.issparse(X):
        Xs = sp.csr_matrix(X)
        if not identity_rows:
            Xs = Xs[rows]
        if not identity_cols:
            Xs = Xs[:, col]
        Xs = sp.csr_matrix(Xs, dtype=np.float32)
        if not np.all(np.isfinite(Xs.data)):
            raise SubmissionError("prediction .X contains NaN/inf")
        n_neg = int(np.count_nonzero(Xs.data < 0))
        if n_neg:
            Xs.data[Xs.data < 0] = 0.0
            Xs.eliminate_zeros()
        Xout = Xs
    else:
        Xd = np.asarray(X)
        if not identity_rows:
            Xd = Xd[rows]
        if not identity_cols:
            Xd = Xd[:, col]
        Xd = np.ascontiguousarray(Xd, dtype=np.float32)   # no copy when already contiguous float32
        if not np.all(np.isfinite(Xd)):
            raise SubmissionError("prediction .X contains NaN/inf")
        n_neg = int(np.count_nonzero(Xd < 0))
        if n_neg:
            if np.shares_memory(Xd, np.asarray(X)):
                Xd = Xd.copy()                             # never clip the caller's array in place
            np.maximum(Xd, 0.0, out=Xd)
        Xout = Xd
    # Storage: CSR costs about 8 bytes per non-zero, dense 4 bytes per entry, so CSR only pays below 50 % density.
    nnz = Xout.nnz if sp.issparse(Xout) else int(np.count_nonzero(Xout))
    density = nnz / max(1, Xout.shape[0] * Xout.shape[1])
    if spec["task"] == "T1" and density < 0.5:
        Xout = sp.csr_matrix(Xout, dtype=np.float32)
    elif sp.issparse(Xout):
        Xout = Xout.toarray()

    # ---- coordinates ----
    C = None
    coords_dropped = False
    if spec["needs_coords"]:
        if coords is None:
            raise SubmissionError(f"board {board} needs obsm['spatial_3D'] but coords is None")
        C = np.asarray(coords)
        if C.ndim != 2 or C.shape[0] != X.shape[0] or C.shape[1] < 3:
            raise SubmissionError(f"coords shape {C.shape} invalid; need (n_cells={X.shape[0]}, >=3)")
        C = np.array(C[rows][:, :3], dtype=np.float32, copy=True, order="C")
        if not np.all(np.isfinite(C)):
            raise SubmissionError("coords contain NaN/inf")
    elif coords is not None:
        coords_dropped = True

    # ---- assemble ----
    obs_out = pd.DataFrame(index=pd.Index([f"cell_{i:06d}" for i in range(n)], name=None))
    if obs is not None:
        extra = obs.iloc[rows].reset_index(drop=True)
        extra.index = obs_out.index
        obs_out = extra
    a = ad.AnnData(X=Xout, obs=obs_out, var=pd.DataFrame(index=pd.Index(panel, name=None)))
    if C is not None:
        a.obsm["spatial_3D"] = C
    a.uns["submission"] = {"board": board, "n_source_cells": int(X.shape[0]), "seed": int(seed),
                           "n_negative_clipped": int(n_neg), "x_density": float(round(density, 4))}
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- write to a temp name, validate, then atomically move into place ----
    tmp_path = out_path.with_name(out_path.stem + ".tmp" + out_path.suffix)
    tmp_path.unlink(missing_ok=True)
    try:
        a.write_h5ad(tmp_path, compression=compression)
        rep = vcheck.check(tmp_path, board, panels)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    errors = list(rep["errors"])
    ignored = []
    if relax_cells:
        ignored = [e for e in errors if "< min_cells" in e]
        errors = [e for e in errors if "< min_cells" not in e]
    rep["errors"], rep["ignored_errors"], rep["ok"] = errors, ignored, not errors
    rep["ok_for_upload"] = not errors and not ignored          # relaxed files are NOT uploadable
    rep["write_info"] = dict(notes, n_negative_clipped=int(n_neg), coords_dropped=coords_dropped,
                             columns_remapped=not identity_cols, x_density=float(round(density, 4)),
                             x_storage=("csr" if sp.issparse(Xout) else "dense"), out=str(out_path))
    if errors:
        tmp_path.unlink(missing_ok=True)
        raise SubmissionError(f"{out_path} fails the {board} contract:\n  " + "\n  ".join(errors))
    os.replace(tmp_path, out_path)
    rep["file"] = str(out_path)
    return rep
