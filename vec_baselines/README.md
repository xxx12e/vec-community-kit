# vec_baselines - baseline generators and submission writer

Re-implementations of three baselines the Virtual Embryo Challenge publishes as one-line definitions, plus the
I/O needed to turn them into board-valid submission files with an explicit cell count.

| baseline | boards | definition | role |
|---|---|---|---|
| `copy_last(last)` | T1, T2 | resubmit the last observed stage verbatim (expression and coordinates) | the organisers' floor row |
| `wt_identity(wt)` | T3 | resubmit the matched wild type verbatim | the organisers' floor row |
| `pseudobulk_shift(prev, last)` | T1, T2 | move each cell of `last` by its own cell type's mean change between `prev` and `last`, clip at 0 | a baseline, not a floor row |

What "floor row" means here: the published floor value of a board (50 on the 0-100 skill scale) is the organisers'
own `copy_last` / `wt_identity` row scored on the hidden target. A file produced by this package is a resample of
the same released stage, so it lands **near** that value, not exactly on it. It is still the right first upload:
it exercises download, panel order, cell bounds, coordinates, upload and (Agent track) evidence with a known
reference point.

The organisers' own baseline code was not public when this kit was written; these are reconstructions of the
published text. Where the text leaves room (cells of `last` whose type has no cells in `prev`), the neutral
reading is used: they are copied unchanged and reported in `info["unmatched_types_in_last"]`.

## Files

* `io.py` - `panel_for_board`, `load_stage` (subset + reorder to the panel), `looks_like_counts` / `log_normalize`,
  `parse_n_cells`, `select_rows`, `write_submission` (validated with `vec_submit_check` before it returns).
* `methods.py` - the three baselines; each returns `(X float32 [n, G], coords float32 [n, 3] | None, info dict)`.
* `make_baseline.py` - CLI (`python -m vec_baselines.make_baseline ...`).

## The cell count is explicit and required

`write_submission(..., n_cells=...)` and `select_rows(..., n_cells=...)` require `n_cells` to be an **int** or the
literal **`"all"`**. Passing `None` (or leaving it out) raises a `ValueError` that says what to pass. An earlier
version defaulted to a 4000-cell subsample and silently changed the number of cells in the file; that is a pitfall
the authors hit themselves, hence the rule.

```python
bio.write_submission(X, C, panel, "pred.h5ad", board, n_cells=5000)   # exactly 5000 rows, drawn without replacement
bio.write_submission(X, C, panel, "pred.h5ad", board, n_cells="all")  # every row you passed
bio.write_submission(X, C, panel, "pred.h5ad", board)                 # ValueError: n_cells is required ...
```

* `n_cells=<int>` must lie inside the board's `[min_cells, max_cells]` (`data/panels/index.json`). Above
  `max_cells` raises; below `min_cells` raises unless `relax_cells=True` (smoke tests on tiny files; such a file is
  not uploadable). A source with fewer rows than requested, but at least `min_cells`, is written whole and the
  report notes `kept_all_rows`.
* `n_cells="all"` writes every source cell. It raises when that exceeds the board's `max_cells`, and the message
  states the bound (e.g. `the source has 17057 cells and the board allows at most max_cells=5118; pass an explicit
  n_cells inside [1000, 5118]`). The released stages hold more cells than most boards allow, so in practice you
  pass a number.

`report["write_info"]` records `n_available`, `target`, `n_written` and `n_cells_mode` (`all` / `explicit`).

Other writer behaviour: columns are mapped by gene name onto the board panel (a 500-gene heart file writes a valid
498-gene embryo-board file; a missing panel gene raises), `.X` is float32 with negatives clipped to 0 (count in
`write_info`), T1 is stored as CSR when sparse enough, T2/T3 dense, `obsm["spatial_3D"]` is float32 `(n, 3)`
when the board needs coordinates and dropped otherwise, and rows are duplicated only when the input has fewer
cells than `min_cells` (never the case for real releases; prefer `relax_cells=True` for smoke tests and never
duplicate cells in a real upload).

## CLI

`--n-cells` is required. Bounds per board are in `data/panels/index.json` (T1:val 1000-5118, T2:embryo:val_interp
583-5000, T2:heart:val_extrap 1000-25179, T2:heart:val_interp 1000-17616, T3:gata4 1000-7449).

```
python -m vec_baselines.make_baseline --method copy_last   --board T1:val               --last E9.5_RNA.h5ad --out pred.h5ad --n-cells 5000
python -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_extrap  --last E9.5.h5ad     --out pred.h5ad --n-cells 5000
python -m vec_baselines.make_baseline --method copy_last   --board T2:embryo:val_interp --last E8.0.h5ad     --out pred.h5ad --n-cells 5000
python -m vec_baselines.make_baseline --method wt_identity --board T3:gata4             --wt WT_E8.75.h5ad   --out pred.h5ad --n-cells 5000
python -m vec_baselines.make_baseline --method pseudobulk_shift --board T1:val --prev E8.5_RNA.h5ad --last E9.5_RNA.h5ad --out pred.h5ad --n-cells 5000
```

Options: `--n-cells N|all` (required), `--seed`, `--relax-cells` (tiny sample data; the file is then not
uploadable), `--log1p-counts` (count-scale inputs), `--celltype-key`, `--json report.json`, `--panels DIR`. Exit
code 0 only when the written file passes the board contract. Example verdict line:

```
[PASS] out/t3_wt_identity.h5ad @ T3:gata4  n_obs=5000 n_vars=500 X=dense[float32] min=0.0 max=7.6104 size=10.1MB
```

## Caveats

1. The scorer works on a 10 % subsample of every stage and splits the target in half (score half / ceiling half);
   local numbers on full data are on a different noise scale (see `vec_local_score`).
2. Cell-type label vocabularies are not necessarily harmonised across released stages; `pseudobulk_shift` shifts
   only the cells whose type exists in both stages and reports `frac_cells_shifted`.
3. The embryo panel has 498 genes while heart / T3 files carry 500; the writer maps columns by name.
4. No labels in submissions: the writer produces an empty `obs`; the scorer types cells itself.
5. Coordinates are copied in the input's own local frame; all spatial metrics are translation and rotation
   invariant.
