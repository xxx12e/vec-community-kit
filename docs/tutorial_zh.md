# 从零到第一次提交 —— Virtual Embryo Challenge（NeurIPS 2026）

这份教程带一个新手从注册走到"每个榜都有一份被打分的提交"，两个赛道都覆盖，全程使用本工具包。下文所有关于比赛的
事实都来自官方站点（https://virtualembryo.ai/challenge）；如有出入，以官方为准。工具包本身只是通用工具：格式校验器、
基线生成器与提交文件写入器、主办方打分器的本地封装、Agent 赛道的证据骨架。它不包含任何建模建议。

下面的命令已于 2026-09-30（UTC）按顺序、原样在真实发布数据上执行过：在一台云端 Linux 机器（32 核，Python 3.10.13）上放一份
全新的工具包，按第 3 节安装，把从数据页下载的文件链接成第 2 节的目录布局。精简后的日志（Python 与依赖版本、退出码、细胞数与
基因数、运行时间和内存）见 `scratchpad/realrun_log_2026-10-01.txt`（其中不含分数和表达值）；执行这些命令的脚本是
`scratchpad/tutorial_realrun.py`。这次执行不包括：上传（第 8 节）、一次真实的 Agent 赛道运行（第 9 节；其测试和锁定步骤执行了），以及第 7 节末尾
E10.5 的例子（它要用 2026-10-20 才发布的验证阶段）。
更早在按同样布局摆放的小型合成数据上的执行记录见 `scratchpad/dryrun_log.txt`。

## 0. 一页看懂比赛

* 主办：Qiu Lab（Stanford）及合作机构；NeurIPS 2026 官方竞赛。数据：约一百万个小鼠胚胎细胞，11 个发育阶段
  （E6.75 到 E12.5），以心脏为中心。
* 三个任务、五个公开榜（board）：
  * **T1** 单细胞 RNA-seq（32,285 个基因，无坐标）：由早期阶段预测更晚阶段。
  * **T2** 3D MERFISH（500 基因面板，带坐标）：全胚胎设定（插值）和心脏设定（插值榜 + 外推榜）。
  * **T3** 条件敲除（与 T2 同一面板、同样带坐标，多一个基因型列）：由训练用敲除和匹配野生型预测一个未见过的敲除。
* 两个赛道在同一套隐藏测试集上打分，排名和奖金池分开：**Human Team** 和 **Agent Team**。Agent 赛道多一条要求：
  配置锁定（configuration lock）之后全自主，并用证据证明。
* 每个赛道奖金：1 x 8K、2 x 5K、3 x 3K 美元；另有旅行奖；以及 Community Contribution Award（每项贡献最多 200 美元，
  最多 100 项，滚动评审至 2026-12-11），奖励帮助他人参赛的工作 —— 本工具包就是这一类。
* 时间线：2026-08-10 提交门户和验证阶段上线；2026-10-20 进入测试阶段（验证集答案公布并成为训练数据，测试输入不带标签
  发布；所有变化见第 11 节）；2026-12-02 最终提交截止；2026-12-11 NeurIPS 现场公布获奖者。获奖者需在 14 天内提交书面方法报告，代码可能被要求
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
  panels/                         公开的榜契约副本（index.json + *.genes.txt；本工具包已附带）
  raw/T1/E8.5_RNA.h5ad            T1 训练：571 MB，16,787 个细胞 x 32,285 个基因
  raw/T1/E9.5_RNA.h5ad            T1 训练：590 MB，17,057 个细胞 x 32,285 个基因
  raw/T2_heart/E8.25_late.h5ad    心脏训练 E8.25：225 MB，58,716 个细胞 x 500 个基因
  raw/T2_heart/E8.75.h5ad         心脏训练 E8.75（也是 T3 在 E8.75 的野生型）：84 MB，24,826 个细胞 x 500
  raw/T2_heart/E9.5.h5ad          心脏训练 E9.5（也是 T3 在 E9.5 的野生型）：164 MB，53,742 个细胞 x 500
  raw/T2_embryo/E6.75.h5ad        全胚胎训练：17 MB，7,093 个细胞 x 498 个基因
  raw/T2_embryo/E7.25.h5ad        全胚胎训练：34 MB，13,295 个细胞 x 498 个基因
  raw/T2_embryo/E8.0.h5ad         全胚胎训练：118 MB，31,671 个细胞 x 500 个基因
  raw/T3/E9.5_mab21l2_ko.h5ad     T3 训练用敲除（Mab21l2 敲除 @E9.5）：458 MB，50,294 个细胞 x 500 个基因
