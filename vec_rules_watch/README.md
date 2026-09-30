# vec_rules_watch - VEC rules and contract watch (en / 中文在下面)

Once a day, a GitHub Action in this repository reads the Virtual Embryo Challenge's public pages, the board contract,
the phase endpoint and the organisers' scorer on GitHub. When something changed, it commits a dated entry to
[`rules-watch/CHANGES.md`](../rules-watch/CHANGES.md) (English) and
[`rules-watch/CHANGES.zh.md`](../rules-watch/CHANGES.zh.md) (Chinese), and for a change of the contract, the phase or
the scorer it also opens an issue with the label `rules-watch`. The aim: every team learns within a day when the
rules, the dates, the file contract or the scorer move, above all around the final-phase switch on 2026-10-20
(validation answers released, test boards open, two official submissions per board).

It is a watcher, not a source: the organisers' pages are authoritative, and it does not interpret the rules.

## What it watches

| source | where | how it is compared |
|---|---|---|
| 27 pages | overview, rules, terms, FAQ, timeline, prizes, community award, publish, data, tasks (4 pages), reference rows, community resources, evaluation (3 tasks x task / submissions / scoring / resources) under https://virtualembryo.ai/challenge | server HTML, the `<main>` element only, split into sections by heading (h1-h4); per section: lines added / removed and short excerpts |
| board contract | https://virtualembryo.ai/challenge/panels/index.json and every gene list it names | canonical JSON (sorted keys), stored in full; rule-based "what this changes for your file" lines |
| phase endpoint | https://kg.virtualembryo.ai/challenge/phase (the endpoint the site's own JavaScript calls) | canonical JSON, stored in full; rule-based lines |
| official scorer | https://github.com/aristoteleo/veckit through the GitHub API | default-branch head (sha, date, subject), version in `pyproject.toml`, branches, tags, releases |
| site links | every link under /challenge on the watched pages (navigation and footer included) | a new link is reported, marked when no watched page covers it, so a new page (say, a final-phase page) is noticed |

Every page URL came from the site navigation (read 2026-09-30); every watched page had its text in the server HTML
(checked with curl), so no browser or Playwright is needed. The list is `watchlist.json`.

Not watched: the leaderboard (it moves with every submission), the submit and account pages and the data manifest
(sign-in), the list of filed community resources (the page loads it with JavaScript after the HTML), the data files,
emails, Discord and Slack.

## What the changelog says

For the **contract** the lines are rule-based, in both languages, each with "What this changes for your file":
boards added or removed; the gene panel of a board (list, order, `n_genes`, `genes_sha256`, `genes_file`, with up to
10 added / removed gene names); `min_cells` / `max_cells`; `obsm_required`, `obs_required`, `needs_coords`; anchors
(floor and ceiling per metric, metrics added or removed); the stage in a board's label; and whether a published gene
list still matches `genes_sha256` in `index.json`. The **phase** lines cover `phase`, `board`, `daily_quota`,
`accepts_submissions`, `shows_scores`, `nominations_open`, `data_open`, `split` and `note`; the **scorer** lines the
default-branch head, the version, tags, releases and other branches. A field the rules do not know still gets a
generic `field: old -> new` line, so a new field cannot slip through.

For **pages**: which sections changed, were added, removed or renamed, how many lines were added and removed, a
short excerpt of each changed line (at most 200 characters, cut around the changed part; at most 6 per section and
24 per page) and the link. Each page type has one fixed hint line (for example the timeline: "Dates may have moved").

The Chinese file is written from fixed templates (`messages.json`, English and Chinese side by side); nothing is
machine-translated. The organisers' own words (board labels, excerpts, commit subjects) are quoted in English in both
files.

## How to subscribe

* **Issues** (contract, phase and scorer changes): on the repository page, Watch > Custom > Issues. Each such change
  opens an issue with the label `rules-watch`:
  https://github.com/xxx12e/vec-community-kit/issues?q=label%3Arules-watch
* **RSS / Atom** of the changelog only (every change, pages included):
  https://github.com/xxx12e/vec-community-kit/commits/main/rules-watch/CHANGES.md.atom
* **Read it**: [`rules-watch/CHANGES.md`](../rules-watch/CHANGES.md), newest first.

## Use the live contract with the validator

`rules-watch/contract/panels/` is a drop-in panels directory (index.json plus the gene lists), refreshed within a
day of a change:

