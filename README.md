# vec-community-kit

Community tooling for the **Virtual Embryo Challenge** (NeurIPS 2026, https://virtualembryo.ai/challenge). Five
parts: a board-contract validator, baseline generators with a submission writer, a local scoring wrapper around
the organisers' scorer veckit, an Agent-track evidence skeleton, and a bilingual step-by-step tutorial from
registration to a first submission on every board. Everything is generic plumbing: the kit contains no modelling
ideas. MIT licensed.

Who it is for: first-time entrants of either track who want a validated first file on each public board before
their first upload; teams who want to compare their own methods on a pseudo split built from released stages (a
comparison on that split, not a prediction of the hidden-target ranking); Agent-track teams who need the
configuration lock and the evidence package the rules describe.

The organisers publish the board contracts (`panels/index.json` + gene lists), the baseline definitions, the scorer
veckit, a local validator/scorer in the starter kit (`score_h5ad.py`) and the portal's own format check. What each
part here adds beyond those is stated below; official sources are cited with the date they were read.

## The five parts

### 1. [`vec_submit_check/`](vec_submit_check/) - local pre-upload checks

`python -m vec_submit_check --board T2:heart:val_interp pred.h5ad` checks a file against the published board
contract: gene panel and order, cell bounds, finite / non-negative / float32-castable values, coordinates
(`(n, >=3)`, first three columns read), size cap; also generic numeric guards (`guards.py`). Each rule is labelled
**portal** (the portal rejects on it), **stricter** (`max_cells` from `panels/index.json`, which the evaluation
pages contradict with "no cap"; an error unless `--ignore-max-cells`) or **advisory** (raw-count-looking values,
labels present) in [`vec_submit_check/README.md`](vec_submit_check/README.md). Exit codes and a `--json` report.

*Adds:* the contract check in a dependency-light tool (anndata, numpy, scipy; no scorer, no target data) with the
first failing rule in plain words, and warnings for what the portal's validation does not catch (a raw-count file
passes validation and is then scored wrongly). The starter kit's `score_h5ad.py` also validates locally; the
portal's validator has the final say and a rejected upload does not consume a scored attempt.

*Example output:* `[PASS] out/heart_interp_copy_last.h5ad @ T2:heart:val_interp  n_obs=5000 n_vars=500`, then
`PASS = local format checks passed; it does not confirm log-normalisation, data provenance or eligibility`, then
sha256, size, value range and coordinate radius.

### 2. [`vec_community_baselines/`](vec_community_baselines/) - baseline generators and submission writer

**Renamed on 2026-09-30** from `vec_baselines`, at the organisers' request: `vec_baselines` is the name of their
official baselines package, and the two must be installable side by side. No alias or shim is kept. Update imports
to `from vec_community_baselines import io as bio, methods as bm` and commands to
`python -m vec_community_baselines.make_baseline ...`; in an existing clone, delete any leftover `vec_baselines/`
directory after pulling (git leaves the untracked `__pycache__/` behind, and Python would still import that
directory as an empty namespace package).

Implements the published baseline recipes - `copy_last` and `wt_identity` (the floor definitions on the
reference-rows page) and `pseudobulk_shift` (a baseline, not a floor row) - as validated submission files, plus
`write_submission`: panel order by gene name, float32, clipping, coordinates, validation on write, and an
**explicit, required** cell count (`n_cells` = an int inside the board bounds or `"all"`). Reconstructed from the
published definitions; not numerically aligned with the organisers' reference rows.

*Adds:* one command from a compatible released stage to a validated file on each supported board (coverage table,
board x method x input x result, in [`vec_community_baselines/README.md`](vec_community_baselines/README.md)), with the cell count
stated rather than guessed (the released stages exceed most boards' `max_cells` in `panels/index.json`, so `all`
errors with the bound unless `--allow-over-max`); a writer your own model can use so that its output is validated
before it leaves your machine. Validation is format only: it cannot tell log-normalised values from counts that
merely look plausible.

*Example output:* `[PASS] out/t3_wt_identity.h5ad @ T3:gata4  n_obs=5000 n_vars=500 X=dense[float32] min=0.0 max=10.2 size=10.1MB`

### 3. [`vec_local_score/`](vec_local_score/) - the veckit scorer's protocol on data you hold

