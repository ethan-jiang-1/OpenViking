# 03 Server 内部拓扑：FastAPI 应用里到底装了什么

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。取证：船长自查（锚点可复核）。姊妹篇：[`01-start-here`](01-start-here.md)（外部接入面）、[`02-ov-cli-reference`](02-ov-cli-reference.md)（CLI）。本文回答：**连上 `:1933` 之后，进程里是什么**。

## 先给结论

OpenViking server 是一个**单进程 asyncio 应用**：FastAPI 只是壳，真正的主干是 `OpenVikingService`（聚合 fs/search/session/compile 等服务的门面）+ 异步队列（v0.5.0 起 8 条）+ TaskTracker 清理循环 + MCP session manager，全部在 lifespan 里装配（`openviking/server/app.py:319-410`）。**27 个 include_router + Bot/Studio + OAuth 2.1 + /mcp**共享同一个 service 实例——这就是"server-first 但不是微服务"的含义：所有接入面在一个进程里汇合到同一棵 viking:// 树。

## 装配顺序：lifespan 的十步（`app.py:319-410`）

| # | 步骤 | 锚点/说明 |
|---|---|---|
| 1 | 配置默认 executor（`_configure_default_executor`）+ 装 executor monitor | :322-327 |
| 2 | 构造/接收 `OpenVikingService`（聚合门面） | :328-332 |
| 3 | Bot 后端（`--with-bot` 时配 compile 本地后端） | :333-334 |
| 4 | session runtime 配置（`_configure_session_runtime`）+ `set_service` | :334-336 |
| 5 | metrics 初始化（Prometheus `/metrics`）+ usage audit | :338-348 |
| 6 | **OAuth 2.1 store 初始化 + GC 循环**（60s 周期清过期授权，SQLite 存储） | :350-370（init，GC task） |
| 7 | **TaskTracker 清理循环**启动 | :371-373 |
| 8 | tracing + OTLP 日志导出 | :375-379 |
| 9 | **MCP session manager 启动**（必须先于 `/mcp` 请求） | :380-383 |
| 10 | **`_initialize_runtime_state`（v0.5.0 新增）**：`service.initialize()` → `apply_agent_evolution_config()` → 装 auth 插件 → **`setup_deletion()`（新 `service/deletion.py`）** | `:385` → 函数体 `:157-172` |

**第 10 步是 v0.5.0 的实质变化**：旧版 lifespan 里没有"服务初始化"这一步，`OpenVikingService` 是在构造时惰性自举的；v0.5.0 把它显式化，并把**删除服务**（`DeletionService` + gateway 侧清理）提升为应用启动依赖。注释原话："Initialize service and auth dependencies before traffic is accepted."（`:161`）

（2026-10-19 全表重锚：v0.5.0 lifespan 整体前移约 10 行并新增第 10 步。）

【硬事实】队列消费者不在 lifespan 显式启动——它们由 service/queuefs 侧按配置惰性启动，server 进程即宿主。

**中间件现在是六层，分两批注册**（注释 ``:464-466``："Later registrations wrap earlier ones: timing/header logging -> profile -> observability -> optional body dump -> routes"）：

| 批 | 层 | 锚点 |
|---|---|---|
| A | `RequestTimingMiddleware` | `:472` |
| A | `ProfileMiddleware` | `:471` |
| A | `HTTPObservabilityMiddleware` | `:470` |
| A | 可选 `dump_http_body`（`@app.middleware("http")`，默认关） | `:452` |
| B | `ExceptionMiddleware`（`handlers={Exception: general_error_handler}`） | `:574` |
| B | `RequestIdMiddleware` | `:575` |
| B | `CORSMiddleware` | `:576-583` |

旧文写"中间件三层：ExceptionMiddleware → RequestId → CORS"，漏了 A 批四层——**这是 v0.5.0 之前就漏的**（可观测性中间件栈属于既有能力，只是旧文没数）。

## 入口面：27 个 router + 2 个特殊 + OAuth

**27 个 `include_router`**（`app.py:596-622`）：system、acl、admin、**gateway（v0.5.0 新增，`:599`）**、agent_evolution、compile、resources、filesystem、content、console、search、privacy_configs、skills、sessions、snapshot、stats、pack、debug、observer、openviking_assets、metrics、tasks、user_settings、watches、**webdav**（`prefix="/webdav/resources"`，`routers/webdav.py:26`——把 `viking://resources/...` 暴露成 WebDAV 目录，OS 文件管理器/办公软件可直接挂）。

**特殊入口**：`bot_router`（`prefix="/bot/v1"`，VikingBot 代理，`--with-bot` 开关）；**`bot_studio_router`（v0.5.0 新增，`:622`，无前缀）**；`/mcp`（MCP streamable HTTP，session manager 管理，`app.py:809`）；OAuth 2.1 路由（按配置注册，`app.py:686` 之后）。

## 20 个 MCP 工具（`server/mcp_endpoint.py`，权威清单见 `:5-7` docstring）

