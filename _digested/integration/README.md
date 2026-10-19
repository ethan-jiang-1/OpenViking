# integration/ — 外部接入面

> **基线**：OpenViking `v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。本目录回答一个问题：**另一个 agent 或宿主应用，怎么把 OpenViking 当上下文/记忆后端接进去？**

## 与官方文档的关系

官方 `docs/en/agent-integrations/`（**19 篇** + **820 行** capability reference）已经把"每个 harness 怎么装"写得很全。本目录**不重复安装指南**，做的是官方文档不做的事：

- 把散在 19 篇文档 + 源码里的接入方式压成少数心智模型（server-first、**七种形态**、**20 工具**集中定义）
- 记录源码级锚点与官方文档口径的对应关系
- 拦截误解（"进程内插件不需要 server"、"client 在 openviking.client 里"这类想当然）

## 篇目

| 篇 | 回答什么 |
|---|---|
| [01-start-here.md](01-start-here.md) | 10 分钟判断：接入前提（连 server :1933）、**七种形态**（含 OpenViking Gateway）、怎么选、九个易误解点 |
| [02-ov-cli-reference.md](02-ov-cli-reference.md) | `ov` CLI 全量命令参考：~18 组 / 110+ 子命令、5 个纯本地命令、与 docs 的 3 处缺漏、agent 对接暗规则 |
| [03-server-topology.md](03-server-topology.md) | server 内部拓扑：lifespan 十步装配、27 router + 特殊入口面、20 个 MCP 工具权威清单、六层中间件、鉴权与进程内后台任务 |

## 待建

- **OpenViking Gateway 专篇**（v0.5.0 新增的第七形态现在只有 01 里的一节；它的 context profile / upstream / gateway key 三个概念、工具循环与压缩时机值得独立拆解）
- coverage-and-parity：以官方 `16-capability-reference.md` 为对照系的源码级核验（不重复造表，只核验 + 补源码锚点）
- 事件与召回管道：auto-recall / capture / commit 的端到端时序
- 三语言 SDK 功能面对比（部分内容已先行折入 [01](01-start-here.md) 状态标注段，本篇做完整对比）
