# VEC 规则与契约监测：变更记录

最新的在最上面。每次运行发现变化或获取问题就写一条。由 `python -m vec_rules_watch run`（vec-community-kit 的每日 GitHub Action）根据 https://virtualembryo.ai/challenge 的公开页面、榜契约（panels/index.json 和基因列表）、阶段接口以及 GitHub 上主办方的打分器 veckit 生成。引用的行是简短摘录（每条最多 200 个字符），保留英文原文；以主办方页面为准。原理和局限见 vec_rules_watch/README.md。英文版：CHANGES.md。

<!-- entries below, newest first -->

## 2026-10-20（UTC 11:46 运行）

### 网站链接

- 比赛网站上出现新链接：https://virtualembryo.ai/challenge/partner-rules（尚未列入监测：可能是值得一读的新页面）

### 页面

#### 概览页

概览页（https://virtualembryo.ai/challenge）：2 个小节有改动，+3 / -3 行。

- 改动：“（页首）”（+1 / -1 行）
- 改动：“Launch → development → final”（+2 / -2 行）

改动的行（英文原文的简短摘录）：

```diff
@@ （页首）
- ...missions are scored and ranked, and the starter kit and reference baselines are out. Next: Test phase starts, validation data released, test leaderboard opens on 20 October 2026. Full timeline →
+ ...missions are scored and ranked, and the starter kit and reference baselines are out. Next: Test phase starts, validation data released, test leaderboard opens on 27 October 2026. Full timeline →
@@ Launch → development → final
- 20 Oct
+ 27 Oct
- 2026-10-20
+ 2026-10-27
```

#### 比赛规则

比赛规则（https://virtualembryo.ai/challenge/rules）：1 个小节有改动，+1 / -0 行。
规则决定什么允许、什么有获奖资格：请到原页面完整阅读改动的小节。

- 改动：“Official Rules”（+1 / -0 行）

改动的行（英文原文的简短摘录）：

```diff
@@ Official Rules
+ Participating in the EigenLab Yukon partner category? See the partner participation arrangements for its team-size exception, collaboration, individual allowances, one-way transfers and exclusio...
```

#### 时间线

时间线（https://virtualembryo.ai/challenge/timeline）：1 个小节有改动，+2 / -2 行。
日期可能变了：请按新的日程核对你的计划。

- 改动：“Challenge timeline”（+2 / -2 行）

改动的行（英文原文的简短摘录）：

```diff
@@ Challenge timeline
- 20 Oct
+ 27 Oct
- 2026-10-20
+ 2026-10-27
```

## 2026-10-16（UTC 11:31 运行）

### 官方打分器（https://github.com/aristoteleo/veckit）

- 新分支 docs/library-size-ratio-no-renormalisation，位于 f56a6e3。

### 页面

#### 常见问题（FAQ）

常见问题（FAQ）（https://virtualembryo.ai/challenge/faq）：1 个小节有改动，+1 / -1 行。
FAQ 里常有对边界情况的裁定：请阅读改动的回答。

- 改动：“Data”（+1 / -1 行）

改动的行（英文原文的简短摘录）：

```diff
@@ Data
- ...t labelled by somite count or Theiler stage that lands in the same window. For the Task 1 extrapolation targets the window is stated outright rather than derived, and it relaxes the midpoint rul...
+ ...te count or Theiler stage that lands in the same window. For the extrapolation targets (Task 1, and Task 2 in the heart setting) the window is stated outright rather than derived, and it relaxes...
```

#### 数据页

数据页（https://virtualembryo.ai/challenge/data）：1 个小节有改动，+1 / -1 行。
数据页列出阶段、下载和各榜细胞数：请与榜契约对照。

- 改动：“Access and reproducibility”（+1 / -1 行）

改动的行（英文原文的简短摘录）：

```diff
@@ Access and reproducibility
- ...t labelled by somite count or Theiler stage that lands in the same window. For the Task 1 extrapolation targets the window is stated outright rather than derived, and it relaxes the midpoint rul...
+ ...te count or Theiler stage that lands in the same window. For the extrapolation targets (Task 1, and Task 2 in the heart setting) the window is stated outright rather than derived, and it relaxes...
```

