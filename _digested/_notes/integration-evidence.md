# OpenViking 外部接入路径取证报告

> ## v0.5.0 复核登记（2026-10-19）
>
> - **基线**：`v0.5.0` = `20f9c1136`。原锚点基于 `0f77ab56`。
> - **最大缺口：本报告写于 gateway 出现之前。** v0.5.0 新增第七种接入形态 `openviking-gateway`（独立进程，默认 `127.0.0.1:1935`，约 7k 行纯 Python ASGI，与内核零代码耦合），本报告完全没有覆盖——见 [`../integration/01`](../integration/01-start-here.md) 的 §OpenViking Gateway。
> - 其他过时项：MCP 工具 15 → **20**；`sessions/{id}/used` **删除**；`heartbeat` **删除**；pi 工具名改 `openviking_<tool>`；安装器默认装 `ov`；新增 Kimi Code / ZCode 宿主。
> - **仍有效**：`/api/v1` 路由分组结构、`AuthPlugin` 5 插件注册模型（无条件 3 + 条件 2）、三语言 SDK 定位对比、`ov` = Rust 二进制 + execv 包装。


> 只读取证（未执行任何 git 命令）。所有行号均为当前工作区文件的真实行号。
> 标记约定：【硬事实】= 源码/文档可直接验证；【解释】= 由事实推断；【未定】= 证据不足。

## 0. 总览

OpenViking 的架构是「中心化 HTTP server + 多协议前端」。所有接入路径最终都打到同一个
FastAPI server（默认 `http://127.0.0.1:1933`）：
- server 侧：`openviking/server/app.py`（`create_app`），`openviking/server/bootstrap.py:131`（`main`，`uvicorn.run`）
- 文档明说：「Every integration on this page connects to a running OpenViking server」
  — docs/en/agent-integrations/01-overview.md:30-32

---

## 1. MCP

### 1.1 内置 MCP endpoint（streamable HTTP）
【硬事实】
- `openviking/server/mcp_endpoint.py:3-15`：模块 docstring —「Exposes OpenViking tools … to
  Claude Code (or any MCP client) via streamable HTTP」；`openviking/server/mcp_endpoint.py:28`
  `from mcp.server.fastmcp import FastMCP`。
- 挂载点：`openviking/server/app.py:809`（`_ScopedRoute` 定义 `:797`）— `_ScopedRoute("/mcp", endpoint=create_mcp_app(),
  methods=["GET","POST","DELETE"])`；`create_mcp_app` 定义在 mcp_endpoint.py:1538。
- MCP session manager 生命周期绑在 FastAPI lifespan：app.py:388-390（`async with mcp_lifespan()`）。
- 工具清单（`@mcp.tool`，15 个，mcp_endpoint.py:1532-1534 自述）：
  `find`(:249) `search`(:276) `read`(:501) `list`/`ls`(:642) `tree`(:704) `remember`(:780)
  `write`(:805) `edit`(:845) `add_resource`(:999) `list_watches`(:1258) `cancel_watch`(:1290)
  `grep`(:1333) `glob`(:1385) `forget`(:1411) `health`(:1424)。
  注释注明与 vikingbot 工具对齐（mcp_endpoint.py:227）。
- `_apply_portable_schemas()`（mcp_endpoint.py:1514-1519）把 FastMCP 类型提示 schema 改写成
  「portable」schema（压平 Optional/Union），说明作者在意跨 MCP 客户端兼容性。
- MCP OAuth 2.1：app.py:679-686 引入 `mcp.server.auth.routes` 并挂 `oauth_router`；
  `openviking/server/oauth/router.py:224` `/.well-known/oauth-protected-resource`（PRM 文档）、
  :255 `/oauth/authorize/page`（OTP 授权页）、:412 `/api/v1/auth/oauth-verify`。

### 1.2 agent-plugins/（Agent Plugins 1.0 包）
【硬事实】
- `agent-plugins/plugin.json:2-5`：`$schema: agent-plugins.org/schemas/1.0.0`，name=`openviking`，
  v0.1.1，AGPL-3.0。README（agent-plugins/README.md:5）说明该规范由 Amazon、Cursor、Microsoft、
  OpenAI、Vercel 等背书，「any conforming client (Cursor, VS Code, Amazon- and OpenAI-side
  clients, ...)」都能加载 —— 即**不是 Claude Code 或 OpenClaw 专用**，是通用打包格式。
