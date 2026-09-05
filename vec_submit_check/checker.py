"""Validate a prediction .h5ad against a Virtual Embryo Challenge board contract.

Contract source: data/panels/index.json + data/panels/<board>.genes.txt, copies of the public files published
at https://virtualembryo.ai/challenge/panels/ . The checks mirror what the official portal rejects on:

  * var_names == board panel, element by element, same order (the portal does not reorder genes)
  * n_obs within [min_cells, max_cells]
  * file size <= MAX_FILE_MB (portal cap: a single .h5ad of at most 1200 MB)
  * .X finite; for T2/T3 also non-negative (log-normalised expression); dtype castable to float32
  * obsm["spatial_3D"] present with shape (n, >=3) and finite when the board needs coordinates
  * warns if cell-type labels are present (the scorer ignores them; harmless)
The panel file itself is verified against index.json's genes_sha256 before it is trusted.

Usage:
  python -m vec_submit_check --board T1:val pred.h5ad
  python -m vec_submit_check --board T2:heart:val_interp pred.h5ad --json report.json

Exit code 0 = passes, 1 = fails, 2 = usage error.

Panel location: the directory named by the VEC_PANELS_DIR environment variable, else <kit>/data/panels, else
./data/panels relative to the current directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PANELS = ROOT / "data" / "panels"
# Portal cap on one prediction file ("single .h5ad, max 1200 MB"), measured in MB = 1e6 bytes (the stricter reading).
MAX_FILE_MB = 1200.0
# .X max above this looks like raw counts rather than log-normalised expression (warning only).
COUNTS_MAX_WARN = 30.0


def panels_dir(panels=None) -> Path:
    """Resolve the directory holding index.json and the *.genes.txt files."""
    if panels is not None:
        return Path(panels)
    env = os.environ.get("VEC_PANELS_DIR")
    if env:
        return Path(env)
    if (DEFAULT_PANELS / "index.json").exists():
        return DEFAULT_PANELS
    local = Path.cwd() / "data" / "panels"
    if (local / "index.json").exists():
        return local
    raise FileNotFoundError("board panel files not found: set VEC_PANELS_DIR to a directory holding index.json and "
                            "the *.genes.txt files (copies ship in data/panels/ of vec-community-kit)")


def load_index(panels=None) -> dict:
    with open(panels_dir(panels) / "index.json", encoding="utf-8") as f:
        return json.load(f)


def known_boards(panels=None) -> list:
    return sorted(load_index(panels))


def panel_sha256(genes) -> str:
    """index.json 'genes_sha256' convention: sha256 of the newline-joined gene list, first 16 hex characters."""
    return hashlib.sha256("\n".join(str(g) for g in genes).encode("utf-8")).hexdigest()[:16]


def load_panel(genes_file: str, expected_sha256=None, panels=None) -> list:
    """Read a board's genes file; when `expected_sha256` (index.json genes_sha256) is given, verify it."""
    with open(panels_dir(panels) / genes_file, encoding="utf-8") as f:
        genes = [line.strip() for line in f if line.strip()]
    if expected_sha256 is not None:
        got = panel_sha256(genes)
        if got != expected_sha256:
            raise RuntimeError(f"{genes_file}: sha256 {got} != index.json genes_sha256 {expected_sha256}; the panel "
                               "file is corrupted or hand-edited, re-download the panel files")
    return genes


def panel_for_board(board: str, panels=None):
    """Return (board spec, ordered gene panel) for an index.json key such as "T1:val" or "T3:gata4"."""
    index = load_index(panels)
    if board not in index:
        raise KeyError(f"unknown board {board!r}; known boards: {sorted(index)}")
    spec = index[board]
    genes = load_panel(spec["genes_file"], spec.get("genes_sha256"), panels)
    if len(genes) != int(spec["n_genes"]):
        raise ValueError(f"{spec['genes_file']} has {len(genes)} genes but index.json says {spec['n_genes']}")
    if len(set(genes)) != len(genes):
        raise ValueError(f"{spec['genes_file']} contains duplicate gene names")
    return spec, genes


