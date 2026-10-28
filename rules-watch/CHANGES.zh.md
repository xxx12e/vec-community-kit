# VEC 规则与契约监测：变更记录

最新的在最上面。每次运行发现变化或获取问题就写一条。由 `python -m vec_rules_watch run`（vec-community-kit 的每日 GitHub Action）根据 https://virtualembryo.ai/challenge 的公开页面、榜契约（panels/index.json 和基因列表）、阶段接口以及 GitHub 上主办方的打分器 veckit 生成。引用的行是简短摘录（每条最多 200 个字符），保留英文原文；以主办方页面为准。原理和局限见 vec_rules_watch/README.md。英文版：CHANGES.md。

<!-- entries below, newest first -->

## 2026-10-28（UTC 13:05 运行）

### 榜契约（https://virtualembryo.ai/challenge/panels/index.json）

- 新增榜 T1:test（T1 · test (E12.5)）：任务 T1，切分 test，32285 个基因（T1__test.genes.txt），细胞数 638-5118，坐标：不需要。
  - 对你的文件意味着什么：T1:test 的文件必须严格使用该榜的基因列表及其顺序（32285 个基因），细胞数在 638 到 5118 之间；坐标：不需要。设置 VEC_PANELS_DIR=rules-watch/contract/panels 即可让工具包的校验器读取新契约。
- 新增榜 T2:embryo:test_interp（T2 embryo · interpolation, test (E7.75)）：任务 T2，切分 test，497 个基因（T2__embryo__test_interp.genes.txt），细胞数 1000-5000，坐标：必须放在 .obsm [spatial_3D]。
  - 对你的文件意味着什么：T2:embryo:test_interp 的文件必须严格使用该榜的基因列表及其顺序（497 个基因），细胞数在 1000 到 5000 之间；坐标：必须放在 .obsm [spatial_3D]。设置 VEC_PANELS_DIR=rules-watch/contract/panels 即可让工具包的校验器读取新契约。
- 新增榜 T2:heart:test_extrap（T2 heart · extrapolation, test (E12.5)）：任务 T2，切分 test，500 个基因（T2__heart__test_extrap.genes.txt），细胞数 1000-34641，坐标：必须放在 .obsm [spatial_3D]。
  - 对你的文件意味着什么：T2:heart:test_extrap 的文件必须严格使用该榜的基因列表及其顺序（500 个基因），细胞数在 1000 到 34641 之间；坐标：必须放在 .obsm [spatial_3D]。设置 VEC_PANELS_DIR=rules-watch/contract/panels 即可让工具包的校验器读取新契约。
- 新增榜 T3:bcatenin（T3 · test (beta-catenin KO)）：任务 T3，切分 test，500 个基因（T3__bcatenin.genes.txt），细胞数 1000-7449，坐标：必须放在 .obsm [spatial_3D]。
  - 对你的文件意味着什么：T3:bcatenin 的文件必须严格使用该榜的基因列表及其顺序（500 个基因），细胞数在 1000 到 7449 之间；坐标：必须放在 .obsm [spatial_3D]。设置 VEC_PANELS_DIR=rules-watch/contract/panels 即可让工具包的校验器读取新契约。

### 阶段接口（https://kg.virtualembryo.ai/challenge/phase）

- 阶段 p2 -> p3（P3 · Final test phase）。
  - 对你的文件意味着什么：比赛进入了新阶段：下次上传前请重读时间线和规则。
- 计分榜 validation -> final。
  - 对你的文件意味着什么：新提交在 final 榜上计分：请核对这些榜的 key 和细胞数范围（见上面的榜契约）。
- daily_quota（每日配额）8 -> 2。
  - 对你的文件意味着什么：请按新配额安排上传。
- 提名已开放：现在可以提名最终参赛作品（nominations_open 为 true）。
- 切分 val -> test。

### 网站链接

- 比赛网站上出现新链接：https://virtualembryo.ai/challenge/panels/T1__test.genes.txt
- 比赛网站上出现新链接：https://virtualembryo.ai/challenge/panels/T2__embryo__test_interp.genes.txt
- 比赛网站上出现新链接：https://virtualembryo.ai/challenge/panels/T2__heart__test_extrap.genes.txt
- 比赛网站上出现新链接：https://virtualembryo.ai/challenge/panels/T3__bcatenin.genes.txt

### 页面

#### 概览页

概览页（https://virtualembryo.ai/challenge）：1 个小节有改动，+0 / -1 行。

- 改动：“（页首）”（+0 / -1 行）

改动的行（英文原文的简短摘录）：

```diff
@@ （页首）
- P2 is open: validation submissions are scored and ranked, and the starter kit and reference baselines are out. Next: P3 opens at 09:00 Los Angeles time; P2 standings freeze on 27 October 2026. F...
```

#### 比赛规则

比赛规则（https://virtualembryo.ai/challenge/rules）：2 个小节有改动，+9 / -4 行。
规则决定什么允许、什么有获奖资格：请到原页面完整阅读改动的小节。

