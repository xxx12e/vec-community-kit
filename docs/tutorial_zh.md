# 从零到第一次提交 —— Virtual Embryo Challenge（NeurIPS 2026）

这份教程带一个新手从注册走到"每个榜都有一份被打分的提交"，两个赛道都覆盖，全程使用本工具包。下文所有关于比赛的
事实都来自官方站点（https://virtualembryo.ai/challenge）；如有出入，以官方为准。工具包本身只是通用工具：格式校验器、
基线生成器与提交文件写入器、主办方打分器的本地封装、Agent 赛道的证据骨架。它不包含任何建模建议。

下面每一条命令都在一组按第 2 节目录布局摆放的小型合成数据上原样执行过；你唯一要换的是把真实文件放到同样的位置。

## 0. 一页看懂比赛

* 主办：Qiu Lab（Stanford）及合作机构；NeurIPS 2026 官方竞赛。数据：约一百万个小鼠胚胎细胞，11 个发育阶段
  （E6.75 到 E12.5），以心脏为中心。
* 三个任务、五个公开榜（board）：
  * **T1** 单细胞 RNA-seq（32,285 个基因，无坐标）：由早期阶段预测更晚阶段。
  * **T2** 3D MERFISH（500 基因面板，带坐标）：全胚胎设定（插值）和心脏设定（插值榜 + 外推榜）。
  * **T3** 条件敲除（与 T2 同构，多一个 condition 列）：由训练用敲除和匹配野生型预测一个未见过的敲除。
* 两个赛道在同一套隐藏测试集上打分，排名和奖金池分开：**Human Team** 和 **Agent Team**。Agent 赛道多一条要求：
  配置锁定（configuration lock）之后全自主，并用证据证明。
* 每个赛道奖金：1 x 8K、2 x 5K、3 x 3K 美元；另有旅行奖；以及 Community Contribution Award（每项贡献最多 200 美元，
  最多 100 项，滚动评审至 2026-12-11），奖励帮助他人参赛的工作 —— 本工具包就是这一类。
* 时间线：2026-08-10 提交门户和验证阶段上线；2026-10-20 进入测试阶段（验证集答案公布并成为训练数据，测试输入不带标签
  发布）；2026-12-02 最终提交截止；2026-12-11 NeurIPS 现场公布获奖者。获奖者需在 14 天内提交书面方法报告，代码可能被要求
  用于核验（不公开）。
* 提交配额：验证阶段每任务每天 20 次（之后 8 次）计分提交；测试阶段每个榜整个阶段只有 2 次正式提交，分数立即公开，不可撤回。
  格式检查不限次数、不消耗配额。
* 排名：取团队在每个榜上的最好成绩；任务分 = 该任务各榜的平均；总分 = T1 + T2 + T3（每项最高 100）。从未被打分的榜按 0 计，
  所以先给每个榜提交一份合格文件。

## 1. 注册

1. 打开 https://virtualembryo.ai/challenge/submit ，用 GitHub 或 Google 登录（比赛站点有独立账号体系，必须本人注册）。
2. 创建或加入队伍。一人一个账号、一人只能在一个队、含队长最多 10 人、队长年满 18 岁、所有成员必须真实参与。
3. 赛道由队长选择。最终截止前切换赛道会作废该队所有成绩。

## 2. 下载数据

下载需登录（https://virtualembryo.ai/challenge/data）。全部文件是 AnnData `.h5ad`。建议放在一个数据根目录下，例如：

```
data/
  panels/                 公开的榜契约副本（index.json + *.genes.txt；本工具包已附带）
  raw/T1/E8.5_RNA.h5ad    T1 训练（约 571 MB，16,787 个细胞）
  raw/T1/E9.5_RNA.h5ad    T1 训练（约 590 MB，17,057 个细胞）
  raw/T2_heart/E8.25_late.h5ad, E8.75.h5ad, E9.5.h5ad     心脏训练阶段（E8.75 与 E9.5 同时是 T3 的野生型参考）
  raw/T2_embryo/E6.75.h5ad, E7.25.h5ad, E8.0.h5ad          全胚胎训练阶段
  raw/T3/<Mab21l2 KO at E9.5>.h5ad                          T3 训练用敲除（约 458 MB）
```

各文件内容：