- `agent-plugins/mcp.json:4-8`：声明 stdio MCP server：`node ${PLUGIN_ROOT}/servers/mcp-proxy.mjs`。
- `agent-plugins/servers/mcp-proxy.mjs:4`：「stdio -> streamable-HTTP MCP proxy for the OpenViking
  Agent Plugins 1.0 package」。
- 为什么走 stdio 代理（README.md:32-34）：server 本身已是 streamable HTTP `/mcp`，但
  Agent Plugins 规范的静态 `mcp.json` 不能放 per-deployment URL 和凭证，所以 stdio 代理在运行时
  解析 URL/API key 再转发。
- 凭证链（README.md:38-43）：env（`OPENVIKING_URL`/`OPENVIKING_API_KEY`…）→ `~/.openviking/ovcli.conf`
  → `~/.openviking/ov.conf` → 默认 `http://127.0.0.1:1933` 无鉴权；与 `ov` CLI 同一解析链。
- 技能：`skills/openviking-memory/SKILL.md`（教模型 recall+persist 循环）、
  `skills/ov-memory-troubleshoot/`（只读排障）。README.md:49 明确该包**不含 hooks**，自动
  召回/捕获不在范围内。
- README.md:51-62：有 hooks 的 harness 应改用 examples/ 下的专用插件
  （claude-code-memory-plugin、codex-memory-plugin、opencode-plugin、cursor/trae/zcode…），
  统一安装脚本 `examples/memory-plugin-shared/install.sh`（README.md:53-56）。
- 测试：`agent-plugins/plugin.test.mjs`（`node --test`），CI 覆盖（README.md:71-82）。

### 1.3 直接连 /mcp 的通用 MCP 客户端
【硬事实】docs/en/agent-integrations/06-mcp-clients.md:3-5：「Any MCP-compatible client can
connect to OpenViking's built-in /mcp endpoint — no plugin installation」；:9-21 给出
`mcpServers` JSON 与 Claude Code `--transport http` 示例；:23「No authentication is needed when
connecting to a local server without root_api_key (dev mode)」。

---

## 2. Python SDK

【硬事实】三层结构，容易误解：
1. **真正的 SDK 是独立包 `openviking-sdk`**（`sdk/python/pyproject.toml:6-7`，"Lightweight Python
   HTTP SDK for OpenViking"，依赖仅 `httpx` :10-13）。
   - 核心类：`sdk/python/openviking_sdk/client.py:298` `AsyncHTTPClient`、`:2199` `SyncHTTPClient`、
     `:141` `VikingURI`、`:164` `Session` / `:214` `SyncSession`（session 对象封装
     add_message/batch_add_messages/commit/get_session_context/get_archive，:219-270）。
   - SyncHTTPClient 方法面（client.py:2199-2608+）：`add_resource` `add_skill` `ls`(:2406)
     `tree`(:2442) `read`(:2493) `write`(:2508) `mkdir/rm/mv` `acl_*`(:2549-2567) `find`(:2570)
     `search`(:2588) `search_context`(:2608) `wait_processed`(:2403) 等。
   - 导出面：`sdk/python/openviking_sdk/__init__.py:1-16`（Async/SyncHTTPClient、errors、
     Message/ContextPart 等 options）。
2. **主包 `openviking` 不是 SDK**：`openviking/__init__.py:19-31` 只有 `__getattr__` 懒加载
   `SyncHTTPClient`/`AsyncHTTPClient`；`openviking/client/__init__.py:10-27` 同样从
   `openviking_cli.client` 懒 re-export。主包反而依赖 SDK：pyproject.toml:33
   `openviking-sdk>=0.1.9`。