- 改动：“10. Data and What You May Use”（+5 / -3 行）
- 改动：“11. Leaderboard Entries and Final Entries”（+4 / -1 行）

改动的行（英文原文的简短摘录）：

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

#### 常见问题（FAQ）

常见问题（FAQ）（https://virtualembryo.ai/challenge/faq）：1 个小节有改动，+1 / -1 行。
FAQ 里常有对边界情况的裁定：请阅读改动的回答。

- 改动：“Data”（+1 / -1 行）

改动的行（英文原文的简短摘录）：

```diff
@@ Data
- You may train on external data, public or your own, and for Task 1 this is expressly encouraged. What you may not use is measured data from a held-out stage or genotype, by any route: not direct...
+ The official P2 validation files obtained through explicit P3 opt-in may be used for P3 preparation. This exception does not permit hidden test targets or additional external data from protected...
```

#### 数据页

数据页（https://virtualembryo.ai/challenge/data）：5 个小节有改动，+9 / -4 行。
数据页列出阶段、下载和各榜细胞数：请与榜契约对照。

- 改动：“Gene panel, per board”（+5 / -0 行）
- 改动：“How many cells to submit”（+1 / -1 行）
- 改动：“File format (2)”（+1 / -1 行）
- 改动：“File format (3)”（+1 / -1 行）
- 改动：“Access and reproducibility”（+1 / -1 行）

改动的行（英文原文的简短摘录）：

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

## 2026-10-27（UTC 12:20 运行）

### 阶段接口（https://kg.virtualembryo.ai/challenge/phase）

- phase_mode 由 null 改为 auto。
- scheduled_p3_start_at 由 null 改为 2026-10-27T16:00:00Z。

### 页面

#### 概览页

概览页（https://virtualembryo.ai/challenge）：3 个小节有改动，+4 / -4 行。

- 改动：“（页首）”（+1 / -1 行）
- 改动：“Three tasks, one shared atlas”（+1 / -1 行）
- 改动：“Launch → development → final”（+2 / -2 行）

改动的行（英文原文的简短摘录）：

