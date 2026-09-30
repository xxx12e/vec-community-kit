# VEC rules and contract watch: changelog

Newest first. One entry per run that found a change. Written by `python -m vec_rules_watch run` (a daily GitHub Action of vec-community-kit) from the public pages of https://virtualembryo.ai/challenge, the board contract (panels/index.json and the gene lists), the phase endpoint and the organisers' scorer veckit on GitHub. Quoted lines are short excerpts (at most 200 characters each); the organisers' pages are the authoritative text. How it works and its limits: vec_rules_watch/README.md. Chinese version: CHANGES.zh.md.

<!-- entries below, newest first -->

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