```

`raw/` 下的文件夹名是本工具包的约定；文件名是发布时的名字，只有敲除文件例外：数据页没有写出它的文件名，`E9.5_mab21l2_ko.h5ad`
是本教程使用的名字，如果你下载到的文件名不同，在第 7 节的命令里换成你的文件名。两个野生型就是心脏文件（数据页列出的大小相同），
`raw/T3/` 下没有另一份副本。大小和细胞数来自真实数据执行时用的文件（大小与数据页一致；数据页没有列出全胚胎文件的大小）。

各文件内容（在发布文件上核对过）：

* T1：`.X` float32、稀疏（CSC）、log1p 归一化，32,285 个基因，顺序与 `T1:val` 面板一致；`obs["celltype"]`；无坐标（`obsm`
  里只有一个 UMAP）。验证目标 E10.5（不公开），测试目标 E12.5（隐藏）。E7.75 的单细胞文件没有发布：E7.75 是 T2 全胚胎设定的
  隐藏测试阶段，所以数据页写明它不对任何任务分发。
* T2：`.X` float32、稀疏（CSC）、对数归一化、有限、非负；`obs["celltype"]`（心脏各阶段和全胚胎 E8.0 另有 `obs["cm_celltype"]`）；
  `obsm["spatial_3D"]` float32 (n, 3)，每个胚胎自己的局部坐标系（阶段之间未配准），旁边还有一个 `obsm["spatial_2D"]`。全胚胎
  设定：训练 E6.75、E7.25、E8.0；验证 E7.5（插值）；测试 E7.75。E6.75 和 E7.25 只有 498 个基因（Casp4 和 Pnliprp1 在这两个阶段
  没有测），E8.0 有全部 500 个，所以全胚胎榜的面板是 498 个基因。心脏设定：训练 E8.25、E8.75、E9.5；验证 E8.5（插值）和 E10.5
  （外推）；测试 E12.5（外推）。测试阶段所有心脏阶段都成为训练输入。心脏文件和 E8.0 的 500 个基因与心脏榜、T3 榜的面板同序；
  E6.75 和 E7.25 与全胚胎榜的面板同序。
* T3：与 T2 同一个 500 基因面板（同序）、同样的 `obsm["spatial_3D"]`。发布的敲除文件里 `.X` 是稠密的，基因型记录在
  `obs["genotype"]` 里，而不是数据页结构表（那里标着 "tbc"）写的 `obs["condition"]`，另外还有若干字段（样本、玻片、切片……）；
  工具包两列都不读。训练：Mab21l2 敲除 @E9.5。验证：Gata4 敲除 @E8.75（两个重复）。测试：beta-catenin 敲除 @E8.75（两个重复）。
  野生型参考：E8.75 和 E9.5（与 T2 心脏共用）。

不要以任何途径获取被保留的阶段或基因型：规则禁止使用这些阶段/基因型的实测数据，包括含有它们的外部数据集（T1：E10.5、E12.5
以及 E9.5 之后到 E13.5（含）之间的任何外部数据；心脏：E8.25 到 E8.75 窗口以及 E10.5、E12.5；全胚胎：E7.5 到 E7.75；T3：E8.75
的 Gata4 与 beta-catenin 敲除、同基因在相近阶段的其他等位基因、以及表型相同的扰动）。其他外部公开数据、预训练模型和已发表
代码在**方法总结中披露**的前提下允许使用；未披露的外部来源无论效果如何都算违规。

## 3. 安装工具包，以及各部分分别需要什么

```
git clone <本仓库> vec-community-kit
cd vec-community-kit
python -m venv .venv && .venv\Scripts\activate        # Windows；Linux/macOS：python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"                               # 工具包本身 + anndata、numpy、scipy、pandas、h5py + pytest
python -m pytest -q                                    # 合成数据测试，不需要比赛数据
```

实际情况（真实数据执行，Linux，Python 3.10.13，pip 需要联网）：安装在那里用了约 15 秒，清空 pip 缓存后重装也是如此（这时下载了
约 75 MB 的包，加上 veckit 再多约 10 MB；家用网络会比那台机器慢），解析出 anndata 0.11.4、numpy 2.2.6、scipy 1.15.3、
pandas 2.3.3、h5py 3.16.0 和 pytest 9.1.1（Python 3.10 拿到的这些包比 3.12 旧一些，两者都能用）。没有 veckit 时测试结果是
`54 passed, 10 skipped`（跳过的是本地打分测试，以及需要环境里 setuptools 77 或更新版本的 wheel 构建测试）；装上 veckit 后是
`63 passed, 1 skipped`。以 root 身份运行（很多云容器就是这样）也能通过。

`pip install -e .` 还会安装五个命令，与下文用到的 `python -m` 写法完全相同（`vec-community-check`、`vec-community-baseline`、
`vec-community-score`、`vec-community-split`、`vec-community-evidence`，见顶层 README）。`pip install -r requirements.txt` 只装依赖，
像本教程这样在克隆目录里用 `python -m` 运行时也够用。

按章节列出前置条件（全程 Python 3.10 及以上）：

| 你想做 | 章节 | 需要 |
|---|---|---|
| 读懂契约、生成基线文件、校验、上传 | 4、5、6、8 | `pip install -e ".[test]"` 或 `pip install -r requirements.txt`（anndata、numpy、scipy、pandas、h5py；测试用 pytest）。不需要别的。 |
| 在伪切分上本地打分 | 7 | 另需主办方的打分器 **veckit** 及其依赖（numpy、scipy、anndata、scikit-learn）。从主办方处获取：`pip install "git+https://github.com/aristoteleo/veckit.git@46d41e63f42a9aab815db20b742feeccd249cb17"`，或把 https://github.com/aristoteleo/veckit 克隆到任意目录并用 `VECKIT_PATH` 指向它（Windows：`set VECKIT_PATH=C:\path\to\veckit`；其他系统：`export VECKIT_PATH=/path/to/veckit`）。检查：`python -c "from vec_local_score import veckit_available, veckit_info; print(veckit_available(), veckit_info())"` 打印 `True` 和一个字典；装的是测试过的那个提交（不计换行符差异）时，其中 `'version': '0.1.1'`、`'matches_tested': True`。本工具包在 veckit 0.1.1 上测试过。`pip` 这条路需要 `git`，在 Python 3.10 上会顺带装上 scikit-learn 1.7.2。 |
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

合格文件的规则（`vec_submit_check` 在本地检查这些，每条规则在 `vec_submit_check/README.md` 里标明是门户规则、更严格还是仅提示；
门户自己的校验器说了算）：

1. 单个 `.h5ad`，不超过 1200 MB。
2. `var_names` 与该榜的基因列表逐元素相等，**顺序也必须一致**。门户不会替你重排。
3. `n_obs` 落在 `panels/index.json` 给该榜的 `[min_cells, max_cells]` 之内（上表；数据页上也有）。超出范围的上传在打分前就被
   拒绝，不消耗计分次数。（评测页曾写"1,000 个以上无上限"，主办方评审本工具包后已更正（2026-09-22）；评测页仍有一段写着
   1,000 个细胞，所以全胚胎榜上 583-999 个细胞时校验器给警告。以 `index.json` 为准，校验器不再提供豁免开关。）细胞数只是样本量，不参与打分；几千个细胞足够（打分器自己的抽样在某些指标上最多用 2000 个细胞，另一些用 1500 个）。
4. `.X` 有限、**每个榜都必须非负**、与发布数据一样是对数归一化；稀疏或稠密都行（打分器自己会稠密化并转成 float32）。
   校验看不出尺度错误：原始计数文件能通过全部检查，然后被打错分（评测页明说了这一点）。
5. T2/T3：`obsm["spatial_3D"]` 形状 (n, 3) 或更宽（取前三列），有限。坐标系任意：空间指标对平移和真旋转不变。
6. 不需要细胞类型标签（打分器忽略它们，用自己的冻结分类器给细胞定型）。

基因面板文件：`data/panels/T1__val.genes.txt`（32,285 行）、`T2__heart__*.genes.txt` 和 `T3__gata4.genes.txt`（500 行，
同一面板）、`T2__embryo__val_interp.genes.txt`（498 行）。`index.json` 记录了每份列表的 sha256，副本损坏能被发现。

## 5. 生成第一份文件：一个基线

`copy_last` 和 `wt_identity` 是主办方的地板行：`copy_last` 原样重提最后一个观测阶段，`wt_identity` 原样重提匹配的野生型。
榜上公布的地板值（100 分里的 50 分）是主办方自己的这一行在隐藏目标上的得分；你生成的文件是同一阶段的一次重抽样，所以会
落在这个值**附近**，而不是正好等于它。它仍然是最合适的第一次上传：用一个已知的参考点把整条流水线跑通。（`pseudobulk_shift`
是第三个基线，不是地板行：每个细胞按自己细胞类型在两个阶段之间的均值变化平移。）

`--n-cells` **必填**：一个在该榜细胞数范围内的整数，或 `all`（写入输入的全部细胞）。下面用到的每个已发布阶段的细胞数都超过
所在榜的 `max_cells`，所以 `all` 会报错并告诉你范围（真实数据执行时五个都核对过）；请给数字（第 4 节第 3 条）。每条命令旁边
写着该榜的范围（来自 `data/panels/index.json`）。

```
# T1:val：1000-5118 个细胞。E9.5_RNA 有 17,057 个细胞，`all` 会报错；5000 在范围内。
python -m vec_community_baselines.make_baseline --method copy_last   --board T1:val               --last data/raw/T1/E9.5_RNA.h5ad          --out out/t1_copy_last.h5ad --n-cells 5000
# T2:embryo:val_interp：583-5000 个细胞（5000 是上限）。E8.0 有 31,671 个细胞，`all` 会报错。
python -m vec_community_baselines.make_baseline --method copy_last   --board T2:embryo:val_interp --last data/raw/T2_embryo/E8.0.h5ad       --out out/embryo_copy_last.h5ad --n-cells 5000
# T2:heart:val_interp：1000-17616 个细胞。E8.25_late 有 58,716 个细胞，`all` 会报错。
python -m vec_community_baselines.make_baseline --method copy_last   --board T2:heart:val_interp  --last data/raw/T2_heart/E8.25_late.h5ad  --out out/heart_interp_copy_last.h5ad --n-cells 5000
# T2:heart:val_extrap：1000-25179 个细胞。E9.5 有 53,742 个细胞，`all` 会报错。
python -m vec_community_baselines.make_baseline --method copy_last   --board T2:heart:val_extrap  --last data/raw/T2_heart/E9.5.h5ad        --out out/heart_extrap_copy_last.h5ad --n-cells 5000
# T3:gata4：1000-7449 个细胞。E8.75 有 24,826 个细胞，`all` 会报错。
python -m vec_community_baselines.make_baseline --method wt_identity --board T3:gata4             --wt   data/raw/T2_heart/E8.75.h5ad       --out out/t3_wt_identity.h5ad --n-cells 5000
```

说明：

* `--n-cells N` 恰好写 N 个细胞，不放回抽取（固定种子，`--seed`）；N 必须在该榜范围内（超过 `max_cells` 直接拒绝，绝不
  悄悄截断）。`--n-cells all` 写入输入的全部细胞，超过 `max_cells` 时报错并给出范围（见第 4 节第 3 条）。若输入的细胞数少于 N（但不少于
  `min_cells`），则全部写入并打印一条 NOTE。注释里的阶段规模是发布文件的细胞数（第 2 节）。
* 全胚胎榜可以直接喂 500 基因的文件（例如发布的 E8.0），写入器按基因名映射成 498 基因面板。
* 哪个阶段算 "last" 由你决定；插值榜通常取目标之前紧邻的阶段，外推榜取最晚发布的阶段。
* CLI 会打印写出文件的本地契约校验结论，只有通过时退出码才是 0，例如
  `[PASS] out/t3_wt_identity.h5ad @ T3:gata4  n_obs=5000 n_vars=500 X=dense[float32] min=0.0 max=... size=10.3MB`，
  随后一行 `PASS = local format checks passed; ...`（只是格式检查通过，不代表归一化正确、数据来源合规或参赛资格）。
* 在真实文件上的表现：上面每条命令在那台机器上都不到 5 秒。T1 那条会把 590 MB 的整个阶段读进来，内存峰值约 1.9 GB，其余都
  低于 0.5 GB。T1 文件按稀疏格式写出，5,000 个细胞约 160 MB；T2/T3 文件是稠密的，约 10 MB。
* 在发布的心脏阶段上，各阶段的细胞类型标签并不一致（数据页说注释词表尚未统一），所以 `pseudobulk_shift` 只平移那些在更早阶段
  也存在的类型的细胞，并打印一条 WARNING 列出其余类型（`--celltype-key` 可以换用另一列 `obs`）。

在 Python 里：

```python
from vec_community_baselines import io as bio, methods as bm
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

