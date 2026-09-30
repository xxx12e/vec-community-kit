# vec_local_score - the veckit scorer's protocol on data you hold

A thin wrapper around the organisers' local scorer **veckit** that runs its metric panels on a pseudo-validation
split built from RAW released stages and turns the raw metrics into the 0-100 skill scale. It follows the veckit
scorer's protocol as of veckit 0.1.1: 10 % subsample, split-half ceiling, floor row, skill scale, plus the task
weights published on the evaluation pages (floor = 50, ceiling = 100).

**The default output is the multi-seed band.** One call scores your prediction under subsample seeds 0 1 2 3 4
and prints the task score as mean, sd and band (min..max over the seeds), with a per-metric table of means;
`--single-seed [--seed N]` gives the old one-seed table (faster, for quick checks), `--seeds ...` other seeds,
`--verbose` every per-seed table as well. Why: the organisers, in their review of this kit (September 2026), said
the subsample seed will depend on each submission, and a single local seed hides how much the score moves with the
subsample. The local band measures the subsampling noise of the protocol on your pseudo split, not on the hidden
target; to decide whether a difference between two of your methods is real, use the paired mode below. Each input
file is read once and reused for every seed; seed `s` of the band is exactly the `--single-seed --seed s` result.

**Comparing two predictions: the paired mode (`--pred A --pred B`).** Both files are scored under the same seeds,
and in each seed against one shared draw - the same reference and target subsamples, target halves, cell-type
probe, floor and ceiling - so the per-seed difference B - A removes the subsampling noise the two files share. The
output gives each file's band, the per-metric point differences, and B - A per seed with its mean, sd and min..max
over the seeds. When min..max stays on one side of 0, one file is ahead on every seed of this split; when it
straddles 0, the seeds disagree. Two bands can overlap while the paired difference keeps its sign (example below).
Seed `s` of either file is exactly that file's `--single-seed --seed s` result. `--single-seed` / `--seed` take one
`--pred`.

**JSON key renamed.** The `--json` of the default (band) output carries `task_score_mean` (with `task_score_sd`,
`task_score_min`, `task_score_max`, `band`, `task_scores`) where the one-seed default of earlier versions wrote
`task_score`; `task_score` is now the key of the `--single-seed` JSON only. Scripts that read `task_score` from the
default output must read `task_score_mean` (or pass `--single-seed`).

**It is not a preview of your real score.** The real target is a stage you do not have; a pseudo board compares
your own methods against each other under the same metric definitions on the split you chose, nothing more: it
does not predict the order on the hidden target, and no local number is a competition score. **The organisers'
scorer is the source of truth and this wrapper may lag it.**

Tested against **veckit 0.1.1** (`pyproject.toml` version; clone at git commit
`46d41e63f42a9aab815db20b742feeccd249cb17` of https://github.com/aristoteleo/veckit, 2026-08-10; sha256 of
`score_h5ad.py` `52034554f03aec10193cb09baa2c78a1de04218ef678f327eb63acc58fa28add`, of `common/core_metrics.py`
`3be7099a0c9a7ad5b609f86078871ed8290ed0bd8916b0cb3e14fb9831909f31`, both over the content with LF line endings as
stored at that commit; CRLF is normalised to LF before hashing, so a Windows clone and a Linux `pip install` of the
same commit match). Every result records the version, location and file hashes of the veckit that actually ran
(`result["veckit"]`; `veckit_info()`, whose `matches_tested` compares them with the tested ones). Up to 2026.10.0
the recorded hashes were those of a Windows CRLF checkout, so the tested commit installed on Linux reported
`matches_tested: False`; the pass over the real release on a Linux runner found this (fixed in 2026.10.1).

## veckit is not vendored

veckit is the organisers' code (MIT, https://github.com/aristoteleo/veckit); it needs numpy, scipy, anndata and
scikit-learn. Provide it in one of three ways; the wrapper checks them in this order:

1. `pip install "git+https://github.com/aristoteleo/veckit.git@46d41e63f42a9aab815db20b742feeccd249cb17"` (the
   tested commit; the default branch moves) or `pip install -e path/to/clone`;
2. `set VECKIT_PATH=path\to\veckit` (Windows) / `export VECKIT_PATH=path/to/veckit` - the directory that
   contains `score_h5ad.py`;
