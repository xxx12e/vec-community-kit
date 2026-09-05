# vec_baselines - the official floor rows as valid submission files

Re-implementations of three reference rows the Virtual Embryo Challenge publishes as one-line definitions, plus
the I/O needed to turn them into board-valid submission files. The floor rows (`copy_last`, `wt_identity`) sit at
exactly 50 on the 0-100 skill scale by construction, which makes them the ideal first upload: the whole pipeline
(download, panel order, cell bounds, coordinates, upload, evidence) is exercised with a known outcome.

| row | boards | definition |
|---|---|---|
| `copy_last(last)` | T1, T2 | resubmit the last observed stage verbatim (expression and coordinates) |
| `wt_identity(wt)` | T3 | resubmit the matched wild type verbatim |
| `pseudobulk_shift(prev, last)` | T1, T2 | move each cell of `last` by its own cell type's mean change between `prev` and `last`, clip at 0 |

The organisers' own baseline code was not public when this kit was written; these are reconstructions of the
published text. Where the text leaves room (cells of `last` whose type has no cells in `prev`), the neutral
reading is used: they are copied unchanged and reported in `info["unmatched_types_in_last"]`.

## Files

* `io.py` - `panel_for_board`, `load_stage` (subset + reorder to the panel), `looks_like_counts` / `log_normalize`,
  `select_rows`, `write_submission` (validated with `vec_submit_check` before it returns).
* `methods.py` - the three rows; each returns `(X float32 [n, G], coords float32 [n, 3] | None, info dict)`.
* `make_baseline.py` - CLI (`python -m vec_baselines.make_baseline ...`).

## The cell-count gotcha

`write_submission(..., n_cells=None)` does **not** write every row you pass. It subsamples to
`min(max_cells, 4000)` cells (seeded, without replacement). That is deliberate - 4000 cells is more than the
scorer's own draws use and it keeps T1 files (32,285 genes) small - but it silently changes your cell count.

```python
bio.write_submission(X, C, panel, "pred.h5ad", board)                 # at most 4000 cells written
bio.write_submission(X, C, panel, "pred.h5ad", board, n_cells="all")  # every row (must be <= max_cells)
bio.write_submission(X, C, panel, "pred.h5ad", board, n_cells=6000)   # exactly 6000 (clamped to max_cells)
```

The CLI prints a NOTE when the default applies; `report["write_info"]` records `n_available`, `target`,
`n_written` and `n_cells_mode` (`default` / `all` / `explicit`).

Other writer behaviour: columns are mapped by gene name onto the board panel (a 500-gene heart file writes a valid
498-gene embryo-board file; a missing panel gene raises), `.X` is float32 with negatives clipped to 0 (count in
`write_info`), T1 is stored as CSR when sparse enough, T2/T3 dense, `obsm["spatial_3D"]` is float32 `(n, 3)`
when the board needs coordinates and dropped otherwise, and rows are duplicated only when the input has fewer
cells than `min_cells` (never the case for real releases; prefer `relax_cells=True` for smoke tests and never
duplicate cells in a real upload).

## CLI

```
python -m vec_baselines.make_baseline --method copy_last   --board T1:val               --last E9.5_RNA.h5ad --out pred.h5ad --n-cells all
python -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_extrap  --last E9.5.h5ad     --out pred.h5ad --n-cells 5000
python -m vec_baselines.make_baseline --method copy_last   --board T2:embryo:val_interp --last E8.0.h5ad     --out pred.h5ad
python -m vec_baselines.make_baseline --method wt_identity --board T3:gata4             --wt WT_E8.75.h5ad   --out pred.h5ad --n-cells all
python -m vec_baselines.make_baseline --method pseudobulk_shift --board T1:val --prev E8.5_RNA.h5ad --last E9.5_RNA.h5ad --out pred.h5ad
```

Options: `--n-cells N|all`, `--seed`, `--relax-cells` (tiny sample data; the file is then not uploadable),
`--log1p-counts` (count-scale inputs), `--celltype-key`, `--json report.json`, `--panels DIR`. Exit code 0 only
when the written file passes the board contract.

## Caveats

1. The server scores a 10 % subsample of every stage and splits the target in half (score half / ceiling half);
   local numbers on full data are on a different noise scale (see `vec_local_score`).
2. Cell-type label vocabularies are not necessarily harmonised across released stages; `pseudobulk_shift` shifts
   only the cells whose type exists in both stages and reports `frac_cells_shifted`.
3. The embryo panel has 498 genes while heart / T3 files carry 500; the writer maps columns by name.
4. No labels in submissions: the writer produces an empty `obs`; the scorer types cells itself.
5. Coordinates are copied in the input's own local frame; all spatial metrics are translation and rotation
   invariant.