3. **兼容垫片**：`openviking_cli/client/_http_compat.py:113,201` — `AsyncHTTPClient` /
   `SyncHTTPClient` **继承** `import_openviking_sdk().AsyncHTTPClient/SyncHTTPClient`，只加旧异常
   映射；`openviking_cli/client/http.py:4` 自述「Compatibility shim for the legacy HTTP client
   import path」。

【解释】宿主应用推荐直接 `pip install openviking-sdk` 并 `from openviking_sdk import SyncHTTPClient`；
`from openviking import SyncHTTPClient` 也能用，但那只是兼容路径。官方 quickstart 即此用法：
`examples/quick_start.py:1-25`（先 `openviking-server init` + `openviking-server`，再
`SyncHTTPClient(url="http://localhost:1933")` → add_resource → get_task → ls/glob/read/abstract/overview）。

---

## 3. TypeScript / Go SDK

### 3.1 TypeScript（存在、可构建、已发布配置）
【硬事实】
- `sdk/typescript/package.json`：name=`@openviking/sdk`，version 0.1.0，`main/module/types` 指
  `dist/`（tsup 构建 :23，vitest :25，engines node>=18 :27）。有 package-lock.json、
  `src/`（client.ts/errors.ts/transport.ts/types.ts/node-files.ts）、`tests/`。
- 导出：`src/index.ts:1-2` `OpenVikingClient`、`normalizeURI`、`OpenVikingError`。
- 类：`src/client.ts:74` `export class OpenVikingClient`；方法覆盖 addResource(:132)、skills、
  watches、find(:356)、search(:360)、searchContext(:400)、grep(:440)、glob(:461)、list/tree/stat/
  mkdir/remove/move(:479-548)、read(:554)、write(:588)、batchWrite(:610)、session 管理
  (:674-832)。README.md:3-4「no runtime dependencies」。
【解释】功能面对比 Python：核心（fs/retrieval/sessions/skills/watches）基本对齐；Python 独有的
富类型是 `Session`/`SyncSession` 对象、`Message`/`ContextPart` parts、`uploads.py`、`observer`
命名空间；TS 的 session 操作是 client 上的扁平方法（createSession/commitSession…）而非对象。
版本 0.1.0，成熟度低于 Python。

### 3.2 Go（存在、独立 module、覆盖面最全）
【硬事实】
- `sdk/go/go.mod:1-2`：module `github.com/volcengine/OpenViking/sdk/go`，go 1.22。
- `sdk/go/client.go:14` `type Client struct`、`:27` `func NewClient(cfg Config)`。
- 方法共 **103 个**（`grep '^func (c \*Client)'` 计数），分布在 acl.go、admin.go、
  agent_evolution.go、compile.go、filesystem.go、retrieval.go（Find :9 / Search :54 /
  SearchContext :100 / Grep :151 / Glob :181）、resources.go、sessions.go、skills.go、system.go、
  upload.go、watches.go、pack.go、openviking_assets.go。
- 有 `client_test.go`、`examples/`、README.md + README_CN.md。
【解释】Go SDK 连 admin/agent-evolution/pack 等管理面都有，覆盖面比 TS 还全；README 定位
「HTTP client for a running OpenViking server」。

---

## 4. HTTP API（REST）

【硬事实】
- 路由注册：`openviking/server/app.py:645-669`，25 个 router（24 业务 + bot；2026-09-13 修正：此前写"26 个"且清单漏 `metrics_router`——现已补入，全文件另有第 26 个注册点 `oauth_router`@:686 按配置注册）。前缀清单（各 router 文件首部）：
  `/api/v1/acl`(acl.py:16)、`/api/v1/admin`(admin.py:60)、`/api/v1/agent-evolution`(:17)、
  `/api/v1`+compile(tasks.py 同前缀)(compile.py:13)、`/api/v1/console`(console.py:15)、
  `/api/v1/content`(content.py:103)、`/api/v1/debug`(debug.py:24)、`/api/v1/fs`(filesystem.py:27)、
  `/api/v1/observer`(:21)、`/api/v1/openviking-assets`(:18)、`/api/v1/pack`(pack.py:27)、
  `/api/v1/privacy-configs`(:16)、`/api/v1`(resources.py:25)、`/api/v1/search`(search.py:62)、
  `/api/v1/sessions`(sessions.py:24)、`/api/v1/skills`(skills.py:40)、`/api/v1/snapshot`(:33)、
  `/api/v1/stats`(stats.py:17)、`/api/v1`(tasks.py:25)、`/api/v1/user-settings`(:26)、
  `/api/v1`(watches.py:31)、`/api/v1`(metrics)、`/webdav/resources`(webdav.py:26)、system 无前缀(system.py:24)、
  bot 挂 `/bot/v1`(app.py:669, bot.py:19)。检索核心端点：`POST /api/v1/search/find`(search.py:326)、
  `/api/v1/search`(:427)、`/api/v1/search/recall`（已 @deprecated=True，:490）。
