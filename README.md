# vec-community-kit

Community tooling for the **Virtual Embryo Challenge** (NeurIPS 2026, https://virtualembryo.ai/challenge): a
board-contract validator, the official floor rows as submission-file generators, a local scoring wrapper around the
organisers' scorer, an Agent-track evidence skeleton, and a step-by-step tutorial from registration to a first
submission on every board. Everything is generic: the kit contains no modelling ideas, only the plumbing every team
needs. MIT licensed.

| package / doc | what it does |
|---|---|
| `vec_submit_check/` | `python -m vec_submit_check --board T2:heart:val_interp pred.h5ad` - validates a file against a board contract (gene panel and order, cell bounds, finite / non-negative / float32 values, coordinates, size cap); also generic numeric guards |
| `vec_baselines/` | `copy_last`, `wt_identity`, `pseudobulk_shift` as board-valid files, and `write_submission` - a safe writer (panel order, float32, clipping, coordinates, validation on write, explicit `n_cells`) |
| `vec_local_score/` | the official protocol (10 % subsample, split-half ceiling, floor rows, skill map, task weights) on a pseudo split you build from released stages, running the organisers' **veckit** (not vendored: `pip install` it or set `VECKIT_PATH`); a seed summary and a split builder |
| `vec_agent_evidence/` | Agent track: configuration lock (hashes prompt, settings, model, tool policy, data files), PreToolUse guard hook and audit hook, launcher, post-run evidence collector (transcript by session id, secret scan, size caps), upload packager (trajectory / prompts / harness zips), a minimal example prompt |
| `data/panels/` | copies of the public board contracts (`index.json` + one gene list per board) |
| `docs/tutorial_en.md`, `docs/tutorial_zh.md` | "from zero to a first submission" for both tracks (English / Chinese) |
| `docs/metrics_overview.md` | what each metric measures, its direction, and the floor / ceiling convention |
| `tests/` | synthetic tests for everything (no challenge data needed); the scorer test is skipped without veckit |

## Quick start

```
pip install -r requirements.txt
python -m pytest -q

# a valid floor file for one board, then validate it
python -m vec_baselines.make_baseline --method wt_identity --board T3:gata4 --wt data/raw/T2_heart/E8.75.h5ad --out out/t3.h5ad --n-cells all
python -m vec_submit_check --board T3:gata4 out/t3.h5ad

# local pseudo-validation with the organisers' scorer (pip install git+https://github.com/aristoteleo/veckit.git)
python -m vec_local_score --task T2 --setting heart --pred out/pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad

# Agent track: lock -> run -> collect evidence -> package
python -m vec_agent_evidence run --task T3 --prompt vec_agent_evidence/example_prompt.md --model <model-id> --data-root ./data --hours 8
python -m vec_agent_evidence package --run-dir runs/<run_id>
```

Requirements: Python 3.10+, anndata, numpy, scipy, pandas (see `requirements.txt`); veckit additionally needs
scikit-learn. Windows and POSIX. Source files are ASCII-only; the docs are in English and Chinese.

## What this kit is not

It does not download data (sign-in required; register yourself), it does not vendor the organisers' scorer, and it
does not tell you how to model anything. The floor rows exist to prove the pipeline with a known outcome. Local
scores are a ranking instrument for your own methods, never a preview of the hidden target.

---

## 中文简介

面向 **Virtual Embryo Challenge**（NeurIPS 2026，https://virtualembryo.ai/challenge）的社区工具包：榜契约校验器、官方地板行
的提交文件生成器、主办方打分器 veckit 的本地封装、Agent 赛道的证据骨架，以及一份"从零到第一次提交"的中英文教程。
全部是通用工具，不含任何建模思路。MIT 许可。

* `vec_submit_check/`：`python -m vec_submit_check --board <榜> pred.h5ad` 校验基因面板与顺序、细胞数范围、数值有限/非负/
  float32、坐标、文件大小。
* `vec_baselines/`：`copy_last`、`wt_identity`、`pseudobulk_shift` 生成合格文件；`write_submission` 是安全写入器（面板顺序、
  float32、负值截断、坐标、写后校验、显式 `n_cells`）。
* `vec_local_score/`：在你自己用已发布阶段构造的伪验证切分上复现官方流程（10% 抽样、对半天花板、地板行、skill 映射、任务
  权重），调用主办方的 veckit（不内置，`pip install` 或设置 `VECKIT_PATH`）；含多种子汇总和切分构造器。
* `vec_agent_evidence/`：Agent 赛道的配置锁定（哈希提示词、设置、模型、工具策略、数据文件）、PreToolUse 守卫 hook 与审计
  hook、启动器、运行后证据收集（按 session id 复制会话记录、凭据扫描、大小上限）、上传打包器（trajectory / prompts /
  harness 三个 zip），以及一份只解释工作区约定的示例提示词。
* `docs/tutorial_zh.md`：注册、下载数据、读懂每个榜的契约（细胞、基因、坐标）、生成地板文件、校验、本地打分、上传，以及
  Agent 赛道需要哪些证据和怎么用工具包产出。`docs/metrics_overview.md`：每个指标度量什么。

安装：`pip install -r requirements.txt`，然后 `python -m pytest -q`（合成数据测试，不需要比赛数据）。