3. `git clone https://github.com/aristoteleo/veckit third_party/veckit` inside this kit.

`python -c "from vec_local_score import veckit_available, veckit_info; print(veckit_available(), veckit_info())"`
tells you whether it is found and which one. The wrapper uses veckit's `score_h5ad._load_task_metrics`, the
`metrics_v2` panels and `common.core_metrics.skill`.

## The one contract: raw stages in, subsample and split inside

The wrapper takes the **raw released stage files** and performs the 10 % subsample and the split-half itself, in
memory, seeded. Hold out a released stage as `--target`, pass the stage the change is measured against as
`--reference` (T1/T2) or `--wt` (T3), and pass your prediction for the held-out stage as `--pred`. That prediction
(`pseudo_pred.h5ad` below) must be built **without** the held-out stage - the `copy_last` file from the earlier
stage, or your model run on the earlier stages only; a prediction that used the pseudo target makes the comparison
meaningless. Do not reuse a file built for another board (an extrapolation prediction of a later stage, say) to
score an earlier held-out stage:

```
# the default: the band over seeds 0-4 (mean, sd, min..max of the task score; per-metric means)
python -m vec_local_score --task T1 --pred pseudo_pred.h5ad --target E9.5_RNA.h5ad --reference E8.5_RNA.h5ad
python -m vec_local_score --task T2 --setting heart --pred pseudo_pred.h5ad --target E8.75.h5ad --reference E8.25_late.h5ad --json band.json
python -m vec_local_score --task T3 --pred pseudo_pred.h5ad --target Mab21l2_KO_E9.5.h5ad --wt WT_E9.5.h5ad

# the old behaviour: one seed, the full per-metric table
python -m vec_local_score --task T2 --setting heart --pred pseudo_pred.h5ad --target E8.75.h5ad --reference E8.25_late.h5ad --single-seed

# two of your methods, paired over the same seeds: B - A per seed, its mean, sd and min..max
python -m vec_local_score --task T2 --setting heart --pred pseudo_pred.h5ad --pred pseudo_pred_mine.h5ad --target E8.75.h5ad --reference E8.25_late.h5ad
```

