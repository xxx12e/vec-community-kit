# vec_local_score - the veckit scorer's protocol on data you hold

A thin wrapper around the organisers' local scorer **veckit** that runs its metric panels on a pseudo-validation
split built from RAW released stages and turns the raw metrics into the 0-100 skill scale. It follows the veckit
scorer's protocol as of veckit 0.1.1: 10 % subsample, split-half ceiling, floor row, skill scale, plus the task
weights published on the evaluation pages (floor = 50, ceiling = 100).

**The default output is the multi-seed band.** One call scores your prediction under subsample seeds 0 1 2 3 4
and prints the task score as mean, sd and band (min..max over the seeds), with a per-metric table of means;
`--single-seed [--seed N]` gives the old one-seed table (faster, for quick checks), `--seeds ...` other seeds,
`--verbose` every per-seed table as well. Why: from 20 October 2026 the organisers' scorer draws its subsample with
a seed that depends on each submission (the organisers, in their review of this kit, September 2026). A published
score is then one draw from a band of this kind - the same file uploaded twice can score differently - and a single
local seed hides how wide that band is. The local band measures the subsampling noise of the protocol on your
pseudo split, not on the hidden target; use it to decide whether a difference between two of your methods is real
(outside the band) or noise (inside it). Each input file is read once and reused for every seed; seed `s` of the
band is exactly the `--single-seed --seed s` result.

**It is not a preview of your real score.** The real target is a stage you do not have; a pseudo board compares
your own methods against each other under the same metric definitions on the split you chose, nothing more: it
does not predict the order on the hidden target, and no local number is a competition score. **The organisers'
scorer is the source of truth and this wrapper may lag it.**

Tested against **veckit 0.1.1** (`pyproject.toml` version; clone at git commit
`46d41e63f42a9aab815db20b742feeccd249cb17` of https://github.com/aristoteleo/veckit, 2026-08-10; sha256 of
`score_h5ad.py` `9460f191d49cdcab2100ceb068759f4d6ea49570174c23846193c59f175f404d`, of `common/core_metrics.py`
`e06dc84ecd8723ecacb1f31a0f4deb9a8722d37ff90193a7af05e2405fefb5e9`). Every result records the version, location
and file hashes of the veckit that actually ran (`result["veckit"]`; `veckit_info()`), and the table footer says
so when they differ from the tested ones.

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
```

Options: `--seeds 0 1 2 3 4` (default), `--single-seed` and `--seed N` (one seed; `--seed` alone implies
`--single-seed`; either with `--seeds` is an error), `--verbose` (multi-seed: also every per-seed table),
`--frac 0.1` (subsample fraction applied to the raw target and reference; veckit protocol 0.1), `--max-cells 4000`
(cap for the reference after the subsample; the target gets twice that), `--pred-max-cells 0` (0 = score every
submitted cell, as the server does; set a cap only for speed), `--json` (multi-seed: the summary with `mode:
multi_seed`, `task_score_mean`, `task_score_sd`, `band`, `task_scores`, per-metric means and every per-seed result;
single seed: the one-seed result with `mode: single_seed`). `python -m vec_local_score.seed_summary` still works and
is now the same as `python -m vec_local_score`. From Python: `score(...)` is one seed, `summarise(..., seeds=...)`
the band.

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
note: from 2026-10-20 the organisers' scorer draws its subsample with a seed that depends on each submission: ...
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
number can sit several points from the mean, which is why the band is the default. Both outputs are copied from
`scratchpad/dryrun_log.txt` (2026-09-30). A resampled floor file lands **near** 50,
not exactly on it: the wrapper's floor row is a 10 % subsample of the
reference stage and your file is a different sample of the same cells. Only the special case `--frac 1.0` with a
prediction identical to the reference gives exactly 50.0 (that is what the tests check).

## Choosing a pseudo board

Hold out the latest released stage and predict it from the earlier ones (for an extrapolation board), or hold
out a middle stage (for an interpolation board). The reference passed to the scorer is the stage the change is
measured against; for T3 it is the matched wild type at the same stage as the knockout. Keep the same
target/reference pair and the same seeds when comparing two methods, and report the band (the default output).