- 认证：`openviking/server/auth/__init__.py:42` `_extract_api_key(x_api_key, authorization)` —
  支持 `X-API-Key` 头和 `Authorization: Bearer`（:174-196 Header 别名）。插件化 auth：
  `auth/plugin.py:19` `AuthPlugin` 抽象基类（第三方可注册）；仓内插件共 5 个：`api_key`(api_key.py:56-62，
  内含 OAuth 2.1 fast path :83-91)、`dev`(dev.py:23-26 — 无鉴权、恒 ROOT、仅限 localhost 绑定)、
  `trusted`(trusted.py:98)、`oidc`、`ldap`（auth/plugins/oidc.py、ldap.py）——5 个都在**包导入时注册**
  （`plugins/__init__.py:8-31`）：前 3 个无条件，oidc/ldap 为 try/ImportError 条件注册（依赖可用才生效）；
  app.py:128-139 对前 3 个再幂等兜底（2026-09-13 精化口径）。
- 启动：`openviking/server/bootstrap.py:131` `main()` → :309 `create_app(...)` → :327-338
  `uvicorn.run("openviking.server.app:create_worker_app")`；`app.py:98` `create_worker_app`
  为多 worker 入口。
- CLI 关系：pyproject.toml:199 `openviking-server = "openviking_cli.server_bootstrap:main"`；
  `openviking_cli/server_bootstrap.py:4-11` — 轻量入口，pre-parse `--config`，`init`/`doctor`
  子命令在进 server 前拦截（:56-58 → `openviking_cli/setup_wizard.py`）。
- API 文档：docs/en/api/ 下 24 个分册（01-overview 到 24-vikingbot），并有 `/openapi.json`
  （web-studio 用它生成客户端，见 §7）。

---

## 5. CLI（两个，不是同一个东西）

【硬事实】
- 入口（pyproject.toml:196-200）：
  - `ov` 与 `openviking` → `openviking_cli.rust_cli:main`，注释原文「Rust CLI 入口（极简包装器）」
    「放弃 python CLI」。
  - `openviking-server` → `openviking_cli.server_bootstrap:main`（Python，起 server）。
  - `vikingbot` → `vikingbot.cli.commands:app`（VikingBot 会话/chat 运行时 CLI）。
- `ov` = **Rust 二进制** `crates/ov_cli`（crate README.md:3-8；要求 Rust >= 1.91.1）。Python 端
  `openviking_cli/rust_cli.py:42` `main()` 只是查找并 `os.execv` 二进制（优先级：dev
  target/release/ov → wheel 自带 → PATH，:48-59 docstring；`doctor` 子命令留 Python :54-56）。
  Rust 侧命令在 `crates/ov_cli/src/commands/`（filesystem/search/session/skills/compile/watch/
  admin/acl…，共 20 个模块；`compile.rs:6` `pub async fn run`）。
- npm 分发：`npm/cli/package.json:2-6` `@openviking/cli`，bin `ov`，postinstall 拉平台二进制
  （optionalDependencies 五个平台包 :11-17）。
- README 中的命令对应关系：`openviking-server init`（README.md:119，写 `~/.openviking/ov.conf`，
  实现在 server_bootstrap.py:56-58 + setup_wizard.py）；`ov compile`（README.md:52，VikingBot
  启用时用 skill 把素材整理成 wiki/知识图谱/报告；Rust 实现 compile.rs）。