输出 `[PASS]` / `[FAIL]` 以及每条错误和警告，然后每行一个字段：细胞数和基因数、文件的 sha256、文件大小和大小上限、`.X` 的存储
格式、取值范围和非零元素占比，以及（T2/T3）坐标半径。真实心脏文件上的输出（来自数据的数值用 `...` 代替）：

```
[PASS] out/heart_interp_copy_last.h5ad @ T2:heart:val_interp  n_obs=5000 n_vars=500
  PASS = local format checks passed; it does not confirm log-normalisation, data provenance or eligibility
  n_obs: 5000
  n_vars: 500
  sha256: <64 hex characters: keep it with the file you upload>
  size_mb: 10.3
  max_file_mb: 1200.0
  X_format: dense[float32]
  X_min: ...
  X_max: ...
  X_nonzero_frac: ...
  spatial_3D_rms_radius: ...
```

T1 文件的报告里是 `X_format: csr_matrix`（稀疏）和 `size_mb: 159.1`，没有 `spatial_3D_rms_radius` 这一行（T1 没有坐标）。

在真实文件上每次检查约 1 秒、内存低于 0.5 GB；`vec-community-check`（第 3 节）给出同样的报告。把心脏文件拿去对全胚胎榜检查
会失败，报 `n_vars=500 but board expects 498` 并列出多出来的两个基因。

