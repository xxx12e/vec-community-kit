# vec-community-kit

Community tooling for the **Virtual Embryo Challenge** (NeurIPS 2026, https://virtualembryo.ai/challenge). Five
parts: a board-contract validator, baseline generators with a submission writer, a local scoring wrapper around
the organisers' scorer veckit, an Agent-track evidence skeleton, and a bilingual step-by-step tutorial from
registration to a first submission on every board. Everything is generic plumbing: the kit contains no modelling
ideas. MIT licensed.

Who it is for: first-time entrants of either track who want a valid file on every board without a round of
portal rejections; teams who want a reproducible local ranking of their own methods before spending scored
submissions; Agent-track teams who need the configuration lock and the evidence package the rules require.

The organisers publish the board contracts (`panels/index.json` + gene lists), the baseline definitions, the scorer
veckit and the portal's own format check. What each part here adds beyond those is stated below.

## The five parts

### 1. [`vec_submit_check/`](vec_submit_check/) - local pre-upload checks

`python -m vec_submit_check --board T2:heart:val_interp pred.h5ad` checks a file against the published board
contract: gene panel and order, cell bounds, finite / non-negative / float32 values (non-negative on every board),
coordinates, size cap; also generic numeric guards (`guards.py`). Exit codes and a `--json` report for scripts.

*Adds:* the same contract check on your machine, offline and without the hidden data, so a broken file is caught
before it goes through an upload-and-debug round trip (the portal's validator has the final say; a rejected upload
does not consume a scored attempt, but it costs the round trip).

*Example output:* `[PASS] out/heart_interp_copy_last.h5ad @ T2:heart:val_interp  n_obs=5000 n_vars=500` followed by
sha256, size, value range and coordinate radius.

### 2. [`vec_baselines/`](vec_baselines/) - baseline generators and submission writer

`copy_last`, `wt_identity` (the organisers' floor rows) and `pseudobulk_shift` (a baseline, not a floor row) as
board-valid files, plus `write_submission`: panel order by gene name, float32, clipping, coordinates, validation
on write, and an **explicit, required** cell count (`n_cells` = an int inside the board bounds or `"all"`).

*Adds:* one command from a released stage to a valid file for any board, with the cell count stated rather than
guessed (the released stages exceed most boards' `max_cells`, so `all` errors with the bound and you pass a
number); a writer your own model can use so that its output is validated before it leaves your machine.

*Example output:* `[PASS] out/t3_wt_identity.h5ad @ T3:gata4  n_obs=5000 n_vars=500 X=dense[float32] min=0.0 max=10.2 size=10.1MB`

### 3. [`vec_local_score/`](vec_local_score/) - the veckit scorer's protocol on data you hold

Follows the veckit scorer's protocol as of veckit 0.1.1 - 10 % subsample, split-half ceiling, floor row, skill
scale - on a pseudo split built from **raw released stages** (hold one out, predict it from the others), running
the organisers' veckit in-process; a multi-seed summary (`seed_summary`) and an optional split exporter for the
veckit CLI (`make_pseudo_split`). veckit is not vendored: `pip install` it or set `VECKIT_PATH`.

*Adds:* veckit alone scores one file against one target file and prints raw metrics; the wrapper adds the
protocol around it (subsample, split-half ceiling, floor row, veckit's `skill()`, the published task weights) and
mean +- sd over seeds, so two of your methods can be ranked on the 0-100 scale locally. Not a preview of the real
score. Tested against **veckit 0.1.1** (commit `46d41e6`); the organisers' scorer is the source of truth and the
wrapper may lag it - every result records the veckit version and file hashes that ran.

*Example output (synthetic heart pair, `copy_last` as the prediction):*
`pseudo_pred.h5ad on E8.75.h5ad: 53.11 +- 3.54 (seeds [0, 1, 2, 3, 4])` above a per-metric table.

### 4. [`vec_agent_evidence/`](vec_agent_evidence/) - Agent-track evidence skeleton

Configuration lock (hashes prompt, settings, model, tool policy, data files, CLI binary), a PreToolUse guard hook
and an audit hook, launcher with wall-clock enforcement, post-run evidence collector (transcript by session id,
secret scan, size caps) and upload packager (trajectory / prompts / harness zips). Targets the Claude Code CLI
(`claude -p --output-format stream-json`); another CLI needs `launch.build_command` adapted. The hooks are regex
hooks that reject recognised network commands and restricted file operations, not a network sandbox; the audit log
and the recorded hashes support post-run verification.

*Adds:* the organisers publish the evidence rules but no tooling for them; this makes lock -> run -> evidence ->
upload package mechanical and refuses to package a run whose lock was broken, whose evidence carries a
credential-shaped string, or whose file was edited.

*Test line:* `python -m pytest tests/test_evidence.py -q` -> `8 passed` (a stand-in agent, no CLI, no API calls).

### 5. [`docs/tutorial_en.md`](docs/tutorial_en.md) / [`docs/tutorial_zh.md`](docs/tutorial_zh.md) - from zero to a first submission

Registration, data download, every board's contract, the first baseline file, validation, local scoring, upload,
and the Agent track's evidence - in English and Chinese, with a prerequisites table saying which sections need
only `requirements.txt`, which need veckit, and which need the Claude Code CLI. [`docs/metrics_overview.md`](docs/metrics_overview.md)
explains what each metric measures.

*Adds:* the complete walkthrough for both tracks in one place, with every command executed as written against
synthetic stages laid out like the real data directory (the cell-count bound is stated next to each command).

*Test line:* `python -m pytest -q` -> `41 passed` (synthetic data; the scorer tests are skipped without veckit).

## Quick start

```
pip install -r requirements.txt
python -m pytest -q

# a valid baseline file for one board (T3:gata4 allows 1000-7449 cells), then validate it
python -m vec_baselines.make_baseline --method wt_identity --board T3:gata4 --wt data/raw/T2_heart/E8.75.h5ad --out out/t3.h5ad --n-cells 5000
python -m vec_submit_check --board T3:gata4 out/t3.h5ad

# local pseudo-validation with the organisers' scorer (pip install git+https://github.com/aristoteleo/veckit.git):
# hold out E8.75, predict it with a copy_last file built from E8.25, score on the raw stages
python -m vec_baselines.make_baseline --method copy_last --board T2:heart:val_interp --last data/raw/T2_heart/E8.25_late.h5ad --out out/pred.h5ad --n-cells 5000
python -m vec_local_score --task T2 --setting heart --pred out/pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad

# Agent track: lock -> run -> collect evidence -> package (needs the Claude Code CLI installed and logged in)
python -m vec_agent_evidence run --task T3 --prompt vec_agent_evidence/example_prompt.md --model <model-id> --data-root ./data --hours 8
python -m vec_agent_evidence package --run-dir runs/<run_id>
```

Requirements: Python 3.10+, anndata, numpy, scipy, pandas, h5py (see `requirements.txt`); veckit additionally
needs scikit-learn; the Agent skeleton additionally needs the Claude Code CLI. Windows and POSIX. Source files are
ASCII-only; the docs are in English and Chinese. `data/panels/` holds copies of the public board contracts.

## What this kit is not

It does not download data (sign-in required; register yourself), it does not vendor the organisers' scorer, and it
does not tell you how to model anything. The baseline files exist to prove the pipeline with a known reference
point (a resampled floor row lands near the published floor, not exactly on it). Local scores are a ranking
instrument for your own methods, never a preview of the hidden target.

---

## 中文简介

面向 **Virtual Embryo Challenge**（NeurIPS 2026，https://virtualembryo.ai/challenge）的社区工具包，五个部分：榜契约校验器、
基线生成器与提交文件写入器、主办方打分器 veckit 的本地封装、Agent 赛道的证据骨架，以及一份"从零到第一次提交"的中英文教程。
全部是通用工具，不含任何建模思路。MIT 许可。面向两个赛道的首次参赛者、想在花掉计分提交前先在本地给自己的方法排序的队伍，
以及需要配置锁定和证据包的 Agent 赛道队伍。

* [`vec_submit_check/`](vec_submit_check/)：`python -m vec_submit_check --board <榜> pred.h5ad` 对照已公布的榜契约做本地上传前
  检查（基因面板与顺序、细胞数范围、数值有限/非负（每个榜）/float32、坐标、文件大小）。比主办方多出来的：在本地、离线、不需要
  隐藏数据就能查，少一轮"上传-排错"往返。示例输出：`[PASS] out/heart_interp_copy_last.h5ad @ T2:heart:val_interp  n_obs=5000 n_vars=500`。
* [`vec_baselines/`](vec_baselines/)：`copy_last`、`wt_identity`（主办方的地板行）、`pseudobulk_shift`（基线，不是地板行）生成合格文件；
  `write_submission` 是写入器（按基因名映射面板顺序、float32、负值截断、坐标、写后校验），细胞数**显式且必填**（范围内的整数或
  `"all"`）。比主办方多出来的：一条命令从发布阶段得到任意榜的合格文件，细胞数明说而不是猜；你自己的模型输出也能用它写。
  示例输出：`[PASS] out/t3_wt_identity.h5ad @ T3:gata4  n_obs=5000 n_vars=500 ...`。
* [`vec_local_score/`](vec_local_score/)：遵循 veckit 打分器截至 0.1.1 版的流程（10% 抽样、对半天花板、地板行、skill 尺度）在你用
  **原始发布阶段**构造的伪切分上打分，调用主办方的 veckit（不内置，`pip install` 或设置 `VECKIT_PATH`）；含多种子汇总。比主办方多出来的：
  veckit 本身只对一个目标文件打出原始指标，封装补上了抽样、对半天花板、地板行、veckit 自己的 `skill()` 和公布的任务权重，以及多种子
  的均值 +- 标准差。不是真实分数的预告；在 veckit 0.1.1 上测试过，主办方的打分器才是最终依据，封装可能滞后。
  示例输出：`pseudo_pred.h5ad on E8.75.h5ad: 53.11 +- 3.54 (seeds [0, 1, 2, 3, 4])`。
* [`vec_agent_evidence/`](vec_agent_evidence/)：Agent 赛道的配置锁定（哈希提示词、设置、模型、工具策略、数据文件、CLI 二进制）、PreToolUse
  守卫 hook 与审计 hook、启动器、运行后证据收集（按 session id 复制会话记录、凭据扫描、大小上限）、上传打包器（trajectory / prompts /
  harness 三个 zip）。面向 Claude Code CLI（`claude -p --output-format stream-json`），换 CLI 需改 `launch.build_command`。hook 是正则
  hook（拒绝能识别出的网络命令和受限文件操作），不是网络沙箱；审计日志和哈希用于运行后核验。比主办方多出来的：规则只说了要什么证据，
  没有工具；这里把锁定 -> 运行 -> 证据 -> 上传包变成机械步骤。测试行：`python -m pytest tests/test_evidence.py -q` -> `8 passed`。
* [`docs/tutorial_zh.md`](docs/tutorial_zh.md) / [`docs/tutorial_en.md`](docs/tutorial_en.md)：注册、下载数据、读懂每个榜的契约、生成第一份
  基线文件、校验、本地打分、上传、Agent 赛道的证据；开头有一张表说明哪些章节只需要 `requirements.txt`、哪些还需要 veckit、哪些需要
  Claude Code CLI。每条命令都在按真实目录布局摆放的合成数据上原样执行过，细胞数范围写在命令旁边。
  [`docs/metrics_overview.md`](docs/metrics_overview.md)：每个指标度量什么。测试行：`python -m pytest -q` -> `41 passed`。

安装：`pip install -r requirements.txt`，然后 `python -m pytest -q`（合成数据测试，不需要比赛数据；没有 veckit 时打分器测试被跳过）。