【解释】`ov` 是面向 server 的客户端操作 CLI（含 TUI），`openviking-server` 是服务端进程；
`openviking` 这个 PyPI 包同时带两者入口。

---

## 6. LangChain 集成

【硬事实】
- `examples/langchain/pyproject.toml:6` 包名 `langchain-openviking`（独立 pip 包，**v0.5.0 复核：目录是 `examples/langchain/`，原写 `integrations/langchain/` 不存在**，
  tag_regex `^langchain-openviking@` :67）。
- README.md:3-5：「official OpenViking integration package for LangChain and LangGraph …
  communicates with remote OpenViking instances through the lightweight `openviking-sdk`」。
- 提供的适配器（README.md:43-45）：`OpenVikingRetriever`（快速示例 :22-42）、
  `OpenVikingSessionRecorder`、`OpenVikingContextMiddleware`、`OpenVikingStore`（LangGraph）、
  `OpenVikingChatMessageHistory`、`create_openviking_tools`。源码对应
  `src/langchain_openviking/{retrievers,recording,middleware,store,history,tools,context}.py`。
- 兼容：README.md:60 旧导入路径 `openviking.integrations.langchain` 仍可用。
- 文档：docs/en/agent-integrations/07-langchain-langgraph.md。

---

## 7. Web Studio

【硬事实】
- `web-studio/README.md:3-7`：「static single page application」；「does not embed OpenViking
  storage … It must connect to a running OpenViking Server」，默认 `http://127.0.0.1:1933`；
  sessions 页依赖 `/bot/v1/*`（需 `openviking-server --with-bot`，否则 503）。
- API 调用：`web-studio/script/gen-server-client/gen-server-client.sh:6-9` — 从运行中 server 的
  `/openapi.json` 用 openapi-ts（@hey-api/client-axios）生成 `src/gen/ov-client`。
- 认证：`src/lib/ov-client/client.ts:191` 请求头 `X-API-Key`；key 存 sessionStorage
  （:156-165, :238），并有 admin key 分流逻辑（:188-190）。
- 它**同时是 server 的一个挂载点**：`openviking/server/app.py:744-786` — 优先 `OPENVIKING_WEB_STUDIO_DIR`（`:746`）
  环境变量，否则 `openviking/web_studio/dist`（docker `web-studio-builder` 阶段产出），
  挂到 `/studio`（`app.py:786` 「Web Studio mounted at /studio」；旧基线为 `:833`）。
【解释】Web Studio 本质是运维/管理控制台（资源、检索、bot 会话、诊断），不是给外部 agent 的
编程接入路径；但技术形态上它就是「一个调 REST API 的第三方前端」，证明了 HTTP API 的完整性。

---

## 8. 成熟度分层（官方推荐 vs 示例/实验）

【硬事实】
- **官方文档主推矩阵**：docs/en/agent-integrations/01-overview.md:5-22 表格列出 14 类集成，
  Claude Code Memory Plugin 排第一，并给能力对比总表（16-capability-reference.md）。
- **实验性标记**：
  - `examples/pi-experimental-context-management/README.md:3-4`：「**EXPERIMENTAL.** A demo
    extension, not a supported product」。
  - `ov` CLI 内部：capability-reference.md:633 `add-memory`（experimental）、:635 `search`
    （experimental）；:631 说明 `[Experimental]` doc 前缀只是渲染标记、默认仍可用。
  - OpenViking Helper（桌面 GUI）自述「currently in beta」（14-openviking-helper.md:15）。
  - docs/en/agent-integrations/08-community-plugins.md:3：社区插件「check the linked README
    before adopting」（ZCode/AstrBot 等在 examples/ 下维护）。
- **大量 harness 插件放在 `examples/` 目录**（claude-code、codex、cursor、trae、zcode、opencode、
  pi、openclaw、openwebui、dsh、memory-plugin-shared），但由官方 install.sh 一键安装、CI 覆盖、
  且是 docs 主推路径 —— 位置上是 example，定位上是产品。
- **SDK 成熟度**：python sdk 是主包的硬依赖（pyproject.toml:33 `openviking-sdk>=0.1.9`，最稳）；
  TS 0.1.0；Go 独立 module 有测试有示例。