```
VEC_PANELS_DIR=rules-watch/contract/panels python -m vec_submit_check --board <board key> pred.h5ad
```

The kit's own `data/panels/` stays the copy that was tested with the kit. When the test boards appear, this is the
quickest way to validate against them.

## Run it yourself

Standard library only, Python 3.10+ (no anndata, no numpy).

```
python -m vec_rules_watch run --state .rules-watch-state --out rules-watch      # what the Action runs
python -m vec_rules_watch run --state st --out my-watch --only contract,phase    # a subset: contract, phase, scorer, page, page:<id>
python -m vec_rules_watch diff rules_old.html rules_new.html                      # two saved pages, no network
python -m vec_rules_watch diff old/index.json new/index.json --lang zh            # gene lists next to each index.json are read too
python -m vec_rules_watch diff old_out/ new_out/                                  # two --out directories
```

`run` exits 0 even when a source cannot be fetched (the error goes into `status.json` and the entry; `--strict`
exits 3 instead). `diff` exits 1 when it printed differences, 0 when there were none. A full run makes about 42
requests with a 1.5 s pause between two requests to the same host: about one minute.

## Output (`rules-watch/`, committed by the Action)

| file | content |
|---|---|
| `CHANGES.md`, `CHANGES.zh.md` | the changelog, newest first |
| `status.json` | every source and its fetch status; an error is kept with the date it began (`failing_since`) |
| `pages/<id>.json` | per page: URL, sha256 of the normalised text, and per section: heading, sha256, line and character counts |
| `contract/panels/index.json` + `*.genes.txt` | the board contract, in full |
| `contract/phase.json` | the phase endpoint, in full |
| `scorer/veckit.json` | the scorer repository's state |
| `site-links.json` | the links under /challenge found on the watched pages |

Nothing in it depends on the time of the run, so a run that finds nothing changes no file and makes no commit.

## Copyright and courtesy

By default the public output does **not** mirror the organisers' page text: it holds headings, hashes, counts and
short excerpts of changed lines with a link to the page. The full normalised text needed for the next day's line
diff lives in the GitHub Actions cache of this repository (restored at the start of a run, saved after the commit).
If the cache is gone (GitHub evicts an entry after 7 days without use), the next run compares the public
per-section hashes instead: it names the changed sections without quoting them, re-baselines, and says so in the
entry.

Storing the full text in the repository is a switch, **off by default**: `--full-text`, or the repository variable
`RULES_WATCH_FULL_TEXT=true` for the Action. We asked the organisers whether mirroring is fine and will only switch
it on if they agree. Switching it off removes the text files from the current tree (not from git history). The
machine-readable contract (index.json, gene lists, phase JSON) is stored in full: it is published for tools to read.

Politeness: one scheduled run a day (06:17 UTC) plus manual runs; the User-Agent names this repository
(`vec-community-kit-rules-watch/2026.10 (+https://github.com/xxx12e/vec-community-kit)`); 1.5 s between requests to
the same host; one retry after 10 s on a timeout, 429 or 5xx; robots.txt is read for virtualembryo.ai and
kg.virtualembryo.ai (on 2026-09-30 it had no Disallow rule and no content signal). GitHub API calls use the
workflow's `GITHUB_TOKEN`, which is sent to api.github.com only.

## Limits

* It reads server-rendered HTML. If the site moves a page's text into client-side JavaScript, the text shrinks:
  under 300 characters the run records an error ("page text too short"), not a change; a partial move shows up as a
  large change.
* Only `<main>` is read. Navigation, header, footer and the "On this page" box are ignored, and so are images,
  figures drawn as SVG, link targets and buttons: a change only in a link URL or a figure is not detected.
* Sections are keyed by heading. A heading renamed with the same body is reported as renamed; renamed and edited at
  once, it shows as one section removed and one added.
* A gene list that cannot be fetched (for example a new board listed before its list is public) is recorded as a
  fetch error; the board change itself is still announced, and the previous copy of that list, if any, is kept, so
  the validator refuses that board from `rules-watch/contract/panels/` until the new list arrives.
* It is a text diff: it says which lines changed, not what they mean. "What this changes for your file" exists for
  the contract, the phase endpoint and the scorer only; for a page, read the page.
* Once a day: a change made and reverted between two runs is missed, and GitHub may start a scheduled run late.
  GitHub also disables scheduled workflows after 60 days without repository activity (the challenge ends
  2026-12-11).