* T1：`.X` float32、log1p 归一化、32,285 个基因；`obs["celltype"]`；无坐标。验证目标 E10.5（不公开），测试目标 E12.5
  （隐藏）。另有 E7.75 文件已发布但任何榜都不使用。
* T2：`.X` 对数归一化、有限、非负，500 基因面板；`obs["celltype"]`；`obsm["spatial_3D"]` float32 (n, 3)，每个胚胎自己的
  局部坐标系（阶段之间未配准）。全胚胎设定：训练 E6.75、E7.25、E8.0；验证 E7.5（插值）；测试 E7.75。全胚胎面板是 498 个基因
  （面板中有两个基因缺失）。心脏设定：训练 E8.25、E8.75、E9.5；验证 E8.5（插值）和 E10.5（外推）；测试 E12.5（外推）。
  测试阶段所有心脏阶段都成为训练输入。
* T3：与 T2 同构，多一个 `obs["condition"]`。训练：Mab21l2 敲除 @E9.5。验证：Gata4 敲除 @E8.75（两个重复）。测试：
  beta-catenin 敲除 @E8.75（两个重复）。野生型参考：E8.75 和 E9.5（与 T2 心脏共用）。

不要以任何途径获取被保留的阶段或基因型：规则禁止使用这些阶段/基因型的实测数据，包括含有它们的外部数据集（T1：E10.5、E12.5
以及 E9.5 之后到 E13.5（含）之间的任何外部数据；心脏：E8.25 到 E8.75 窗口以及 E10.5、E12.5；全胚胎：E7.5 到 E7.75；T3：E8.75
的 Gata4 与 beta-catenin 敲除、同基因在相近阶段的其他等位基因、以及表型相同的扰动）。其他外部公开数据、预训练模型和已发表
代码在**方法总结中披露**的前提下允许使用；未披露的外部来源无论效果如何都算违规。

## 3. 安装工具包，以及各部分分别需要什么

```
git clone <本仓库> vec-community-kit
cd vec-community-kit
python -m venv .venv && .venv\Scripts\activate        # Windows；其他系统用 source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q                                    # 合成数据测试，不需要比赛数据
```

按章节列出前置条件（全程 Python 3.10 及以上）：

| 你想做 | 章节 | 需要 |
|---|---|---|
| 读懂契约、生成基线文件、校验、上传 | 4、5、6、8 | `pip install -r requirements.txt`（anndata、numpy、scipy、pandas、h5py；测试用 pytest）。不需要别的。 |
| 在伪切分上本地打分 | 7 | 另需主办方的打分器 **veckit** 及其依赖（numpy、scipy、anndata、scikit-learn）。从主办方处获取：`pip install git+https://github.com/aristoteleo/veckit.git`，或把 https://github.com/aristoteleo/veckit 克隆到任意目录并用 `VECKIT_PATH` 指向它（Windows：`set VECKIT_PATH=C:\path\to\veckit`；其他系统：`export VECKIT_PATH=/path/to/veckit`）。检查：`python -c "from vec_local_score import veckit_available, veckit_info; print(veckit_available(), veckit_info())"`。本工具包在 veckit 0.1.1 上测试过。 |
| 真正运行 Agent 赛道骨架 | 9 | 另需安装并登录 Claude Code CLI（`claude --version` 能打印版本；无头命令 `claude -p "say ok" --max-turns 1` 能返回结果）。干跑 `python -m pytest tests/test_evidence.py -q` 既不需要 CLI 也不需要 API key。 |

没有 veckit 时，打分器相关测试会被跳过，其余一切照常工作。

## 4. 读懂每个榜的文件契约

门户按你上传到的榜校验文件。公开契约在 `data/panels/index.json` 和每个榜一份的基因列表里：

| 榜 | 基因数 | 细胞数（最小-最大） | 坐标 | 地板模型 |
|---|---|---|---|---|
| `T1:val`（E10.5） | 32,285 | 1000-5118 | 否 | copy_last |
| `T2:embryo:val_interp`（E7.5） | 498 | 583-5000 | 是 | copy_last |
| `T2:heart:val_extrap`（E10.5） | 500 | 1000-25179 | 是 | copy_last |
| `T2:heart:val_interp`（E8.5） | 500 | 1000-17616 | 是 | copy_last |
| `T3:gata4`（E8.75） | 500 | 1000-7449 | 是 | wt_identity |