退出码 0 = 通过，1 = 不通过，2 = 用法错误（未知的榜或文件不存在）。这是一组对照已公布契约的本地格式检查；每条规则在
`vec_submit_check/README.md` 里标明是 portal / stricter / advisory。门户自己的校验器说了算，主办方的 starter kit（`score_h5ad.py`）
也能在本地校验；在这里违反 portal 规则的文件到了门户同样会被拒。PASS 不说明归一化是否正确、细胞从哪里来、是否符合参赛规则。
最常见的失败：基因顺序不一致（`reorder with the panel file`）、`n_obs` 超出榜的范围、负值或 NaN（每个榜都拒绝负值）、
缺少 `obsm["spatial_3D"]`、超过文件大小上限。关于 `obs["celltype"]` 的警告无害；`.X max looks like raw counts` 的警告说明
你的矩阵没有做对数归一化。

## 7. 在伪验证切分上本地打分

你无法对隐藏目标打分，但可以留出一个已发布阶段，用更早的阶段预测它（绝不能用留出的阶段本身），再用主办方的打分器算分。
结果比较的是你的方法在这个切分上的表现，不预测它们在隐藏目标上的名次。`vec_local_score` 为此封装了 veckit，遵循 veckit
打分器截至 0.1.1 版的流程：每个阶段抽样 10%、对半天花板、地板行、skill 尺度（外加评测页公布的任务权重）；默认还把参考阶段
限制在 4,000 个细胞以内（见下面的"实际情况"）。主办方门户上的打分器才是最终依据，这层封装可能滞后于它。

