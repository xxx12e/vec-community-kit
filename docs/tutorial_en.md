# From zero to a first submission - Virtual Embryo Challenge (NeurIPS 2026)

This tutorial takes a newcomer from registration to a scored submission on every board, for both tracks, using
the tools in this kit. Every fact about the challenge below comes from the official site
(https://virtualembryo.ai/challenge); when in doubt the site wins. The kit itself is generic tooling: a
validator, baseline generators with a submission writer, a local scoring wrapper around the organisers' scorer,
and an evidence skeleton for the Agent track. It contains no modelling advice.

The commands below were executed, in order and as written, against the real release on 2026-09-30 (UTC): a fresh
copy of the kit on a cloud Linux runner (32 cores, Python 3.10.13), installed as section 3 says, with the files
downloaded from the Data page linked into the layout of section 2. The trimmed log, with the Python and package
versions, exit codes, cell and gene counts, run times and memory, is `scratchpad/realrun_log_2026-10-01.txt`
(scores and expression values are left out of it); `scratchpad/tutorial_realrun.py` is the script that ran them.
Not part of that pass: the upload (section 8), a live Agent-track run (section 9; its tests and the lock step
were run) and the E10.5 example at the end of section 7 (it needs the validation stages released on 2026-10-20). Earlier runs on small synthetic stages laid out the same way are in `scratchpad/dryrun_log.txt`.

## 0. The challenge in one page

* Host: Qiu Lab (Stanford) with collaborators; an official NeurIPS 2026 competition. Data: about one million
  mouse-embryo cells across 11 stages (E6.75 to E12.5), heart-centred.
* Three tasks, five public boards:
  * **T1** single-cell RNA-seq (32,285 genes, no coordinates): predict a later stage from earlier stages.
  * **T2** 3D MERFISH (500-gene panel, coordinates): a whole-embryo setting (interpolation) and a heart setting
    (interpolation and extrapolation boards).
  * **T3** conditional knockouts (same panel and coordinates as T2, plus a genotype column): predict an unseen
    knockout from a training knockout and the matched wild types.
* Two tracks scored on the same hidden tests with separate rankings and prize pools: **Human Team** and
  **Agent Team**. The Agent track adds one requirement: autonomy after a configuration lock, proven by evidence.
* Prizes per track: 1 x 8K, 2 x 5K, 3 x 3K USD. Travel awards. A Community Contribution Award (up to 200 USD per
  contribution, up to 100 contributions, rolling until 2026-12-11) rewards work that helps others compete - this
  kit is an example of the genre.
* Timeline: portal and validation phase live since 2026-08-10; test phase from 2026-10-20 (validation answers are
  released and become training data, test inputs are released without labels; section 11 lists everything that
  changes); final submissions 2026-12-02; winners announced 2026-12-11 at NeurIPS. Winners deliver a written method report within 14 days; code may be
  requested for verification (kept private).
* Submission quotas: validation phase 20 (later 8) scored submissions per day per task; test phase 2 official
  submissions per board for the whole phase, scores public immediately, no withdrawal. Format checks are
  unlimited and do not consume quota.
* Ranking: the team's best result per board; task score = mean over the task's boards; total = T1 + T2 + T3
  (each at most 100). A board never scored counts 0, so submit a valid file to every board first.

## 1. Register

1. Open https://virtualembryo.ai/challenge/submit and sign in with GitHub or Google (the challenge keeps its own
   account; you must register personally).
2. Create a team or join one. One account per person, one team per person, at most 10 members including the
   captain, captain at least 18, every member must have genuinely contributed.
3. The captain chooses the track. Switching tracks before the final deadline retires all of the team's scores.

## 2. Download the data