合格文件的规则（`vec_submit_check` 在本地检查这些；门户自己的校验器说了算）：

1. 单个 `.h5ad`，不超过 1200 MB。
2. `var_names` 与该榜的基因列表逐元素相等，**顺序也必须一致**。门户不会替你重排。
3. `n_obs` 在该榜的细胞数范围内。细胞数只是样本量，不参与打分；几千个细胞足够（打分器自己的抽样在某些指标上最多用
   2000 个细胞，另一些用 1500 个）。
4. `.X` 有限、可转 float32、**每个榜都必须非负**、与发布数据一样是对数归一化。
5. T2/T3：`obsm["spatial_3D"]` 形状 (n, 3) 或更宽（取前三列），有限。坐标系任意：空间指标对平移和真旋转不变。
6. 不需要细胞类型标签（打分器忽略它们，用自己的冻结分类器给细胞定型）。

基因面板文件：`data/panels/T1__val.genes.txt`（32,285 行）、`T2__heart__*.genes.txt` 和 `T3__gata4.genes.txt`（500 行，
同一面板）、`T2__embryo__val_interp.genes.txt`（498 行）。`index.json` 记录了每份列表的 sha256，副本损坏能被发现。

## 5. 生成第一份文件：一个基线

`copy_last` 和 `wt_identity` 是主办方的地板行：`copy_last` 原样重提最后一个观测阶段，`wt_identity` 原样重提匹配的野生型。
榜上公布的地板值（100 分里的 50 分）是主办方自己的这一行在隐藏目标上的得分；你生成的文件是同一阶段的一次重抽样，所以会
落在这个值**附近**，而不是正好等于它。它仍然是最合适的第一次上传：用一个已知的参考点把整条流水线跑通。（`pseudobulk_shift`
是第三个基线，不是地板行：每个细胞按自己细胞类型在两个阶段之间的均值变化平移。）

`--n-cells` **必填**：一个在该榜细胞数范围内的整数，或 `all`（写入输入的全部细胞）。已发布的阶段在五个榜中的四个上都超过
上限，`all` 会报错并告诉你范围；请给数字。每条命令旁边写着该榜的范围（来自 `data/panels/index.json`）。

```
# T1:val：1000-5118 个细胞。E9.5_RNA 有 17,057 个细胞，`all` 会报错；5000 在范围内。
python -m vec_baselines.make_baseline --method copy_last   --board T1:val               --last data/raw/T1/E9.5_RNA.h5ad          --out out/t1_copy_last.h5ad --n-cells 5000
# T2:embryo:val_interp：583-5000 个细胞（5000 是上限）。
python -m vec_baselines.make_baseline --method copy_last   --board T2:embryo:val_interp --last data/raw/T2_embryo/E8.0.h5ad       --out out/embryo_copy_last.h5ad --n-cells 5000
# T2:heart:val_interp：1000-17616 个细胞。E8.25_late 约有 59,000 个细胞（index.json 的 ref_cells x 10），`all` 会报错。
python -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_interp  --last data/raw/T2_heart/E8.25_late.h5ad  --out out/heart_interp_copy_last.h5ad --n-cells 5000
# T2:heart:val_extrap：1000-25179 个细胞。E9.5 约有 54,000 个细胞，`all` 会报错。
python -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_extrap  --last data/raw/T2_heart/E9.5.h5ad        --out out/heart_extrap_copy_last.h5ad --n-cells 5000
# T3:gata4：1000-7449 个细胞。E8.75 约有 25,000 个细胞，`all` 会报错。
python -m vec_baselines.make_baseline --method wt_identity --board T3:gata4             --wt   data/raw/T2_heart/E8.75.h5ad       --out out/t3_wt_identity.h5ad --n-cells 5000
```

说明：

* `--n-cells N` 恰好写 N 个细胞，不放回抽取（固定种子，`--seed`）；N 必须在该榜范围内（超过 `max_cells` 直接拒绝，绝不
  悄悄截断）。`--n-cells all` 写入输入的全部细胞，超过 `max_cells` 时报错并给出范围。若输入的细胞数少于 N（但不少于
  `min_cells`），则全部写入并打印一条 NOTE。上面的阶段规模：E9.5_RNA 的 17,057 来自数据页；心脏各阶段取 `index.json` 中
  `ref_cells` 的十倍（打分器的 10% 参考抽样），所以是"约"。