前置条件：veckit（第 3 节）。检查：
`python -c "from vec_local_score import veckit_available, veckit_info; print(veckit_available(), veckit_info())"`。

**封装接收的是原始发布阶段文件**，抽样和切分由它自己完成：`--target` 是留出的原始阶段，`--reference`（T1/T2）或 `--wt`（T3）
是衡量变化所对照的原始阶段，`--pred` 是你对留出阶段的预测。伪预测要用留下的阶段来构造，绝不能用留出的那个阶段（从目标本身
抽出来的文件会得 100 分，什么也说明不了）。例如在心脏插值榜上留出 E8.75，用 E8.25 构造的 `copy_last` 基线作为预测：

```
python -m vec_community_baselines.make_baseline --method copy_last --board T2:heart:val_interp --last data/raw/T2_heart/E8.25_late.h5ad --out out/pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad
python -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --single-seed
```

第一条打分命令输出的是**区间**（2026-09-30 起的默认输出）：抽样种子 0-4 下任务分的均值、标准差和最小..最大值，外加各指标均值表。
第二条（`--single-seed`，可加 `--seed N`）输出单个种子的完整指标表。之所以默认给区间，是因为主办方在对本工具包的评审中说，
抽样种子将随每次提交而定；只看一个本地种子，就看不出分数随抽样变动多少。

其他榜同样的做法，各举一个切分（T1：留出 E9.5_RNA，用 E8.5_RNA 预测；T3：留出训练用敲除，用同阶段的野生型作 `--wt`；全胚胎：
留出 E7.25，以 E6.75 为参考；心脏外推：留出 E9.5，以 E8.75 为参考）。这里每个预测都是从参考阶段构造的地板模型，只用来演示
流程；换成你自己方法的文件：

```
python -m vec_community_baselines.make_baseline --method copy_last --board T1:val --last data/raw/T1/E8.5_RNA.h5ad --out out/t1_pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T1 --pred out/t1_pseudo_pred.h5ad --target data/raw/T1/E9.5_RNA.h5ad --reference data/raw/T1/E8.5_RNA.h5ad
python -m vec_community_baselines.make_baseline --method wt_identity --board T3:gata4 --wt data/raw/T2_heart/E9.5.h5ad --out out/t3_pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T3 --pred out/t3_pseudo_pred.h5ad --target data/raw/T3/E9.5_mab21l2_ko.h5ad --wt data/raw/T2_heart/E9.5.h5ad
python -m vec_community_baselines.make_baseline --method copy_last --board T2:embryo:val_interp --last data/raw/T2_embryo/E6.75.h5ad --out out/embryo_pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T2 --setting embryo --pred out/embryo_pseudo_pred.h5ad --target data/raw/T2_embryo/E7.25.h5ad --reference data/raw/T2_embryo/E6.75.h5ad
python -m vec_community_baselines.make_baseline --method copy_last --board T2:heart:val_extrap --last data/raw/T2_heart/E8.75.h5ad --out out/heart_extrap_pseudo_pred.h5ad --n-cells 5000
python -m vec_local_score --task T2 --setting heart --pred out/heart_extrap_pseudo_pred.h5ad --target data/raw/T2_heart/E9.5.h5ad --reference data/raw/T2_heart/E8.75.h5ad
```

