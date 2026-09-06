# vec_submit_check - local pre-upload checks against the published board contracts

`python -m vec_submit_check --board <board> pred.h5ad` reads one prediction file and tests it against the board's
published contract. It needs anndata, numpy and scipy only: no scorer, no target data, no sign-in. The first
failing rule is printed in plain words; `--json` writes the full report for scripts.

```
pip install -r requirements.txt
python -m vec_submit_check --board T2:heart:val_interp pred.h5ad
python -m vec_submit_check --board T1:val pred.h5ad --json report.json
python -m vec_submit_check --board T3:gata4 big.h5ad --ignore-max-cells
```

Boards: `T1:val`, `T2:embryo:val_interp`, `T2:heart:val_interp`, `T2:heart:val_extrap`, `T3:gata4`. Exit code 0 =
passes, 1 = fails, 2 = usage error. Panel files: `data/panels/` in the kit, or the directory named by
`VEC_PANELS_DIR`, or `./data/panels`.

## Sources, and which rules are the portal's

Two official sources were read on 2026-09-05 and copies of the machine-readable one ship in `data/panels/`:

* `https://virtualembryo.ai/challenge/panels/index.json` + one gene list per board (`min_cells`, `max_cells`,
  `n_genes`, `needs_coords`, panel file and its sha256);
* the "Requirements for a valid file" section of `https://virtualembryo.ai/challenge/evaluation?section=submissions&task=1|2|3`.

The two disagree on one point (the cell-count upper bound), so every rule below says where it comes from and what
the checker does with it. **portal** = the portal's validator rejects on it (a file that fails here would fail
there); **stricter** = the checker is stricter than the pages; **advisory** = a warning for something no validator
catches.

| rule | source | checker |
|---|---|---|
| `var_names` equal the board panel, element by element, in panel order | portal (pages: "the check is element by element"; the panel files) | error; a same-set-different-order file is told to reorder |
| `.X` is a 2D cells x genes matrix, finite, non-negative; sparse or dense | portal | error on NaN/inf or negatives |
| `.X` dtype float32 | not a portal rule: "the scorer densifies and casts to float32 either way" | warning only when the dtype is not a float |
| `obsm["spatial_3D"]` present with shape (n, >= 3), finite (T2/T3) | portal ("cells x 3 or more ... only the first three columns are read") | error; only the first three columns are inspected |
| one `.h5ad` of at most 1200 MB | portal (rules page) | error, measured as 1e6-byte MB (the stricter reading) |
| at least `min_cells` cells | portal; the pages say "at least 1,000 cells" for every board while `index.json` gives 583 on the embryo board | error below `index.json`'s `min_cells`; a warning between that and 1,000 |
| at most `max_cells` cells | **conflict**: `index.json` carries `max_cells` per board; the pages say "no cap" above the minimum | stricter: error by default, warning with `--ignore-max-cells`; an upload above `max_cells` is untested |
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