#### 评测页，任务 1：提交

评测页，任务 1：提交（https://virtualembryo.ai/challenge/evaluation?section=submissions&task=1）：1 个小节有改动，+1 / -1 行。
评测页规定文件契约和指标：请检查你的文件或本地打分是否受影响。

- 改动：“What is deliberately not constrained”（+1 / -1 行）

改动的行（英文原文的简短摘录）：

```diff
@@ What is deliberately not constrained
- ...above the floor. Nothing requires n_pred = n_true. A genuine growth or proliferation model may predict a different number of cells than the target has, and only the 1,000-cell minimum is enforce...
+ ...within the board’s limits. Nothing requires n_pred = n_true. A genuine growth or proliferation model may predict a different number of cells than the target has, and only the board’s own minimum...
```

#### 评测页，任务 2：提交

评测页，任务 2：提交（https://virtualembryo.ai/challenge/evaluation?section=submissions&task=2）：1 个小节有改动，+1 / -1 行。
评测页规定文件契约和指标：请检查你的文件或本地打分是否受影响。

- 改动：“What is deliberately not constrained”（+1 / -1 行）

改动的行（英文原文的简短摘录）：

```diff
@@ What is deliberately not constrained
- ...above the floor. Nothing requires n_pred = n_true. A genuine growth or proliferation model may predict a different number of cells than the target has, and only the 1,000-cell minimum is enforce...
+ ...within the board’s limits. Nothing requires n_pred = n_true. A genuine growth or proliferation model may predict a different number of cells than the target has, and only the board’s own minimum...
```

#### 评测页，任务 3：提交

评测页，任务 3：提交（https://virtualembryo.ai/challenge/evaluation?section=submissions&task=3）：1 个小节有改动，+1 / -1 行。
评测页规定文件契约和指标：请检查你的文件或本地打分是否受影响。

- 改动：“What is deliberately not constrained”（+1 / -1 行）

改动的行（英文原文的简短摘录）：

```diff
@@ What is deliberately not constrained
- ...above the floor. Nothing requires n_pred = n_true. A genuine growth or proliferation model may predict a different number of cells than the target has, and only the 1,000-cell minimum is enforce...
+ ...within the board’s limits. Nothing requires n_pred = n_true. A genuine growth or proliferation model may predict a different number of cells than the target has, and only the board’s own minimum...
```

## 2026-10-03（UTC 11:45 运行）

### 官方打分器（https://github.com/aristoteleo/veckit）

- main 分支从 46d41e6 移到 cc3859a（2026-10-02："Merge pull request #9 from Shashwat-srivastav/fix-issue7-right-handed-frame"）。
  - 对你的文件意味着什么：主办方的打分器变了。相信本地分数之前先看这次提交；本工具包的 vec_local_score 固定使用 veckit 46d41e6 (0.1.1)。

## 2026-09-30（UTC 17:03 运行）

首次运行：本条记录起点，之后的条目列出相对它的变化。

### 榜契约（https://virtualembryo.ai/challenge/panels/index.json）

- 基线：index.json 中共有 5 个榜。
- T1:val：32285 个基因（T1__val.genes.txt，genes_sha256 807549e15be01989），细胞数 1000-5118，坐标：不需要。
- T2:embryo:val_interp：498 个基因（T2__embryo__val_interp.genes.txt，genes_sha256 f8a2aaa79bf32cfb），细胞数 583-5000，坐标：必须放在 .obsm [spatial_3D]。
- T2:heart:val_extrap：500 个基因（T2__heart__val_extrap.genes.txt，genes_sha256 a9a553108e19acb6），细胞数 1000-25179，坐标：必须放在 .obsm [spatial_3D]。
- T2:heart:val_interp：500 个基因（T2__heart__val_interp.genes.txt，genes_sha256 a9a553108e19acb6），细胞数 1000-17616，坐标：必须放在 .obsm [spatial_3D]。
- T3:gata4：500 个基因（T3__gata4.genes.txt，genes_sha256 a9a553108e19acb6），细胞数 1000-7449，坐标：必须放在 .obsm [spatial_3D]。