Follows the veckit scorer's protocol as of veckit 0.1.1 - 10 % subsample, split-half ceiling, floor row, skill
scale - on a pseudo split built from **raw released stages** (hold one out, predict it from the others), running
the organisers' veckit in-process; a multi-seed summary (`seed_summary`) and an optional split exporter for the
veckit CLI (`make_pseudo_split`). veckit is not vendored: `pip install` it or set `VECKIT_PATH`.

*Adds:* veckit alone scores one file against one target file and prints raw metrics; the wrapper adds the
protocol around it (subsample, split-half ceiling, floor row, veckit's `skill()`, the published task weights) and
mean +- sd over seeds, so two of your methods can be compared on the 0-100 scale on the pseudo split you built.
That comparison holds for that split only: it is not a preview of the real score and not a prediction of the
hidden-target ranking. Tested against **veckit 0.1.1** (commit `46d41e6`; install that commit, see below); the
organisers' scorer is the source of truth and the wrapper may lag it - every result records the veckit version
and file hashes that ran.

*Example output (synthetic heart pair, `copy_last` as the prediction):*
`pseudo_pred.h5ad on E8.75.h5ad: 53.11 +- 3.54 (seeds [0, 1, 2, 3, 4])` above a per-metric table.

### 4. [`vec_agent_evidence/`](vec_agent_evidence/) - Agent-track evidence skeleton

Configuration lock (hashes prompt, settings, model, tool policy, data files, CLI binary), a PreToolUse guard hook
and an audit hook, launcher with wall-clock enforcement, post-run evidence collector (transcript by session id,
secret scan, size caps) and upload packager (trajectory / prompts / harness zips). Targets the Claude Code CLI
(`claude -p --output-format stream-json`); another CLI needs `launch.build_command` adapted. The hooks are regex
hooks that reject recognised network commands and restricted file operations, not a network sandbox; the audit log
and the recorded hashes support post-run verification.

*Adds:* lock -> run -> evidence -> upload package as one mechanical path, refusing to package a run whose lock
hashes changed, whose evidence carries a credential-shaped string, or whose prediction bytes differ from the
finalized ones. What comes out is an auditable evidence bundle (configuration snapshots, integrity checks,
best-effort guard hooks, audit log); it does not independently attest compliance with the rules, and it cannot
know what your team uploaded before (`package --team-uploaded-mb` keeps the 600 MB team total in view).

*Test line:* `python -m pytest tests/test_evidence.py -q` -> `8 passed` (a stand-in agent, no CLI, no API calls).

### 5. [`docs/tutorial_en.md`](docs/tutorial_en.md) / [`docs/tutorial_zh.md`](docs/tutorial_zh.md) - from zero to a first submission

Registration, data download, every board's contract, the first baseline file, validation, local scoring, upload,
and the Agent track's evidence - in English and Chinese, with a prerequisites table saying which sections need
only `requirements.txt`, which need veckit, and which need the Claude Code CLI. [`docs/metrics_overview.md`](docs/metrics_overview.md)
explains what each metric measures.

*Adds:* the complete walkthrough for both tracks in one place; the commands were executed against synthetic
stages laid out like the real data directory (2026-09-05; log and environment in `scratchpad/dryrun_log.txt`), not
against the real release inside this repository; the cell-count bound is stated next to each command.

*Test line:* `python -m pytest -q` -> `41 passed` (synthetic data; the scorer tests are skipped without veckit).

## Install

```
git clone https://github.com/xxx12e/vec-community-kit && cd vec-community-kit
pip install -e ".[test]"          # the kit, its dependencies and pytest (editable: the Agent skeleton records the git commit)
python -m pytest -q               # synthetic data only
```

`pip install -e .` (or `pip install .`, or `pip install "git+https://github.com/xxx12e/vec-community-kit"`) installs the
four packages - `vec_submit_check`, `vec_community_baselines`, `vec_local_score`, `vec_agent_evidence` - and five
commands, each the same as its `python -m` form:

| command | same as |
|---|---|
| `vec-community-check` | `python -m vec_submit_check` |
| `vec-community-baseline` | `python -m vec_community_baselines.make_baseline` |
| `vec-community-score` | `python -m vec_local_score` |
| `vec-community-split` | `python -m vec_local_score.make_pseudo_split` |
| `vec-community-evidence` | `python -m vec_agent_evidence` |

The command names carry a `vec-community-` prefix so they cannot collide with the organisers' tools or other community
packages. An installed copy carries the board contracts inside the validator package (`vec_submit_check/panels/`), so
it works from any directory; `VEC_PANELS_DIR` still overrides them. Extras: `.[test]` adds pytest, `.[score]` adds the
organisers' scorer veckit pinned to the tested commit (needs git). `pip install -r requirements.txt` still works for
people who run the tools from a clone without installing it; the two dependency lists are kept identical (a test
checks it).

## Quick start

```

# a valid baseline file for one board (T3:gata4 allows 1000-7449 cells), then validate it
python -m vec_community_baselines.make_baseline --method wt_identity --board T3:gata4 --wt data/raw/T2_heart/E8.75.h5ad --out out/t3.h5ad --n-cells 5000
python -m vec_submit_check --board T3:gata4 out/t3.h5ad

# local pseudo-validation with the organisers' scorer, pinned to the tested commit:
#   pip install "git+https://github.com/aristoteleo/veckit.git@46d41e63f42a9aab815db20b742feeccd249cb17"
# hold out E8.75 (the pseudo target: it must not be used to build the prediction), predict it with a copy_last file
# built from E8.25 only, score on the raw stages
python -m vec_community_baselines.make_baseline --method copy_last --board T2:heart:val_interp --last data/raw/T2_heart/E8.25_late.h5ad --out out/pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad

# Agent track: lock -> run -> collect evidence -> package (needs the Claude Code CLI installed and logged in)
python -m vec_agent_evidence run --task T3 --prompt vec_agent_evidence/example_prompt.md --model <model-id> --data-root ./data --hours 8
python -m vec_agent_evidence package --run-dir runs/<run_id>
```

Requirements: Python 3.10+, anndata, numpy, scipy, pandas, h5py (`pyproject.toml` / `requirements.txt`); veckit additionally
needs scikit-learn; the Agent skeleton additionally needs the Claude Code CLI. Windows and POSIX. Source files are
ASCII-only; the docs are in English and Chinese. `data/panels/` holds copies of the public board contracts.

## What this kit is not

It does not download data (sign-in required; register yourself), it does not vendor the organisers' scorer, and it
does not tell you how to model anything. The baseline files exist to prove the pipeline with a known reference
point (a resampled floor row lands near the published floor, not exactly on it). Local scores compare your
own methods on the pseudo split you chose; they are neither a preview of the hidden target nor a prediction of the
leaderboard order.

---

## 中文简介

面向 **Virtual Embryo Challenge**（NeurIPS 2026，https://virtualembryo.ai/challenge）的社区工具包，五个部分：榜契约校验器、
基线生成器与提交文件写入器、主办方打分器 veckit 的本地封装、Agent 赛道的证据骨架，以及一份"从零到第一次提交"的中英文教程。
全部是通用工具，不含任何建模思路。MIT 许可。面向两个赛道的首次参赛者、想在自己构造的伪切分上比较自己几种方法的队伍（只是该切分上的比较，
不预测隐藏目标上的名次），以及需要配置锁定和证据包的 Agent 赛道队伍。

* [`vec_submit_check/`](vec_submit_check/)：`python -m vec_submit_check --board <榜> pred.h5ad` 对照已公布的榜契约做本地上传前
  检查（基因面板与顺序、细胞数范围、数值有限/非负/可转 float32、坐标、文件大小）；每条规则标明是 portal（门户会拒）、stricter（`index.json`
  的 `max_cells`，评测页却写"无上限"，默认报错，`--ignore-max-cells` 降为警告）还是 advisory（疑似原始计数、带标签）。比主办方多出来的：
  轻依赖（不装打分器、不需要目标数据）、第一条失败规则说人话、对门户校验查不出来的问题给警告（原始计数文件能过校验但会被打错分）。
  PASS 只表示本地格式检查通过，不代表归一化正确、数据来源合规或参赛资格。示例输出：`[PASS] out/heart_interp_copy_last.h5ad @ T2:heart:val_interp  n_obs=5000 n_vars=500`。
* [`vec_community_baselines/`](vec_community_baselines/)（2026-09-30 应主办方要求由 `vec_baselines` 改名：`vec_baselines`
  是主办方官方基线包的名字，两者要能同时安装；不保留别名。已有克隆在拉取后请删掉残留的 `vec_baselines/` 目录，其中未跟踪的
  `__pycache__/` 会让 Python 仍把它当作空的命名空间包导入）：`copy_last`、`wt_identity`（主办方的地板行）、`pseudobulk_shift`（基线，不是地板行）生成合格文件；
  `write_submission` 是写入器（按基因名映射面板顺序、float32、负值截断、坐标、写后校验），细胞数**显式且必填**（范围内的整数或
  `"all"`）。按公布的基线定义重新实现，没有与主办方的参考行做数值对齐。比主办方多出来的：一条命令从兼容的发布阶段得到所支持各榜的已校验文件
  （覆盖表见 `vec_community_baselines/README.md`），细胞数明说而不是猜；你自己的模型输出也能用它写。校验只管格式，分不清对数归一化和看起来像样的计数。
  示例输出：`[PASS] out/t3_wt_identity.h5ad @ T3:gata4  n_obs=5000 n_vars=500 ...`。
* [`vec_local_score/`](vec_local_score/)：遵循 veckit 打分器截至 0.1.1 版的流程（10% 抽样、对半天花板、地板行、skill 尺度）在你用
  **原始发布阶段**构造的伪切分上打分，调用主办方的 veckit（不内置，`pip install` 或设置 `VECKIT_PATH`）；含多种子汇总。比主办方多出来的：
  veckit 本身只对一个目标文件打出原始指标，封装补上了抽样、对半天花板、地板行、veckit 自己的 `skill()` 和公布的任务权重，以及多种子
  的均值 +- 标准差。只是你所选伪切分上的比较：不是真实分数的预告，也不预测隐藏目标上的名次；在 veckit 0.1.1（commit `46d41e6`，请安装该
  commit）上测试过，主办方的打分器才是最终依据，封装可能滞后。
  示例输出：`pseudo_pred.h5ad on E8.75.h5ad: 53.11 +- 3.54 (seeds [0, 1, 2, 3, 4])`。
* [`vec_agent_evidence/`](vec_agent_evidence/)：Agent 赛道的配置锁定（哈希提示词、设置、模型、工具策略、数据文件、CLI 二进制）、PreToolUse
  守卫 hook 与审计 hook、启动器、运行后证据收集（按 session id 复制会话记录、凭据扫描、大小上限）、上传打包器（trajectory / prompts /
  harness 三个 zip）。面向 Claude Code CLI（`claude -p --output-format stream-json`），换 CLI 需改 `launch.build_command`。hook 是正则
  hook（拒绝能识别出的网络命令和受限文件操作），不是网络沙箱；审计日志和哈希用于运行后核验。比主办方多出来的：把锁定 -> 运行 -> 证据 ->
  上传包变成一条机械路径，锁定哈希变了、证据里有凭据形状的字符串、预测文件字节被改过都拒绝打包。产出的是可审计的证据包（配置快照、
  完整性校验、尽力而为的守卫 hook、审计日志），不能独立证明合规；它也不知道你们队之前传了多少（`package --team-uploaded-mb` 帮你盯住
  600 MB 总额）。测试行：`python -m pytest tests/test_evidence.py -q` -> `8 passed`。
* [`docs/tutorial_zh.md`](docs/tutorial_zh.md) / [`docs/tutorial_en.md`](docs/tutorial_en.md)：注册、下载数据、读懂每个榜的契约、生成第一份
  基线文件、校验、本地打分、上传、Agent 赛道的证据；开头有一张表说明哪些章节只需要 `requirements.txt`、哪些还需要 veckit、哪些需要
  Claude Code CLI。命令在按真实目录布局摆放的合成数据上执行过（2026-09-05，日志和环境见 `scratchpad/dryrun_log.txt`），没有在真实发布数据上跑过；
  细胞数范围写在命令旁边。
  [`docs/metrics_overview.md`](docs/metrics_overview.md)：每个指标度量什么。测试行：`python -m pytest -q` -> `41 passed`。

安装：`pip install -e ".[test]"`（工具包本身、依赖和 pytest；另有 `vec-community-check` / `-baseline` / `-score` / `-split` / `-evidence`
五个命令，与对应的 `python -m` 用法相同；`.[score]` 额外安装固定到已测试 commit 的 veckit），或只装依赖 `pip install -r requirements.txt`；
然后 `python -m pytest -q`（合成数据测试，不需要比赛数据；没有 veckit 时打分器测试被跳过）。安装后的副本把榜契约放在
`vec_submit_check/panels/` 里，在任何目录下都能用。