Options: `--seeds 0 1 2 3 4` (default), `--single-seed` and `--seed N` (one seed; `--seed` alone implies
`--single-seed`; either with `--seeds` is an error), `--verbose` (multi-seed: also every per-seed table),
`--frac 0.1` (subsample fraction applied to the raw target and reference; veckit protocol 0.1), `--max-cells 4000`
(cap for the reference after the subsample; the target gets twice that), `--pred-max-cells 0` (0 = score every
submitted cell, as the server does; set a cap only for speed), `--json` (multi-seed: the summary with `mode:
multi_seed`, `task_score_mean`, `task_score_sd`, `band`, `task_scores`, per-metric means and every per-seed result;
single seed: the one-seed result with `mode: single_seed` and `task_score`; paired: `mode: paired`, `diff_scores`
(B - A per seed), `diff_mean`, `diff_sd`, `diff_min`, `diff_max`, `b_higher_seeds`, `metric_diffs`, and `a` / `b`,
each file's band as in the multi-seed JSON). `--pred-max-cells` draws each prediction's cells with a generator of
its own, so a cap never changes the draw of the target, the reference or the other prediction.
`python -m vec_local_score.seed_summary` still works and is now the same as `python -m vec_local_score`. From
Python: `score(...)` is one seed, `summarise(..., seeds=...)` the band, `compare(task, pred_a, pred_b, ...)` the
paired comparison, `score_many(...)` several predictions under one seed and one shared draw.

`make_pseudo_split` is a separate, optional tool: it **exports** one fixed split as files (`target_score.h5ad`,
`target_ceiling.h5ad`, `reference.h5ad`, `meta.json`) for inspection or for calling the veckit CLI directly, which
scores whatever files you give it without subsampling. Its outputs are **not** inputs to `vec_local_score`: they
carry `uns["vec_pseudo_split"]` and the wrapper refuses them, because scoring them there would subsample twice.

```
python -m vec_local_score.make_pseudo_split --target E8.75.h5ad --reference E8.25_late.h5ad \
    --out-dir pseudo/heart --panel data/panels/T2__heart__val_interp.genes.txt --require-coords
veckit --task T2 --setting heart --input pseudo/heart/target_ceiling.h5ad --target pseudo/heart/target_score.h5ad --reference pseudo/heart/reference.h5ad   # ceiling row
veckit --task T2 --setting heart --input pseudo/heart/reference.h5ad      --target pseudo/heart/target_score.h5ad --reference pseudo/heart/reference.h5ad   # floor row
veckit --task T2 --setting heart --input pseudo_pred.h5ad                        --target pseudo/heart/target_score.h5ad --reference pseudo/heart/reference.h5ad   # your model
```

## What the wrapper computes, exactly

1. Reference and target are subsampled to `--frac` of their cells (reference capped at `--max-cells`, target at
   twice that). The target subsample is split in half: **A** is scored against, **B** is scored as a prediction
   to estimate the attainable ceiling (veckit: `common.core_metrics.split_half`).
2. Three veckit panel runs against A, sharing one frozen cell-type probe trained on A: your prediction (every
   submitted cell unless `--pred-max-cells`), the **floor row** (the reference resubmitted: copy_last on T1/T2,
   wt_identity on T3) and the **ceiling** (half B).
3. Per metric, `skill = veckit.common.core_metrics.skill(value, floor, ceiling, lower_is_better)`: hyperbolic,
   floor -> 0.5, ceiling -> 1.0 (clipped above), worse than the floor -> below 0.5 towards 0.
4. `task score = 100 * sum_g w_g * sum_{m in g} w_m skill(m)`; a missing / NaN metric counts as skill 0.

Conventions the wrapper adds (veckit only returns raw metrics, so these are the wrapper's choices):

* **Direction per metric.** Higher is better: `de_score`, `de_direction`, `occupancy_dice`. Lower is better:
  `mmd_u`, `variogram`, `d2_shape`, `neighborhood_mmd`. Target 0: `scale_log_ratio`, `severity_slope`.
* **Target-0 metrics are folded.** veckit 0.1.1 reports both as signed values - `scale_log_ratio` is the log of
  the RMS-radius ratio prediction/truth, `severity_slope` the log of the regression slope of predicted on observed
  log fold change with a finite worst case `log(1e-3)` for a no / inverted / unrelated response - and veckit's
  `skill()` has no symmetric mode. The wrapper takes `|value|` of the prediction, the floor and the ceiling and
  scores that as lower-is-better. This matches the published definitions (0 = the right size; severity as
  min(beta, 1/beta) in log space); an overshoot is penalised, not credited. The table marks these metrics with `*`.
  (An earlier version used `|value - ceiling|` around the signed ceiling instead; that is not what the code does now.)
* **Degenerate reference values.** When floor and ceiling coincide on a small split (`|floor - ceiling| < 1e-12`
  after folding; veckit's `skill()` returns NaN there), the metric cannot discriminate: the wrapper assigns 1.0 if
  the prediction is at least as good as the ceiling and 0.0 otherwise, and flags the row `degenerate`. Treat such a
  metric as uninformative at that sample size. A metric whose floor or ceiling is missing is flagged `undefined`
  and scores 0.

## Reading the output

| column | meaning |
|---|---|
| raw | veckit's raw metric for your prediction against target half A (signed, as veckit reports it) |
| floor | the same metric for the reference stage resubmitted (copy_last / wt_identity) |
| ceiling | the same metric for target half B (what a perfect sampler attains at this cell count) |
| skill | veckit's skill(): floor -> 0.5, ceiling -> 1.0, worse than floor -> below 0.5; `*` = computed on the absolute values |
| pts | 100 * weight * skill; the task score is the sum |

Example of the default output (a `copy_last` file scored on a small synthetic heart pair, the one the tutorial dry
run plants; the real tables look the same):

```
T2 heart  pred=pseudo_pred.h5ad  target=E8.75.h5ad  ref=E8.25_late.h5ad  cells pred/A/B/ref = 2400/120/120/240  frac=0.1  seeds=[0, 1, 2, 3, 4]
metric               raw_mean    raw_sd      floor    ceiling   skill     sd    pts
de_score              -0.9569    0.0875     0.0000     1.0000   0.338  0.010   4.23
...
scale_log_ratio*      -0.2424    0.0190    -0.2473     0.0021   0.504  0.032   4.20
neighborhood_mmd       0.4421    0.0457     0.4500     0.2188   0.507  0.015  12.67
TASK SCORE (0-100; floor=50, ceiling=100): mean 53.11  sd 3.54  band 48.86..56.96 (min..max over 5 seeds)  [4.5s]
pseudo_pred.h5ad on E8.75.h5ad: 53.11 +- 3.54 (sd), band 48.86..56.96 (min..max over seeds [0, 1, 2, 3, 4])
* target-0 metric: skill computed on |value| (prediction, floor and ceiling), lower is better
note: the organisers, in their review of this kit, said the subsample seed will depend on each submission ...
veckit 0.1.1; the organisers' scorer is the source of truth and this wrapper may lag it
```

The same file with `--single-seed` (seed 0; the old default) prints one seed's full table:

```
T2 heart  pred=pseudo_pred.h5ad  target=E8.75.h5ad  ref=E8.25_late.h5ad  cells pred/A/B/ref = 2400/120/120/240  frac=0.1 seed=0
group                        metric                    raw      floor    ceiling   skill    pts
...
Tissue shape and growth      scale_log_ratio*      -0.2558    -0.3007    -0.0407   0.547   4.56
...
                                      TASK SCORE (0-100; floor=50, ceiling=100)  50.02   [0.7s]
* target-0 metric: skill computed on |value| (prediction, floor and ceiling), lower is better
veckit 0.1.1; the organisers' scorer is the source of truth and this wrapper may lag it
```

On this toy pair seed 0 gives 50.02 while the band over five seeds spans 48.86..56.96 (mean 53.11): a single local
number can sit several points from the mean, which is why the band is the default.

The paired mode on the same pair, with a stand-in B (the `copy_last` file with its coordinates grown by the factor
the synthetic target was scaled by, 1.25):

```
T2 heart  target=E8.75.h5ad  ref=E8.25_late.h5ad  frac=0.1  seeds=[0, 1, 2, 3, 4]  (paired comparison)
A = pseudo_pred.h5ad: mean 53.11  sd 3.54  band 48.86..56.96
B = pseudo_pred_mine.h5ad: mean 57.19  sd 3.87  band 52.49..61.32
metric               A pts   B pts  B-A pts     sd
de_score              4.23    4.23    +0.00   0.00
...
scale_log_ratio*      4.20    8.27    +4.07   0.35
neighborhood_mmd     12.67   12.67    +0.00   0.00
TASK SCORE B - A per seed: 0: +3.77  1: +4.23  2: +4.38  3: +3.63  4: +4.36
TASK SCORE B - A: mean +4.07  sd 0.35  min..max +3.63..+4.38 over 5 seeds  [5.5s]
B - A (pseudo_pred_mine.h5ad - pseudo_pred.h5ad) on E8.75.h5ad: +4.07 +- 0.35 (sd), min..max +3.63..+4.38 over seeds [0, 1, 2, 3, 4]; B higher on 5 of 5 seeds
...
```

The two bands overlap (48.86..56.96 and 52.49..61.32), yet B is ahead on every seed by 3.63 to 4.38 points: the
paired difference is the reading to use for a comparison. (Copied from the addendum of `scratchpad/dryrun_log.txt`.) Both outputs are copied from
`scratchpad/dryrun_log.txt` (2026-09-30). A resampled floor file lands **near** 50,
not exactly on it: the wrapper's floor row is a 10 % subsample of the
reference stage and your file is a different sample of the same cells. Only the special case `--frac 1.0` with a
prediction identical to the reference gives exactly 50.0 (that is what the tests check).

## Choosing a pseudo board

Hold out the latest released stage and predict it from the earlier ones (for an extrapolation board), or hold
out a middle stage (for an interpolation board). The reference passed to the scorer is the stage the change is
measured against; for T3 it is the matched wild type at the same stage as the knockout. Compare two methods with
the paired mode (`--pred A --pred B`: same target/reference pair, same seeds, one shared draw per seed) and report
B - A with its min..max over the seeds.
