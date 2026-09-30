# rules-watch/ (generated)

This folder is written by a daily GitHub Action (`.github/workflows/rules-watch.yml`, code in
[`vec_rules_watch/`](../vec_rules_watch/README.md)). It watches the Virtual Embryo Challenge's public pages, the board
contract (`panels/index.json` and the gene lists), the phase endpoint and the organisers' scorer veckit on GitHub.

* [`CHANGES.md`](CHANGES.md) / [`CHANGES.zh.md`](CHANGES.zh.md): what changed, newest first.
* `contract/panels/`: the current board contract; use it with `VEC_PANELS_DIR=rules-watch/contract/panels`.
* `pages/*.json`: per-section headings and hashes of each page (no page text).
* `status.json`: which sources could be fetched.

Subscribe: Watch > Custom > Issues (label `rules-watch`), or the feed
https://github.com/xxx12e/vec-community-kit/commits/main/rules-watch/CHANGES.md.atom . The organisers' pages are the
authoritative text.

本目录由每日运行的 GitHub Action 自动生成，监测比赛公开页面、榜契约、阶段接口和官方打分器。变更记录见
[`CHANGES.zh.md`](CHANGES.zh.md)（中文）和 [`CHANGES.md`](CHANGES.md)（英文），最新的在最上面；说明见
[`vec_rules_watch/README.md`](../vec_rules_watch/README.md)。以主办方页面为准。