这些只是例子，不是推荐：任何已发布阶段都可以留出，只要预测从不使用它。伪预测的 `--board` 只决定文件的基因面板和细胞数范围。

在真实文件上的实际情况（上面那台机器，五个种子，`OMP_NUM_THREADS=4`、`LOKY_MAX_CPU_COUNT=4`）：

| 切分 | cells pred/A/B/ref（表头一行） | 时间 | 内存峰值 |
|---|---|---|---|
| T1，用 E8.5_RNA 预测 E9.5_RNA | 5000/853/853/1679 | 约 2 分钟 | 约 6 GB |
| T2 心脏，用 E8.25_late 预测 E8.75 | 5000/1241/1242/4000 | 约 25 秒 | 约 1 GB |
| T2 心脏，用 E8.75 预测 E9.5 | 5000/2687/2687/2483 | 约 35 秒 | 约 1 GB |
| T2 全胚胎，用 E6.75 预测 E7.25 | 5000/665/665/709 | 约 15 秒 | 约 0.6 GB |
| T3，用野生型 E9.5 预测 Mab21l2 敲除 | 5000/2514/2515/4000 | 约 40 秒 | 约 1.5 GB |

`--single-seed` 大约是它的四分之一。T1 切分内存用得最多：两个全转录组阶段都要整个读进来，被打分的细胞要在 32,285 个基因上
稠密化。ref 一列体现了封装的上限：`--max-cells`（默认 4,000）在 10% 抽样之后再限制参考阶段，在真实文件上对 E8.25_late（10%
为 5,872 个细胞）和心脏 E9.5（5,374 个）起作用；想保留完整的 10% 样本（与 `index.json` 里主办方的 `ref_cells` 一致），加
`--max-cells 6000`。veckit 的细胞类型探针向 joblib 要全部核心（`n_jobs=-1`）；scikit-learn 1.7（Python 3.10 装到的版本）会因此
每个核心起一个工作进程，所以在共用的机器上打分前设 `LOKY_MAX_CPU_COUNT=4`（或你可以用的核心数）。

怎么读：每个阶段抽样 10%，目标一分为二；地板（原样重提参考阶段）定义 skill 尺度上的 50，天花板（目标的另一半）定义 100；
你的预测得到每个指标的 skill（用 veckit 自己的 `skill()`）和一个任务分。两个"目标值为 0"的指标（`scale_log_ratio`、
`severity_slope`）标有 `*`：它们的 skill 按绝对值计算（过冲和不足同样计）。你重抽样得到的 `copy_last` 文件会落在 50
**附近**，而不是正好 50 —— 封装里的地板行是参考阶段的 10% 抽样，你的文件是同一批细胞的另一次抽样；偏离 50 几分是正常的
（真实数据执行时，上面五个地板模型预测的五种子均值都在 50 的 5 分以内）。
本地分数**不是**真实分数的预告；它只是在同一切分、同一组种子上给你自己的方法排序。每一列的含义见
`docs/metrics_overview.md`；封装到底实现了哪些约定，见 `vec_local_score/README.md`。

**比较你自己的两种方法：配对模式。** 在一次调用里传入对留出阶段的两个预测，`--pred A --pred B`。每个种子下两个文件都对着
同一次抽样、同一对目标半份、同一个地板和天花板打分，所以逐种子的差值 B - A 消掉了两者共有的抽样噪声。输出给出两个文件各自的区间、
各指标的分数差，以及逐种子的 B - A 和它在各种子上的均值、标准差和最小..最大：

```
python -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --pred out/pseudo_pred_mine.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad
```

`out/pseudo_pred_mine.h5ad` 代表你自己的方法对 E8.75 的预测，用留下的阶段构造（用第 5 节的 `write_submission` 写出），绝不能用
E8.75。看 B - A 的最小..最大：整段在 0 的同一侧，说明在这个切分的每个种子上都是同一个文件领先；跨过 0，说明各种子意见不一，
这个差异不算结果。两个区间可以重叠而配对差值始终同号：在试运行的合成数据上，一个替身 B（把 `copy_last` 文件的坐标放大到目标
的尺寸）的区间是 52.49..61.32，A 是 48.86..56.96，而 B - A 在全部五个种子上是 +3.63..+4.38。无论哪种情况，这都只是这个伪切分
上的比较，不预测隐藏目标上的名次。在真实文件上配对命令约 30 秒、1 GB（真实数据日志只记录它跑通了，不记录数值）。