账号与 ACL 组：`list_users`（:355）、`list_groups`（:393）、`get_acl`（:407）、`set_acl`（:417）——**四个都是 v0.5.0 新增**。

内容组：`find`（:449）、`search`（:509）、`read`（:852）、`list`/ls（:1005）、`tree`（:1087）、`remember`（:1167，存消息进记忆管线）、`write`（:1203）、`edit`（:1250）、`add_resource`（:1422）、**`add_skill`（:1727，v0.5.0 新增）**、`grep`（:1975）、`glob`（:2050）、`forget`（:2079）。

Watch 与状态组：`list_watches`（:1898）、`cancel_watch`（:1931）、`health`（:2095）。

【解释】工具面语义与 [`vfs/03`](../vfs/03-operation-semantics.md) 一致：`find` 是语义检索、`remember/forget` 是记忆生命周期入口——agent 通过 MCP 看到的"文件系统"是经过这 20 个动词裁剪过的视图。**但"裁剪"的说法需要修正**：v0.5.0 起 ACL 管理（`get_acl`/`set_acl`）和账号枚举（`list_users`/`list_groups`）**已进入 MCP**，旧文"比内部 API 少：无 chmod、无 ACL 管理、无 admin"里**"无 ACL 管理"已作废**。仍然没有的是 `chmod` 和 admin 配置面。

## 鉴权与租户

- **auth 插件注册表**（`server/auth/registry.py:27`）：仓内插件 **5 个全部在包导入时注册**（`auth/plugins/__init__.py:8-31`）——`dev`/`api_key`/`trusted` 无条件注册（`app.py:128-139` 再幂等兜底一遍），`oidc`/`ldap` 是**条件注册**（try/ImportError，依赖可用才生效）。默认 `auth_mode` 不在 5 个之列时才落 `app.py:141` "Unknown auth_mode" 报错（2026-09-13 修正：此前版本写"内置 3 个——api_key/dev/ldap"，名单错；也不必为 ldap 自写注册器）。第三方可 `@register_auth_plugin` 但需自写启动器（[`harness/1.1`](../harness/01-Architecture/1.1_extension_seams.md) 判断 2）。
- **请求身份**：`RequestContext`（account_id / user_id / actor_peer_id）由鉴权层解析后绑定（`server/identity.py`；CLI 侧对应 `--account/--user/--actor-peer-id`）。storage 层直接 import 该类型（[`harness/1.2`](../harness/01-Architecture/1.2_layering_discipline.md) 判断 1b）。
- **WebDAV 的护栏**：拒绝盘符前缀段（`webdav.py:59` "unsafe WebDAV drive-prefixed segment"）——与 [`vfs/01`](../vfs/01-bridge-to-disk.md) 的 `_safe_uri_parts` 同一防御哲学在 HTTP 层的重现。

## 进程内后台任务清单

| 任务 | 周期/触发 | 锚点 |
|---|---|---|
| OAuth GC 循环 | 60s | `app.py:363-375` |
| TaskTracker 清理循环 | 常驻 | `app.py:377-379` |
| 语义队列消费者（L0/L1 生成+向量化） | 队列驱动 | `openviking/storage/queuefs/semantic_processor.py` + 新 `semantic_executor.py`/`semantic_work.py` |
| session commit 消费者 | 同上 | `openviking/storage/queuefs/session_commit_processor.py` |
| **自动 commit 调度器** | 默认 600s，限速 2 files/s | `openviking/service/session_auto_commit.py:44-53` |
| **Reindex 消费者**（v0.5.0 新增） | 队列驱动，并发 4 | `openviking/storage/queuefs/reindex_processor.py` |
| **DeletionService**（启动步 10 装配） | 队列驱动，并发 1 | `openviking/service/deletion.py:62` |
| MCP session manager | 常驻 | `mcp_endpoint.py mcp_lifespan` |

【解释】这就是 [`architecture/01`](../architecture/01-three-languages.md) 调用图的"进程视角"：Rust 绑定（ragfs）与 C++ 引擎都加载在**这个进程**里，队列消费者、HTTP handler、MCP session 共享它们——单进程多入口，靠 PathLock 与队列保证并发正确性，而非多服务分片。

## 状态标注

- 硬事实：lifespan 十步、27 个 include_router、MCP 20 工具、auth 插件、WebDAV 前缀、六层中间件（2026-10-19 对 `v0.5.0` 快照逐个复核）
- 反转记录（2026-10-19，v0.5.0）：lifespan 九步→十步（新增 `_initialize_runtime_state`）；router 24→27（+gateway、+bot_studio）；MCP 15→20；`/mcp` 挂载点 :856→:809；旧文漏记的可观测性中间件四层已补
- 解释：队列消费者惰性启动的判断（lifespan 无显式启动代码，从 service 构造推断）；"单进程多入口"定性
- 未定：多 worker 部署形态（uvicorn workers / gunicorn）下的队列竞争细节