```diff
@@ （页首）
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

#### 常见问题（FAQ）

常见问题（FAQ）（https://virtualembryo.ai/challenge/faq）：1 个小节有改动，+1 / -1 行。
FAQ 里常有对边界情况的裁定：请阅读改动的回答。

- 改动：“Data”（+1 / -1 行）

改动的行（英文原文的简短摘录）：

```diff
@@ Data
- ...Validation and test ground truth are withheld while they can still affect the board, until the final phase a validation submission returns a leaderboard score, not the answers. At the start of t...
+ ...During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
```

#### 时间线

时间线（https://virtualembryo.ai/challenge/timeline）：1 个小节有改动，+3 / -3 行。
日期可能变了：请按新的日程核对你的计划。

- 改动：“Challenge timeline”（+3 / -3 行）

改动的行（英文原文的简短摘录）：

```diff
@@ Challenge timeline
- P3 · Test phase starts, validation data released, test leaderboard opens
+ P3 · P3 opens at 09:00 Los Angeles time; P2 standings freeze
- Test phase starts, validation data released, test leaderboard opens
+ P3 opens at 09:00 Los Angeles time; P2 standings freeze
- The point where the two halves swap. The validation data is released for every task (it can no longer be used to probe the board, because ranking moves to the hidden test split) so validation be...
+ At 09:00 PDT (16:00 UTC), the default leaderboard switches to Test and Frozen P2 preserves results scored before this cutoff. During P3, eligible participants can explicitly request the P2 valid...
```

#### 数据页

数据页（https://virtualembryo.ai/challenge/data）：9 个小节有改动，新增 1 个，+17 / -16 行。
数据页列出阶段、下载和各榜细胞数：请与榜契约对照。

- 改动：“Download”（+1 / -4 行）
- 改动：“Task 1: single-cell RNA”（+1 / -1 行）
- 改动：“File format”（+2 / -2 行）
- 改动：“Task 2: 3D MERFISH (embryo setting)”（+1 / -1 行）
- 改动：“File format (2)”（+2 / -2 行）
- 改动：“Task 2: 3D MERFISH (heart setting)”（+3 / -3 行）
- 改动：“Task 3: conditional knock-outs”（+1 / -1 行）
- 改动：“File format (3)”（+1 / -1 行）
- 改动：“Access and reproducibility”（+2 / -1 行）
- 新增：“Validation answers for P3”（3 行）

改动的行（英文原文的简短摘录）：

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

#### 任务总览

任务总览（https://virtualembryo.ai/challenge/tasks）：2 个小节有改动，+2 / -2 行。
任务说明变了：请检查切分以及输入和输出。

- 改动：“Three tasks, one shared resource”（+1 / -1 行）
- 改动：“Spatial-temporal multiscale prediction”（+1 / -1 行）

改动的行（英文原文的简短摘录）：

```diff
@@ Three tasks, one shared resource
- Ground truth is withheld while it can still affect the board. Until the final phase a validation submission returns a leaderboard score, not the answers. At the start of the final phase the vali...
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
@@ Spatial-temporal multiscale prediction
- ... train, E10.5 extrapolation validation, E12.5 extrapolation test, and in the final phase every heart stage is training input. Embryo, in order: E6.75 train, E7.25 train, E7.5 validation, E7.75 t...
+ ...ion validation, E12.5 extrapolation test, and during P3 the validation stages become training input only after explicit opt-in; E12.5 remains hidden. Embryo, in order: E6.75 train, E7.25 train, ...
```

#### 任务 1（时间）

任务 1（时间）（https://virtualembryo.ai/challenge/tasks/temporal）：1 个小节有改动，+2 / -2 行。
任务说明变了：请检查切分以及输入和输出。

- 改动：“Splits”（+2 / -2 行）

改动的行（英文原文的简短摘录）：

```diff
@@ Splits
- Ground truth is withheld while it can still affect the board. Until the final phase a validation submission returns a leaderboard score, not the answers. At the start of the final phase the vali...
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
- Scored through the leaderboard until the final phase, when the answers are released.
+ Scored through the leaderboard until the final phase, when participants can explicitly request the answers and permanently end their P2 submission eligibility.
```

#### 任务 2（时空）

任务 2（时空）（https://virtualembryo.ai/challenge/tasks/spatial）：1 个小节有改动，+2 / -2 行。
任务说明变了：请检查切分以及输入和输出。

- 改动：“Splits”（+2 / -2 行）

改动的行（英文原文的简短摘录）：

```diff
@@ Splits
- Ground truth is withheld while it can still affect the board. Until the final phase a validation submission returns a leaderboard score, not the answers. At the start of the final phase the vali...
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
- One interpolation target inside the observed range, one extrapolation target beyond it. Scored through the leaderboard until the final phase, when the answers are released.
+ ...ne extrapolation target beyond it. Scored through the leaderboard until the final phase, when participants can explicitly request the answers and permanently end their P2 submission eligibility.
```

#### 任务 3（扰动）

任务 3（扰动）（https://virtualembryo.ai/challenge/tasks/perturbation）：2 个小节有改动，+3 / -3 行。
任务说明变了：请检查切分以及输入和输出。

- 改动：“The question”（+1 / -1 行）
- 改动：“Splits”（+2 / -2 行）

改动的行（英文原文的简短摘录）：

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

#### 评测页，任务 1：任务说明

评测页，任务 1：任务说明（https://virtualembryo.ai/challenge/evaluation?section=task&task=1）：1 个小节有改动，+2 / -2 行。
评测页规定文件契约和指标：请检查你的文件或本地打分是否受影响。

- 改动：“Splits”（+2 / -2 行）

改动的行（英文原文的简短摘录）：

```diff
@@ Splits
- Ground truth is withheld while it can still affect the board. Until the final phase a validation submission returns a leaderboard score, not the answers. At the start of the final phase the vali...
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
- Scored through the leaderboard until the final phase, when the answers are released.
+ Scored through the leaderboard until the final phase, when participants can explicitly request the answers and permanently end their P2 submission eligibility.
```

#### 评测页，任务 2：任务说明

评测页，任务 2：任务说明（https://virtualembryo.ai/challenge/evaluation?section=task&task=2）：1 个小节有改动，+2 / -2 行。
评测页规定文件契约和指标：请检查你的文件或本地打分是否受影响。

- 改动：“Splits”（+2 / -2 行）

改动的行（英文原文的简短摘录）：

```diff
@@ Splits
- Ground truth is withheld while it can still affect the board. Until the final phase a validation submission returns a leaderboard score, not the answers. At the start of the final phase the vali...
+ During P3, eligible participants can explicitly request the P2 validation answers for model development. Receiving access or submitting a first final P3 entry permanently stops further P2 submis...
- One interpolation target inside the observed range, one extrapolation target beyond it. Scored through the leaderboard until the final phase, when the answers are released.
+ ...ne extrapolation target beyond it. Scored through the leaderboard until the final phase, when participants can explicitly request the answers and permanently end their P2 submission eligibility.
```

#### 评测页，任务 3：任务说明

评测页，任务 3：任务说明（https://virtualembryo.ai/challenge/evaluation?section=task&task=3）：2 个小节有改动，+3 / -3 行。
评测页规定文件契约和指标：请检查你的文件或本地打分是否受影响。

- 改动：“Task”（+1 / -1 行）
- 改动：“Splits”（+2 / -2 行）

改动的行（英文原文的简短摘录）：

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

## 2026-10-21（UTC 11:58 运行）

### 网站链接

- 比赛网站上出现新链接：https://virtualembryo.ai/challenge/privacy（尚未列入监测：可能是值得一读的新页面）

### 页面

#### 使用条款

使用条款（https://virtualembryo.ai/challenge/terms）：1 个小节有改动，+1 / -0 行。
使用条款变了：请到原页面阅读改动的小节。

- 改动：“8. Privacy”（+1 / -0 行）

改动的行（英文原文的简短摘录）：

```diff
@@ 8. Privacy
+ Read the Challenge Privacy Policy.
```

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
