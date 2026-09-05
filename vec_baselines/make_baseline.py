#!/usr/bin/env python
"""Build one baseline (the organisers' published definitions) and write a board-valid submission .h5ad.

Inputs per method (all .h5ad, loaded and reordered to the board panel):
  copy_last         --last
  wt_identity       --wt
  pseudobulk_shift  --prev --last   [--celltype-key celltype]

Examples (paths are illustrative; the released stages hold more cells than most boards allow, so pass a count):
  python -m vec_baselines.make_baseline --method copy_last   --board T1:val  --last E9.5_RNA.h5ad --out pred.h5ad --n-cells 5000
  python -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_extrap --last E9.5.h5ad --out pred.h5ad --n-cells 5000
  python -m vec_baselines.make_baseline --method wt_identity --board T3:gata4 --wt WT_E8.75.h5ad --out pred.h5ad --n-cells 5000
  python -m vec_baselines.make_baseline --method pseudobulk_shift --board T2:heart:val_extrap --prev E8.75.h5ad --last E9.5.h5ad --out pred.h5ad --n-cells 5000

Cell count: --n-cells is REQUIRED - an integer inside the board's [min_cells, max_cells], or 'all' for every cell
of the source stage ('all' errors, stating the bound, when the stage exceeds max_cells). A source with fewer cells
than requested (but at least min_cells) is written whole, with a NOTE.
Smoke tests on tiny files: --relax-cells skips only the min_cells check (the file is then NOT uploadable);
--log1p-counts normalises count-scale inputs (normalize_total 1e4 + log1p).
Exit code 0 = file written and passes vec_submit_check; 1 = failed; 2 = usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):                       # run as a plain script: make the kit importable
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from vec_baselines import io as bio        # noqa: E402
from vec_baselines import methods as bm    # noqa: E402

NEEDS = {"copy_last": ["last"], "wt_identity": ["wt"], "pseudobulk_shift": ["prev", "last"]}
OUTPUT_STAGE = {"copy_last": "last", "wt_identity": "wt", "pseudobulk_shift": "last"}


def _jsonable(o):
    import numpy as np
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m vec_baselines.make_baseline", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--method", required=True, choices=sorted(NEEDS))
    p.add_argument("--board", required=True, help="index.json key, e.g. T1:val, T2:heart:val_extrap, T3:gata4")
    p.add_argument("--last", type=Path, help="last observed stage (copy_last, pseudobulk_shift)")
    p.add_argument("--prev", type=Path, help="stage before --last (pseudobulk_shift)")
    p.add_argument("--wt", type=Path, help="matched wild type at the target stage (wt_identity)")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--n-cells", required=True,
                   help="REQUIRED: cells to write - an integer inside the board's [min_cells, max_cells], or 'all' for "
                        "every cell of the source stage ('all' errors when the stage exceeds max_cells)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--relax-cells", action="store_true", help="ignore the min_cells check (tiny sample data; not uploadable)")
    p.add_argument("--celltype-key", default="celltype", help="obs column with cell-type labels (pseudobulk_shift)")
    p.add_argument("--log1p-counts", action="store_true",
                   help="normalize_total(1e4)+log1p any input whose .X max > 30 (count-scale)")
    p.add_argument("--panels", type=Path, default=None, help="directory with index.json + *.genes.txt")
    p.add_argument("--json", type=Path, help="write method info + check report as JSON here")
    args = p.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="backslashreplace")
            except (ValueError, AttributeError):
                pass

    missing = [k for k in NEEDS[args.method] if getattr(args, k) is None]
    if missing:
        p.error(f"--method {args.method} needs --" + " --".join(m.replace("_", "-") for m in missing))
    try:
        n_cells = bio.parse_n_cells(args.n_cells)
    except ValueError:
        p.error("--n-cells must be an integer or 'all'")

    t0 = time.time()
    try:
        spec, panel = bio.panel_for_board(args.board, args.panels)
    except KeyError as e:
        print(f"usage error: {e}", file=sys.stderr)
        return 2

    inputs = {}
    for k in NEEDS[args.method]:
        path = getattr(args, k)
        a = bio.load_stage(path, panel)
        if bio.looks_like_counts(a.X):
            if not args.log1p_counts:
                print(f"ERROR: {path} .X max > {bio.COUNTS_MAX_THRESHOLD}: looks like counts, not log1p expression. "
                      "Pass --log1p-counts to normalise it (normalize_total 1e4 + log1p).", file=sys.stderr)
                return 1
            a = bio.log_normalize(a)
            print(f"[make_baseline] {path.name}: count-scale .X detected -> normalize_total(1e4) + log1p applied")
        inputs[k] = a
        coords = " (+coords)" if "spatial_3D" in a.obsm else ""
        print(f"[make_baseline] loaded {k:<5s} {path.name}: {a.n_obs} cells x {a.n_vars} genes{coords}")

    # choose output rows up front so the method never densifies more cells than will be written
    src = inputs[OUTPUT_STAGE[args.method]]
    try:
        rows, notes = bio.select_rows(src.n_obs, spec, n_cells=n_cells, seed=args.seed, relax_cells=args.relax_cells)
    except ValueError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    if notes.get("kept_all_rows") and notes["n_written"] != notes["target"]:
        print(f"[make_baseline] NOTE: --n-cells {args.n_cells} requested but the source has only {notes['n_available']} "
              f"cells; writing all {notes['n_written']} of them.")

    try:
        if args.method == "copy_last":
            X, C, info = bm.copy_last(inputs["last"], rows=rows)
        elif args.method == "wt_identity":
            X, C, info = bm.wt_identity(inputs["wt"], rows=rows)
        else:
            X, C, info = bm.pseudobulk_shift(inputs["prev"], inputs["last"], celltype_key=args.celltype_key, rows=rows)
            if info["frac_cells_shifted"] < 0.8:
                print(f"WARNING: only {100 * info['frac_cells_shifted']:.1f}% of cells were shifted; types of --last with "
                      f"no cells in --prev: {json.dumps(info['unmatched_types_in_last'])}. Consider --celltype-key "
                      "<harmonised column>.", file=sys.stderr)
    except (ValueError, KeyError) as e:
        print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    info["row_selection"] = notes

    print("[make_baseline] method info:")
    print(json.dumps(info, indent=2, default=_jsonable))

    try:
        # rows were already selected above (inside the bounds), so the writer receives exactly the cells to write
        rep = bio.write_submission(X, C, panel, args.out, args.board, relax_cells=args.relax_cells, n_cells="all",
                                   seed=args.seed, panels=args.panels)
        ok = True
    except (bio.SubmissionError, ValueError, KeyError) as e:
        print(f"FAIL: {e}", file=sys.stderr)
        rep = {"ok": False, "errors": str(e).splitlines()[1:] or [str(e)], "warnings": [], "info": {}, "ignored_errors": []}
        ok = False

    status = "PASS" if ok else "FAIL"
    note = " (relaxed: below min_cells; NOT uploadable)" if ok and rep.get("ignored_errors") else ""
    inf = rep.get("info", {})
    print(f"\n[{status}]{note} {args.out} @ {args.board}  n_obs={inf.get('n_obs')} n_vars={inf.get('n_vars')} "
          f"X={inf.get('X_format')} min={inf.get('X_min')} max={inf.get('X_max')} size={inf.get('size_mb')}MB")
    for e in rep.get("errors", []):
        print(f"  ERROR: {e}")
    for e in rep.get("ignored_errors", []):
        print(f"  ignored (--relax-cells): {e}")
    for w in rep.get("warnings", []):
        print(f"  warn : {w}")
    print(f"  done in {time.time() - t0:.1f}s")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {"args": {k: str(v) for k, v in vars(args).items()}, "info": info, "check": rep}
        args.json.write_text(json.dumps(payload, indent=2, default=_jsonable) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