Data download requires sign-in (https://virtualembryo.ai/challenge/data). All files are AnnData `.h5ad`. Put them
under one data root, for example:

```
data/
  panels/                         copies of the public board contracts (index.json + *.genes.txt; shipped with this kit)
  raw/T1/E8.5_RNA.h5ad            T1 training: 571 MB, 16,787 cells x 32,285 genes
  raw/T1/E9.5_RNA.h5ad            T1 training: 590 MB, 17,057 cells x 32,285 genes
  raw/T2_heart/E8.25_late.h5ad    heart training E8.25: 225 MB, 58,716 cells x 500 genes
  raw/T2_heart/E8.75.h5ad         heart training E8.75 (also the T3 wild type at E8.75): 84 MB, 24,826 cells x 500
  raw/T2_heart/E9.5.h5ad          heart training E9.5 (also the T3 wild type at E9.5): 164 MB, 53,742 cells x 500
  raw/T2_embryo/E6.75.h5ad        embryo training: 17 MB, 7,093 cells x 498 genes
  raw/T2_embryo/E7.25.h5ad        embryo training: 34 MB, 13,295 cells x 498 genes
  raw/T2_embryo/E8.0.h5ad         embryo training: 118 MB, 31,671 cells x 500 genes
  raw/T3/E9.5_mab21l2_ko.h5ad     T3 training knockout (Mab21l2 KO at E9.5): 458 MB, 50,294 cells x 500 genes
```

The folder names under `raw/` are this kit's convention; the file names are the released ones, except that the
Data page does not print the knockout's file name: `E9.5_mab21l2_ko.h5ad` is the name used in this tutorial, so if
your download is named differently, use your name in the section 7 commands. The two wild types are the heart files
(the Data page lists the same sizes); there is no separate copy under `raw/T3/`. Sizes and counts are those of the
files used in the real-release pass (the sizes match the Data page, which lists all but the embryo files).

What each file holds (checked on the released files):

* T1: `.X` float32, sparse (CSC), log1p-normalised, 32,285 genes in the order of the `T1:val` panel;
  `obs["celltype"]`; no coordinates (`obsm` holds only a UMAP). Validation target is E10.5 (withheld), test target
  E12.5 (hidden). No E7.75 single-cell file is released: E7.75 is the hidden test stage of the T2 embryo setting, so
  the Data page lists it as not distributed for any task.
* T2: `.X` float32, sparse (CSC), log-normalised, finite, non-negative; `obs["celltype"]` (the heart stages and
  embryo E8.0 also carry `obs["cm_celltype"]`); `obsm["spatial_3D"]` float32 (n, 3) in a per-embryo local frame
  (not registered across stages), next to an `obsm["spatial_2D"]`. Embryo setting: train E6.75, E7.25, E8.0;
  validation E7.5 (interpolation); test E7.75. E6.75 and E7.25 carry 498 genes (Casp4 and Pnliprp1 were not
  measured there), E8.0 carries all 500, so the embryo board's panel has 498 genes. Heart setting: train E8.25,
  E8.75, E9.5; validation E8.5 (interpolation) and E10.5 (extrapolation); test E12.5 (extrapolation). In the test
  phase every heart stage becomes training input. The heart files and E8.0 have their 500 genes in the order of the
  heart and T3 panels; E6.75 and E7.25 are in the order of the embryo panel.
* T3: the same 500-gene panel (same order) and `obsm["spatial_3D"]` as T2. The released knockout file stores `.X`
  dense and records the genotype in `obs["genotype"]`, not in the `obs["condition"]` of the Data page's schema table
  (marked "tbc" there), together with further fields (sample, slide, section, ...); the kit reads neither column.
  Train: Mab21l2 knockout at E9.5. Validation: Gata4 knockout at E8.75 (two replicates). Test: beta-catenin
  knockout at E8.75 (two replicates). Reference wild types: E8.75 and E9.5 (shared with T2 heart).

Never try to obtain the withheld stages or genotypes by any route: the rules forbid measured data from held-out
stages and genotypes, including external datasets that contain them (T1: E10.5, E12.5 and any external data after
E9.5 through E13.5 inclusive; heart: the E8.25-E8.75 window plus E10.5 and E12.5; embryo: E7.5-E7.75; T3: the
Gata4 and beta-catenin knockouts at E8.75, other alleles of the same genes at comparable stages, and phenocopying
perturbations). External public data, pretrained models and published code are otherwise allowed WITH disclosure in
the method summary; an undisclosed external source is a violation regardless of effect.

## 3. Install the kit, and what each part needs

```
git clone <this repository> vec-community-kit
cd vec-community-kit
python -m venv .venv && .venv\Scripts\activate        # Windows; Linux/macOS: python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"                               # the kit + anndata, numpy, scipy, pandas, h5py + pytest
python -m pytest -q                                    # synthetic tests, no challenge data needed
```

What to expect (real-release pass, Linux, Python 3.10.13, internet access for pip): the install took about 15 s
there, also when repeated with an empty pip cache (it then downloaded about 75 MB of packages, about 10 MB more
with veckit; a home connection will take longer than the runner's), and resolved anndata 0.11.4, numpy 2.2.6,
scipy 1.15.3, pandas 2.3.3, h5py 3.16.0 and pytest 9.1.1 (Python 3.10 gets older releases of these than 3.12 does;
both work). Without veckit the tests end with `54 passed, 10 skipped`
(the local-scoring tests, plus the wheel build, which needs setuptools 77 or newer in the environment); with veckit
installed, `63 passed, 1 skipped`. They also pass when run as root, as in many cloud containers.

`pip install -e .` also installs five commands that are the same as the `python -m` forms used below
(`vec-community-check`, `vec-community-baseline`, `vec-community-score`, `vec-community-split`,
`vec-community-evidence`; see the top-level README). `pip install -r requirements.txt` installs only the
dependencies, which is enough when you run everything from the clone with `python -m`, as this tutorial does.

Prerequisites by section (Python 3.10 or newer throughout):

| you want to | sections | you need |
|---|---|---|
| understand the contracts, build baseline files, validate, upload | 4, 5, 6, 8 | `pip install -e ".[test]"` or `pip install -r requirements.txt` (anndata, numpy, scipy, pandas, h5py; pytest for the tests). Nothing else. |
| score locally on a pseudo split | 7 | additionally the organisers' scorer **veckit** and its dependencies (numpy, scipy, anndata, scikit-learn). Obtain it from the organisers: `pip install "git+https://github.com/aristoteleo/veckit.git@46d41e63f42a9aab815db20b742feeccd249cb17"`, or `git clone https://github.com/aristoteleo/veckit` anywhere and point `VECKIT_PATH` at the clone (`set VECKIT_PATH=C:\path\to\veckit` on Windows, `export VECKIT_PATH=/path/to/veckit` elsewhere). Check: `python -c "from vec_local_score import veckit_available, veckit_info; print(veckit_available(), veckit_info())"` prints `True` and a dict with `'version': '0.1.1'` and `'matches_tested': True` when the installed files are those of the tested commit (line endings aside). The kit was tested against veckit 0.1.1. The `pip` route needs `git` and pulled in scikit-learn 1.7.2 on Python 3.10. |
| run the Agent-track skeleton for real | 9 | additionally the Claude Code CLI installed and logged in (`claude --version` prints a version; a headless `claude -p "say ok" --max-turns 1` returns a result). The dry run `python -m pytest tests/test_evidence.py -q` needs neither the CLI nor an API key. |

Without veckit the scorer tests are skipped and everything else works.

## 4. Understand each board's contract

The portal validates a file against the board you upload it to. The public contracts are in
`data/panels/index.json` and one gene list per board:

| board | genes | cells (min-max) | coordinates | floor model |
|---|---|---|---|---|
| `T1:val` (E10.5) | 32,285 | 1000-5118 | no | copy_last |
| `T2:embryo:val_interp` (E7.5) | 498 | 583-5000 | yes | copy_last |
| `T2:heart:val_extrap` (E10.5) | 500 | 1000-25179 | yes | copy_last |
| `T2:heart:val_interp` (E8.5) | 500 | 1000-17616 | yes | copy_last |
| `T3:gata4` (E8.75) | 500 | 1000-7449 | yes | wt_identity |

Rules of a valid file (`vec_submit_check` tests these locally, labelling each rule portal / stricter / advisory in
`vec_submit_check/README.md`; the portal's own validator has the final say):

1. A single `.h5ad`, at most 1200 MB.
2. `var_names` equal to the board's gene list, element by element, **in the same order**. The portal does not
   reorder for you.
3. `n_obs` inside the board's `[min_cells, max_cells]` from `panels/index.json` (the table above; also on the Data
   page). An upload outside them is rejected before scoring and does not spend a scored attempt. (Until they were
   corrected after the organisers reviewed this kit (2026-09-22), the evaluation pages said "no cap" above 1,000
   cells; one paragraph of the evaluation pages still says 1,000 cells, so the checker warns on 583-999 cells on the
   embryo board. `index.json` is authoritative, and the checker has no opt-out.) The cell count is a sample size, not a scored quantity; a few thousand cells is plenty (the scorer's own draws use at
   most 2000 cells for some metrics and 1500 for others).
4. `.X` finite, **non-negative on every board**, log-normalised like the released data; sparse or dense (the scorer
   densifies and casts to float32 itself). Validation cannot see a wrong scale: a raw-count file passes every
   check and is then scored wrongly (the pages say so explicitly).
5. For T2/T3: `obsm["spatial_3D"]` with shape (n, 3) or wider (the first three columns are used), finite. Any
   coordinate frame is fine: the spatial metrics are invariant to translation and proper rotation.
6. No cell-type labels are needed (the scorer ignores them and types cells with its own frozen classifier).

Gene panels: `data/panels/T1__val.genes.txt` (32,285 lines), `T2__heart__*.genes.txt` and `T3__gata4.genes.txt`
(500 lines, the same panel), `T2__embryo__val_interp.genes.txt` (498 lines). `index.json` records a sha256 of each
list so a corrupted copy is detected.

## 5. Build the first file: a baseline

`copy_last` and `wt_identity` are the organisers' floor rows: `copy_last` resubmits the last observed stage,
`wt_identity` resubmits the matched wild type. The published floor value of a board (50 of 100) is the
organisers' own row scored on the hidden target; a file you generate is a resample of the same stage, so it lands
**near** that value, not exactly on it. It is still the right first upload: it exercises the whole pipeline with a
known reference point. (`pseudobulk_shift` is a third, non-floor baseline: each cell moved by its own cell type's
mean change between two stages.)

`--n-cells` is **required**: an integer inside the board's cell bounds, or `all` for every cell of the input.
Every released stage used below holds more cells than its board's `max_cells`, so `all` stops with an error that
states the bound (checked on all five in the real-release pass); pass a number (section 4 rule 3). The bound is
written next to each command (from `data/panels/index.json`).

```
# T1:val: 1000-5118 cells. E9.5_RNA has 17,057 cells, so `all` would error; 5000 fits.
python -m vec_community_baselines.make_baseline --method copy_last   --board T1:val               --last data/raw/T1/E9.5_RNA.h5ad          --out out/t1_copy_last.h5ad --n-cells 5000
# T2:embryo:val_interp: 583-5000 cells (5000 is the maximum). E8.0 has 31,671 cells, so `all` would error.
python -m vec_community_baselines.make_baseline --method copy_last   --board T2:embryo:val_interp --last data/raw/T2_embryo/E8.0.h5ad       --out out/embryo_copy_last.h5ad --n-cells 5000
# T2:heart:val_interp: 1000-17616 cells. E8.25_late has 58,716 cells, so `all` would error.
python -m vec_community_baselines.make_baseline --method copy_last   --board T2:heart:val_interp  --last data/raw/T2_heart/E8.25_late.h5ad  --out out/heart_interp_copy_last.h5ad --n-cells 5000
# T2:heart:val_extrap: 1000-25179 cells. E9.5 has 53,742 cells, so `all` would error.
python -m vec_community_baselines.make_baseline --method copy_last   --board T2:heart:val_extrap  --last data/raw/T2_heart/E9.5.h5ad        --out out/heart_extrap_copy_last.h5ad --n-cells 5000
# T3:gata4: 1000-7449 cells. E8.75 has 24,826 cells, so `all` would error.
python -m vec_community_baselines.make_baseline --method wt_identity --board T3:gata4             --wt   data/raw/T2_heart/E8.75.h5ad       --out out/t3_wt_identity.h5ad --n-cells 5000
```

Notes:

* `--n-cells N` writes exactly N cells drawn without replacement (seeded, `--seed`); N must lie inside the board's
  bounds (a value above `max_cells` is refused, never clamped). `--n-cells all` writes every cell of the input and
  errors, stating the bound, when that exceeds `max_cells`. If the input has fewer cells than N (but at least
  `min_cells`) every cell is written and the CLI prints a NOTE. The stage sizes in the comments are the cell counts
  of the released files (section 2).
* The embryo board takes a 500-gene file, such as the released E8.0, and writes the 498-gene panel automatically
  (columns are mapped by gene name).
* Which stage is "last" is your choice; for an interpolation board it is usually the stage right before the
  target, for an extrapolation board the latest released stage.
* The CLI prints the local contract verdict for the written file and exits 0 only when it passes, e.g.
  `[PASS] out/t3_wt_identity.h5ad @ T3:gata4  n_obs=5000 n_vars=500 X=dense[float32] min=0.0 max=... size=10.3MB`
  followed by `PASS = local format checks passed; it does not confirm log-normalisation, data provenance or
  eligibility`.
* What to expect on the real files: each command above finished in under 5 s on the runner. The T1 command reads
  the whole 590 MB stage and peaked at about 1.9 GB of memory, the others below 0.5 GB. The T1 file is written
  sparse, about 160 MB for 5,000 cells; the T2/T3 files are dense, about 10 MB.
* On the released heart stages the cell-type labels are not the same from stage to stage (the Data page says the
  annotation vocabulary is not harmonised), so `pseudobulk_shift` shifts only the cells whose type also exists in
  the earlier stage and prints a WARNING that names the others (`--celltype-key` selects another `obs` column).

From Python:

```python
from vec_community_baselines import io as bio, methods as bm
spec, panel = bio.panel_for_board("T3:gata4")
wt = bio.load_stage("data/raw/T2_heart/E8.75.h5ad", panel)
X, C, info = bm.wt_identity(wt)
report = bio.write_submission(X, C, panel, "out/t3_wt_identity.h5ad", "T3:gata4", n_cells=5000)
print(report["ok"], report["info"]["n_obs"])
```

`write_submission` accepts any (cells x genes) matrix plus coordinates: use it for your own model's output too. It
maps columns by gene name, clips negatives to 0, writes float32, and validates the file before it returns.
`n_cells` is required here as well (an int inside the bounds, or `"all"`); leaving it out raises a `ValueError`
that says what to pass.

## 6. Validate

```
python -m vec_submit_check --board T2:heart:val_interp out/heart_interp_copy_last.h5ad
python -m vec_submit_check --board T1:val out/t1_copy_last.h5ad --json out/t1_check.json
```

`[PASS]` / `[FAIL]` plus every error and warning, then one field per line: cell and gene counts, the file's
sha256, its size and the size cap, the storage of `.X`, its value range and share of non-zero entries, and (T2/T3)
the coordinate radius. On the real heart file (values that come from the data replaced by `...`):

```
[PASS] out/heart_interp_copy_last.h5ad @ T2:heart:val_interp  n_obs=5000 n_vars=500
  PASS = local format checks passed; it does not confirm log-normalisation, data provenance or eligibility
  n_obs: 5000
  n_vars: 500
  sha256: <64 hex characters: keep it with the file you upload>
  size_mb: 10.3
  max_file_mb: 1200.0
  X_format: dense[float32]
  X_min: ...
  X_max: ...
  X_nonzero_frac: ...
  spatial_3D_rms_radius: ...
```

For the T1 file the report shows `X_format: csr_matrix` (sparse) and `size_mb: 159.1`, and it has no
`spatial_3D_rms_radius` line (T1 has no coordinates).

On the real files each check took about a second and under 0.5 GB of memory; `vec-community-check` (section 3)
gives the same report. A heart file checked against the embryo board fails with `n_vars=500 but board expects 498`
and names the two extra genes.

Exit code 0 = passes, 1 = fails, 2 = usage error (unknown board or missing file). These are local format checks
against the published contracts; each rule is labelled portal / stricter / advisory in `vec_submit_check/README.md`.
The portal's validator has the final say, and the organisers' starter kit (`score_h5ad.py`) validates locally too;
a file that fails a portal-labelled rule here would have failed there. PASS says nothing about the normalisation,
the provenance of the cells or eligibility under the rules. The most common failures: gene order differs (`reorder with the panel file`),
`n_obs` outside the board bounds, negative or NaN entries (negative values are rejected on every board), missing
`obsm["spatial_3D"]`, and the file size cap. A warning about `obs["celltype"]` is harmless; a warning that
`.X max looks like raw counts` means your matrix is not log-normalised.

## 7. Score locally on a pseudo split

You cannot score against the hidden target, but you can hold out a released stage, predict it from the earlier
ones (never from the held-out stage itself), and run the organisers' scorer on that. The result compares your
methods on that split; it does not predict their order on the hidden target. `vec_local_score` wraps veckit for this and follows the veckit
scorer's protocol as of veckit 0.1.1: 10 % subsample of every stage, split-half ceiling, floor row, skill scale
(plus the task weights published on the evaluation pages); by default it also caps the reference at 4,000 cells
(see "What to expect" below). The organisers' portal scorer is the source of truth and the wrapper may lag it.

Prerequisite: veckit (section 3). Check with
`python -c "from vec_local_score import veckit_available, veckit_info; print(veckit_available(), veckit_info())"`.

**The wrapper takes the raw released stage files** and does the subsample and the split itself: `--target` is the
held-out raw stage, `--reference` (T1/T2) or `--wt` (T3) the raw stage the change is measured against, `--pred`
your prediction for the held-out stage. Build the pseudo-prediction from the stages you keep, never from the
held-out one (a file sampled from the target itself scores 100 and tells you nothing). Example, heart
interpolation board with E8.75 held out and the `copy_last` baseline built from E8.25 as the prediction:

```
python -m vec_community_baselines.make_baseline --method copy_last --board T2:heart:val_interp --last data/raw/T2_heart/E8.25_late.h5ad --out out/pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad
python -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --single-seed
```

The first scoring command prints the **band** - the default output since 2026-09-30: the task score over subsample
seeds 0-4 as mean, sd and min..max, with a per-metric table of means. The second (`--single-seed`, optionally
`--seed N`) prints one seed's full per-metric table. The band is the default because the organisers, in their
review of this kit, said the subsample seed will depend on each submission; a single local seed hides how much the
score moves with the subsample.

The same pattern for the other boards, one split each (T1: hold out E9.5_RNA, predict it from E8.5_RNA; T3: hold
out the training knockout, with the wild type of the same stage as `--wt`; embryo: hold out E7.25 with E6.75 as the
reference; heart extrapolation: hold out E9.5 with E8.75 as the reference). Each prediction is the floor model built
from the reference, so it only shows the plumbing; replace it with your own method's file:

```
python -m vec_community_baselines.make_baseline --method copy_last --board T1:val --last data/raw/T1/E8.5_RNA.h5ad --out out/t1_pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T1 --pred out/t1_pseudo_pred.h5ad --target data/raw/T1/E9.5_RNA.h5ad --reference data/raw/T1/E8.5_RNA.h5ad
python -m vec_community_baselines.make_baseline --method wt_identity --board T3:gata4 --wt data/raw/T2_heart/E9.5.h5ad --out out/t3_pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T3 --pred out/t3_pseudo_pred.h5ad --target data/raw/T3/E9.5_mab21l2_ko.h5ad --wt data/raw/T2_heart/E9.5.h5ad
python -m vec_community_baselines.make_baseline --method copy_last --board T2:embryo:val_interp --last data/raw/T2_embryo/E6.75.h5ad --out out/embryo_pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T2 --setting embryo --pred out/embryo_pseudo_pred.h5ad --target data/raw/T2_embryo/E7.25.h5ad --reference data/raw/T2_embryo/E6.75.h5ad
python -m vec_community_baselines.make_baseline --method copy_last --board T2:heart:val_extrap --last data/raw/T2_heart/E8.75.h5ad --out out/heart_extrap_pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T2 --setting heart --pred out/heart_extrap_pseudo_pred.h5ad --target data/raw/T2_heart/E9.5.h5ad --reference data/raw/T2_heart/E8.75.h5ad
```

These are examples, not recommendations: any released stage can be held out, as long as the prediction never uses
it. The `--board` of a pseudo prediction only picks the gene panel and the cell bounds of the file.

What to expect on the real files (runner above, five seeds, `OMP_NUM_THREADS=4`, `LOKY_MAX_CPU_COUNT=4`):

| split | cells pred/A/B/ref (header line) | time | peak memory |
|---|---|---|---|
| T1, E9.5_RNA from E8.5_RNA | 5000/853/853/1679 | about 2 min | about 6 GB |
| T2 heart, E8.75 from E8.25_late | 5000/1241/1242/4000 | about 25 s | about 1 GB |
| T2 heart, E9.5 from E8.75 | 5000/2687/2687/2483 | about 35 s | about 1 GB |
| T2 embryo, E7.25 from E6.75 | 5000/665/665/709 | about 15 s | about 0.6 GB |
| T3, Mab21l2 KO from wild type E9.5 | 5000/2514/2515/4000 | about 40 s | about 1.5 GB |

`--single-seed` takes about a quarter of that. The T1 split needs the most memory: both whole-transcriptome stages
are read in full and the scored cells are densified over 32,285 genes. The reference column shows the wrapper's cap: `--max-cells` (default 4,000) limits
the reference after the 10 % subsample, and on the real files it binds for E8.25_late (5,872 cells at 10 %) and
the E9.5 heart stage (5,374); pass `--max-cells 6000` to keep the whole 10 % sample, as the organisers' `ref_cells`
in `index.json` do. veckit's cell-type probe asks joblib for every core (`n_jobs=-1`); with scikit-learn 1.7 (what
Python 3.10 installs) that starts one worker process per core, so on a shared machine set `LOKY_MAX_CPU_COUNT=4`
(or the number of cores you may use) before scoring.

How to read it: every stage is subsampled to 10 %, the target is split in half; the floor (the reference
resubmitted) defines 50 and the ceiling (the other half of the target) defines 100 on the skill scale; your
prediction gets a skill per metric (veckit's own `skill()`) and a task score. The two target-0 metrics
(`scale_log_ratio`, `severity_slope`) are marked `*`: their skill is computed on the absolute values (an overshoot
counts like an undershoot). Your resampled `copy_last` file lands **near** 50, not exactly on it - the wrapper's
floor row is a 10 % subsample of the reference and your file is a different sample of the same cells; a value a
few points off 50 is normal (in the real-release pass, the five-seed mean of each of the five floor-model
predictions above was within 5 points of 50). A local score is **not** a preview of the real one; it ranks your own methods on the
same split with the same seeds. `docs/metrics_overview.md` explains every column, and `vec_local_score/README.md`
states exactly which conventions the wrapper implements.

**Comparing two of your methods: the paired mode.** Pass both predictions of the held-out stage in one call,
`--pred A --pred B`. In every seed both files are scored against the same subsample, target halves, floor and
ceiling, so the per-seed difference B - A removes the subsampling noise the two share. The output gives each file's
band, the per-metric point differences, and B - A per seed with its mean, sd and min..max over the seeds:

```
python -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --pred out/pseudo_pred_mine.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad
```

`out/pseudo_pred_mine.h5ad` stands for your own method's prediction of E8.75, built from the stages you keep (write
it with `write_submission`, section 5) - never from E8.75. Read the min..max of B - A: when it stays on one side of
0, one file is ahead on every seed of this split; when it straddles 0, the seeds disagree and the difference is not
a result. Two bands can overlap while the paired difference keeps its sign: on the synthetic pair of the dry run, a
stand-in B (the `copy_last` file with its coordinates grown to the target's size) has the band 52.49..61.32 against
A's 48.86..56.96, and B - A is +3.63..+4.38 on all five seeds. Either way it is a comparison on this pseudo split,
not a prediction of the order on the hidden target. On the real files the paired command took about 30 s and 1 GB
(the real-release log records that it ran, not its numbers).

From 20 October the validation stages are released with their answers (section 11), so a real held-out stage can
be the `--target` instead of a training stage - for example the released T2 heart E10.5 with `--reference` E9.5,
the prediction built from the earlier stages only. It is still the kit's local protocol, not the organisers' score.

`python -m vec_local_score.make_pseudo_split` is optional: it exports one fixed split as files for inspection or for
calling the veckit CLI directly (it applies the 10 % subsample without the reference cap). Its outputs are not
inputs to `vec_local_score` (the wrapper refuses them, because it would subsample twice).

## 8. Upload

1. Sign in at https://virtualembryo.ai/challenge/submit, open the board's tab and upload the `.h5ad`. Format
   checks are unlimited and free; scored submissions count against the phase quota.
2. The result appears on the public ranking once scored (Agent track: only after evidence is attached, section 9).
3. Repeat for every board: a board never scored counts 0 in the total.
4. Keep the file you uploaded together with its sha256 (`vec_submit_check` prints it), the command that produced
   it and a short method note; the final report and any verification request will ask for them.

## 9. Agent track: what evidence is required and how to produce it

The rules (Agent Team section of the site):

* What distinguishes an Agent entry is autonomy after the **configuration lock**, the moment a run starts.
  Before the lock anything goes: write or rewrite the harness, choose the model, draft prompts, set budgets, run as
  often as you like. After it: no human reading intermediate results (scores, diagnostics, partial outputs) and
  steering, no mid-run configuration change, no picking among a run's intermediate outputs on the agent's behalf.
  Choosing WHICH COMPLETED RUN to submit is allowed.
* The submitted file must be unedited agent output. Any human edit (by hand, by script, by substitution) makes it
  a non-Agent entry.
* At least TWO distinct kinds of evidence from {trajectory, prompts (every prompt including the initial one),
  harness (orchestration code, tools, evaluation loop)} must be uploaded against a submission before it is scored
  or appears on the ranking. The evidence must be from the exact run that produced the file. Organisers may audit
  and ask you to re-run the harness. A prize requires evidence.
* Limits: 200 MB per evidence file, 600 MB per team in total (across every upload; `package --team-uploaded-mb`
  writes the running total into the package README, but the bookkeeping is yours).
* From the FAQ: "The framework is not the point; the absence of a human in the loop is."

`vec_agent_evidence` makes all of this mechanical: it produces an auditable evidence bundle (configuration
snapshots, integrity checks, best-effort guard hooks, audit log) that you hand to the organisers; it does not by
itself attest that the run complied. The current implementation targets the Claude Code CLI in
headless mode (`claude -p --output-format stream-json`), installed and logged in (section 3); another agent CLI
needs `launch.build_command` adapted. For a Codex CLI run there is a minimal, after-the-fact packager,
`python -m vec_agent_evidence codex-package` (stream, rollout, prompt, `AGENTS.md` files, harness files and
predictions into the same three zips); it is untested against a live Codex run - see `vec_agent_evidence/README.md`.

```
# 0. dry run with a stand-in agent, no CLI and no API calls: proves the plumbing on your machine
python -m pytest tests/test_evidence.py -q

# 1. write your prompt (start from vec_agent_evidence/example_prompt.md: it explains the workspace contract only)
# 2. lock + run + collect, in one command; from the lock message on, walk away
python -m vec_agent_evidence run --task T3 --prompt my_prompt.md --model <full model id> --data-root ./data --hours 8 --max-turns 400

# 3. after run_manifest.json exists: check it, then build the upload package
python -m vec_agent_evidence package --run-dir runs/<run_id>
```

(`python -m vec_agent_evidence lock ...` with the same arguments freezes a run directory and prints the exact
launch command without launching anything, if you want to inspect it first. In the real-release pass, `lock` with
`--data-root ./data` hashed the nine released `.h5ad` files in a few seconds; with no `claude` on PATH it records the
binary as missing and still prints the command. The `run` and `package` steps were not part of that pass.)

What you get, all hashed in `config.lock.json` and re-verified in `run_manifest.json`:

* **prompts**: `initial_prompt.md` (rendered byte-exact from your template), optional
  `system_prompt_appendix.md`, `prompts.manifest.json`;
* **trajectory**: `transcript/<session-id>.jsonl` (the CLI's own transcript, copied by session id), `stream.jsonl`
  (the CLI's stdout, byte for byte), `hooks/tool_audit.jsonl` (one line per tool call), `hooks/guard_denials.jsonl`
  (every rejected call and why);
* **harness**: `harness_snapshot.zip` (the kit code and templates that produced the run), `config.lock.json`
  (model, tool policy, limits, seed, environment, data-file hashes, CLI binary version and sha256),
  `claude_settings.json` (deny rules and hooks), `launch_command.json`, `env/`.

The `package` step writes `predictions/` (byte-identical, sha256-verified), `trajectory.zip`, `prompts.zip`,
`harness.zip` and `evidence_bundle.zip` plus a README, and refuses to build if the lock was broken, a credential-
shaped string appears in the evidence, the run aborted, or a zip exceeds 200 MB. On the portal: upload the
prediction on the board's tab and attach the evidence ON THAT TAB (two kinds minimum; `evidence_bundle.zip` holds
all three), then submit. Repeat per board.

Inside a run, two hooks are wired into the CLI: the guard hook rejects **recognised** network commands (curl,
wget, pip install, git clone, ssh, requests/urllib one-liners, any URL, ...), reads of the CLI's configuration
directory, references to other runs, writes into `submission/` except through `tools/finalize_submission.py`
(which validates, hashes and records every finalized file), edits of the read-only tools and data, and
process-kill commands; the audit hook logs every tool call. These are regex hooks over the tool input, not a
network sandbox: the audit log, the trajectory and the hashes recorded at lock and post-run time are what supports
verification after the run. The agent has the same validator, baseline generator and local scorer as you do,
copied read-only into its workspace. Read-only here means file permissions, which do not stop a process running as
root (as in many cloud containers); run the agent as an ordinary user if that matters to you. The guard hook and the
recorded hashes apply either way.

Human do's and don'ts: before the lock, anything; between the lock and `run_manifest.json`, nothing (do not open
the stream, the workspace or the ranking for that run); after, read the manifest and NOTES.md, decide which
completed run to upload, upload the unchanged file and the zips, and put what you learned into the next prompt
version (record it with `--note` when you lock the next run). Never resume a session, never feed one run's
artefacts into another's workspace, never edit a submission.

## 10. Checklist before every upload

- [ ] `python -m vec_submit_check --board <board> <file>` prints `[PASS]` (format only; the next three lines are
      yours to confirm).
- [ ] The gene order equals the panel file (the checker says so; the portal will not reorder).
- [ ] Cell count inside `index.json`'s `[min_cells, max_cells]` for that board (you passed it explicitly); no
      duplicated cells; no labels needed.
- [ ] `.X` log-normalised like the released data (no `raw counts` warning), finite, non-negative (every board).
- [ ] T2/T3: `obsm["spatial_3D"]` present, (n, 3), finite.
- [ ] File under 1200 MB.
- [ ] You know which board tab the file belongs to (heart interpolation vs extrapolation are different boards).
- [ ] Agent track: `run_manifest.json` says `lock_integrity.ok`, `secret_scan.clean`, `abort: null`, and the
      board is `uploadable`; the prediction you upload has the sha256 recorded there; two evidence kinds attached.
- [ ] External data or pretrained models used? Disclosed in the method summary.

## 11. What changes at the final phase (from 2026-10-20)

Sources, all read on 2026-09-30: the timeline (https://virtualembryo.ai/challenge/timeline, which calls itself
"the authoritative schedule"), the rules (https://virtualembryo.ai/challenge/rules, sections 10, 11, 13, 14 and the
Agent Team section), the Data page (https://virtualembryo.ai/challenge/data) and the FAQ. The pages win over this
section; re-read them on 20 October.

To hear about a change without re-reading every page, follow the kit's daily rules watch: [`rules-watch/CHANGES.md`](../rules-watch/CHANGES.md) (pages, board contract, phase endpoint, scorer; how to subscribe in [`vec_rules_watch/README.md`](../vec_rules_watch/README.md)).

| date (2026) | what happens (timeline) |
|---|---|
| 20 Oct | P3, the test phase: the validation data is released for every task, the test inputs are released without labels, the test leaderboard opens |
| 2 Dec | final submissions due: the last moment a submission can be made or a final entry nominated; nothing after it counts, in either track |
| 4 Dec | official evaluation on the hidden test sets, both tracks; Agent Team entries are checked against the evidence attached to them |
| 11 Dec | winners announced at NeurIPS; final rankings use the hidden test set, not the development leaderboard |

1. **The validation answers become development and training data.** At the start of P3 the validation stages are
   released for every task with their answers (timeline, FAQ); the Data page says they then "become training
   material". Test answers are never distributed. What you hold then for each hidden test target (Data page):

   | test target | released training / reference stages | validation stages released with answers in P3 |
   |---|---|---|
   | T1 E12.5 (extrapolation) | E8.5, E9.5 | E10.5 |
   | T2 heart E12.5 (extrapolation) | E8.25, E8.75, E9.5 | E8.5, E10.5 |
   | T2 embryo E7.75 (interpolation) | E6.75, E7.25, E8.0 | E7.5 |
   | T3 beta-catenin KO at E8.75 | Mab21l2 KO at E9.5; wild types E8.75, E9.5 | Gata4 KO at E8.75 (two replicates) |

   Rules section 10 still lists the validation stages among the held-out stages when it restricts *external* data
   (for Task 1, for example, no external data after E9.5 up to and including E13.5); those restrictions on outside
   sources do not lapse. If your method depends on a particular reading of how released validation files may be
   used, ask the organisers before submitting - the rules invite exactly that.
2. **Two official submissions per board, for the whole phase** (rules section 11). "Each is scored and published
   when it is made, and cannot be withdrawn; the board ranks a team by its best." Format checks stay unlimited and
   free, and a rejected (invalid) upload does not consume a scored attempt, but a valid, weak file uses up half of
   the phase's quota on that board. Validate every file locally first (section 6), choose your two files per board
   before the first upload, and keep each uploaded file with its sha256.
3. **The scorer's subsample seed.** The organisers, in their review of this kit, said the subsample seed will
   depend on each submission.
4. **Test inputs are released without labels, and the test boards get their own contracts.** The kit's copies in
   `data/panels/` are the validation boards as of 2026-09-30. When the test boards appear, download the new
   `panels/index.json` and gene lists into `data/panels/` (or point `VEC_PANELS_DIR` at them); `vec_submit_check`,
   the baseline writer and the Agent-track lock (`--boards <test board key>`) read board keys and cell bounds from
   there, so no code change is needed. Check each test board's `min_cells` / `max_cells` again: the portal rejects
   an upload outside them.
5. **Final rankings use the hidden test sets** (rules section 13), not the validation leaderboard. A team is
   prize-eligible only if its final standing exceeds what a floor entry would achieve on the same boards (the floor
   scores 50 per board, so more than 150 over three tasks); winners may be asked for documentation or code
   sufficient to reproduce the result and must deliver a written method report within 14 days (sections 14-15).
   The Generality Award goes to one shared architecture answering at least two tasks, described in the method
   summary.
6. **Nomination and evidence.** 2 December is the last moment to nominate a final entry (timeline). Agent Team: a
   final entry nominated for prizes must carry its evidence, and without it may keep a leaderboard position but is
   not prize-eligible; every submission is held until at least two kinds of evidence, one of them the trajectory,
   are attached; every submission states the framework and the model string actually run; predictions must be
   written by the agent - a file a person edited is not an Agent entry (rules, Agent Team section and section 14).
   Keep every run directory untouched until the organisers' checks from 4 December; build the upload with
   `python -m vec_agent_evidence package` (Claude Code runs) or `codex-package` (Codex runs, section 9).