def sha256_file(path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def check(path, board: str, panels=None, max_file_mb: float = MAX_FILE_MB) -> dict:
    """Validate one file against one board. Returns a report dict with ok / errors / warnings / info."""
    import anndata as ad
    import scipy.sparse as sp

    path = Path(path)
    spec, panel = panel_for_board(board, panels)
    report = {"file": str(path), "board": board, "errors": [], "warnings": [], "info": {}}
    err, warn, info = report["errors"].append, report["warnings"].append, report["info"]

    a = ad.read_h5ad(path)
    n, g = a.shape
    info.update(n_obs=int(n), n_vars=int(g), sha256=sha256_file(path), size_mb=round(path.stat().st_size / 1e6, 1),
                max_file_mb=max_file_mb)
    if info["size_mb"] > max_file_mb:
        err(f"file size {info['size_mb']} MB > portal cap {max_file_mb:g} MB (store .X as CSR when it is sparse, dense "
            "float32 when it is not; write fewer cells; or use compression='gzip')")

    # --- genes ---
    if g != spec["n_genes"]:
        err(f"n_vars={g} but board expects {spec['n_genes']}")
    names = list(map(str, a.var_names))
    if names != panel:
        if sorted(names) == sorted(panel):
            err("gene set matches the panel but ORDER differs; the portal rejects this (reorder with the panel file)")
        else:
            missing = sorted(set(panel) - set(names))[:10]
            extra = sorted(set(names) - set(panel))[:10]
            err(f"gene names differ from panel; missing e.g. {missing}; extra e.g. {extra}")
    if len(set(names)) != len(names):
        err("duplicate var_names")

    # --- cells ---
    if n < spec["min_cells"]:
        err(f"n_obs={n} < min_cells={spec['min_cells']}")
    if n > spec["max_cells"]:
        err(f"n_obs={n} > max_cells={spec['max_cells']}")

    # --- X ---
    X = a.X
    if sp.issparse(X):
        data = X.data
        info["X_format"] = type(X).__name__
        has_implicit_zero = X.nnz < n * g
    else:
        data = np.asarray(X).ravel()
        info["X_format"] = f"dense[{np.asarray(X).dtype}]"
        has_implicit_zero = False
    if data.size == 0:
        err(".X is empty")
    else:
        if not np.all(np.isfinite(data)):
            err(".X contains NaN/inf")
        finite = data[np.isfinite(data)]
        xmin = float(np.min(finite)) if finite.size else 0.0
        xmax = float(np.max(finite)) if finite.size else 0.0
        if has_implicit_zero:
            xmin, xmax = min(xmin, 0.0), max(xmax, 0.0)
        info.update(X_min=round(xmin, 4), X_max=round(xmax, 4),
                    X_nonzero_frac=round(float(np.count_nonzero(data)) / max(1, n * g), 4))
        if spec["task"] in ("T2", "T3") and xmin < 0:
            err(f".X has negative entries (min={xmin:.4f}); T2/T3 expression must be non-negative")
        if spec["task"] == "T1" and xmin < 0:
            warn(f".X has negative entries (min={xmin:.4f}); log1p data should be >= 0")
        if xmax > COUNTS_MAX_WARN:
            warn(f".X max={xmax:.2f} looks like raw counts, not log-normalised expression")
        if not np.issubdtype(data.dtype, np.floating):
            warn(f".X dtype {data.dtype} is not float; the scorer casts to float32")
        if finite.size and np.allclose(finite, finite[0]):
            err(".X is constant")

    # --- coordinates ---
    if spec["needs_coords"]:
        for key in spec["obsm_required"]:
            if key not in a.obsm:
                err(f"obsm[{key!r}] missing (required for {board})")
                continue
            C = np.asarray(a.obsm[key])
            if C.ndim != 2 or C.shape[0] != n or C.shape[1] < 3:
                err(f"obsm[{key!r}] shape {C.shape} invalid; need (n_obs, >=3)")
            elif not np.all(np.isfinite(C[:, :3])):
                err(f"obsm[{key!r}] has NaN/inf")
            else:
                rms = float(np.sqrt(np.mean(np.sum((C[:, :3] - C[:, :3].mean(0)) ** 2, axis=1))))
                info[f"{key}_rms_radius"] = round(rms, 3)
                if rms == 0:
                    err(f"obsm[{key!r}] collapsed to a point")
    elif "spatial_3D" in a.obsm:
        warn("obsm['spatial_3D'] present but the board does not need coordinates (harmless)")

    for k in spec["obs_required"]:
        if k not in a.obs:
            err(f"obs[{k!r}] required but missing")
    if "celltype" in a.obs:
        warn("obs['celltype'] present; the scorer ignores it and re-types cells with its own frozen classifier")

    report["ok"] = not report["errors"]
    return report


def format_report(rep: dict) -> str:
    status = "PASS" if rep["ok"] else "FAIL"
    lines = [f"[{status}] {rep['file']} @ {rep['board']}  n_obs={rep['info'].get('n_obs')} n_vars={rep['info'].get('n_vars')}"]
    lines += [f"  ERROR: {e}" for e in rep["errors"]]
    lines += [f"  warn : {w}" for w in rep["warnings"]]
    lines += [f"  {k}: {v}" for k, v in rep["info"].items()]
    return "\n".join(lines)


def safe_std_streams() -> None:
    """Never die on printing a path: with a non-UTF-8 stdout a non-ASCII path would raise after the real work."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="backslashreplace")
            except (ValueError, AttributeError):
                pass


def main(argv=None) -> int:
    safe_std_streams()
    p = argparse.ArgumentParser(prog="python -m vec_submit_check", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("h5ad", type=Path)
    p.add_argument("--board", required=True,
                   help="T1:val | T2:embryo:val_interp | T2:heart:val_interp | T2:heart:val_extrap | T3:gata4")
    p.add_argument("--panels", type=Path, default=None, help="directory with index.json + *.genes.txt (default: see module doc)")
    p.add_argument("--json", type=Path, help="write the report as JSON here")
    args = p.parse_args(argv)
    if not args.h5ad.exists():
        print(f"no such file: {args.h5ad}", file=sys.stderr)
        return 2
    try:
        rep = check(args.h5ad, args.board, args.panels)
    except (KeyError, FileNotFoundError) as e:
        print(f"usage error: {e}", file=sys.stderr)
        return 2
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    print(format_report(rep))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