* 全胚胎榜可以直接喂 500 基因的心脏同构文件，写入器按基因名映射成 498 基因面板。
* 哪个阶段算 "last" 由你决定；插值榜通常取目标之前紧邻的阶段，外推榜取最晚发布的阶段。
* CLI 会打印写出文件的契约校验结论，只有通过时退出码才是 0，例如
  `[PASS] out/t3_wt_identity.h5ad @ T3:gata4  n_obs=5000 n_vars=500 X=dense[float32] min=0.0 max=10.2 size=10.1MB`。

在 Python 里：

```python
from vec_baselines import io as bio, methods as bm
spec, panel = bio.panel_for_board("T3:gata4")
wt = bio.load_stage("data/raw/T2_heart/E8.75.h5ad", panel)
X, C, info = bm.wt_identity(wt)
report = bio.write_submission(X, C, panel, "out/t3_wt_identity.h5ad", "T3:gata4", n_cells=5000)
print(report["ok"], report["info"]["n_obs"])
```

`write_submission` 接受任意（细胞 x 基因）矩阵加坐标：你自己模型的输出也用它写。它按基因名映射列、把负值截到 0、写成
float32，并在返回前校验文件。这里的 `n_cells` 同样必填（范围内的整数或 `"all"`）；不给会抛出 `ValueError` 并告诉你该传什么。

## 6. 校验

```
python -m vec_submit_check --board T2:heart:val_interp out/heart_interp_copy_last.h5ad
python -m vec_submit_check --board T1:val out/t1_copy_last.h5ad --json out/t1_check.json
```

输出 `[PASS]` / `[FAIL]` 以及每条错误和警告，然后是文件的 sha256、大小、取值范围和坐标半径：

```
[PASS] out/heart_interp_copy_last.h5ad @ T2:heart:val_interp  n_obs=5000 n_vars=500
  sha256: <64 hex characters: keep it with the file you upload>
  X_format: dense[float32]  X_min: 0.0  X_max: 12.1656  spatial_3D_rms_radius: 84.589  ...
```

退出码 0 = 通过，1 = 不通过，2 = 用法错误（未知的榜或文件不存在）。这是一组对照已公布契约的本地上传前检查，不是对门户
全部规则的复刻：门户自己的校验器说了算，但在这里不通过的文件到了门户同样不通过，所以先在本地查能省掉不必要的"上传-排错"
往返。最常见的失败：基因顺序不一致（`reorder with the panel file`）、`n_obs` 超出榜的范围、负值或 NaN（每个榜都拒绝负值）、
缺少 `obsm["spatial_3D"]`、超过文件大小上限。关于 `obs["celltype"]` 的警告无害；`.X max looks like raw counts` 的警告说明
你的矩阵没有做对数归一化。

## 7. 在伪验证切分上本地打分

你无法对隐藏目标打分，但可以留出一个已发布阶段，用更早的阶段预测它，再用主办方的打分器算分。`vec_local_score` 为此封装了
veckit，遵循 veckit 打分器截至 0.1.1 版的流程：每个阶段抽样 10%、对半天花板、地板行、skill 尺度（外加评测页公布的任务权重）。
主办方门户上的打分器才是最终依据，这层封装可能滞后于它。

前置条件：veckit（第 3 节）。检查：
`python -c "from vec_local_score import veckit_available, veckit_info; print(veckit_available(), veckit_info())"`。

**封装接收的是原始发布阶段文件**，抽样和切分由它自己完成：`--target` 是留出的原始阶段，`--reference`（T1/T2）或 `--wt`（T3）
是衡量变化所对照的原始阶段，`--pred` 是你对留出阶段的预测。伪预测要用留下的阶段来构造，绝不能用留出的那个阶段（从目标本身
抽出来的文件会得 100 分，什么也说明不了）。例如在心脏插值榜上留出 E8.75，用 E8.25 构造的 `copy_last` 基线作为预测：

