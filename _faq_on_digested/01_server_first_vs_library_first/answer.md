# 答案：server-first vs library-first——产品定位决定锚点，锚点决定代价

## 一句话判断

**谁需要"被多个进程共享"，谁就需要 server；谁的目标是"进到别人的进程里当引擎"，谁就要做库。** pi-mono 的被集成物是**控制流**（agent loop 必须跑在宿主进程里、逐 token 流回宿主），OpenViking 的被集成物是**数据**（上下文的存取要跨 agent、跨会话、跨工具共享一致状态）。定位决定锚点：pi 把不可变锚点设在"loop 与宿主同进程"，OpenViking 把不可变锚点设在"一个权威 server 持有全部状态"。

## 逐项对照

| 维度 | pi-mono（library-first） | OpenViking（server-first） |
|---|---|---|
| 被集成物 | 控制流（agent loop、工具执行） | 数据（上下文文件系统 + 向量索引） |
| 推荐接入 | `createAgentSession()` 进程内 SDK | 连 `http://localhost:1933` 的任一客户端 |
| 无 server 能否用 | 能（SDK 进程内就是全部） | **不能**（主包无嵌入式 API，绑定只服务 server） |
| HTTP server | 刻意没有（要 HTTP 自己包一层） | FastAPI 即产品本体（25 个 router，WebDAV 含内 + `/mcp` + 按配置 OAuth） |
| 状态一致性 | 宿主各持 session，无共享需求 | 多 agent / 多会话共享同一棵 viking:// 树 |
| 接入面数量 | 2 条 supported（SDK/RPC）+ 1 条 dev-only（protocol/client/server） | 7 条真实路径（MCP / Agent Plugins / harness 插件 / 3 SDK / REST / LangChain / WebDAV） |
| 原生绑定的角色 | 无（纯 TS/JS 运行时） | 核心（Rust 内容存储 + C++ 向量引擎，缺一不可） |

## 为什么这个差异是必然的

**1. 数据库天然是"共享权威状态"的问题。** OpenViking 的价值主张是"跨 session 复用记忆、多 agent 共享上下文"（`viking://user/{uid}` 的 owner 校验、`agent/skills` 共享根、多写存储 primary+backups）——这些语义要求**有一个进程持有真相**。如果做成嵌入式库，每个宿主进程各存一份，记忆就失去了"复用"的前提。所以 server 不是集成方式的选型，而是产品语义的一部分。

**2. Agent 引擎天然是"控制流与宿主共舞"的问题。** pi 的宿主要接管 TUI 渲染、权限审批、工具注册、事件流——这些都需要在宿主进程内拿到 loop 的控制权（订阅事件、拦截工具调用、steer/abort）。跨进程做这些要么延迟不可接受，要么协议面膨胀到难以维护。所以 pi 把进程内 SDK 做成一等公民，HTTP server 反而是它刻意不做的。

**3. 两边都为锚点付出了对称的代价。**
- pi 的代价：跨语言宿主只能走 RPC 子进程（JSONL 协议面要手动维护）；远程/多客户端共享一个 agent 会话需要另起炉灶（protocol/client/server 三件套，且 v0.85 已降级 dev-only——这条路它试过又收了回去）。
- OpenViking 的代价：没有"轻量试用"——最小集成也要先跑一个 server（Python + Rust + C++ 三个原生层都得就位，`create_agfs_client()` 绑定缺失直接 ImportError）；单机单进程用户也背上了进程间通信的固定开销。

**4. 值得记录的两个"松动"信号**（都还没成气候）：
- pi 曾建 protocol/client/server 三件套想补 server 路线，v0.85 又拆掉重建为 chord 薄适配层并降级 dev-only——说明"给 agent 引擎加 server"连它自己都没走通。
- OpenViking 的 examples/ 里所有 harness 插件都是"hook + MCP proxy"形态——宿主侧仍然只是 server 的客户端，没有出现嵌入式 SDK 的苗头。

## 判据：我该模仿谁

问一个问题：**你的组件被集成时，"状态住在哪"是单进程还是跨进程？**

- 单进程（引擎、运行时、UI 组件）→ library-first：把进程内 API 做到极致，协议面是负债。
- 跨进程（存储、记忆、索引、队列）→ server-first：把 server 的运维面（配置、认证、多写、观测）做到极致，嵌入式模式是幻觉。

pi 和 OpenViking 各自都是这个判据的自洽实现——真正不该学的是中间态：既提供嵌入式 API 又提供 server，结果两边语义分叉（OpenClaw 集成 pi 的教训、pi 建 server 三件套又拆掉的教训，都属于此类）。

## 引用

- pi 侧：`pi-mono/_digested/integration/01-start-here.md`（"pi-mono 没有 HTTP server"）、`06-coverage-and-parity.md`（三件套 dev-only）、`07-chord-and-facets.md`（chord 重建），基线 v0.85.1
- OpenViking 侧：`_digested/integration/01-start-here.md`（~~六种~~ **七种**接入形态 + server-first 结论；"七条"是 integration-evidence §10 按 wire-path 的细分口径，两套分类学勿混）、`_digested/architecture/01-three-languages.md`（三原生层）、`_digested/_notes/integration-evidence.md` §9（反直觉事实清单），基线 `0f77ab56`

---

## 反转记录（2026-10-19，v0.5.0 复核）

**本文的核心对照（pi-mono 刻意不做 server / OpenViking 一切接入必经 server）在 v0.5.0 得到了一个更强的例证**：

- 接入形态从 **6 种变成 7 种**，新增的是 `openviking-gateway` —— 它**不是**对"必须有 server"的背离，而是把这条原则推得更远：网关是**又一个独立的 server 进程**（默认端口 1935，约 7k 行，`grep -c "from openviking" openviking_gateway` = **0**，即与内核零代码耦合），专门给一组 harness 客户端提供统一的 OpenAI 兼容 + MCP 前端。
- 换句话说，pi-mono 用"库 + 宿主"解决扩展性，OpenViking 的解法是**再起一个 server 去挡住接入复杂度**。**两边的哲学在 v0.5.0 里没有靠拢，反而更分开了。**
- 结论本身（server-first vs library-first 是刻意的、系统性的取向差异）不需要修改。

细节见 [`_digested/integration/01-start-here.md`](../../_digested/integration/01-start-here.md) 的 OpenViking Gateway 一节。
