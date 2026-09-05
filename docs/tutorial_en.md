# From zero to a first submission - Virtual Embryo Challenge (NeurIPS 2026)

This tutorial takes a newcomer from registration to a scored submission on every board, for both tracks, using
the tools in this kit. Every fact about the challenge below comes from the official site
(https://virtualembryo.ai/challenge); when in doubt the site wins. The kit itself is generic tooling: a
validator, the official floor rows as file generators, a local scoring wrapper and an evidence skeleton for the
Agent track. It contains no modelling advice.

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

## 3. Install the kit

```
git clone <this repository> vec-community-kit
cd vec-community-kit
python -m venv .venv && .venv\Scripts\activate        # Windows; use source .venv/bin/activate elsewhere
pip install -r requirements.txt
python -m pytest -q                                    # synthetic tests, no challenge data needed
```

Python 3.10 or newer; the tools need only anndata, numpy, scipy and pandas. For local scoring you also need the
organisers' scorer veckit (section 7).

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

Rules of a valid file (this is exactly what `vec_submit_check` tests):

1. A single `.h5ad`, at most 1200 MB.
2. `var_names` equal to the board's gene list, element by element, **in the same order**. The portal does not
   reorder for you.
3. `n_obs` inside the board's cell bounds. The cell count is a sample size, not a scored quantity; a few thousand
   cells is plenty (the scorer's own draws use at most 2000 cells for some metrics and 1500 for others).
4. `.X` finite, castable to float32, log-normalised like the released data; for T2/T3 also non-negative.
5. For T2/T3: `obsm["spatial_3D"]` with shape (n, 3) or wider (the first three columns are used), finite. Any
   coordinate frame is fine: the spatial metrics are invariant to translation and proper rotation.
6. No cell-type labels are needed (the scorer ignores them and types cells with its own frozen classifier).

Gene panels: `data/panels/T1__val.genes.txt` (32,285 lines), `T2__heart__*.genes.txt` and `T3__gata4.genes.txt`
(500 lines, the same panel), `T2__embryo__val_interp.genes.txt` (498 lines). `index.json` records a sha256 of each
list so a corrupted copy is detected.

## 5. Build the floor file

The floor rows are official reference rows and score exactly the floor (50 of 100 on a board) by construction:
`copy_last` resubmits the last observed stage, `wt_identity` resubmits the matched wild type. They are the right
first upload because they exercise the whole pipeline with a known outcome.

```
python -m vec_baselines.make_baseline --method copy_last   --board T1:val               --last data/raw/T1/E9.5_RNA.h5ad          --out out/t1_copy_last.h5ad --n-cells all
python -m vec_baselines.make_baseline --method copy_last   --board T2:embryo:val_interp --last data/raw/T2_embryo/E8.0.h5ad       --out out/embryo_copy_last.h5ad --n-cells 5000
python -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_interp  --last data/raw/T2_heart/E8.25_late.h5ad  --out out/heart_interp_copy_last.h5ad --n-cells all
python -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_extrap  --last data/raw/T2_heart/E9.5.h5ad        --out out/heart_extrap_copy_last.h5ad --n-cells all
python -m vec_baselines.make_baseline --method wt_identity --board T3:gata4             --wt   data/raw/T2_heart/E8.75.h5ad       --out out/t3_wt_identity.h5ad --n-cells all
```

Notes:

* `--n-cells`: without it the writer subsamples to at most 4000 cells (seeded). `all` writes every cell of the
  input if that fits the board's maximum; a number writes exactly that many. If `all` exceeds the maximum (T1:
  17,057 cells vs 5118) pass a number, e.g. `--n-cells 5000`. See `vec_baselines/README.md`, "The cell-count gotcha".
* The embryo board takes a 500-gene heart-schema file and writes the 498-gene panel automatically (columns are
  mapped by gene name).
* Which stage is "last" is your choice; for an interpolation board it is usually the stage right before the
  target, for an extrapolation board the latest released stage.
* The CLI prints the board-contract verdict for the written file and exits 0 only when it passes.

From Python:

```python
from vec_baselines import io as bio, methods as bm
spec, panel = bio.panel_for_board("T3:gata4")
wt = bio.load_stage("data/raw/T2_heart/E8.75.h5ad", panel)
X, C, info = bm.wt_identity(wt)
report = bio.write_submission(X, C, panel, "out/t3_wt_identity.h5ad", "T3:gata4", n_cells="all")
print(report["ok"], report["info"]["n_obs"])
```

`write_submission` accepts any (cells x genes) matrix plus coordinates: use it for your own model's output too. It
maps columns by gene name, clips negatives to 0, writes float32, and validates the file before it returns.

## 6. Validate

```
python -m vec_submit_check --board T2:heart:val_interp out/heart_interp_copy_last.h5ad
python -m vec_submit_check --board T1:val out/t1_copy_last.h5ad --json out/t1_check.json
```

`[PASS]` / `[FAIL]` plus every error and warning. Exit code 0 = passes, 1 = fails, 2 = usage error (unknown board
or missing file). The most common failures: gene order differs (`reorder with the panel file`), `n_obs` below the
board minimum, negative or NaN entries, missing `obsm["spatial_3D"]`, and the file size cap. A warning about
`obs["celltype"]` is harmless; a warning that `.X max looks like raw counts` means your matrix is not
log-normalised.

## 7. Score locally on a pseudo split

You cannot score against the hidden target, but you can reproduce the official protocol on data you hold: hold
out a released stage, predict it from the earlier ones, and run the organisers' scorer with the official
aggregation. The kit wraps veckit for that.

Install veckit (it is the organisers' MIT-licensed code; not vendored here):

```
pip install git+https://github.com/aristoteleo/veckit.git
# or: git clone https://github.com/aristoteleo/veckit third_party/veckit    (or set VECKIT_PATH to a clone)
```

Then, for example on the heart interpolation board with E8.75 held out:

```
python -m vec_baselines.make_baseline --method copy_last --board T2:heart:val_interp --last data/raw/T2_heart/E8.25_late.h5ad --out out/pseudo_pred.h5ad --n-cells all
python -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --frac 0.1 --seed 0
python -m vec_local_score.seed_summary --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --seeds 0 1 2 3 4
```

For T1 use `--task T1 --target E9.5_RNA.h5ad --reference E8.5_RNA.h5ad`; for T3 use `--task T3 --target <knockout>
--wt <matched wild type at the same stage>`.

How to read it: every stage is subsampled to 10 %, the target is split in half, the floor (reference resubmitted)
is 50 and the ceiling (the other half of the target) is 100 by construction; your prediction gets a skill per
metric and a task score. The floor file you just built lands at 50.0 - a good check that the pipeline works. A
local score is **not** a preview of the real one; it is a ranking instrument for your own methods on the same split
with the same seeds. Report mean and spread over several seeds (`seed_summary`); a difference within one standard
deviation is not a result. `docs/metrics_overview.md` explains every column.

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
* Limits: 200 MB per evidence file, 600 MB per team in total.
* From the FAQ: "The framework is not the point; the absence of a human in the loop is."

`vec_agent_evidence` makes all of this mechanical for a headless coding-agent CLI (it targets Claude Code's
`claude -p --output-format stream-json`; adapt `launch.build_command` for another CLI):

```
# 0. dry run with a stand-in agent, no API calls: proves the plumbing on your machine
python -m pytest tests/test_evidence.py -q

# 1. write your prompt (start from vec_agent_evidence/example_prompt.md: it explains the workspace contract only)
# 2. lock + run + collect, in one command; from the lock message on, walk away
python -m vec_agent_evidence run --task T3 --prompt my_prompt.md --model <full model id> --data-root ./data --hours 8 --max-turns 400

# 3. after run_manifest.json exists: check it, then build the upload package
python -m vec_agent_evidence package --run-dir runs/<run_id>
```

What you get, all hashed in `config.lock.json` and re-verified in `run_manifest.json`:

* **prompts**: `initial_prompt.md` (rendered byte-exact from your template), optional
  `system_prompt_appendix.md`, `prompts.manifest.json`;
* **trajectory**: `transcript/<session-id>.jsonl` (the CLI's own transcript, copied by session id), `stream.jsonl`
  (the CLI's stdout, byte for byte), `hooks/tool_audit.jsonl` (one line per tool call), `hooks/guard_denials.jsonl`
  (every denied call and why);
* **harness**: `harness_snapshot.zip` (the kit code and templates that produced the run), `config.lock.json`
  (model, tool policy, limits, seed, environment, data-file hashes, CLI binary version and sha256),
  `claude_settings.json` (deny rules and hooks), `launch_command.json`, `env/`.

The `package` step writes `predictions/` (byte-identical, sha256-verified), `trajectory.zip`, `prompts.zip`,
`harness.zip` and `evidence_bundle.zip` plus a README, and refuses to build if the lock was broken, a credential-
shaped string appears in the evidence, the run aborted, or a zip exceeds 200 MB. On the portal: upload the
prediction on the board's tab and attach the evidence ON THAT TAB (two kinds minimum; `evidence_bundle.zip` holds
all three), then submit. Repeat per board.

Inside a run the hooks deny network access, reads of the CLI's configuration directory, references to other runs,
writes into `submission/` except through `tools/finalize_submission.py` (which validates, hashes and records every
finalized file), edits of the read-only tools and data, and process-kill commands. The agent has the same
validator, floor-row generator and local scorer as you do, copied read-only into its workspace.

Human do's and don'ts: before the lock, anything; between the lock and `run_manifest.json`, nothing (do not open
the stream, the workspace or the ranking for that run); after, read the manifest and NOTES.md, decide which
completed run to upload, upload the unchanged file and the zips, and put what you learned into the next prompt
version (record it with `--note` when you lock the next run). Never resume a session, never feed one run's
artefacts into another's workspace, never edit a submission.

## 10. Checklist before every upload

- [ ] `python -m vec_submit_check --board <board> <file>` prints `[PASS]`.
- [ ] The gene order equals the panel file (the checker says so; the portal will not reorder).
- [ ] Cell count inside the board bounds; no duplicated cells; no labels needed.
- [ ] `.X` log-normalised like the released data (no `raw counts` warning), finite, non-negative for T2/T3.
- [ ] T2/T3: `obsm["spatial_3D"]` present, (n, 3), finite.
- [ ] File under 1200 MB.
- [ ] You know which board tab the file belongs to (heart interpolation vs extrapolation are different boards).
- [ ] Agent track: `run_manifest.json` says `lock_integrity.ok`, `secret_scan.clean`, `abort: null`, and the
      board is `uploadable`; the prediction you upload has the sha256 recorded there; two evidence kinds attached.
- [ ] External data or pretrained models used? Disclosed in the method summary.
