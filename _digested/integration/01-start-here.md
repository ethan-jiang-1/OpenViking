# 01 Start Here：先判断怎么接

> **基线**：OpenViking `v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。`ethan` 分支已搬迁到 `v0.5.0` 源码之上，**锚点可在工作树直接核对**；官方文档对照 `docs/en/agent-integrations/`。

## 先给结论

OpenViking 可以作为 agent 的长期记忆与上下文后端接入，且**接入前提只有一条：连上一个运行中的 OpenViking server**（HTTP，默认 `http://localhost:1933`，远程使用需要 API key）。在这个前提之上，按宿主形态有**七种**接入方式（v0.5.0 新增第 7 种）：

1. **MCP 透传**（通用）：任何 MCP client 指向 server 内置的 `/mcp` 端点，获得 **20 个 server 端集中定义的工具**
2. **原生进程内插件**（深度最高）：dsh（Cordis 插件）、pi（extension + compaction 接管）、openclaw（ContextEngine 全接管）、hermes（MemoryProvider）
3. **薄 hook**：cursor / trae / zcode 共享 `agent-hook-runtime`，行为核心一致
4. **SDK 库**：Python / TypeScript / Go 三语言 HTTP SDK（LangChain/LangGraph 也走 SDK 形态）
5. **CLI**：`ov` 命令行（~18 组 / 110+ 子命令，全部显式调用、无后台自动行为，详见 [02-ov-cli-reference](02-ov-cli-reference.md)）
6. **便携插件包**：Agent Plugins 1.0（`openviking-memory` skill + MCP 工具的打包规范）
7. **模型网关**（v0.5.0 新增，beta）：`openviking-gateway`——**只改 base URL 和 API key**，任何模型客户端就获得自动召回 + 模型可调 OpenViking 工具 + 会话回存压缩。见下文 §OpenViking Gateway

与 pi-mono 那种"没有 HTTP server、SDK 进程内优先"的形态**正好相反**：OpenViking 是 **server-first** 的——即使是"进程内"插件（dsh Cordis），也仍然通过 MCP proxy 连 server（见官方 capability matrix 中 dsh 行："native Cordis plugin (same process) + MCP proxy"）。**不存在脱离 server 的纯嵌入式 core 用法**。

## 你真正接到的是什么

```
你的 agent / 宿主
   │
   ├─ MCP passthrough ──────► /mcp 端点（20 个工具，server 端集中定义）
   ├─ 原生插件（dsh/pi/…）──► 进程内事件 + MCP proxy
   ├─ 薄 hook（cursor/…）───► agent-hook-runtime + MCP proxy
   ├─ SDK（py/ts/go）───────► HTTP API
   ├─ ov CLI ────────────────► HTTP API（显式命令）
   └─ 模型客户端 ───────────► openviking-gateway :1935 ──► upstream 模型（只走 HTTP 公共 API）
   │
OpenViking server（FastAPI, 默认 :1933）
   │
viking:// 上下文文件系统（resources / user / agent 命名空间）
```

### 前提：server 与默认端点

- 默认端口 **1933**：`openviking/server/config.py:306`（`port: int = 1933`）；**gateway 默认端口 1935**（`openviking_gateway/config.py:17`）
- server 是 FastAPI 应用：`openviking/server/app.py`；MCP session manager 在 app lifespan 内启动（`app.py:380-383`）
- `/mcp` 路由挂载为 GET/POST/DELETE：`app.py:809`（`_ScopedRoute("/mcp", endpoint=create_mcp_app(), ...)`）
- 官方口径："Every integration on this page connects to a running OpenViking server"（`docs/en/agent-integrations/01-overview.md:30`）

### MCP 工具面（20 个，全部定义在 server 端）

工具用 `@mcp.tool` 装饰器定义在 `openviking/server/mcp_endpoint.py`，一处定义、所有透传 harness 共享：

