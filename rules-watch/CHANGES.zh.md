# VEC 规则与契约监测：变更记录

最新的在最上面。每次运行发现变化或获取问题就写一条。由 `python -m vec_rules_watch run`（vec-community-kit 的每日 GitHub Action）根据 https://virtualembryo.ai/challenge 的公开页面、榜契约（panels/index.json 和基因列表）、阶段接口以及 GitHub 上主办方的打分器 veckit 生成。引用的行是简短摘录（每条最多 200 个字符），保留英文原文；以主办方页面为准。原理和局限见 vec_rules_watch/README.md。英文版：CHANGES.md。

<!-- entries below, newest first -->

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