10 月 20 日起验证阶段连同答案一起发布（第 11 节），届时可以用真实的留出阶段代替训练阶段作为 `--target`——例如把发布的 T2 心脏
E10.5 作为 `--target`、E9.5 作为 `--reference`，预测只用更早的阶段构造。这仍然是工具包的本地流程，不是主办方的分数。

`python -m vec_local_score.make_pseudo_split` 是可选工具：把一个固定切分导出成文件，供检查或直接调用 veckit 命令行（它只做
10% 抽样，不加参考阶段上限）。它的输出不是 `vec_local_score` 的输入（封装会拒绝它们，否则会抽样两次）。

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
* 限制：每个证据文件 200 MB，每队合计 600 MB（跨所有上传累计；`package --team-uploaded-mb` 会把累计值写进打包 README，
  但账要你自己记）。
* FAQ 原话：框架不是重点，重点是回路中没有人。

`vec_agent_evidence` 把这一切变成机械步骤：产出的是交给主办方的可审计证据包（配置快照、完整性校验、尽力而为的守卫 hook、
审计日志），它本身不能证明运行合规。当前实现面向无头模式的 Claude Code CLI（`claude -p --output-format stream-json`），
需要先安装并登录（第 3 节）；换别的 agent CLI 需要改 `launch.build_command`。Codex CLI 的运行有一个事后打包的最小适配器
`python -m vec_agent_evidence codex-package`（把事件流、rollout、提示词、`AGENTS.md`、harness 文件和预测文件打成同样的三个 zip）；
它没有在真实的 Codex 运行上测试过，详见 `vec_agent_evidence/README.md`。

```
# 0. 用替身 agent 做一次干跑，不需要 CLI 也不调任何 API：证明流水线在你机器上能通
python -m pytest tests/test_evidence.py -q

# 1. 写你的提示词（从 vec_agent_evidence/example_prompt.md 起步：它只解释工作区约定）
# 2. 锁定 + 运行 + 收集，一条命令；看到锁定提示后人就离开
python -m vec_agent_evidence run --task T3 --prompt my_prompt.md --model <完整模型 id> --data-root ./data --hours 8 --max-turns 400

# 3. run_manifest.json 出现后：检查它，然后打上传包
python -m vec_agent_evidence package --run-dir runs/<run_id>
```

（同样的参数换成 `python -m vec_agent_evidence lock ...` 只冻结运行目录并打印将要执行的启动命令，不启动任何东西，适合先检查。
真实数据执行时，`lock` 加 `--data-root ./data` 在几秒内算完了九个发布 `.h5ad` 文件的哈希；PATH 上没有 `claude` 时，它把可执行
文件记为缺失，照样打印命令。`run` 和 `package` 两步不在那次执行范围内。）

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
它的工作区里拥有与你相同的校验器、基线生成器和本地打分器（只读副本）。这里的只读指文件权限，挡不住以 root 身份运行的进程
（很多云容器就是这样）；如果你在意，就用普通用户运行 agent。守卫 hook 和记录下来的哈希在两种情况下都起作用。

人可以做和不可以做的事：锁定前，随意；锁定到 `run_manifest.json` 出现之间，什么都不做（不要打开这次运行的流、工作区或
公开排名）；之后，读 manifest 和 NOTES.md，决定上传哪一次已完成的运行，原样上传文件和 zip，把学到的东西写进下一版提示词
（下次锁定时用 `--note` 记录）。永远不要恢复会话、不要把一次运行的产物喂进另一次运行的工作区、不要编辑提交文件。

## 10. 每次上传前的清单

- [ ] `python -m vec_submit_check --board <榜> <文件>` 打印 `[PASS]`（只是格式；下面三条要你自己确认）。
- [ ] 基因顺序与面板文件一致（校验器会说；门户不会重排）。
- [ ] 细胞数落在该榜 `index.json` 的 `[min_cells, max_cells]` 之内（你是显式传入的）；没有重复细胞；不需要标签。
- [ ] `.X` 与发布数据一样对数归一化（没有 `raw counts` 警告）、有限、非负（每个榜）。
- [ ] T2/T3：`obsm["spatial_3D"]` 存在、(n, 3)、有限。
- [ ] 文件小于 1200 MB。
- [ ] 你清楚这个文件属于哪个榜的标签页（心脏插值和外推是两个不同的榜）。
- [ ] Agent 赛道：`run_manifest.json` 显示 `lock_integrity.ok`、`secret_scan.clean`、`abort: null`，该榜 `uploadable`；
      你上传的预测文件 sha256 与其中记录一致；附上两种证据。
- [ ] 用了外部数据或预训练模型？已在方法总结中披露。