| # | 工具 | 定义锚点 | 备注 |
|---|------|---------|------|
| 1 | `list_users` | `mcp_endpoint.py:355` | **v0.5.0 新增**；`include_credentials` 需 ADMIN |
| 2 | `list_groups` | `:393` | **v0.5.0 新增** |
| 3 | `get_acl` | `:407` | **v0.5.0 新增** |
| 4 | `set_acl` | `:417` | **v0.5.0 新增** |
| 5 | `find` | `:449` | |
| 6 | `search` | `:509` | |
| 7 | `read` | `:852` | |
| 8 | `list` | `:1005` | 输出**不含** abstract |
| 9 | `tree` | `:1087` | v0.5.0 新增 `include_abstract`（上限 1024 字符，`:1069`） |
| 10 | `remember` | `:1167` | |
| 11 | `write` | `:1203` | |
| 12 | `edit` | `:1250` | |
| 13 | `add_resource` | `:1422` | |
| 14 | `add_skill` | `:1727` | **v0.5.0 新增**；MCP 上唯一能建 skill 的工具 |
| 15 | `list_watches` | `:1898` | |
| 16 | `cancel_watch` | `:1931` | |
| 17 | `grep` | `:1975` | 参数只有 `uri/pattern/case_insensitive/node_limit`——**没有** `before_context`/`after_context`（REST/Rust/Python 都有） |
| 18 | `glob` | `:2050` | |
| 19 | `forget` | `:2079` | |
| 20 | `health` | `:2095` | |

**v0.5.0 的行为级变更**（不只是数量）：

- 全部工具声明了 MCP `ToolAnnotations`（`:254-285`）；`search`/`remember`/`write`/`edit` 标 `destructiveHint=true`。
- 业务错误统一转成 `CallToolResult(isError=True)`，带结构化 `{code, message, details}`——由 `_mcp_error_results`（`:298-352`）在**保留原 `@mcp.tool` 注册**的前提下替换线上 handler。docstring 原话："the literal `@mcp.tool` registrations below are the authoritative list"（`:5-7`）。
- 服务启动时日志输出 `len(tools)` 而不是硬编码数字（`:2200-2203`）——upstream 自己也把工具数当成会变的东西了。
- **官方口径变了**：v0.4.19 的 "future updates will be centrally published there" **已删除**，改为 "A server upgrade can add tools without a plugin release; reconnect the client to see them"（`docs/en/agent-integrations/16-capability-reference.md:81`）。官方名册 `:85-90` 也是 20 个。

> ⚠️ **计数陷阱**：`grep -c '@mcp.tool'` 会数出 23——因为 `_mcp_error_results(structured_output=False|True)` 两种变体把装饰器写了两遍。**工具数以"有多少个 `async def` 被 `@mcp.tool` 注册"为准 = 20**（用 AST 或 `re: @mcp\.tool\([^\n]*\)\s*\n(?:@[^\n]*\n)*async def` 数）。

## OpenViking Gateway（v0.5.0 新增，第七种形态）

**定位**：给"装不了插件、也不想跑 MCP server"的客户端——聊天应用、SDK 脚本、低代码平台。客户端只改两处：base URL 指向 gateway，模型 provider 的 API key 换成 gateway key。**不装插件、不改代码、不改 prompt。**

| 能力 | 网关做什么 |
|---|---|
| 自动召回 | 每条新用户消息先搜 OpenViking，把相关记忆追加进这条消息再发给模型；后续请求把内容放回原位置，**保住 provider 的 prompt cache** |
| 模型驱动记忆 | 模型调 OpenViking 工具（搜/读/写/导入），**网关自己执行**并把结果喂回模型，客户端只看到一段连续回复 |
| 保存与压缩 | 会话回存 OpenViking 抽取新记忆；接近上下文窗口时，网关让同一个模型写摘要替换前段 |

**工程事实**：

- 独立进程 `openviking-gateway`（`pyproject.toml:216`），**默认 `127.0.0.1:1935`**（`openviking_gateway/config.py:17`），版本号独立硬编码 `0.2.0`（`openviking_gateway/__init__.py:5`，不走 setuptools_scm）。
- 纯 Python ASGI（FastAPI + aiohttp + orjson + sqlite3 + Fernet），约 **6,984 行**。
- **与内核零代码耦合**：`grep -c "from openviking" openviking_gateway` = **0**，只走 HTTP 公共 API；服务端仅在 `/api/v1/admin/gateway/{path}` 做管理代理（`server/routers/gateway.py:21`）。
- 状态自持：两个加密 SQLite 文件（`storage.py:27` `SCHEMA_VERSION = 5`；管理数据 Fernet 加密 `:46-53`），30 天无活动清理会话态；OpenViking 挂了会话继续（无记忆，保存自动重试）。
- 三套协议：Anthropic Messages / OpenAI Chat Completions / OpenAI Responses，**原样转发**不做互转；显式拒绝 WebSocket（`app.py:421-426`）。
- extras：`gateway` / `gateway-fast`（`pyproject.toml:92-101`）。
- **不是 VikingBot Gateway**：那个是 `vikingbot gateway`，另一个组件（`docs/en/guides/15-gateway.md:23`）。
- 官方文档：`docs/en/guides/15-gateway.md`（怎么用）+ `22-gateway-operations.md`（部署运维）+ `docs/en/api/25-gateway.md`（管理 API）。

