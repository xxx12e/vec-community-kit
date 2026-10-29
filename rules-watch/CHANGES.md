# VEC rules and contract watch: changelog

Newest first. One entry per run that found a change or a fetch problem. Written by `python -m vec_rules_watch run` (a daily GitHub Action of vec-community-kit) from the public pages of https://virtualembryo.ai/challenge, the board contract (panels/index.json and the gene lists), the phase endpoint and the organisers' scorer veckit on GitHub. Quoted lines are short excerpts (at most 200 characters each); the organisers' pages are the authoritative text. How it works and its limits: vec_rules_watch/README.md. Chinese version: CHANGES.zh.md.

<!-- entries below, newest first -->

## 2026-10-29 (run 13:11 UTC)

### Site links

- New link on the challenge site: https://virtualembryo.ai/challenge/data-protocol (not in the watch list yet: it may be a new page worth reading)

### Pages

#### Challenge Rules

Challenge Rules (https://virtualembryo.ai/challenge/rules): 1 section(s) changed, +1 / -1 lines.
The rules decide what is allowed and what is prize-eligible: read the changed sections on the page in full.

- Changed: "9. Agent Team Entries" (+1 / -1 lines)

Changed lines (short excerpts):

```diff
@@ 9. Agent Team Entries
- Evidence is capped at 200 MB per file and 600 MB per team in total. Trajectories compress well; a trace that does not fit is a trace that should be filed in full and summarised, not truncated si...
+ ...pped at 200 MiB per file and 2 GiB in total per submission, not per team. Evidence attached to other submissions, including P2 entries, does not reduce a new submission’s allowance. Trajectories...
```

#### Data

Data (https://virtualembryo.ai/challenge/data): 2 section(s) changed, 1 added, 1 removed, +13 / -3 lines.
The Data page lists stages, downloads and per-board cell counts: compare it with the board contract.

- Changed: "Download" (+1 / -0 lines)
- Changed: "How many cells to submit" (+1 / -0 lines)
- Added: "File checksums" (11 line(s))
- Removed: "Validation answers for P3" (3 line(s))

Changed lines (short excerpts):

```diff
@@ Download
+ Sign in to download →
@@ How many cells to submit
+ How the samples were collected, dissected and processed: Data Protocol.
@@ File checksums
+ SHA-256 of each file in the training release. Check a download with shasum -a 256 <file>.
+ File | Bytes | SHA-256
+ T1/E8.5_RNA.h5ad | 570,917,395 | 8eab2d0ccaa89f92861b09816b76b6a731b8ed6b5995e4af196d9ed8ff76e504
+ T1/E9.5_RNA.h5ad | 589,907,081 | 0296e0043842f944a663f3c11ac1542d1bbee733c1cd657bd56f75af65958361
+ T2/E8.25_late.h5ad | 225,091,568 | d56f94d3e2d719ed3074d86c03eae457ccf90b24145d33300f9958f0e8078593
+ T2/E9.5.h5ad | 163,640,212 | 371ca6530e084de2b6cd6703b49d95f4bb59546c9291659809575382a630ee9a
@@ Validation answers for P3
- P2 validation answers can be used to prepare your final P3 models. Hidden test answers are never released. Browsing this page does not change your eligibility.
- Available to eligible registered participants during P3, after explicit confirmation.
- Sign in to download →
```
(5 more changed lines not quoted)

## 2026-10-28 (run 13:05 UTC)

### Board contract (https://virtualembryo.ai/challenge/panels/index.json)

- New board T1:test (T1 · test (E12.5)): task T1, split test, 32285 genes (T1__test.genes.txt), cells 638-5118, coordinates: not used.
  - What this changes for your file: A file for T1:test needs exactly this board's gene list in its order (32285 genes) and 638 to 5118 cells; coordinates: not used. The kit's validator reads the new contract with VEC_PANELS_DIR=rules-watch/contract/panels.
- New board T2:embryo:test_interp (T2 embryo · interpolation, test (E7.75)): task T2, split test, 497 genes (T2__embryo__test_interp.genes.txt), cells 1000-5000, coordinates: required in .obsm [spatial_3D].
  - What this changes for your file: A file for T2:embryo:test_interp needs exactly this board's gene list in its order (497 genes) and 1000 to 5000 cells; coordinates: required in .obsm [spatial_3D]. The kit's validator reads the new contract with VEC_PANELS_DIR=rules-watch/contract/panels.
- New board T2:heart:test_extrap (T2 heart · extrapolation, test (E12.5)): task T2, split test, 500 genes (T2__heart__test_extrap.genes.txt), cells 1000-34641, coordinates: required in .obsm [spatial_3D].
  - What this changes for your file: A file for T2:heart:test_extrap needs exactly this board's gene list in its order (500 genes) and 1000 to 34641 cells; coordinates: required in .obsm [spatial_3D]. The kit's validator reads the new contract with VEC_PANELS_DIR=rules-watch/contract/panels.
- New board T3:bcatenin (T3 · test (beta-catenin KO)): task T3, split test, 500 genes (T3__bcatenin.genes.txt), cells 1000-7449, coordinates: required in .obsm [spatial_3D].
  - What this changes for your file: A file for T3:bcatenin needs exactly this board's gene list in its order (500 genes) and 1000 to 7449 cells; coordinates: required in .obsm [spatial_3D]. The kit's validator reads the new contract with VEC_PANELS_DIR=rules-watch/contract/panels.

### Phase endpoint (https://kg.virtualembryo.ai/challenge/phase)

- Phase p2 -> p3 (P3 · Final test phase).
  - What this changes for your file: The challenge is in a new phase: re-read the timeline and the rules before your next upload.
- Scored board validation -> final.
  - What this changes for your file: New submissions are scored on the final board: check the keys and cell bounds of its boards (board contract above).
- daily_quota 8 -> 2.
  - What this changes for your file: Plan your uploads for the new quota.
- Nominations are open: a final entry can be nominated now (nominations_open true).
- split val -> test.

### Site links

- New link on the challenge site: https://virtualembryo.ai/challenge/panels/T1__test.genes.txt
- New link on the challenge site: https://virtualembryo.ai/challenge/panels/T2__embryo__test_interp.genes.txt
- New link on the challenge site: https://virtualembryo.ai/challenge/panels/T2__heart__test_extrap.genes.txt
- New link on the challenge site: https://virtualembryo.ai/challenge/panels/T3__bcatenin.genes.txt

### Pages

#### Overview

Overview (https://virtualembryo.ai/challenge): 1 section(s) changed, +0 / -1 lines.

- Changed: "(top of page)" (+0 / -1 lines)

Changed lines (short excerpts):

```diff
@@ (top of page)
- P2 is open: validation submissions are scored and ranked, and the starter kit and reference baselines are out. Next: P3 opens at 09:00 Los Angeles time; P2 standings freeze on 27 October 2026. F...
```

#### Challenge Rules

Challenge Rules (https://virtualembryo.ai/challenge/rules): 2 section(s) changed, +9 / -4 lines.
The rules decide what is allowed and what is prize-eligible: read the changed sections on the page in full.

- Changed: "10. Data and What You May Use" (+5 / -3 lines)
- Changed: "11. Leaderboard Entries and Final Entries" (+4 / -1 lines)

Changed lines (short excerpts):

```diff
@@ 10. Data and What You May Use
- Training stages are released at registration. Validation and test targets are never distributed while they rank: a submission comes back as a score, not as answers.
+ Training stages are released at registration. Before P3, validation answers are withheld. Hidden test ground truth is never distributed.
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
+ The official P2 validation files supplied through this opt-in are a specific exception to the held-out-data restrictions below, solely for preparing P3 predictions after access is granted. This ...
- ...d, by any route: not directly, not through a model pre-trained on it, and not through a public dataset that contains it. This is the one restriction that decides whether a result means anything.
+ ...not through a model pre-trained on it, and not through a public dataset that contains it. The only exception is the official P2 validation release obtained through the P3 opt-in described above.
- ...s excluded from after E9.5 up to and including E13.5. E10.5 and E12.5, the validation and test targets themselves, are excluded absolutely. Anything after E13.5 may be used, provided the source ...
+ ....5. External data at E10.5 and E12.5 remains prohibited. The official E10.5 validation files may be used only after the P3 opt-in described above; E12.5 test ground truth remains prohibited. Any...
@@ 11. Leaderboard Entries and Final Entries
- Each task is scored on its own boards, and a submission names the board it answers. Limits are per team, per task, per UTC day:
+ ...d it answers. P1 and P2 limits are per team, per task, per UTC day; P3 limits are per test board for the entire phase. The published partner arrangements specify the individual Yukon allowances.
+ P3 opens on 27 October 2026 at 09:00 America/Los_Angeles (16:00 UTC). The default leaderboard becomes Test (P3). Live Validation (P2) remains available, and a separate Frozen P2 board preserves ...
+ Only P2 submissions already scored before 09:00 at that cutoff enter Frozen P2. A submission uploaded before the cutoff but scored afterward enters only the live Validation board. Later scores o...
+ Participants may continue submitting to live Validation during P3 under the P2 allowances until they explicitly obtain validation-data access or their first P3 submission is accepted, whichever ...
```

#### FAQ

FAQ (https://virtualembryo.ai/challenge/faq): 1 section(s) changed, +1 / -1 lines.
The FAQ often carries rulings on edge cases: read the changed answers.

- Changed: "Data" (+1 / -1 lines)

Changed lines (short excerpts):

```diff
@@ Data
- You may train on external data, public or your own, and for Task 1 this is expressly encouraged. What you may not use is measured data from a held-out stage or genotype, by any route: not direct...
+ The official P2 validation files obtained through explicit P3 opt-in may be used for P3 preparation. This exception does not permit hidden test targets or additional external data from protected...
```

#### Data

Data (https://virtualembryo.ai/challenge/data): 5 section(s) changed, +9 / -4 lines.
The Data page lists stages, downloads and per-board cell counts: compare it with the board contract.

- Changed: "Gene panel, per board" (+5 / -0 lines)
- Changed: "How many cells to submit" (+1 / -1 lines)
- Changed: "File format (2)" (+1 / -1 lines)
- Changed: "File format (3)" (+1 / -1 lines)
- Changed: "Access and reproducibility" (+1 / -1 lines)

Changed lines (short excerpts):

```diff
@@ Gene panel, per board
+ Both Validation (P2) and Test (P3) submission specifications are listed below. Use the file for the exact board you submit to: embryo interpolation requires 498 genes for P2 and 497 for P3. Thes...
+ T1:test | 32,285 | 638-5,118 | T1__test.genes.txt ↓
+ T2:heart:test_extrap | 500 | 1,000-34,641 | T2__heart__test_extrap.genes.txt ↓
+ T2:embryo:test_interp | 497 | 1,000-5,000 | T2__embryo__test_interp.genes.txt ↓
+ T3:bcatenin | 500 | 1,000-7,449 | T3__bcatenin.genes.txt ↓
@@ How many cells to submit
- ...d one to estimate the ceiling. So truth_cells and ref_cells in index.json are counts of our working copy, not of an embryo and not of the release. Your submission is not expected to mirror them.
+ ...For P2, truth_cells and ref_cells in index.json are counts of our working copy, not of an embryo and not of the release. Your submission is not expected to mirror them. P3 specifications publish...
@@ File format (2)
- var index | string [500] | The 500 panel genes, in panel order. Identical across every Task-2 and Task-3 file.
+ ...Source files use a 500-gene measured panel. Predictions must use the exact ordered panel for their board: heart 500, embryo validation 498, embryo test 497. Download the corresponding gene list ...
@@ File format (3)
- var index | string [500] | The same 500 panel genes as Task 2, in the same order.
+ var index | string [500] | Use the exact ordered 500-gene list published for the Task-3 board. Do not substitute a Task-2 panel.
@@ Access and reproducibility
- You may train on external data, public or your own, and for Task 1 this is expressly encouraged. What you may not use is measured data from a held-out stage or genotype, by any route: not direct...
+ The official P2 validation files obtained through explicit P3 opt-in may be used for P3 preparation. This exception does not permit hidden test targets or additional external data from protected...
```

## 2026-10-27 (run 12:20 UTC)

### Phase endpoint (https://kg.virtualembryo.ai/challenge/phase)

- phase_mode null -> auto.
- scheduled_p3_start_at null -> 2026-10-27T16:00:00Z.

### Pages

#### Overview

Overview (https://virtualembryo.ai/challenge): 3 section(s) changed, +4 / -4 lines.

- Changed: "(top of page)" (+1 / -1 lines)
- Changed: "Three tasks, one shared atlas" (+1 / -1 lines)
- Changed: "Launch → development → final" (+2 / -2 lines)

Changed lines (short excerpts):

```diff
@@ (top of page)
- ...missions are scored and ranked, and the starter kit and reference baselines are out. Next: Test phase starts, validation data released, test leaderboard opens on 27 October 2026. Full timeline →
+ ...lidation submissions are scored and ranked, and the starter kit and reference baselines are out. Next: P3 opens at 09:00 Los Angeles time; P2 standings freeze on 27 October 2026. Full timeline →
@@ Three tasks, one shared atlas
- ... train, E10.5 extrapolation validation, E12.5 extrapolation test, and in the final phase every heart stage is training input. Embryo, in order: E6.75 train, E7.25 train, E7.5 validation, E7.75 t...
+ ...ion validation, E12.5 extrapolation test, and during P3 the validation stages become training input only after explicit opt-in; E12.5 remains hidden. Embryo, in order: E6.75 train, E7.25 train, ...
@@ Launch → development → final
- P3 · Test phase starts, validation data released, test leaderboard opens
+ P3 · P3 opens at 09:00 Los Angeles time; P2 standings freeze
- P3 · Test phase starts, validation data released, test leaderboard opens
+ P3 · P3 opens at 09:00 Los Angeles time; P2 standings freeze
```

#### FAQ

FAQ (https://virtualembryo.ai/challenge/faq): 1 section(s) changed, +1 / -1 lines.
The FAQ often carries rulings on edge cases: read the changed answers.

- Changed: "Data" (+1 / -1 lines)

Changed lines (short excerpts):

```diff
@@ Data
- ...Validation and test ground truth are withheld while they can still affect the board, until the final phase a validation submission returns a leaderboard score, not the answers. At the start of t...
+ ...During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
```

#### Timeline

Timeline (https://virtualembryo.ai/challenge/timeline): 1 section(s) changed, +3 / -3 lines.
Dates may have moved: check your plan against the new schedule.

- Changed: "Challenge timeline" (+3 / -3 lines)

Changed lines (short excerpts):

```diff
@@ Challenge timeline
- P3 · Test phase starts, validation data released, test leaderboard opens
+ P3 · P3 opens at 09:00 Los Angeles time; P2 standings freeze
- Test phase starts, validation data released, test leaderboard opens
+ P3 opens at 09:00 Los Angeles time; P2 standings freeze
- The point where the two halves swap. The validation data is released for every task (it can no longer be used to probe the board, because ranking moves to the hidden test split) so validation be...
+ At 09:00 PDT (16:00 UTC), the default leaderboard switches to Test and Frozen P2 preserves results scored before this cutoff. During P3, eligible participants can explicitly request the P2 valid...
```

#### Data

Data (https://virtualembryo.ai/challenge/data): 9 section(s) changed, 1 added, +17 / -16 lines.
The Data page lists stages, downloads and per-board cell counts: compare it with the board contract.

- Changed: "Download" (+1 / -4 lines)
- Changed: "Task 1: single-cell RNA" (+1 / -1 lines)
- Changed: "File format" (+2 / -2 lines)
- Changed: "Task 2: 3D MERFISH (embryo setting)" (+1 / -1 lines)
- Changed: "File format (2)" (+2 / -2 lines)
- Changed: "Task 2: 3D MERFISH (heart setting)" (+3 / -3 lines)
- Changed: "Task 3: conditional knock-outs" (+1 / -1 lines)
- Changed: "File format (3)" (+1 / -1 lines)
- Changed: "Access and reproducibility" (+2 / -1 lines)
- Added: "Validation answers for P3" (3 line(s))

Changed lines (short excerpts):

```diff
@@ Download
- ...ing stages are released to registered participants. Validation and test targets come back as a score rather than as answers, until the final phase releases the validation answers for every task.
+ ... a score rather than as answers, until the final phase allows you to opt in to the validation answers for P3 preparation. Accessing those answers permanently ends your P2 submission eligibility.
- More data comes later
- This is not all the data you will get. At the final test phase the validation stages are released too, with their answers, so they become training material rather than something you can only pro...
- Sign in to download →
@@ Task 1: single-cell RNA
- E10.5 | val | validation target, answers withheld | 647 MB
+ E10.5 | val | validation target, answers available during P3 after explicit opt-in | 647 MB
@@ File format
- never distributed. Submit and the server scores it
+ available during P3 after explicit opt-in; access permanently ends P2 submissions
- inputs released at the final test phase, without labels
+ hidden test target; ground truth is never released
@@ Task 2: 3D MERFISH (embryo setting)
- E7.5 | val | interpolation validation, answers withheld
+ E7.5 | val | interpolation validation, answers available during P3 after explicit opt-in
@@ File format (2)
- never distributed. Submit and the server scores it
+ available during P3 after explicit opt-in; access permanently ends P2 submissions
- inputs released at the final test phase, without labels
+ hidden test target; ground truth is never released
@@ Task 2: 3D MERFISH (heart setting)
- E8.5 | val | interpolation validation, answers withheld | 85 MB
+ E8.5 | val | interpolation validation, answers available during P3 after explicit opt-in | 85 MB
- E10.5 | val | extrapolation validation, answers withheld | 484 MB
+ E10.5 | val | extrapolation validation, answers available during P3 after explicit opt-in | 484 MB
- ...k if you want to know how that skill will be judged. What this setting carries into the final phase is extrapolation, on the hidden E12.5. In the final phase every heart stage is training input.
+ ... judged. What this setting carries into the final phase is extrapolation, on the hidden E12.5. During P3, the validation stages become training input after explicit opt-in; E12.5 remains hidden.
@@ Task 3: conditional knock-outs
- Gata4 KO @ E8.75 | val | Mesp1-Cre; Gata4 F/F; Gata6 F/+, two replicates; answers released at the final phase | 374 + 409 MB
+ Gata4 KO @ E8.75 | val | Mesp1-Cre; Gata4 F/F; Gata6 F/+, two replicates; answers available during P3 after explicit opt-in | 374 + 409 MB
@@ File format (3)
- inputs released at the final test phase, without labels
+ hidden test target; ground truth is never released
@@ Access and reproducibility
- ...Validation and test ground truth are withheld while they can still affect the board: a validation submission comes back as a leaderboard score, not the answers. At the start of the final phase t...
+ ...During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
+ After you explicitly unlock the official P2 validation release above, you may use those released validation files for P3 preparation. This does not permit access to hidden test data or other res...
@@ Validation answers for P3
+ P2 validation answers can be used to prepare your final P3 models. Hidden test answers are never released. Browsing this page does not change your eligibility.
+ Available to eligible registered participants during P3, after explicit confirmation.
+ Sign in to download →
```

#### Tasks

Tasks (https://virtualembryo.ai/challenge/tasks): 2 section(s) changed, +2 / -2 lines.
A task description changed: check the splits and the input and output.

- Changed: "Three tasks, one shared resource" (+1 / -1 lines)
- Changed: "Spatial-temporal multiscale prediction" (+1 / -1 lines)

Changed lines (short excerpts):

```diff
@@ Three tasks, one shared resource
- Ground truth is withheld while it can still affect the board. Until the final phase a validation submission returns a leaderboard score, not the answers. At the start of the final phase the vali...
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
@@ Spatial-temporal multiscale prediction
- ... train, E10.5 extrapolation validation, E12.5 extrapolation test, and in the final phase every heart stage is training input. Embryo, in order: E6.75 train, E7.25 train, E7.5 validation, E7.75 t...
+ ...ion validation, E12.5 extrapolation test, and during P3 the validation stages become training input only after explicit opt-in; E12.5 remains hidden. Embryo, in order: E6.75 train, E7.25 train, ...
```

#### Task 1 (temporal)

Task 1 (temporal) (https://virtualembryo.ai/challenge/tasks/temporal): 1 section(s) changed, +2 / -2 lines.
A task description changed: check the splits and the input and output.

- Changed: "Splits" (+2 / -2 lines)

Changed lines (short excerpts):

```diff
@@ Splits
- Ground truth is withheld while it can still affect the board. Until the final phase a validation submission returns a leaderboard score, not the answers. At the start of the final phase the vali...
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
- Scored through the leaderboard until the final phase, when the answers are released.
+ Scored through the leaderboard until the final phase, when participants can explicitly request the answers and permanently end their P2 submission eligibility.
```

#### Task 2 (spatial-temporal)

Task 2 (spatial-temporal) (https://virtualembryo.ai/challenge/tasks/spatial): 1 section(s) changed, +2 / -2 lines.
A task description changed: check the splits and the input and output.

- Changed: "Splits" (+2 / -2 lines)

Changed lines (short excerpts):

```diff
@@ Splits
- Ground truth is withheld while it can still affect the board. Until the final phase a validation submission returns a leaderboard score, not the answers. At the start of the final phase the vali...
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
- One interpolation target inside the observed range, one extrapolation target beyond it. Scored through the leaderboard until the final phase, when the answers are released.
+ ...ne extrapolation target beyond it. Scored through the leaderboard until the final phase, when participants can explicitly request the answers and permanently end their P2 submission eligibility.
```

#### Task 3 (perturbation)

Task 3 (perturbation) (https://virtualembryo.ai/challenge/tasks/perturbation): 2 section(s) changed, +3 / -3 lines.
A task description changed: check the splits and the input and output.

- Changed: "The question" (+1 / -1 lines)
- Changed: "Splits" (+2 / -2 lines)

Changed lines (short excerpts):

```diff
@@ The question
- ...Task 3 is the only one whose validation answers are released during the competition. At the start of the final phase, when the rank has moved to the hidden knockout and they can no longer be use...
+ ...ondingly diffuse. Validation answers become available by explicit opt-in during P3, as for the other tasks. Access permanently ends P2 submission eligibility; hidden test answers remain private.
@@ Splits
- Ground truth is withheld while it can still affect the board. Until the final phase a validation submission returns a leaderboard score, not the answers. At the start of the final phase the vali...
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
- Also specific, at a different stage. Scored through the leaderboard until the final phase, when the answers are released.
+ Also specific, at a different stage. Scored through the leaderboard until the final phase, when participants can explicitly request the answers and permanently end their P2 submission eligibility.
```

#### Evaluation, Task 1: task

Evaluation, Task 1: task (https://virtualembryo.ai/challenge/evaluation?section=task&task=1): 1 section(s) changed, +2 / -2 lines.
The evaluation pages define the file contract and the metrics: check whether your file or your local scoring is affected.

- Changed: "Splits" (+2 / -2 lines)

Changed lines (short excerpts):

```diff
@@ Splits
- Ground truth is withheld while it can still affect the board. Until the final phase a validation submission returns a leaderboard score, not the answers. At the start of the final phase the vali...
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
- Scored through the leaderboard until the final phase, when the answers are released.
+ Scored through the leaderboard until the final phase, when participants can explicitly request the answers and permanently end their P2 submission eligibility.
```

#### Evaluation, Task 2: task

Evaluation, Task 2: task (https://virtualembryo.ai/challenge/evaluation?section=task&task=2): 1 section(s) changed, +2 / -2 lines.
The evaluation pages define the file contract and the metrics: check whether your file or your local scoring is affected.

- Changed: "Splits" (+2 / -2 lines)

Changed lines (short excerpts):

```diff
@@ Splits
- Ground truth is withheld while it can still affect the board. Until the final phase a validation submission returns a leaderboard score, not the answers. At the start of the final phase the vali...
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
- One interpolation target inside the observed range, one extrapolation target beyond it. Scored through the leaderboard until the final phase, when the answers are released.
+ ...ne extrapolation target beyond it. Scored through the leaderboard until the final phase, when participants can explicitly request the answers and permanently end their P2 submission eligibility.
```

#### Evaluation, Task 3: task

Evaluation, Task 3: task (https://virtualembryo.ai/challenge/evaluation?section=task&task=3): 2 section(s) changed, +3 / -3 lines.
The evaluation pages define the file contract and the metrics: check whether your file or your local scoring is affected.

- Changed: "Task" (+1 / -1 lines)
- Changed: "Splits" (+2 / -2 lines)

Changed lines (short excerpts):

```diff
@@ Task
- ...Task 3 is the only one whose validation answers are released during the competition. At the start of the final phase, when the rank has moved to the hidden knockout and they can no longer be use...
+ ...ondingly diffuse. Validation answers become available by explicit opt-in during P3, as for the other tasks. Access permanently ends P2 submission eligibility; hidden test answers remain private.
@@ Splits
- Ground truth is withheld while it can still affect the board. Until the final phase a validation submission returns a leaderboard score, not the answers. At the start of the final phase the vali...
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
- Also specific, at a different stage. Scored through the leaderboard until the final phase, when the answers are released.
+ Also specific, at a different stage. Scored through the leaderboard until the final phase, when participants can explicitly request the answers and permanently end their P2 submission eligibility.
```

## 2026-10-21 (run 11:58 UTC)

### Site links

- New link on the challenge site: https://virtualembryo.ai/challenge/privacy (not in the watch list yet: it may be a new page worth reading)

### Pages

#### Terms of Use

Terms of Use (https://virtualembryo.ai/challenge/terms): 1 section(s) changed, +1 / -0 lines.
The terms of use changed: read the changed sections on the page.

- Changed: "8. Privacy" (+1 / -0 lines)

Changed lines (short excerpts):

```diff
@@ 8. Privacy
+ Read the Challenge Privacy Policy.
```

## 2026-10-20 (run 11:46 UTC)

### Site links

- New link on the challenge site: https://virtualembryo.ai/challenge/partner-rules (not in the watch list yet: it may be a new page worth reading)

### Pages

#### Overview

Overview (https://virtualembryo.ai/challenge): 2 section(s) changed, +3 / -3 lines.

- Changed: "(top of page)" (+1 / -1 lines)
- Changed: "Launch → development → final" (+2 / -2 lines)

Changed lines (short excerpts):

```diff
@@ (top of page)
- ...missions are scored and ranked, and the starter kit and reference baselines are out. Next: Test phase starts, validation data released, test leaderboard opens on 20 October 2026. Full timeline →
+ ...missions are scored and ranked, and the starter kit and reference baselines are out. Next: Test phase starts, validation data released, test leaderboard opens on 27 October 2026. Full timeline →
@@ Launch → development → final
- 20 Oct
+ 27 Oct
- 2026-10-20
+ 2026-10-27
```

#### Challenge Rules

Challenge Rules (https://virtualembryo.ai/challenge/rules): 1 section(s) changed, +1 / -0 lines.
The rules decide what is allowed and what is prize-eligible: read the changed sections on the page in full.

- Changed: "Official Rules" (+1 / -0 lines)

Changed lines (short excerpts):

```diff
@@ Official Rules
+ Participating in the EigenLab Yukon partner category? See the partner participation arrangements for its team-size exception, collaboration, individual allowances, one-way transfers and exclusio...
```

#### Timeline

Timeline (https://virtualembryo.ai/challenge/timeline): 1 section(s) changed, +2 / -2 lines.
Dates may have moved: check your plan against the new schedule.

- Changed: "Challenge timeline" (+2 / -2 lines)

Changed lines (short excerpts):

```diff
@@ Challenge timeline
- 20 Oct
+ 27 Oct
- 2026-10-20
+ 2026-10-27
```

## 2026-10-16 (run 11:31 UTC)

### Official scorer (https://github.com/aristoteleo/veckit)

- New branch docs/library-size-ratio-no-renormalisation at f56a6e3.

### Pages

#### FAQ

FAQ (https://virtualembryo.ai/challenge/faq): 1 section(s) changed, +1 / -1 lines.
The FAQ often carries rulings on edge cases: read the changed answers.

- Changed: "Data" (+1 / -1 lines)

Changed lines (short excerpts):

```diff
@@ Data
- ...t labelled by somite count or Theiler stage that lands in the same window. For the Task 1 extrapolation targets the window is stated outright rather than derived, and it relaxes the midpoint rul...
+ ...te count or Theiler stage that lands in the same window. For the extrapolation targets (Task 1, and Task 2 in the heart setting) the window is stated outright rather than derived, and it relaxes...
```

#### Data

Data (https://virtualembryo.ai/challenge/data): 1 section(s) changed, +1 / -1 lines.
The Data page lists stages, downloads and per-board cell counts: compare it with the board contract.

- Changed: "Access and reproducibility" (+1 / -1 lines)

Changed lines (short excerpts):

```diff
@@ Access and reproducibility
- ...t labelled by somite count or Theiler stage that lands in the same window. For the Task 1 extrapolation targets the window is stated outright rather than derived, and it relaxes the midpoint rul...
+ ...te count or Theiler stage that lands in the same window. For the extrapolation targets (Task 1, and Task 2 in the heart setting) the window is stated outright rather than derived, and it relaxes...
```

#### Evaluation, Task 1: submissions

Evaluation, Task 1: submissions (https://virtualembryo.ai/challenge/evaluation?section=submissions&task=1): 1 section(s) changed, +1 / -1 lines.
The evaluation pages define the file contract and the metrics: check whether your file or your local scoring is affected.

- Changed: "What is deliberately not constrained" (+1 / -1 lines)

Changed lines (short excerpts):

```diff
@@ What is deliberately not constrained
- ...above the floor. Nothing requires n_pred = n_true. A genuine growth or proliferation model may predict a different number of cells than the target has, and only the 1,000-cell minimum is enforce...
+ ...within the board’s limits. Nothing requires n_pred = n_true. A genuine growth or proliferation model may predict a different number of cells than the target has, and only the board’s own minimum...
```

#### Evaluation, Task 2: submissions

Evaluation, Task 2: submissions (https://virtualembryo.ai/challenge/evaluation?section=submissions&task=2): 1 section(s) changed, +1 / -1 lines.
The evaluation pages define the file contract and the metrics: check whether your file or your local scoring is affected.

- Changed: "What is deliberately not constrained" (+1 / -1 lines)

Changed lines (short excerpts):

```diff
@@ What is deliberately not constrained
- ...above the floor. Nothing requires n_pred = n_true. A genuine growth or proliferation model may predict a different number of cells than the target has, and only the 1,000-cell minimum is enforce...
+ ...within the board’s limits. Nothing requires n_pred = n_true. A genuine growth or proliferation model may predict a different number of cells than the target has, and only the board’s own minimum...
```

#### Evaluation, Task 3: submissions

Evaluation, Task 3: submissions (https://virtualembryo.ai/challenge/evaluation?section=submissions&task=3): 1 section(s) changed, +1 / -1 lines.
The evaluation pages define the file contract and the metrics: check whether your file or your local scoring is affected.

- Changed: "What is deliberately not constrained" (+1 / -1 lines)

Changed lines (short excerpts):

```diff
@@ What is deliberately not constrained
- ...above the floor. Nothing requires n_pred = n_true. A genuine growth or proliferation model may predict a different number of cells than the target has, and only the 1,000-cell minimum is enforce...
+ ...within the board’s limits. Nothing requires n_pred = n_true. A genuine growth or proliferation model may predict a different number of cells than the target has, and only the board’s own minimum...
```

## 2026-10-03 (run 11:45 UTC)

### Official scorer (https://github.com/aristoteleo/veckit)

- main moved 46d41e6 -> cc3859a (2026-10-02: "Merge pull request #9 from Shashwat-srivastav/fix-issue7-right-handed-frame").
  - What this changes for your file: The organisers' scorer changed. Read the commit before you trust local scores; this kit's vec_local_score pins veckit 46d41e6 (0.1.1).

## 2026-09-30 (run 17:03 UTC)

First run: this entry records the starting point. Later entries list what changed against it.

### Board contract (https://virtualembryo.ai/challenge/panels/index.json)

- Baseline: 5 boards in index.json.
- T1:val: 32285 genes (T1__val.genes.txt, genes_sha256 807549e15be01989), cells 1000-5118, coordinates: not used.
- T2:embryo:val_interp: 498 genes (T2__embryo__val_interp.genes.txt, genes_sha256 f8a2aaa79bf32cfb), cells 583-5000, coordinates: required in .obsm [spatial_3D].
- T2:heart:val_extrap: 500 genes (T2__heart__val_extrap.genes.txt, genes_sha256 a9a553108e19acb6), cells 1000-25179, coordinates: required in .obsm [spatial_3D].
- T2:heart:val_interp: 500 genes (T2__heart__val_interp.genes.txt, genes_sha256 a9a553108e19acb6), cells 1000-17616, coordinates: required in .obsm [spatial_3D].
- T3:gata4: 500 genes (T3__gata4.genes.txt, genes_sha256 a9a553108e19acb6), cells 1000-7449, coordinates: required in .obsm [spatial_3D].

### Phase endpoint (https://kg.virtualembryo.ai/challenge/phase)

- Baseline: phase p2 (P2 · Baselines released), board validation, split val, daily_quota 8, accepts_submissions true, nominations_open false.

### Official scorer (https://github.com/aristoteleo/veckit)

- Baseline: aristoteleo/veckit main at 46d41e6 (2026-08-10), version 0.1.1; tags: none; releases: none; branches: feat/metric-hardening-0.2.0, main.

### Pages

- Baseline recorded for 27 pages.
- Overview (https://virtualembryo.ai/challenge): baseline recorded, 7 section(s).
- Challenge Rules (https://virtualembryo.ai/challenge/rules): baseline recorded, 20 section(s).
- Terms of Use (https://virtualembryo.ai/challenge/terms): baseline recorded, 16 section(s).
- FAQ (https://virtualembryo.ai/challenge/faq): baseline recorded, 7 section(s).
- Timeline (https://virtualembryo.ai/challenge/timeline): baseline recorded, 1 section(s).
- Prizes (https://virtualembryo.ai/challenge/prizes): baseline recorded, 5 section(s).
- Community award (https://virtualembryo.ai/challenge/community): baseline recorded, 5 section(s).
- Publish with us (https://virtualembryo.ai/challenge/publish): baseline recorded, 5 section(s).
- Data (https://virtualembryo.ai/challenge/data): baseline recorded, 16 section(s).
- Tasks (https://virtualembryo.ai/challenge/tasks): baseline recorded, 5 section(s).
- Task 1 (temporal) (https://virtualembryo.ai/challenge/tasks/temporal): baseline recorded, 10 section(s).
- Task 2 (spatial-temporal) (https://virtualembryo.ai/challenge/tasks/spatial): baseline recorded, 10 section(s).
- Task 3 (perturbation) (https://virtualembryo.ai/challenge/tasks/perturbation): baseline recorded, 10 section(s).
- Reference rows (https://virtualembryo.ai/challenge/baselines): baseline recorded, 19 section(s).
- Community resources (https://virtualembryo.ai/challenge/resources): baseline recorded, 3 section(s).
- Evaluation, Task 1: task (https://virtualembryo.ai/challenge/evaluation?section=task&task=1): baseline recorded, 3 section(s).
- Evaluation, Task 1: submissions (https://virtualembryo.ai/challenge/evaluation?section=submissions&task=1): baseline recorded, 7 section(s).
- Evaluation, Task 1: scoring (https://virtualembryo.ai/challenge/evaluation?section=scoring&task=1): baseline recorded, 16 section(s).
- Evaluation, Task 1: resources (https://virtualembryo.ai/challenge/evaluation?section=resources&task=1): baseline recorded, 3 section(s).
- Evaluation, Task 2: task (https://virtualembryo.ai/challenge/evaluation?section=task&task=2): baseline recorded, 3 section(s).
- Evaluation, Task 2: submissions (https://virtualembryo.ai/challenge/evaluation?section=submissions&task=2): baseline recorded, 7 section(s).
- Evaluation, Task 2: scoring (https://virtualembryo.ai/challenge/evaluation?section=scoring&task=2): baseline recorded, 20 section(s).
- Evaluation, Task 2: resources (https://virtualembryo.ai/challenge/evaluation?section=resources&task=2): baseline recorded, 3 section(s).
- Evaluation, Task 3: task (https://virtualembryo.ai/challenge/evaluation?section=task&task=3): baseline recorded, 3 section(s).
- Evaluation, Task 3: submissions (https://virtualembryo.ai/challenge/evaluation?section=submissions&task=3): baseline recorded, 7 section(s).
- Evaluation, Task 3: scoring (https://virtualembryo.ai/challenge/evaluation?section=scoring&task=3): baseline recorded, 17 section(s).
- Evaluation, Task 3: resources (https://virtualembryo.ai/challenge/evaluation?section=resources&task=3): baseline recorded, 3 section(s).