## 11. 最终阶段（2026-10-20 起）有哪些变化

来源（均于 2026-09-30 读取）：时间线页 https://virtualembryo.ai/challenge/timeline（页面自称"权威日程"）、规则页
https://virtualembryo.ai/challenge/rules（第 10、11、13、14 节和 Agent Team 部分）、数据页 https://virtualembryo.ai/challenge/data
以及 FAQ。以官方页面为准；10 月 20 日请重新读一遍。

| 日期（2026） | 发生什么（时间线页） |
|---|---|
| 10-20 | P3 测试阶段开始：每个任务的验证集数据发布，测试输入不带标签发布，测试榜开放 |
| 12-02 | 最终提交截止：提交或提名最终参赛作品的最后时刻；此后的一切都不算，两个赛道都一样 |
| 12-04 | 在隐藏测试集上正式评测，两个赛道都做；Agent Team 的作品按所附证据核查 |
| 12-11 | NeurIPS 现场公布获奖者；最终排名用隐藏测试集，不用开发阶段的榜 |

1. **验证集答案变成开发和训练数据。** P3 开始时，每个任务的验证阶段连同答案一起发布（时间线、FAQ）；数据页说它们届时成为
   "训练材料"。测试集答案永远不发布。届时针对每个隐藏测试目标你手里有（数据页）：

   | 测试目标 | 已发布的训练 / 参考阶段 | P3 随答案发布的验证阶段 |
   |---|---|---|
   | T1 E12.5（外推） | E8.5、E9.5 | E10.5 |
   | T2 心脏 E12.5（外推） | E8.25、E8.75、E9.5 | E8.5、E10.5 |
   | T2 全胚胎 E7.75（插值） | E6.75、E7.25、E8.0 | E7.5 |
   | T3 beta-catenin 敲除 @E8.75 | Mab21l2 敲除 @E9.5；野生型 E8.75、E9.5 | Gata4 敲除 @E8.75（两个重复） |

   规则第 10 节在限制**外部**数据时仍把验证阶段列为保留阶段（例如 T1 不得使用 E9.5 之后到 E13.5（含）的外部数据）；这些对外部
   来源的限制不会失效。如果你的方法依赖于对"已发布的验证文件可以怎样使用"的某种理解，提交前先问主办方——规则本身就鼓励这样做。
2. **每个榜整个阶段只有两次正式提交**（规则第 11 节）：每次提交当场打分并公布，不可撤回；榜上按最好的一次排名。格式检查仍然
   不限次、不花钱，被拒的（不合格的）上传不消耗计分次数，但一个合格却很弱的文件会用掉这个榜本阶段一半的配额。每个文件先在
   本地校验（第 6 节），第一次上传前就想好每个榜交哪两个文件，并把每个上传文件和它的 sha256 一起保存。
3. **打分器的抽样种子。** 主办方在对本工具包的评审中说，抽样种子将随每次提交而定。
4. **测试输入不带标签发布，测试榜有自己的契约。** 工具包 `data/panels/` 里的副本是 2026-09-30 时的验证榜。测试榜公布后，把新的
   `panels/index.json` 和基因列表下载到 `data/panels/`（或用 `VEC_PANELS_DIR` 指向它们）；`vec_submit_check`、基线写入器和 Agent
   赛道的锁定（`--boards <测试榜 key>`）都从那里读取榜的 key 和细胞数范围，不需要改代码。请重新核对每个测试榜的 `min_cells` /
   `max_cells`：超出范围的上传会被门户拒绝。
5. **最终排名用隐藏测试集**（规则第 13 节），不看验证榜。只有最终成绩超过同样几个榜上地板作品成绩的队伍才有获奖资格（地板在
   每个榜上是 50 分，三个任务合计要超过 150）；获奖者可能被要求提供足以复现结果的文档或代码，并须在 14 天内提交书面方法报告
   （第 14-15 节）。Generality Award 颁给用同一个共享架构回答至少两个任务的方法，需要在方法总结里说明。
6. **提名与证据。** 12 月 2 日是提名最终参赛作品的最后时刻（时间线）。Agent Team：提名参评的最终作品必须带着证据，没有证据的
   可以留在榜上但没有获奖资格；每份提交在附上至少两种证据（其中一种必须是 trajectory）之前都处于挂起状态；每份提交都要写明
   实际运行的框架和模型字符串；预测文件必须由 agent 写出——被人改过的文件不是 Agent 作品（规则 Agent Team 部分和第 14 节）。
   在主办方 12 月 4 日开始核查之前，不要动任何运行目录；上传包用 `python -m vec_agent_evidence package`（Claude Code 运行）或
   `codex-package`（Codex 运行，第 9 节）生成。
