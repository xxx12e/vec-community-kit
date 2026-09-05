# vec_local_score - the official scoring protocol on data you hold

A thin wrapper around the organisers' local scorer **veckit** that reproduces the official aggregation on a
pseudo-validation split you build from released stages: 10 % subsample of every stage, target split in half
(score half / ceiling half), floor = `copy_last` / `wt_identity`, the hyperbolic skill map, the published task
weights, and a task score on the 0-100 scale where the floor is 50 and the ceiling is 100.

**It is not a preview of your real score.** The real target is a stage you do not have; a pseudo board ranks
your own methods against each other under the official metric definitions, nothing more.

## veckit is not vendored

veckit is the organisers' code (MIT, https://github.com/aristoteleo/veckit). Provide it in one of three ways;
the wrapper checks them in this order:

1. `pip install git+https://github.com/aristoteleo/veckit.git` (or `pip install -e path/to/clone`);
2. `set VECKIT_PATH=path\to\veckit` (Windows) / `export VECKIT_PATH=path/to/veckit` - the directory that
   contains `score_h5ad.py`;
3. `git clone https://github.com/aristoteleo/veckit third_party/veckit` inside this kit.

`python -c "from vec_local_score import veckit_available; print(veckit_available())"` tells you whether it is found.
The wrapper uses veckit's `score_h5ad._load_task_metrics` and the `metrics_v2` panels (veckit 0.1.x).

## Commands

```
# one seed, full table
python -m vec_local_score --task T1 --pred pred.h5ad --target E9.5_RNA.h5ad --reference E8.5_RNA.h5ad
python -m vec_local_score --task T2 --setting heart --pred pred.h5ad --target E8.75.h5ad --reference E8.25_late.h5ad
python -m vec_local_score --task T3 --pred pred.h5ad --target Mab21l2_KO_E9.5.h5ad --wt WT_E9.5.h5ad

# several seeds, mean +- sd per metric and for the task score
python -m vec_local_score.seed_summary --task T2 --setting heart --pred pred.h5ad --target E8.75.h5ad \
    --reference E8.25_late.h5ad --seeds 0 1 2 3 4 --json summary.json

# materialise the split as files (to call the veckit CLI directly)
python -m vec_local_score.make_pseudo_split --target E8.75.h5ad --reference E8.25_late.h5ad \
    --out-dir pseudo/heart --panel data/panels/T2__heart__val_interp.genes.txt --require-coords
```

Options: `--frac 0.1` (stage subsample; use `1.0` on files that are already subsampled), `--seed`, `--max-cells 4000`
(cap for the reference after the subsample; the target gets twice that), `--pred-max-cells 0` (0 = score every
submitted cell, as the server does; set a cap only for speed), `--json`.

## Reading the output

| column | meaning |
|---|---|
| raw | veckit's raw metric for your prediction against target half A |
| floor | the same metric for the reference stage resubmitted (copy_last / wt_identity) |
| ceiling | the same metric for target half B (what a perfect sampler attains at this cell count) |
| skill | min(d_floor / (d_floor + d), 1): floor -> 0.5, ceiling -> 1.0, worse than floor -> below 0.5 |
| pts | 100 * weight * skill; the task score is the sum |

A metric that comes back NaN scores 0 (not 0.5), exactly as on the server. On very small local splits a shape
metric's ceiling half can come out no better than the floor (the split cannot discriminate); the wrapper then
assigns skill 1.0 to that metric and you should treat it as uninformative at that sample size.

## Choosing a pseudo board

Hold out the latest released stage and predict it from the earlier ones (for an extrapolation board), or hold
out a middle stage (for an interpolation board). The reference passed to the scorer is the stage the change is
measured against; for T3 it is the matched wild type at the same stage as the knockout. Keep the same
target/reference pair and the same seeds when comparing two methods, and report the spread.
