# From zero to a first submission - Virtual Embryo Challenge (NeurIPS 2026)

This tutorial takes a newcomer from registration to a scored submission on every board, for both tracks, using
the tools in this kit. Every fact about the challenge below comes from the official site
(https://virtualembryo.ai/challenge); when in doubt the site wins. The kit itself is generic tooling: a
validator, baseline generators with a submission writer, a local scoring wrapper around the organisers' scorer,
and an evidence skeleton for the Agent track. It contains no modelling advice.

The commands below were executed against small synthetic stages laid out like the data directory of section 2
(2026-09-05; the log, with the Python and package versions, is `scratchpad/dryrun_log.txt`); they have not been
run against the real release inside this repository. The only thing you change is having the real files there.

## 0. The challenge in one page

* Host: Qiu Lab (Stanford) with collaborators; an official NeurIPS 2026 competition. Data: about one million
  mouse-embryo cells across 11 stages (E6.75 to E12.5), heart-centred.
* Three tasks, five public boards:
  * **T1** single-cell RNA-seq (32,285 genes, no coordinates): predict a later stage from earlier stages.
  * **T2** 3D MERFISH (500-gene panel, coordinates): a whole-embryo setting (interpolation) and a heart setting
    (interpolation and extrapolation boards).
  * **T3** conditional knockouts (same schema as T2 plus a condition): predict an unseen knockout from a training
    knockout and the matched wild types.
* Two tracks scored on the same hidden tests with separate rankings and prize pools: **Human Team** and
  **Agent Team**. The Agent track adds one requirement: autonomy after a configuration lock, proven by evidence.
* Prizes per track: 1 x 8K, 2 x 5K, 3 x 3K USD. Travel awards. A Community Contribution Award (up to 200 USD per
  contribution, up to 100 contributions, rolling until 2026-12-11) rewards work that helps others compete - this
  kit is an example of the genre.
* Timeline: portal and validation phase live since 2026-08-10; test phase from 2026-10-20 (validation answers are
  released and become training data, test inputs are released without labels); final submissions 2026-12-02;
  winners announced 2026-12-11 at NeurIPS. Winners deliver a written method report within 14 days; code may be
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
  panels/                 copies of the public board contracts (index.json + *.genes.txt; shipped with this kit)
  raw/T1/E8.5_RNA.h5ad    T1 training (about 571 MB, 16,787 cells)
  raw/T1/E9.5_RNA.h5ad    T1 training (about 590 MB, 17,057 cells)
  raw/T2_heart/E8.25_late.h5ad, E8.75.h5ad, E9.5.h5ad     heart training stages (E8.75 and E9.5 double as T3 wild types)
  raw/T2_embryo/E6.75.h5ad, E7.25.h5ad, E8.0.h5ad          embryo training stages
  raw/T3/<Mab21l2 KO at E9.5>.h5ad                          T3 training knockout (about 458 MB)
```

What each file holds:

* T1: `.X` float32, log1p-normalised, 32,285 genes; `obs["celltype"]`; no coordinates. Validation target is E10.5
  (withheld), test target E12.5 (hidden). An E7.75 file is released but not used by any board.
* T2: `.X` log-normalised, finite, non-negative over the 500-gene panel; `obs["celltype"]`; `obsm["spatial_3D"]`
  float32 (n, 3) in a per-embryo local frame (not registered across stages). Embryo setting: train E6.75, E7.25,
  E8.0; validation E7.5 (interpolation); test E7.75. The embryo panel has 498 genes (two panel genes are absent).
  Heart setting: train E8.25, E8.75, E9.5; validation E8.5 (interpolation) and E10.5 (extrapolation); test E12.5
  (extrapolation). In the test phase every heart stage becomes training input.
* T3: same schema as T2 plus `obs["condition"]`. Train: Mab21l2 knockout at E9.5. Validation: Gata4 knockout at
  E8.75 (two replicates). Test: beta-catenin knockout at E8.75 (two replicates). Reference wild types: E8.75 and
  E9.5 (shared with T2 heart).

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
python -m venv .venv && .venv\Scripts\activate        # Windows; use source .venv/bin/activate elsewhere
pip install -r requirements.txt
python -m pytest -q                                    # synthetic tests, no challenge data needed
```

Prerequisites by section (Python 3.10 or newer throughout):

| you want to | sections | you need |
|---|---|---|
| understand the contracts, build baseline files, validate, upload | 4, 5, 6, 8 | `pip install -r requirements.txt` (anndata, numpy, scipy, pandas, h5py; pytest for the tests). Nothing else. |
| score locally on a pseudo split | 7 | additionally the organisers' scorer **veckit** and its dependencies (numpy, scipy, anndata, scikit-learn). Obtain it from the organisers: `pip install "git+https://github.com/aristoteleo/veckit.git@46d41e63f42a9aab815db20b742feeccd249cb17"`, or `git clone https://github.com/aristoteleo/veckit` anywhere and point `VECKIT_PATH` at the clone (`set VECKIT_PATH=C:\path\to\veckit` on Windows, `export VECKIT_PATH=/path/to/veckit` elsewhere). Check: `python -c "from vec_local_score import veckit_available, veckit_info; print(veckit_available(), veckit_info())"`. The kit was tested against veckit 0.1.1. |
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
3. `n_obs` at least the board's minimum. The evaluation pages (read 2026-09-05) say "at least 1,000 cells ... no
   cap", while the organisers' `panels/index.json` carries a `max_cells` per board (the table above); the checker
   treats `max_cells` as an error unless `--ignore-max-cells`, because an upload above it is untested. The cell
   count is a sample size, not a scored quantity; a few thousand cells is plenty (the scorer's own draws use at
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
The released stages hold more cells than four of the five boards' `max_cells`, so `all` would stop with an error
that states the bound; pass a number (or `--allow-over-max`, see section 4 rule 3). The bound is written next to
each command (from `data/panels/index.json`).

```
# T1:val: 1000-5118 cells. E9.5_RNA has 17,057 cells, so `all` would error; 5000 fits.
python -m vec_baselines.make_baseline --method copy_last   --board T1:val               --last data/raw/T1/E9.5_RNA.h5ad          --out out/t1_copy_last.h5ad --n-cells 5000
# T2:embryo:val_interp: 583-5000 cells (5000 is the maximum).
python -m vec_baselines.make_baseline --method copy_last   --board T2:embryo:val_interp --last data/raw/T2_embryo/E8.0.h5ad       --out out/embryo_copy_last.h5ad --n-cells 5000
# T2:heart:val_interp: 1000-17616 cells. E8.25_late has roughly 59,000 cells (index.json ref_cells x 10), so `all` would error.
python -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_interp  --last data/raw/T2_heart/E8.25_late.h5ad  --out out/heart_interp_copy_last.h5ad --n-cells 5000
# T2:heart:val_extrap: 1000-25179 cells. E9.5 has roughly 54,000 cells, so `all` would error.
python -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_extrap  --last data/raw/T2_heart/E9.5.h5ad        --out out/heart_extrap_copy_last.h5ad --n-cells 5000
# T3:gata4: 1000-7449 cells. E8.75 has roughly 25,000 cells, so `all` would error.
python -m vec_baselines.make_baseline --method wt_identity --board T3:gata4             --wt   data/raw/T2_heart/E8.75.h5ad       --out out/t3_wt_identity.h5ad --n-cells 5000
```

Notes:

* `--n-cells N` writes exactly N cells drawn without replacement (seeded, `--seed`); N must lie inside the board's
  bounds (a value above `max_cells` is refused, never clamped). `--n-cells all` writes every cell of the input and
  errors, stating the bound, when that exceeds `max_cells`. If the input has fewer cells than N (but at least
  `min_cells`) every cell is written and the CLI prints a NOTE. The stage sizes above are 17,057 for E9.5_RNA (data
  page) and, for the heart stages, ten times `index.json`'s `ref_cells` (the scorer's 10 % reference), so "roughly".
* The embryo board takes a 500-gene heart-schema file and writes the 498-gene panel automatically (columns are
  mapped by gene name).
* Which stage is "last" is your choice; for an interpolation board it is usually the stage right before the
  target, for an extrapolation board the latest released stage.
* The CLI prints the local contract verdict for the written file and exits 0 only when it passes, e.g.
  `[PASS] out/t3_wt_identity.h5ad @ T3:gata4  n_obs=5000 n_vars=500 X=dense[float32] min=0.0 max=10.2 size=10.1MB`
  followed by `PASS = local format checks passed; it does not confirm log-normalisation, data provenance or
  eligibility`.

From Python:

```python
from vec_baselines import io as bio, methods as bm
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

`[PASS]` / `[FAIL]` plus every error and warning, then the file's sha256, size, value range and coordinate radius:

```
[PASS] out/heart_interp_copy_last.h5ad @ T2:heart:val_interp  n_obs=5000 n_vars=500
  PASS = local format checks passed; it does not confirm log-normalisation, data provenance or eligibility
  sha256: <64 hex characters: keep it with the file you upload>
  X_format: dense[float32]  X_min: 0.0  X_max: 12.1656  spatial_3D_rms_radius: 84.589  ...
```

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
(plus the task weights published on the evaluation pages). The organisers' portal scorer is the source of truth
and the wrapper may lag it.

Prerequisite: veckit (section 3). Check with
`python -c "from vec_local_score import veckit_available, veckit_info; print(veckit_available(), veckit_info())"`.

**The wrapper takes the raw released stage files** and does the subsample and the split itself: `--target` is the
held-out raw stage, `--reference` (T1/T2) or `--wt` (T3) the raw stage the change is measured against, `--pred`
your prediction for the held-out stage. Build the pseudo-prediction from the stages you keep, never from the
held-out one (a file sampled from the target itself scores 100 and tells you nothing). Example, heart
interpolation board with E8.75 held out and the `copy_last` baseline built from E8.25 as the prediction:

```
python -m vec_baselines.make_baseline --method copy_last --board T2:heart:val_interp --last data/raw/T2_heart/E8.25_late.h5ad --out out/pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --frac 0.1 --seed 0
python -m vec_local_score.seed_summary --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --seeds 0 1 2 3 4
```

For T1 hold out E9.5_RNA and predict it from E8.5_RNA: build the prediction from `--last data/raw/T1/E8.5_RNA.h5ad`
and score with `--task T1 --target data/raw/T1/E9.5_RNA.h5ad --reference data/raw/T1/E8.5_RNA.h5ad`. For T3 hold
out the training knockout: `--task T3 --target <Mab21l2 knockout> --wt <matched wild type at the same stage, E9.5>`,
with the prediction built from the wild type.

How to read it: every stage is subsampled to 10 %, the target is split in half; the floor (the reference
resubmitted) defines 50 and the ceiling (the other half of the target) defines 100 on the skill scale; your
prediction gets a skill per metric (veckit's own `skill()`) and a task score. The two target-0 metrics
(`scale_log_ratio`, `severity_slope`) are marked `*`: their skill is computed on the absolute values (an overshoot
counts like an undershoot). Your resampled `copy_last` file lands **near** 50, not exactly on it - the wrapper's
floor row is a 10 % subsample of the reference and your file is a different sample of the same cells; a value a
few points off 50 is normal. A local score is **not** a preview of the real one; it ranks your own methods on the
same split with the same seeds. Report mean and spread over several seeds (`seed_summary`); a difference within
one standard deviation is not a result. `docs/metrics_overview.md` explains every column, and
`vec_local_score/README.md` states exactly which conventions the wrapper implements.

`python -m vec_local_score.make_pseudo_split` is optional: it exports one fixed split as files for inspection or for
calling the veckit CLI directly. Its outputs are not inputs to `vec_local_score` (the wrapper refuses them, because
it would subsample twice).

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
needs `launch.build_command` adapted.

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
launch command without launching anything, if you want to inspect it first.)

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
copied read-only into its workspace.

Human do's and don'ts: before the lock, anything; between the lock and `run_manifest.json`, nothing (do not open
the stream, the workspace or the ranking for that run); after, read the manifest and NOTES.md, decide which
completed run to upload, upload the unchanged file and the zips, and put what you learned into the next prompt
version (record it with `--note` when you lock the next run). Never resume a session, never feed one run's
artefacts into another's workspace, never edit a submission.

## 10. Checklist before every upload

- [ ] `python -m vec_submit_check --board <board> <file>` prints `[PASS]` (format only; the next three lines are
      yours to confirm).
- [ ] The gene order equals the panel file (the checker says so; the portal will not reorder).
- [ ] Cell count at least 1,000 and, unless you chose otherwise, at most `index.json`'s `max_cells` (you passed it
      explicitly); no duplicated cells; no labels needed.
- [ ] `.X` log-normalised like the released data (no `raw counts` warning), finite, non-negative (every board).
- [ ] T2/T3: `obsm["spatial_3D"]` present, (n, 3), finite.
- [ ] File under 1200 MB.
- [ ] You know which board tab the file belongs to (heart interpolation vs extrapolation are different boards).
- [ ] Agent track: `run_manifest.json` says `lock_integrity.ok`, `secret_scan.clean`, `abort: null`, and the
      board is `uploadable`; the prediction you upload has the sha256 recorded there; two evidence kinds attached.
- [ ] External data or pretrained models used? Disclosed in the method summary.
