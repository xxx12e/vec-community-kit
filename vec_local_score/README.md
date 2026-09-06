# vec_local_score - the veckit scorer's protocol on data you hold

A thin wrapper around the organisers' local scorer **veckit** that runs its metric panels on a pseudo-validation
split built from RAW released stages and turns the raw metrics into the 0-100 skill scale. It follows the veckit
scorer's protocol as of veckit 0.1.1: 10 % subsample, split-half ceiling, floor row, skill scale, plus the task
weights published on the evaluation pages (floor = 50, ceiling = 100).

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
# one seed, full table
python -m vec_local_score --task T1 --pred pseudo_pred.h5ad --target E9.5_RNA.h5ad --reference E8.5_RNA.h5ad
python -m vec_local_score --task T2 --setting heart --pred pseudo_pred.h5ad --target E8.75.h5ad --reference E8.25_late.h5ad
python -m vec_local_score --task T3 --pred pseudo_pred.h5ad --target Mab21l2_KO_E9.5.h5ad --wt WT_E9.5.h5ad

# several seeds, mean +- sd per metric and for the task score
python -m vec_local_score.seed_summary --task T2 --setting heart --pred pseudo_pred.h5ad --target E8.75.h5ad \
    --reference E8.25_late.h5ad --seeds 0 1 2 3 4 --json summary.json
```

Options: `--frac 0.1` (subsample fraction applied to the raw target and reference; veckit protocol 0.1), `--seed`,
`--max-cells 4000` (cap for the reference after the subsample; the target gets twice that), `--pred-max-cells 0`
(0 = score every submitted cell, as the server does; set a cap only for speed), `--json`.

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

Example (a `copy_last` file scored on a small synthetic heart pair; the real tables look the same):

```
T2 heart  pred=pseudo_pred.h5ad  target=E8.75.h5ad  ref=E8.25_late.h5ad  cells pred/A/B/ref = 2400/120/120/240  frac=0.1 seed=0
group                        metric                    raw      floor    ceiling   skill    pts
...
Tissue shape and growth      scale_log_ratio*      -0.2968    -0.3007    -0.0069   0.508   4.23
...
                                        TASK SCORE (0-100; floor=50, ceiling=100)  49.85   [1.4s]
* target-0 metric: skill computed on |value| (prediction, floor and ceiling), lower is better
veckit 0.1.1; the organisers' scorer is the source of truth and this wrapper may lag it
```

A resampled floor file lands **near** 50, not exactly on it: the wrapper's floor row is a 10 % subsample of the
reference stage and your file is a different sample of the same cells. Only the special case `--frac 1.0` with a
prediction identical to the reference gives exactly 50.0 (that is what the tests check).

## Choosing a pseudo board

Hold out the latest released stage and predict it from the earlier ones (for an extrapolation board), or hold
out a middle stage (for an interpolation board). The reference passed to the scorer is the stage the change is
measured against; for T3 it is the matched wild type at the same stage as the knockout. Keep the same
target/reference pair and the same seeds when comparing two methods, and report the spread (`seed_summary`).
