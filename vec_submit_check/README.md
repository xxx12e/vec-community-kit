# vec_submit_check - local pre-upload checks against the published board contracts

`python -m vec_submit_check --board <board> pred.h5ad` reads one prediction file and tests it against the board's
published contract. It needs anndata, numpy and scipy only: no scorer, no target data, no sign-in. The first
failing rule is printed in plain words; `--json` writes the full report for scripts.

```
pip install -e .                  # or: pip install -r requirements.txt (then run it from the clone)
python -m vec_submit_check --board T2:heart:val_interp pred.h5ad
python -m vec_submit_check --board T1:val pred.h5ad --json report.json
```

Boards: `T1:val`, `T2:embryo:val_interp`, `T2:heart:val_interp`, `T2:heart:val_extrap`, `T3:gata4`. Exit code 0 =
passes, 1 = fails, 2 = usage error. Installed with pip, the same check is the `vec-community-check` command. Panel
files: the directory named by `VEC_PANELS_DIR`, else `data/panels/` in the kit (a clone or an editable install),
else the copy installed with the package (`vec_submit_check/panels/`), else `./data/panels`.

## Sources, and which rules are the portal's

Two official sources were first read on 2026-09-05 and re-read on 2026-09-30; copies of the machine-readable one
ship in `data/panels/` (`index.json` unchanged between the two reads):

* `https://virtualembryo.ai/challenge/panels/index.json` + one gene list per board (`min_cells`, `max_cells`,
  `n_genes`, `needs_coords`, panel file and its sha256);
* the "Requirements for a valid file" section of `https://virtualembryo.ai/challenge/evaluation?section=submissions&task=1|2|3`.

Until 2026-09-22 the two disagreed on the cell-count upper bound: the evaluation pages said "no cap" above 1,000
cells while `index.json` carried a `max_cells` per board, so earlier versions of this checker treated `max_cells` as
a "stricter" rule with an `--ignore-max-cells` opt-out. The organisers corrected the pages on 2026-09-22 (uploads
above `max_cells` had been rejected by the portal all along); they now say that both bounds "differ by board and
are listed on the Data page and in index.json" and that an upload outside them "is rejected before scoring".
`index.json` is authoritative, and the opt-out was removed in 2026.10.0. Every rule below says where it comes from and
what the checker does with it. **portal** = the portal's validator rejects on it (a file that fails here would fail
there); **stricter** = the checker is stricter than the pages; **advisory** = a warning for something no validator
catches.

| rule | source | checker |
|---|---|---|
| `var_names` equal the board panel, element by element, in panel order | portal (pages: "the check is element by element"; the panel files) | error; a same-set-different-order file is told to reorder |
| `.X` is a 2D cells x genes matrix, finite, non-negative; sparse or dense | portal | error on NaN/inf or negatives |
| `.X` dtype float32 | not a portal rule: "the scorer densifies and casts to float32 either way" | warning only when the dtype is not a float |
| `obsm["spatial_3D"]` present with shape (n, >= 3), finite (T2/T3) | portal ("cells x 3 or more ... only the first three columns are read") | error; only the first three columns are inspected |
| one `.h5ad` of at most 1200 MB | portal (rules page) | error, measured as 1e6-byte MB (the stricter reading) |
| at least `min_cells` cells | portal (`index.json`, the Data page and the pages' requirements section; 583 on the embryo board, 1,000 elsewhere) | error below `min_cells`; an advisory warning between 583 and 1,000, because the pages' "not constrained" paragraph still mentions a 1,000-cell minimum (read 2026-09-30) |
| at most `max_cells` cells | portal (`index.json` and the Data page; the pages' requirements section since the 2026-09-22 correction) | error; no opt-out |
| `.X` not constant | not a portal rule | stricter: error (a constant matrix cannot be a prediction) |
| values look like raw counts (`.X` max > 30) | the pages: "a raw count matrix ... passes every check and is then scored as though it were on the log scale" | advisory warning; the checker cannot see a normalised-but-not-log file |
| `obs["celltype"]` present | ignored by the scorer | advisory warning |
| coordinates on a board without coordinates | ignored | advisory warning |

The panel file itself is verified against `index.json`'s `genes_sha256` before it is trusted. The organisers'
starter kit (`score_h5ad.py`) also validates a local file and, given the target, scores it; this checker is the
dependency-light subset for people who only want the format question answered.

## What PASS means

```
[PASS] out/heart_interp_copy_last.h5ad @ T2:heart:val_interp  n_obs=5000 n_vars=500
  PASS = local format checks passed; it does not confirm log-normalisation, data provenance or eligibility
  sha256: ...
  size_mb: 10.1  X_format: dense[float32]  X_min: 0.0  X_max: 12.17  spatial_3D_rms_radius: 84.6
```

PASS is a statement about format. It does not say that the values are log-normalised the way the released data
is (the pages' "not caught by validation" case), where the cells came from, or whether the file is an eligible
entry under the rules. The portal's validator has the final say; a rejected upload does not consume a scored
attempt.

## Library use

```python
from vec_submit_check import check, format_report, panel_for_board
rep = check("pred.h5ad", "T3:gata4")            # rep["ok"], rep["errors"], rep["warnings"], rep["info"]
print(format_report(rep))
spec, genes = panel_for_board("T1:val")         # bounds + ordered gene panel
```

`guards.py` holds the generic numeric guards (finite, non-negative, float32-castable; coordinate shape) for reuse
in your own writer. Tests: `python -m pytest tests/test_submit_check.py -q` (synthetic files; no competition data).
