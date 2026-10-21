# VEC rules and contract watch: changelog

Newest first. One entry per run that found a change or a fetch problem. Written by `python -m vec_rules_watch run` (a daily GitHub Action of vec-community-kit) from the public pages of https://virtualembryo.ai/challenge, the board contract (panels/index.json and the gene lists), the phase endpoint and the organisers' scorer veckit on GitHub. Quoted lines are short excerpts (at most 200 characters each); the organisers' pages are the authoritative text. How it works and its limits: vec_rules_watch/README.md. Chinese version: CHANGES.zh.md.

<!-- entries below, newest first -->

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