```
python -m vec_baselines.make_baseline --method copy_last --board T2:heart:val_interp --last data/raw/T2_heart/E8.25_late.h5ad --out out/pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --frac 0.1 --seed 0
python -m vec_local_score.seed_summary --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --seeds 0 1 2 3 4
```

T1：留出 E9.5_RNA、用 E8.5_RNA 预测它 —— 预测用 `--last data/raw/T1/E8.5_RNA.h5ad` 构造，打分用
`--task T1 --target data/raw/T1/E9.5_RNA.h5ad --reference data/raw/T1/E8.5_RNA.h5ad`。T3：留出训练用敲除 ——
`--task T3 --target <Mab21l2 敲除> --wt <同阶段（E9.5）匹配野生型>`，预测用野生型构造。

怎么读：每个阶段抽样 10%，目标一分为二；地板（原样重提参考阶段）定义 skill 尺度上的 50，天花板（目标的另一半）定义 100；
你的预测得到每个指标的 skill（用 veckit 自己的 `skill()`）和一个任务分。两个"目标值为 0"的指标（`scale_log_ratio`、
`severity_slope`）标有 `*`：它们的 skill 按绝对值计算（过冲和不足同样计）。你重抽样得到的 `copy_last` 文件会落在 50
**附近**，而不是正好 50 —— 封装里的地板行是参考阶段的 10% 抽样，你的文件是同一批细胞的另一次抽样；偏离 50 几分是正常的。
本地分数**不是**真实分数的预告；它只是在同一切分、同一组种子上给你自己的方法排序。请报告多个种子的均值和离散度
（`seed_summary`）；差异在一个标准差以内不算结果。每一列的含义见 `docs/metrics_overview.md`；封装到底实现了哪些约定，见
`vec_local_score/README.md`。

`python -m vec_local_score.make_pseudo_split` 是可选工具：把一个固定切分导出成文件，供检查或直接调用 veckit 命令行。它的
输出不是 `vec_local_score` 的输入（封装会拒绝它们，否则会抽样两次）。

## 8. 上传

1. 登录 https://virtualembryo.ai/challenge/submit ，打开对应榜的标签页，上传 `.h5ad`。格式检查不限次、不消耗配额；计分提交
   占用当前阶段的配额。
2. 打分完成后结果出现在公开排名上（Agent 赛道：必须先附上证据，见第 9 节）。
3. 每个榜都重复一遍：从未被打分的榜在总分里按 0 计。
4. 保留你上传的文件及其 sha256（`vec_submit_check` 会打印）、生成它的命令和一小段方法说明；最终报告和任何核验请求都会
   用到。

## 9. Agent 赛道：需要什么证据、怎么用工具包产出

规则（站点的 Agent Team 部分）：

* Agent 参赛作品的区别在于**配置锁定**之后的自主性；锁定即运行开始的那一刻。锁定之前一切随意：写或改 harness、选模型、
  写提示词、定预算、想跑多少次都行。锁定之后：不允许人读中间结果（分数、诊断、部分输出）并施加干预，不允许中途改配置，
  不允许替 agent 在运行的中间产物里做选择。允许人决定提交**哪一次已完成的运行**。
* 提交的文件必须是未经编辑的 agent 输出。任何人为编辑（手改、脚本、替换）都使其不再是 Agent 参赛作品。
* 每份提交在被打分或上榜之前，必须附上 {trajectory（轨迹）、prompts（所有提示词，含初始提示词）、harness（编排代码、工具、
  评估循环）} 中至少**两种**不同类型的证据。证据必须来自产生该文件的那一次运行。主办方可能审计并要求重跑 harness。
  拿奖必须有证据。
* 限制：每个证据文件 200 MB，每队合计 600 MB。
* FAQ 原话：框架不是重点，重点是回路中没有人。

`vec_agent_evidence` 把这一切变成机械步骤。当前实现面向无头模式的 Claude Code CLI（`claude -p --output-format stream-json`），
需要先安装并登录（第 3 节）；换别的 agent CLI 需要改 `launch.build_command`。

