# Trajectory Lens（轨迹阅读器）简要说明

Agent 赛道的一次运行会留下几千行 JSON 日志：模型消息、工具调用、工具输出、token 计数。规则要求把轨迹作为证据上传，主办方也可能审计。
`vec_trajectory_lens` 把这样的日志变成**一个自包含的 HTML 文件**（摘要卡片 + 可筛选的时间线）和**一个摘要 JSON**：队伍可以在挑选
"提交哪一次已完成的运行"之前先看清自己的运行，审阅者不用安装对应的 CLI 也能读懂一次运行。完全离线：HTML 不加载任何外部资源。

```
python -m vec_trajectory_lens <日志文件 | 运行目录或证据包目录 | .zip> --out report.html --json summary.json
    [--framework auto|claude|codex|opencode] [--session ID] [--events events.jsonl] [--redact-env 变量名]
```

能读的格式：

* **Claude Code**：`claude -p --output-format stream-json --verbose` 的输出；CLI 写在 `~/.claude/projects/` 下的会话 JSONL
  （同名目录下的 `subagents/*.jsonl` 会一起读入）；本工具包的运行目录。字段名对照过本工具包自己的启动器和 CLI 写出的会话文件
  （只看结构，没有复制任何内容），测试用合成日志。
* **Codex CLI**：`codex exec --json` 的输出（新旧两种事件格式）、会话 rollout、解压后的 `codex-package` 包。复用
  `vec_agent_evidence/codex.py` 的解析；只在合成日志上测试过，没有真实运行。
* **OpenCode**：`opencode run --format json` 的输出、`opencode export <sessionID>` 导出的 JSON、OpenCode 的数据库
  （只读，只查会话相关的表）、v1.1.x 及以前的 JSON 存储。复用 `vec_agent_evidence/opencode.py`（依据 OpenCode 源码 v1.18.33）；
  只在合成文件上测试过。
* **PantheonOS**：暂不支持。它的文档说明了会话存放位置（`.pantheon/memory/<id>_<name>.jsonl`，每行一个 JSON 对象），
  但没有说明每行的字段，写解析器只能靠猜。

摘要卡片包括：框架和 CLI 版本、出现过的所有模型字符串（多于一个时标出）、轮数（并说明该框架下"一轮"指什么）、按工具统计的调用次数
和失败次数、token 合计（输入 / 输出 / 缓存读 / 缓存写 / 推理；每次模型回复只计一次）、墙钟时间、写入和修改过的文件、
"看起来像联网"的命令（用证据骨架守卫 hook `guard.py` 的同一套正则），以及凭据扫描结果。

凭据：输入文件用 `vec_agent_evidence/common.py` 的同一套凭据模式扫描；写进任何输出的字符串都先脱敏为
`[REDACTED:<模式名>]`，`--redact-env 变量名` 还会脱敏该环境变量的值（比如没有固定形状的网关密钥）。写文件前再扫一遍所有输出，
若仍有凭据形状的字符串，则什么都不写，退出码为 3。报告脱敏了不代表原始日志干净：原始日志仍含凭据时不要原样上传。

局限：它只是读日志，**不能证明**运行是自主的、配置锁定过、无人干预或遵守了规则；联网标记只是命令文本上的正则，
看不到经过混淆或间接的联网；凭据扫描只找"形状像凭据"的字符串和你传入的值。

相关工作：已提交的 **VEC Evidence Check**（Alex Solonsky）离线计算哈希并封存证据包；Trajectory Lens 不做哈希和封存，
只负责把日志变得可读，两者互补。