**不适合**：用订阅账号直接登录的客户端（要走订阅则把 CLIProxyAPI 之类挂成 upstream，并自担条款风险）；Cursor / Trae 这类模型请求从厂商服务器发出的客户端。

## 七种形态怎么选（按宿主类型）

| 你的宿主 | 选什么 | 理由 |
|---|---|---|
| Claude Code / Codex / Cursor / TRAE / OpenCode / zcode 等 MCP client | 官方对应插件（MCP 透传 + 生命周期 hook） | hook 提供 auto-recall / auto-capture，光连 MCP 只有工具面 |
| DSH | `@deepseek-ai/dsh-mcp-client` + Cordis 插件（进程内，`mcp__openviking__` 前缀） | 官方有专门的 Memory Bundle（docs 17-dsh.md） |
| pi | 原生 extension（**0.4.0 起改为 MCP 透传 `openviking_<tool>`** + compaction 接管） | pi 与 openclaw 都接管宿主 compaction：pi 是 extension 级 takeover（默认开启），openclaw 是 `ownsCompaction:true` 的全量 ContextEngine 接管（官方 capability matrix 两行均 ✅）。**v0.5.0 breaking**：pi 删掉自己那 7 个手写 `viking_*` REST 工具，改走官方 MCP 客户端，工具名一律 `openviking_<tool>`（`viking_search` → `openviking_search`），**无别名期**。`--tools`/`--exclude-tools` 按精确名匹配，旧 allowlist 会**静默丢工具** |
| 聊天应用 / 低代码平台 / 装不了插件的 SDK 脚本 | **OpenViking Gateway** | 只改 base URL + key，网关负责召回/工具执行/回存 |
| LangChain / LangGraph | SDK 形态（retriever / tools / store / middleware） | 库级集成 |
| 自研 agent / 其他语言 | 三语言 SDK 或直接 HTTP API | 最薄的集成面 |
| 人工操作 / 脚本 | `ov` CLI | 全部显式调用 |

完整对照矩阵官方已维护：`docs/en/agent-integrations/16-capability-reference.md`（**820 行**，含工具面 / hook 面 / shutdown×提交语义 / 配置分层）——**这是官方自己维护的 parity 表**，本目录后续的 coverage 文档以它为对照系，不重复造表。

## 容易误解的点

1. **`openviking.client` 是三层兼容链，真身在独立包 `openviking-sdk`**。推荐的导入是 `from openviking_sdk import SyncHTTPClient`（核心类在 `sdk/python/openviking_sdk/client.py:298` `AsyncHTTPClient` / `:2199` `SyncHTTPClient`，依赖仅 httpx）；主包 `openviking` 反而是 SDK 的**消费者**（`pyproject.toml:33` `openviking-sdk>=0.1.9`），`from openviking import SyncHTTPClient` 只经 `openviking_cli/client/_http_compat.py:113/201` 的子类垫片转发，是兼容路径。
2. **`ov` 命令是 Rust 二进制，不是 Python**。PyPI wheel 里的 `ov`/`openviking` 入口只是几十行的 `execv` 包装器（`openviking_cli/rust_cli.py:42`，按 dev target → wheel 自带 → PATH 顺序找二进制）；pyproject.toml:198 注释原话「放弃 python CLI」，Python 版 CLI 已退役（只剩 `doctor`）。真正的命令面在 `crates/ov_cli/src/commands/`（20 个模块），另有 npm 分发 `@openviking/cli`。
3. **MCP `write` 不支持写 skill，但 MCP 有了 `add_skill`（v0.5.0 反转）**。旧结论"skill 只能走 openclaw 的 `add_skill`、`ov add-skill` 或 REST API"**作废**——server 端 `mcp_endpoint.py:1727` 现在原生提供 `add_skill`。`write`/`edit` 仍拒绝 skill 包内的文件（`write` 的 docstring `:1222` 原话："a plain write skips installation, so the skill's abstract, overview and source metadata go stale. Change a skill with the add_skill tool."）。
4. **`forget` 无类型边界但有命名空间保护**：MCP `forget` 不区分 memory/resource/skill，但 storage 层拒绝删除裸 `viking://`、`viking://user`、`viking://agent` 根（官方脚注 ²，见 §3.5 类型边界）。
5. **"进程内"不等于"不连 server"**：dsh Cordis、pi extension 等原生插件仍通过 MCP proxy / HTTP 连 server；进程内的是事件挂钩与召回注入，不是存储引擎。
6. **安装器现在默认装 `ov` CLI**：统一的 `curl -fsSL https://openviking.ai/install | bash`（`examples/memory-plugin-shared/install.sh:3-5`）覆盖 Claude Code、Codex、Cursor、TRAE/TRAE CN、TraeCode CLI 2.0、**ZCode**、**Kimi Code**、OpenCode、pi、DSH；`ov` 从 npm 包 `@openviking/cli` 默认装上（`install.sh:10-11,229`）。**新增两个一等宿主：Kimi Code（peer id 形态 `kc-<id>`）与 ZCode**；`zcode`/`trae`/`cursor` 的插件已合并到共享的 `agent-hook-plugin`。
7. **`POST /api/v1/sessions/{session_id}/used` 已删除（v0.5.0）**，无替代、无 changelog 记录——依赖它记账的集成会**静默失去数据**。
8. **agent-plugins 走 stdio 代理不是技术落后**：server 原生就是 streamable HTTP `/mcp`，但 Agent Plugins 1.0 规范禁止静态 `mcp.json` 携带部署 URL 和凭证，所以 stdio 代理在运行时解析 `OPENVIKING_URL`/`~/.openviking/ovcli.conf` 再转发（`agent-plugins/servers/mcp-proxy.mjs:4`、`agent-plugins/README.md:32-34`）。
9. **冷门但完整的路径：WebDAV**。`/webdav/resources`（`openviking/server/routers/webdav.py:26`）让文件系统客户端直接挂载 OpenViking。

