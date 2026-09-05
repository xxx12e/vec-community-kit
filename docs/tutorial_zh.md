# 从零到第一次提交 —— Virtual Embryo Challenge（NeurIPS 2026）

这份教程带一个新手从注册走到"每个榜都有一份被打分的提交"，两个赛道都覆盖，全程使用本工具包。下文所有关于比赛的
事实都来自官方站点（https://virtualembryo.ai/challenge）；如有出入，以官方为准。工具包本身只是通用工具：格式校验器、
官方地板基线的文件生成器、本地打分封装、Agent 赛道的证据骨架。它不包含任何建模建议。

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

## 3. 安装工具包

```
git clone <本仓库> vec-community-kit
cd vec-community-kit
python -m venv .venv && .venv\Scripts\activate        # Windows；其他系统用 source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q                                    # 合成数据测试，不需要比赛数据
```

Python 3.10 及以上；工具只依赖 anndata、numpy、scipy、pandas。本地打分还需要主办方的打分器 veckit（见第 7 节）。

## 4. 读懂每个榜的文件契约

门户按你上传到的榜校验文件。公开契约在 `data/panels/index.json` 和每个榜一份的基因列表里：

| 榜 | 基因数 | 细胞数（最小-最大） | 坐标 | 地板模型 |
|---|---|---|---|---|
| `T1:val`（E10.5） | 32,285 | 1000-5118 | 否 | copy_last |
| `T2:embryo:val_interp`（E7.5） | 498 | 583-5000 | 是 | copy_last |
| `T2:heart:val_extrap`（E10.5） | 500 | 1000-25179 | 是 | copy_last |
| `T2:heart:val_interp`（E8.5） | 500 | 1000-17616 | 是 | copy_last |
| `T3:gata4`（E8.75） | 500 | 1000-7449 | 是 | wt_identity |

合格文件的规则（`vec_submit_check` 检查的正是这些）：

1. 单个 `.h5ad`，不超过 1200 MB。
2. `var_names` 与该榜的基因列表逐元素相等，**顺序也必须一致**。门户不会替你重排。
3. `n_obs` 在该榜的细胞数范围内。细胞数只是样本量，不参与打分；几千个细胞足够（打分器自己的抽样在某些指标上最多用
   2000 个细胞，另一些用 1500 个）。
4. `.X` 有限、可转 float32、与发布数据一样是对数归一化；T2/T3 还必须非负。
5. T2/T3：`obsm["spatial_3D"]` 形状 (n, 3) 或更宽（取前三列），有限。坐标系任意：空间指标对平移和真旋转不变。
6. 不需要细胞类型标签（打分器忽略它们，用自己的冻结分类器给细胞定型）。

基因面板文件：`data/panels/T1__val.genes.txt`（32,285 行）、`T2__heart__*.genes.txt` 和 `T3__gata4.genes.txt`（500 行，
同一面板）、`T2__embryo__val_interp.genes.txt`（498 行）。`index.json` 记录了每份列表的 sha256，副本损坏能被发现。

## 5. 生成地板文件

地板行是官方参考行，按定义正好落在地板（一个榜 100 分里的 50 分）：`copy_last` 原样重提最后一个观测阶段，`wt_identity`
原样重提匹配的野生型。它们是最合适的第一次上传：用一个已知结果把整条流水线跑通。

```
python -m vec_baselines.make_baseline --method copy_last   --board T1:val               --last data/raw/T1/E9.5_RNA.h5ad          --out out/t1_copy_last.h5ad --n-cells all
python -m vec_baselines.make_baseline --method copy_last   --board T2:embryo:val_interp --last data/raw/T2_embryo/E8.0.h5ad       --out out/embryo_copy_last.h5ad --n-cells 5000
python -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_interp  --last data/raw/T2_heart/E8.25_late.h5ad  --out out/heart_interp_copy_last.h5ad --n-cells all
python -m vec_baselines.make_baseline --method copy_last   --board T2:heart:val_extrap  --last data/raw/T2_heart/E9.5.h5ad        --out out/heart_extrap_copy_last.h5ad --n-cells all
python -m vec_baselines.make_baseline --method wt_identity --board T3:gata4             --wt   data/raw/T2_heart/E8.75.h5ad       --out out/t3_wt_identity.h5ad --n-cells all
```

说明：

* `--n-cells`：不给这个参数时写入器会抽样到最多 4000 个细胞（固定种子）。`all` 写入输入的全部细胞（前提是不超过该榜上限）；
  给一个数字就写恰好这么多。若 `all` 超过上限（T1：17,057 个细胞 vs 上限 5118），请给数字，例如 `--n-cells 5000`。
  详见 `vec_baselines/README.md` 的 "The cell-count gotcha"。
* 全胚胎榜可以直接喂 500 基因的心脏同构文件，写入器按基因名映射成 498 基因面板。
* 哪个阶段算 "last" 由你决定；插值榜通常取目标之前紧邻的阶段，外推榜取最晚发布的阶段。
* CLI 会打印写出文件的契约校验结论，只有通过时退出码才是 0。

在 Python 里：

```python
from vec_baselines import io as bio, methods as bm
spec, panel = bio.panel_for_board("T3:gata4")
wt = bio.load_stage("data/raw/T2_heart/E8.75.h5ad", panel)
X, C, info = bm.wt_identity(wt)
report = bio.write_submission(X, C, panel, "out/t3_wt_identity.h5ad", "T3:gata4", n_cells="all")
print(report["ok"], report["info"]["n_obs"])
```