- agent-plugins 目录在仓库顶层（不在 examples/），v0.1.1，有 conformance 测试（plugin.test.mjs）。

【解释】分层：
- 成熟/官方推荐：HTTP API + Python SDK（主包依赖）、内置 /mcp endpoint、`openviking-server`、
  `ov` Rust CLI、Claude Code/Codex memory plugins（文档首推 + 统一安装器）。
- 正式但较新：TS/Go SDK、agent-plugins 1.0 包、LangChain 包、Web Studio。
- 示例/实验：examples/ 下 pi-experimental-context-management（明确 EXPERIMENTAL）、社区插件、
  Helper（beta）、`ov add-memory`/`ov search` 子命令（experimental 标记）。

---

## 9. 反直觉事实

1. **必须先有 HTTP server，没有任何「嵌入式/进程内」接入模式。** 与「pi-mono 没有 HTTP server」
   正好相反：OpenViking 的所有路径——SDK（三个语言都是纯 HTTP 客户端，README 原话
   "for a/an existing/running OpenViking server"，sdk/python/README.md:3、sdk/typescript/README.md:3、
   sdk/go/README.md:4-5）、MCP（streamable HTTP）、CLI（对 server 说话）、LangChain（经
   openviking-sdk）、Web Studio——都要求一个运行中的 server。主 `openviking` 包里装的是
   server 引擎本身，不含可 import 的本地存储 API。
2. **`from openviking import SyncHTTPClient` 是兼容假象**：真实类在独立包 `openviking-sdk`
   （client.py），主包经 `openviking_cli/client/_http_compat.py:113` 的子类垫片转发；依赖方向
   是 openviking → openviking-sdk（pyproject.toml:33），不是反过来。
3. **`ov` 命令是 Rust 二进制**，PyPI wheel 里的 `ov`/`openviking` 入口只是 60 行 execv 包装器
   （rust_cli.py:8-17「职责单一：仅负责查找二进制并 execv」；pyproject.toml:198 注释
   「放弃 python CLI」）；Python 版 CLI 已退役，只剩 `doctor`（rust_cli.py:54-56）。
4. **agent-plugins 用 stdio 代理不是技术落后**：server 原生就是 streamable HTTP `/mcp`
   （app.py:809），走 stdio 纯粹是因为 Agent Plugins 1.0 规范禁止静态声明里带部署 URL/凭证
   （agent-plugins/README.md:32-34）。
5. **MCP 认证可以完全无鉴权**：本地 dev 模式（无 root_api_key）直接裸连（06-mcp-clients.md:23、
   dev.py:23-26）；远程才需要 API key 或 MCP OAuth 2.1（oauth/router.py:224）。
6. **冷门完整路径：WebDAV**。`/webdav/resources`（webdav.py:26）让文件系统客户端也能挂载
   OpenViking，文档在 docs/en/api/20-webdav.md。
7. 【未定】`crates/ragfs`（AGFS 的 Rust 复刻，ORIGIN.md:3-4）与 `crates/ragfs-python` 是否构成
   独立接入面证据不足——仓库内未见面向外部的使用文档，更像内部文件系统抽象
   （`RAGFS_IMPL=auto/rust/go` 切换），本报告不计入接入路径。

## 10. 一句话结论

外部 agent/宿主接入 OpenViking 共 7 条真实路径：① 直接连内置 `/mcp`（streamable HTTP，15 工具）；
② Agent Plugins 1.0 包（stdio 代理 + skills）；③ 各 harness 专用插件（examples/，hooks 驱动）；
④ Python SDK `openviking-sdk`（或经 `openviking` 兼容导入）；⑤ TS / Go SDK；⑥ LangChain 包
`langchain-openviking`；⑦ 裸 REST `/api/v1/*`（含 WebDAV、/bot/v1、OAuth）。另有运维侧的
`ov`（Rust CLI）、`openviking-server`（服务端）、`vikingbot` CLI 和 Web Studio `/studio`。
共同前提：一切路径都要求先跑起 HTTP server（默认 127.0.0.1:1933），无嵌入式模式。