## 成熟度分层（别把实验路径当 supported 面）

| 层 | 内容 | 证据 |
|---|---|---|
| 成熟 / 官方推荐 | HTTP API + Python SDK（主包硬依赖）、内置 `/mcp`、`ov` + `openviking-server` 两个 CLI、Claude Code / Codex memory plugins | docs 主推矩阵 + `pyproject.toml:33` |
| 正式但较新 | TS / Go SDK、agent-plugins 1.0 包、`langchain-openviking`、Web Studio、**OpenViking Gateway（自标 beta，独立进程）** | 各自 package/module 独立存在，有测试 |
| 示例 / 实验 | `examples/pi-experimental-context-management`（README 明写 "EXPERIMENTAL, not a supported product"）、社区插件、OpenViking Helper（beta）、`ov add-memory` / `ov search`（experimental 标记） | `examples/pi-experimental-context-management/README.md:3-4`、`16-capability-reference.md:633-635` |

注意一个位置与定位的反差：**大量 harness 插件放在 `examples/` 目录**（claude-code、codex、cursor、pi、dsh、openclaw…），但由官方 `install.sh` 一键安装、CI 覆盖、docs 主推——位置上是 example，定位上是产品。判断成熟度看文档定位与测试覆盖，不看目录名。

## 状态标注

- 硬事实：以上所有锚点均在 `v0.5.0` tag 快照逐个核对过（2026-10-19；源码 grep + 官方文档交叉印证 + 四个只读取证 agent）
- 反转记录（2026-10-19，v0.5.0）：MCP 15→20 工具；新增 `add_skill`（旧"MCP 不能建 skill"作废）；新增第七形态 OpenViking Gateway；pi 工具名改 `openviking_<tool>`；安装器默认装 CLI；新增 Kimi Code / ZCode 宿主；`sessions/{id}/used` 删除
- 已由取证补全（原料见 [`../_notes/integration-evidence.md`](../_notes/integration-evidence.md)）：REST 路由清单（`app.py:645-669` 共 25 个 router = 24 业务 + bot；`:686` 另按配置注册 oauth_router，全文件 26 个注册点）、认证插件面（`AuthPlugin` 抽象 + 仓内 5 个插件 dev/api_key/trusted/oidc/ldap，包导入时全部注册——前 3 个无条件、oidc/ldap 依赖可用时条件注册）、agent-plugins 1.0 规范细节、三语言 SDK 对比（Go 103 方法覆盖最全 / TS 0.1.0 无 Session 对象 / Python 最稳且是主包硬依赖）、`langchain-openviking` 独立包、`ov` CLI = Rust 二进制 + execv 包装
- 仍待取证：`/api/v1` 各 router 的端点级清单（24 分册 API 文档已存在，未逐个核对）、`vikingbot` CLI、`examples/` 下各 harness 插件的行为细节
- 证据明确排除：`crates/ragfs` 不是面向外部的接入路径（内部文件系统抽象）。**注意**：旧文写的 "`RAGFS_IMPL` 切换" 是**死开关**——`RAGFS_IMPL` 只出现在 `crates/ragfs/ORIGIN.md:14-16`，全仓无代码读取点，`third_party/agfs/` 也不存在