```
# 0. 用替身 agent 做一次干跑，不需要 CLI 也不调任何 API：证明流水线在你机器上能通
python -m pytest tests/test_evidence.py -q

# 1. 写你的提示词（从 vec_agent_evidence/example_prompt.md 起步：它只解释工作区约定）
# 2. 锁定 + 运行 + 收集，一条命令；看到锁定提示后人就离开
python -m vec_agent_evidence run --task T3 --prompt my_prompt.md --model <完整模型 id> --data-root ./data --hours 8 --max-turns 400

# 3. run_manifest.json 出现后：检查它，然后打上传包
python -m vec_agent_evidence package --run-dir runs/<run_id>
```

（同样的参数换成 `python -m vec_agent_evidence lock ...` 只冻结运行目录并打印将要执行的启动命令，不启动任何东西，适合先检查。）

你会得到（全部哈希记录在 `config.lock.json`，并在 `run_manifest.json` 里复核）：

* **prompts**：`initial_prompt.md`（从模板逐字节渲染）、可选的 `system_prompt_appendix.md`、`prompts.manifest.json`；
* **trajectory**：`transcript/<session-id>.jsonl`（CLI 自己的会话记录，按 session id 复制）、`stream.jsonl`（CLI 标准输出
  逐字节留存）、`hooks/tool_audit.jsonl`（每次工具调用一行）、`hooks/guard_denials.jsonl`（每次被拒绝的调用及原因）；
* **harness**：`harness_snapshot.zip`（产生这次运行的工具包代码和模板）、`config.lock.json`（模型、工具策略、限制、种子、
  环境、数据文件哈希、CLI 二进制版本与 sha256）、`claude_settings.json`（拒绝规则和 hooks）、`launch_command.json`、`env/`。

`package` 步骤生成 `predictions/`（逐字节相同、sha256 已核对）、`trajectory.zip`、`prompts.zip`、`harness.zip` 和
`evidence_bundle.zip` 加一份 README；如果锁定被破坏、证据里出现凭据形状的字符串、运行中止、或某个 zip 超过 200 MB，它会拒绝
打包。到门户上：在对应榜的标签页上传预测文件，并**在同一标签页**附上证据（至少两种；`evidence_bundle.zip` 三种都有），
然后提交。每个榜重复。

运行期间接入 CLI 的有两个 hook：守卫 hook 拒绝**能识别出的**网络命令（curl、wget、pip install、git clone、ssh、
requests/urllib 一行程序、任何 URL……）、读取 CLI 配置目录、引用其他运行目录、绕过 `tools/finalize_submission.py` 直接写
`submission/`（该工具会校验、哈希并登记每个定稿文件）、修改只读的工具和数据、以及杀进程命令；审计 hook 记录每一次工具调用。
它们是作用在工具输入上的正则 hook，不是网络沙箱：运行后的核验靠的是审计日志、轨迹以及锁定时和运行后记录的哈希。agent 在
它的工作区里拥有与你相同的校验器、基线生成器和本地打分器（只读副本）。

人可以做和不可以做的事：锁定前，随意；锁定到 `run_manifest.json` 出现之间，什么都不做（不要打开这次运行的流、工作区或
公开排名）；之后，读 manifest 和 NOTES.md，决定上传哪一次已完成的运行，原样上传文件和 zip，把学到的东西写进下一版提示词
（下次锁定时用 `--note` 记录）。永远不要恢复会话、不要把一次运行的产物喂进另一次运行的工作区、不要编辑提交文件。

## 10. 每次上传前的清单

- [ ] `python -m vec_submit_check --board <榜> <文件>` 打印 `[PASS]`。
- [ ] 基因顺序与面板文件一致（校验器会说；门户不会重排）。
- [ ] 细胞数在榜的范围内（你是显式传入的）；没有重复细胞；不需要标签。
- [ ] `.X` 与发布数据一样对数归一化（没有 `raw counts` 警告）、有限、非负（每个榜）。
- [ ] T2/T3：`obsm["spatial_3D"]` 存在、(n, 3)、有限。
- [ ] 文件小于 1200 MB。
- [ ] 你清楚这个文件属于哪个榜的标签页（心脏插值和外推是两个不同的榜）。
- [ ] Agent 赛道：`run_manifest.json` 显示 `lock_integrity.ok`、`secret_scan.clean`、`abort: null`，该榜 `uploadable`；
      你上传的预测文件 sha256 与其中记录一致；附上两种证据。
- [ ] 用了外部数据或预训练模型？已在方法总结中披露。