* Tested with synthetic fixtures (`python -m pytest tests/test_rules_watch.py -q` -> `31 passed`, no network) and by
  two live runs from a home connection on 2026-09-30 (42 requests each, no fetch error, the second run found no
  change, so the normalised text is stable from one request to the next). **Not yet run inside GitHub Actions** at
  the time of writing: the runner's IP address could be challenged by Cloudflare; the fetcher recognises a challenge
  page and records "blocked by a bot challenge" rather than a change.
* The first Action run after the baseline commit has no cache yet: if nothing changed it seeds the cache silently;
  if a page changed in between, that entry names sections without excerpts.

## Setup on GitHub (repository owner)

1. Settings > Actions > General > Workflow permissions: "Read and write permissions" (the job commits
   `rules-watch/` and opens issues). If the default branch is protected against direct pushes, allow
   `github-actions[bot]` or the commit step fails.
2. Actions tab > "rules-watch" > "Run workflow" once, to check that the runner can reach the site.
3. Optional repository variables (Settings > Secrets and variables > Actions > Variables):
   `RULES_WATCH_FULL_TEXT=true` stores the full page text (only with the organisers' agreement);
   `RULES_WATCH_ISSUES=false` turns the issues off.

Related community work (filed for the Community Contribution Award before this one): VEC Evidence Check (Alex
Solonsky), VecBench (Arjun Kode), Intuition Lab and External Data Catalog (Ivan Habib), h5ad Inspector and ScoreLens
(Caden Tan), Submission Viewer (Shashwat srivastava), vec-submit-check (Wei Dai). None of them watches the rules or
the contract; the contract copy here can feed any validator that reads `index.json` and the gene lists.

---

## 中文说明

每天一次，本仓库的 GitHub Action 读取 Virtual Embryo Challenge 的公开页面、榜契约、阶段接口，以及主办方在 GitHub
上的打分器。发现变化时，它把一条带日期的记录提交到 [`rules-watch/CHANGES.zh.md`](../rules-watch/CHANGES.zh.md)（中文）和
[`rules-watch/CHANGES.md`](../rules-watch/CHANGES.md)（英文）；如果变的是榜契约、阶段或打分器，还会开一个带
`rules-watch` 标签的 issue。目的：规则、日期、文件契约或打分器一有变动，每个队伍都能在一天之内知道，尤其是 2026-10-20
进入最终阶段前后（验证集答案发布、测试榜开放、每个榜两次正式提交）。

它只是一个监测工具，不是信息来源：以主办方页面为准，它也不解释规则。

### 监测什么

| 来源 | 位置 | 比较方式 |
|---|---|---|
| 27 个页面 | https://virtualembryo.ai/challenge 下的概览、规则、条款、FAQ、时间线、奖项、社区贡献奖、合作发表、数据、任务（4 页）、参考行、社区资源、评测（3 个任务 x 任务说明 / 提交 / 打分 / 资源） | 服务器返回的 HTML，只读 `<main>`，按标题（h1-h4）切成小节；每个小节给出增删行数和简短摘录 |
| 榜契约 | https://virtualembryo.ai/challenge/panels/index.json 以及它列出的每个基因列表 | 规范化 JSON（键排序），完整保存；按规则生成"对你的文件意味着什么" |
| 阶段接口 | https://kg.virtualembryo.ai/challenge/phase（网站自己的 JavaScript 调用的接口） | 规范化 JSON，完整保存；按规则生成说明 |
| 官方打分器 | 通过 GitHub API 读取 https://github.com/aristoteleo/veckit | 默认分支的最新提交（sha、日期、标题）、`pyproject.toml` 里的版本、分支、标签、发布 |
| 网站链接 | 被监测页面上所有 /challenge 下的链接（包括导航和页脚） | 出现新链接就报告，并标明它是否还没被监测，这样新页面（比如最终阶段的说明页）也能被发现 |

页面地址都来自网站导航（2026-09-30 读取）；每个被监测的页面，其文字都在服务器返回的 HTML 里（用 curl 核对过），
所以不需要浏览器或 Playwright。列表在 `watchlist.json`。

不监测：排行榜（每次提交都会变）、提交页和账户页以及数据清单（需要登录）、已提交的社区资源列表（页面在 HTML 之后用
JavaScript 加载）、数据文件本身、邮件、Discord 和 Slack。

### 变更记录写些什么

**榜契约**的每一行都按规则生成、中英文各一份，并附"对你的文件意味着什么"：新增或移除的榜；某个榜的基因面板（列表、
顺序、`n_genes`、`genes_sha256`、`genes_file`，最多列出 10 个新增 / 移除的基因名）；`min_cells` / `max_cells`；
`obsm_required`、`obs_required`、`needs_coords`；锚点（每个指标的地板和天花板、新增或移除的指标）；榜标签中的发育阶段；
以及发布的基因列表是否仍与 `index.json` 的 `genes_sha256` 一致。**阶段**覆盖 `phase`、`board`、`daily_quota`、
`accepts_submissions`、`shows_scores`、`nominations_open`、`data_open`、`split` 和 `note`；**打分器**覆盖默认分支的
最新提交、版本、标签、发布和其他分支。规则不认识的字段也会得到一行通用的 `字段 由 旧值 改为 新值`，新字段不会漏掉。

**页面**：哪些小节改动、新增、移除或改名，增删了多少行，每条改动行的简短摘录（最多 200 个字符，截取改动附近；每个小节
最多 6 条，每页最多 24 条），以及链接。每类页面有一句固定提示（例如时间线："日期可能变了"）。

中文记录由固定模板生成（`messages.json`，中英文并列），不做任何机器翻译。主办方的原话（榜标签、摘录、提交标题）在两个
文件里都保留英文原文。

### 怎么订阅

* **Issue**（榜契约、阶段、打分器的变化）：在仓库页面点 Watch > Custom > Issues。每次这类变化都会开一个带 `rules-watch`
  标签的 issue：https://github.com/xxx12e/vec-community-kit/issues?q=label%3Arules-watch
* **RSS / Atom**，只包含变更记录的提交（所有变化，包括页面）：
  https://github.com/xxx12e/vec-community-kit/commits/main/rules-watch/CHANGES.md.atom
* **直接看**：[`rules-watch/CHANGES.zh.md`](../rules-watch/CHANGES.zh.md)，最新的在最上面。

### 用最新契约做校验

`rules-watch/contract/panels/` 可以直接当作榜契约目录用（index.json 加基因列表），契约变化后一天之内更新：

```
VEC_PANELS_DIR=rules-watch/contract/panels python -m vec_submit_check --board <榜 key> pred.h5ad
```

工具包自己的 `data/panels/` 仍是和工具包一起测试过的那份。测试榜公布后，这是对照它们校验的最快办法。

### 自己运行

只用 Python 标准库，Python 3.10+（不需要 anndata、numpy）。

```
python -m vec_rules_watch run --state .rules-watch-state --out rules-watch      # Action 运行的就是这条
python -m vec_rules_watch run --state st --out my-watch --only contract,phase    # 只跑一部分：contract、phase、scorer、page、page:<id>
python -m vec_rules_watch diff rules_old.html rules_new.html                      # 比较两个保存下来的页面，不联网
python -m vec_rules_watch diff old/index.json new/index.json --lang zh            # 同目录下的基因列表也会读取
python -m vec_rules_watch diff old_out/ new_out/                                  # 比较两个 --out 目录
```

某个来源取不到时，`run` 仍然返回 0（错误写进 `status.json` 和记录；加 `--strict` 则返回 3）。`diff` 有差异时返回 1，
没有差异返回 0。一次完整运行约 42 个请求，同一主机的两次请求之间停 1.5 秒，大约一分钟。

### 输出（`rules-watch/`，由 Action 提交）

| 文件 | 内容 |
|---|---|
| `CHANGES.md`、`CHANGES.zh.md` | 变更记录，最新的在最上面 |
| `status.json` | 每个来源及其获取状态；出错时记下开始出错的日期（`failing_since`） |
| `pages/<id>.json` | 每个页面：URL、规范化文本的 sha256，以及每个小节的标题、sha256、行数和字符数 |
| `contract/panels/index.json` + `*.genes.txt` | 完整的榜契约 |
| `contract/phase.json` | 完整的阶段接口返回 |
| `scorer/veckit.json` | 打分器仓库的状态 |
| `site-links.json` | 被监测页面上找到的 /challenge 下的链接 |

这些文件都不含运行时间，所以一次什么都没发现的运行不会改任何文件，也不会产生提交。

### 版权与礼貌

默认情况下，公开输出**不**镜像主办方的页面全文：只有标题、哈希、计数和改动行的简短摘录，外加页面链接。第二天逐行比较
所需的完整规范化文本放在本仓库的 GitHub Actions 缓存里（运行开始时恢复，提交之后保存）。如果缓存没了（GitHub 会清除
7 天没用过的缓存），下一次运行改为比较公开的小节哈希：只列出改动的小节名、不引用内容，重新建立基线，并在记录里说明。

把全文存进仓库是一个开关，**默认关闭**：`--full-text`，或在 Action 里设置仓库变量 `RULES_WATCH_FULL_TEXT=true`。我们
已经问过主办方是否可以镜像，只有他们同意才会打开。关掉开关会从当前文件树里删除这些文本文件（git 历史里仍有）。机器可读的
契约（index.json、基因列表、阶段 JSON）完整保存：它们本来就是发布给工具读取的。

礼貌：每天定时运行一次（UTC 06:17），外加手动运行；User-Agent 写明本仓库
（`vec-community-kit-rules-watch/2026.10 (+https://github.com/xxx12e/vec-community-kit)`）；同一主机的请求之间间隔 1.5 秒；
超时、429 或 5xx 时 10 秒后重试一次；读取 virtualembryo.ai 和 kg.virtualembryo.ai 的 robots.txt（2026-09-30 时没有任何
Disallow 规则，也没有 content signal）。GitHub API 调用使用工作流的 `GITHUB_TOKEN`，它只会发给 api.github.com。

### 局限

* 它读的是服务器渲染的 HTML。如果网站把某页的文字改成由浏览器端 JavaScript 生成，文字就会变少：少于 300 个字符时记为
  错误（"page text too short"），不记为变化；只移走一部分时会显示为一次大改动。
* 只读 `<main>`。导航、页眉、页脚和"On this page"框都被忽略，图片、用 SVG 画的图、链接地址和按钮也被忽略：只改了链接
  地址或图的变化检测不到。
* 小节按标题区分。标题改名而内容不变，报告为改名；同时改名又改内容，会显示为移除一个小节、新增一个小节。
* 取不到的基因列表（例如新榜已列出、但它的列表还没公开）记为获取错误；榜本身的变化照样报告，该列表的旧副本（如果有）会
  保留，所以在新列表到来之前，校验器用 `rules-watch/contract/panels/` 会拒绝这个榜。
* 它做的是文本比较：只说哪些行变了，不说意味着什么。"对你的文件意味着什么"只针对榜契约、阶段接口和打分器；页面请自己读。
* 每天一次：两次运行之间改了又改回去的变化会漏掉；GitHub 的定时运行也可能推迟。仓库 60 天没有活动时 GitHub 会停用定时
  工作流（比赛在 2026-12-11 结束）。
* 测试：合成数据的单元测试（`python -m pytest tests/test_rules_watch.py -q` -> `31 passed`，不联网），以及 2026-09-30 从
  家里网络做的两次真实运行（每次 42 个请求，没有获取错误，第二次没有发现变化，说明规范化文本在两次请求之间是稳定的）。
  撰写本文时**还没有在 GitHub Actions 里运行过**：运行器的 IP 可能被 Cloudflare 拦下做人机验证；获取器能认出验证页，会记为
  "blocked by a bot challenge"，而不是记成变化。
* 基线提交之后的第一次 Action 运行还没有缓存：如果没有变化，它会静默建立缓存；如果中间有页面改动，那条记录只列小节名、
  没有摘录。

### 仓库所有者在 GitHub 上的设置

1. Settings > Actions > General > Workflow permissions 选 "Read and write permissions"（任务要提交 `rules-watch/` 并开
   issue）。如果默认分支禁止直接推送，需要放行 `github-actions[bot]`，否则提交步骤会失败。
2. 在 Actions 页面选 "rules-watch" > "Run workflow" 手动运行一次，确认运行器能访问网站。
3. 可选的仓库变量（Settings > Secrets and variables > Actions > Variables）：`RULES_WATCH_FULL_TEXT=true` 保存页面全文
   （只在主办方同意后）；`RULES_WATCH_ISSUES=false` 关闭 issue。

相关的社区工作（在本工具之前已提交社区贡献奖）：VEC Evidence Check（Alex Solonsky）、VecBench（Arjun Kode）、Intuition Lab
和 External Data Catalog（Ivan Habib）、h5ad Inspector 和 ScoreLens（Caden Tan）、Submission Viewer（Shashwat srivastava）、
vec-submit-check（Wei Dai）。它们都不监测规则或契约；这里的契约副本可以提供给任何读取 `index.json` 和基因列表的校验器。