`write_submission` 接受任意（细胞 x 基因）矩阵加坐标：你自己模型的输出也用它写。它按基因名映射列、把负值截到 0、写成
float32，并在返回前校验文件。

## 6. 校验

```
python -m vec_submit_check --board T2:heart:val_interp out/heart_interp_copy_last.h5ad
python -m vec_submit_check --board T1:val out/t1_copy_last.h5ad --json out/t1_check.json
```

输出 `[PASS]` / `[FAIL]` 以及每条错误和警告。退出码 0 = 通过，1 = 不通过，2 = 用法错误（未知的榜或文件不存在）。最常见的
失败：基因顺序不一致（`reorder with the panel file`）、`n_obs` 低于榜的下限、负值或 NaN、缺少 `obsm["spatial_3D"]`、超过文件
大小上限。关于 `obs["celltype"]` 的警告无害；`.X max looks like raw counts` 的警告说明你的矩阵没有做对数归一化。

## 7. 在伪验证切分上本地打分

你无法对隐藏目标打分，但可以在自己手里的数据上复现官方流程：留出一个已发布阶段，用更早的阶段预测它，然后用主办方的
打分器加官方聚合方式算分。工具包对 veckit 做了这层封装。

安装 veckit（主办方的 MIT 代码，本仓库不内置）：

```
pip install git+https://github.com/aristoteleo/veckit.git
# 或：git clone https://github.com/aristoteleo/veckit third_party/veckit    （或把 VECKIT_PATH 指向一个克隆目录）
```

例如在心脏插值榜上留出 E8.75：

```
python -m vec_baselines.make_baseline --method copy_last --board T2:heart:val_interp --last data/raw/T2_heart/E8.25_late.h5ad --out out/pseudo_pred.h5ad --n-cells all
python -m vec_local_score --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --frac 0.1 --seed 0
python -m vec_local_score.seed_summary --task T2 --setting heart --pred out/pseudo_pred.h5ad --target data/raw/T2_heart/E8.75.h5ad --reference data/raw/T2_heart/E8.25_late.h5ad --seeds 0 1 2 3 4
```

T1 用 `--task T1 --target E9.5_RNA.h5ad --reference E8.5_RNA.h5ad`；T3 用 `--task T3 --target <敲除> --wt <同阶段匹配野生型>`。

怎么读：每个阶段抽样 10%，目标一分为二，地板（原样重提参考阶段）按定义是 50，天花板（目标的另一半）是 100；你的预测得到
每个指标的 skill 和一个任务分。刚生成的地板文件正好落在 50.0 —— 这是流水线正常的好证据。本地分数**不是**真实分数的预告；
它只是在同一切分、同一组种子上给你自己的方法排序的工具。请报告多个种子的均值和离散度（`seed_summary`）；差异在一个
标准差以内不算结果。每一列的含义见 `docs/metrics_overview.md`。

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

`vec_agent_evidence` 把这一切变成机械步骤，面向无头运行的编码 agent CLI（目标是 Claude Code 的
`claude -p --output-format stream-json`；换别的 CLI 请改 `launch.build_command`）：

```
# 0. 用替身 agent 做一次干跑，不调任何 API：证明流水线在你机器上能通
python -m pytest tests/test_evidence.py -q

# 1. 写你的提示词（从 vec_agent_evidence/example_prompt.md 起步：它只解释工作区约定）
# 2. 锁定 + 运行 + 收集，一条命令；看到锁定提示后人就离开
python -m vec_agent_evidence run --task T3 --prompt my_prompt.md --model <完整模型 id> --data-root ./data --hours 8 --max-turns 400

# 3. run_manifest.json 出现后：检查它，然后打上传包
python -m vec_agent_evidence package --run-dir runs/<run_id>
```

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

运行期间 hooks 会拒绝：任何网络访问、读取 CLI 的配置目录、引用其他运行目录、绕过 `tools/finalize_submission.py` 直接写
`submission/`（该工具会校验、哈希并登记每个定稿文件）、修改只读的工具和数据、以及杀进程命令。agent 在它的工作区里拥有与你
相同的校验器、地板行生成器和本地打分器（只读副本）。

人可以做和不可以做的事：锁定前，随意；锁定到 `run_manifest.json` 出现之间，什么都不做（不要打开这次运行的流、工作区或
公开排名）；之后，读 manifest 和 NOTES.md，决定上传哪一次已完成的运行，原样上传文件和 zip，把学到的东西写进下一版提示词
（下次锁定时用 `--note` 记录）。永远不要恢复会话、不要把一次运行的产物喂进另一次运行的工作区、不要编辑提交文件。

## 10. 每次上传前的清单

- [ ] `python -m vec_submit_check --board <榜> <文件>` 打印 `[PASS]`。
- [ ] 基因顺序与面板文件一致（校验器会说；门户不会重排）。
- [ ] 细胞数在榜的范围内；没有重复细胞；不需要标签。
- [ ] `.X` 与发布数据一样对数归一化（没有 `raw counts` 警告）、有限、T2/T3 非负。
- [ ] T2/T3：`obsm["spatial_3D"]` 存在、(n, 3)、有限。
- [ ] 文件小于 1200 MB。
- [ ] 你清楚这个文件属于哪个榜的标签页（心脏插值和外推是两个不同的榜）。
- [ ] Agent 赛道：`run_manifest.json` 显示 `lock_integrity.ok`、`secret_scan.clean`、`abort: null`，该榜 `uploadable`；
      你上传的预测文件 sha256 与其中记录一致；附上两种证据。
- [ ] 用了外部数据或预训练模型？已在方法总结中披露。