### 阶段接口（https://kg.virtualembryo.ai/challenge/phase）

- 基线：阶段 p2（P2 · Baselines released），榜 validation，切分 val，daily_quota 8，accepts_submissions true，nominations_open false。

### 官方打分器（https://github.com/aristoteleo/veckit）

- 基线：aristoteleo/veckit 的 main 分支位于 46d41e6（2026-08-10），版本 0.1.1；标签：无；发布：无；分支：feat/metric-hardening-0.2.0，main。

### 页面

- 已为 27 个页面记录基线。
- 概览页（https://virtualembryo.ai/challenge）：已记录基线，7 个小节。
- 比赛规则（https://virtualembryo.ai/challenge/rules）：已记录基线，20 个小节。
- 使用条款（https://virtualembryo.ai/challenge/terms）：已记录基线，16 个小节。
- 常见问题（FAQ）（https://virtualembryo.ai/challenge/faq）：已记录基线，7 个小节。
- 时间线（https://virtualembryo.ai/challenge/timeline）：已记录基线，1 个小节。
- 奖项（https://virtualembryo.ai/challenge/prizes）：已记录基线，5 个小节。
- 社区贡献奖（https://virtualembryo.ai/challenge/community）：已记录基线，5 个小节。
- 合作发表（https://virtualembryo.ai/challenge/publish）：已记录基线，5 个小节。
- 数据页（https://virtualembryo.ai/challenge/data）：已记录基线，16 个小节。
- 任务总览（https://virtualembryo.ai/challenge/tasks）：已记录基线，5 个小节。
- 任务 1（时间）（https://virtualembryo.ai/challenge/tasks/temporal）：已记录基线，10 个小节。
- 任务 2（时空）（https://virtualembryo.ai/challenge/tasks/spatial）：已记录基线，10 个小节。
- 任务 3（扰动）（https://virtualembryo.ai/challenge/tasks/perturbation）：已记录基线，10 个小节。
- 参考行（基线）（https://virtualembryo.ai/challenge/baselines）：已记录基线，19 个小节。
- 社区资源（https://virtualembryo.ai/challenge/resources）：已记录基线，3 个小节。
- 评测页，任务 1：任务说明（https://virtualembryo.ai/challenge/evaluation?section=task&task=1）：已记录基线，3 个小节。
- 评测页，任务 1：提交（https://virtualembryo.ai/challenge/evaluation?section=submissions&task=1）：已记录基线，7 个小节。
- 评测页，任务 1：打分（https://virtualembryo.ai/challenge/evaluation?section=scoring&task=1）：已记录基线，16 个小节。
- 评测页，任务 1：资源（https://virtualembryo.ai/challenge/evaluation?section=resources&task=1）：已记录基线，3 个小节。
- 评测页，任务 2：任务说明（https://virtualembryo.ai/challenge/evaluation?section=task&task=2）：已记录基线，3 个小节。
- 评测页，任务 2：提交（https://virtualembryo.ai/challenge/evaluation?section=submissions&task=2）：已记录基线，7 个小节。
- 评测页，任务 2：打分（https://virtualembryo.ai/challenge/evaluation?section=scoring&task=2）：已记录基线，20 个小节。
- 评测页，任务 2：资源（https://virtualembryo.ai/challenge/evaluation?section=resources&task=2）：已记录基线，3 个小节。
- 评测页，任务 3：任务说明（https://virtualembryo.ai/challenge/evaluation?section=task&task=3）：已记录基线，3 个小节。
- 评测页，任务 3：提交（https://virtualembryo.ai/challenge/evaluation?section=submissions&task=3）：已记录基线，7 个小节。
- 评测页，任务 3：打分（https://virtualembryo.ai/challenge/evaluation?section=scoring&task=3）：已记录基线，17 个小节。
- 评测页，任务 3：资源（https://virtualembryo.ai/challenge/evaluation?section=resources&task=3）：已记录基线，3 个小节。
