# 问题：为什么 pi-mono 刻意不做 HTTP server，而 OpenViking 一切接入都必须有 server？

## 背景

两个项目我们都在消化（pi-mono 侧有 `_digested` @ v0.85.1，OpenViking 侧有本仓库 `_digested/` @ `0f77ab56`），发现它们的**接入哲学正好相反**，而且都是刻意的、系统性的，不是偶然：

- **pi-mono**（AI coding agent 平台）：library-first。`createAgentSession()` 进程内嵌入是推荐路径，RPC（JSONL over stdin/stdout 子进程）是第二条路径，README/文档强调**没有 HTTP server** 作为主要集成方式——agent 内核以库的形态被宿主持有。
- **OpenViking**（上下文数据库）：server-first。三语言 SDK 的 README 都自述 "for a running OpenViking server"，主包里没有任何可 import 的本地存储 API，"进程内插件"（dsh Cordis）也仍通过 MCP proxy 连 server。

## 具体困惑

1. 这个差异是产品定位决定的（agent 引擎 vs 数据库），还是有更深的设计理由？
2. 两种取向各自付出了什么代价、换来了什么好处？
3. 边界上有没有例外或松动？（比如 pi 后来长出的 protocol/client/server 三件套、OpenViking 的 lib 模式传闻）
4. 对"我该模仿谁"这个问题，判据是什么？

## 证据边界

- **pi 侧**：只引用 pi-mono 仓库 `_digested/`（v0.85.1 基线）的结论：`integration/01-start-here.md`（SDK/RPC 两路径、无 HTTP server）、~~`integration/06-coverage-and-parity.md`~~（protocol/client/server 第三条路径 dev-only）、~~`integration/07-chord-and-facets.md`~~。**不做 pi 源码的新审计。**
- **OpenViking 侧**：引用本仓库 `_digested/integration/01-start-here.md`、`_digested/architecture/01-three-languages.md`、`_digested/_notes/integration-evidence.md`（`0f77ab56` 基线）。
- 只做"消化材料→判断"的综合，不引入两边材料之外的新断言。
