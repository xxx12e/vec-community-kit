# What the Virtual Embryo Challenge metrics measure

A neutral description of the evaluation, taken from the official evaluation pages and the organisers' open-source
scorer (veckit). Metric names are veckit's. Nothing here is a strategy; it is what each number means so that a
local score table can be read.

## The skill scale

Every raw metric is rescaled with two reference values computed by the organisers on the hidden target:

* **floor** - the raw metric of the floor model: `copy_last` for T1/T2 (the last observed stage resubmitted
  verbatim) and `wt_identity` for T3 (the matched wild type resubmitted verbatim);
* **ceiling** - the raw metric of one half of the target scored against the other half (what a perfect sampler
  attains at that cell count), estimated after the 10 % subsample.

    skill(m) = min( d_floor / (d_floor + d(m)), 1 )

where `d(m)` is the distance of the raw metric from the ceiling (inverted for lower-is-better metrics) and
`d_floor` the floor's distance. So floor -> 0.5, ceiling -> 1.0, worse than floor -> below 0.5 (unbounded towards 0).
A metric that comes back missing or NaN is scored 0, not 0.5.

    task score = 100 * sum over groups g of w_g * sum over metrics m in g of w_(m|g) * skill(m)

Each task is worth 100 points; the total is T1 + T2 + T3, at most 300. A task with several boards (T2) takes the
mean of the team's best result on each board; a board that was never scored counts 0.

Scoring protocol: every stage (reference, target, prediction) is subsampled to 10 % before comparison; the target
is split in half (score half / ceiling half). Cell-type labels are never read from the submission; the scorer
types cells with a frozen classifier trained on the real target. The cell count of a submission is a sample size,
not a scored quantity.

## Metrics

| veckit name | direction | what it measures |
|---|---|---|
| `de_score` | higher is better | Differential-expression recovery. The truth's DE genes (target vs the reference stage / matched WT: Mann-Whitney U, Benjamini-Hochberg FDR 0.05, absolute mean log fold change >= 0.25) define how many genes go up and down. The prediction ranks genes by its own change (prediction minus reference) and names exactly that many up and down genes; the overlap is normalised against the overlap achieved by ranking genes by their expression level. 0 = no better than that expression-level baseline; 1 = the truth's own sets. A prediction with no change scores 0. |
| `de_direction` | higher is better | Direction of change: rank (partial) correlation between the predicted and the observed log fold change, controlling for the reference expression level. A no-change prediction scores 0. |
| `severity_slope` (T3) | higher is better, target 0 | Size of the response on the truth's DE genes: the zero-intercept regression slope of predicted on observed log fold change, reported in log space (0 = right magnitude, negative = undershoot, positive = overshoot). A prediction whose response does not track the truth's, or has no response, is assigned the maximal-undershoot floor. |
| `mmd_u` | lower is better | Distribution distance of cells: unbiased multi-kernel RBF maximum mean discrepancy in a 30-component PCA space fitted on the target only, kernel widths at 0.25 to 4 times the target's median heuristic, up to 2000 cells per side. |
| `variogram` | lower is better | Gene-gene co-variation structure: for 20,000 random gene pairs (i, j), the squared difference between the prediction's and the truth's mean of abs(x_i - x_j)^0.5 over cells. The only expression term that constrains the joint distribution rather than marginals. |
| `d2_shape` (T2) | lower is better | Tissue shape: coordinates are canonicalised (centred, PCA-aligned, rescaled by the RMS radius) and the distributions of pairwise distances are compared by a Wasserstein-1 distance. |
| `occupancy_dice` (T2) | higher is better | Voxel occupancy overlap: canonicalised coordinates are voxelised on a 16^3 grid over [-3, 3] RMS radii; Dice overlap with the truth, maximised over the four proper sign flips. |
| `scale_log_ratio` (T2) | target value 0 | Tissue scale: log of the ratio of the truth's RMS radius to the prediction's. 0 means the same size. |
| `neighborhood_mmd` (T2) | lower is better | Local spatial organisation: each cell's 15-nearest-neighbour neighbourhood is summarised as a pseudobulk profile; MMD between the sets of neighbourhood profiles of prediction and truth. |

All spatial metrics are invariant to translation and to proper rotations (mirroring is a stated blind spot).
Coordinates may be in any frame.

## Weights

| task | group (weight) | metrics (weight within group) |
|---|---|---|
| T1 | DE recovery (25 %) | `de_score` |
| T1 | Change direction (25 %) | `de_direction` |
| T1 | Cell-state distribution (30 %) | `mmd_u` |
| T1 | Gene-gene co-variation (20 %) | `variogram` |
| T2 (each board) | Expression change (25 %) | `de_score` 50 %, `de_direction` 50 % |
| T2 | Cell-state distribution (25 %) | `mmd_u` 60 %, `variogram` 40 % |
| T2 | Tissue shape and growth (25 %) | `d2_shape`, `occupancy_dice`, `scale_log_ratio` (1/3 each) |
| T2 | Local spatial organisation (25 %) | `neighborhood_mmd` |
| T3 | Response gene recovery (30 %) | `de_score` |
| T3 | Response direction (25 %) | `de_direction` |
| T3 | Response magnitude (25 %) | `severity_slope` |
| T3 | Cell-state distribution (20 %) | `mmd_u` 60 %, `variogram` 40 % |

All T3 differential-expression metrics are computed against the matched wild type at the SAME stage as the
knockout. The T3 knockout is scored against each of its two replicates; the public ranking uses a fixed one and
the difference between the two is published as a noise estimate.

## Reading a local table

`vec_local_score` prints, per metric: raw (your prediction), floor (the reference resubmitted), ceiling (the
other half of the target), skill and points. On a local pseudo split the floor and ceiling are computed from your
own data, so the floor row lands exactly at 50 and the ceiling half at 100 by construction. The absolute values
are not comparable with the hidden target's; the comparison that is meaningful is between two of your own
predictions on the same split with the same seeds.
