# 基线 0001：`_digested/` 初始建立

**日期**: 2026-09-12
**upstream**: [volcengine/OpenViking](https://github.com/volcengine/OpenViking)
**fork**: [ethan-jiang-1/OpenViking](https://github.com/ethan-jiang-1/OpenViking)
**基线 commit**: `0f77ab56`（`fix(mcp): bound search's context arguments the way POST /search does (#4892)`）= upstream/main @ 建档日，即 **v0.4.19 + 57 个未发布 commit**（`git describe --match='v*'` → `v0.4.19-57-g0f77ab56`）
**仓库总 commit 数**: 2341
**参考版本口径**: release tag 最新为 **v0.4.19**（2026-09-08，`f3afef11`，共 64 个 v* tag）；README 自述的 "OpenViking 0.3.22 has been evaluated on ..." 是 benchmark 报告口径，明显滞后于 release tag——引用版本号时先说清用的是哪个口径（pyproject 用 dynamic version）

> **口径修正（2026-09-12）**：本记录最初依据 `git ls-remote --tags origin` 写成"upstream 不打 tag"——错在查了 fork（origin）而不是 upstream，且文件名原为 ~~`0001-baseline-v0.3.22.md`~~。fetch upstream 后核实：upstream 有 64 个版本 tag。教训记入方法论：**核实事实要查权威源头本身，不能查它的副本。**

## 这不是一次 sync

这是 `_digested/` 的初始建立——不是从一个旧版本同步到新版本，而是对 OpenViking 源码的**首次消化建档**。`ethan` 分支从 fork 的 `main`（= `origin/main`）@ `0f77ab56` 建立，`_digested/` 作为首个研究 commit 叠在上面。upstream remote（`git@github.com:volcengine/OpenViking.git`）于建档当日添加。

## 覆盖范围（建档时的地图级勘察）

### 工程形态：多语言 monorepo（本目录地图层的核心事实）

| 部分 | 语言 | 关键锚点 | 初步定性 |
|---|---|---|---|
| Python 主包 `openviking/` | Python | `openviking/core/`（`building_tree.py` / `directories.py` / `uri_validation.py` / `retrieval_targets.py` 等）、`openviking/server/app.py`（FastAPI + `mcp_endpoint.py`）、`retrieve/` `session/` `storage/` `parse/` `ingest/` `client/` `eval/` | 产品主体：核心域逻辑、HTTP/MCP 服务、客户端 |
| Rust 层 `crates/` | Rust | `crates/ragfs`、`crates/ragfs-python`、`crates/ov_cli` | 文件系统层（ragfs）+ CLI + Python 绑定 |
| C++ 引擎 | C++ | `src/abi3_engine_backend.cpp`、`src/index/`、`src/store/`、`CMakeLists.txt` | 索引/存储引擎后端，abi3 供 Python 调用 |
| 三语言 SDK | Python/TS/Go | `sdk/python` `sdk/typescript` `sdk/go` | 外部宿主的客户端接入面 |
| agent 插件 | JS | `agent-plugins/plugin.json` `agent-plugins/servers/` `agent-plugins/skills/` `mcp.json` | 面向 coding agent 的 MCP 插件封装 |
| VikingBot | Python | `bot/` | `ov compile` 背后的资料组织能力（wiki / knowledge graph / report） |
| LangChain 集成 | Python | `integrations/langchain` | 第三方框架集成示例 |
| Web Studio | TS | `web-studio/` | 自托管上下文浏览/语义搜索前端 |
| Benchmark | — | `benchmark/` | LoCoMo（用户记忆）/ tau2-bench（agent 任务）复现 |

### 官方文档结构（`docs/`，消化时的对照系）

`docs/en/concepts/` 16 篇（2026-09-13 修正：建档时写 15 篇，实数 16 个 md 文件——`15-acl.md` 与 `15-vikingbot.md` 同占用 15 号，按文件数计 16）：architecture、context-types、context-layers（L0/L1/L2）、viking-uri、storage、extraction、retrieval、session、transaction、encryption、multi-tenant、metrics、privacy、multi-write-storage、acl、vikingbot；另有 `agent-integrations/`、`api/`、`configuration/`、`context-compilation/`、`guides/`。

`docs/design/` 存有设计稿（~~`l0-l1-okf-sidecars-rfc.md`~~、~~`git-version-control-design.md`~~、~~`memory-link-design.md`~~、~~`mcp-oauth2-1.md`~~ 等）——**注意**：design 目录是设计稿，引用时须区分"规格"与"已实现现状"（pi-mono 的 ~~`facets.md`~~ 教训）。

### 已知问题

- ~~多语言三层的真实边界（Python 核心域逻辑 vs Rust ragfs vs C++ 引擎）尚未取证~~ **已解（2026-09-12 取证）**：Python 运行时**确实使用** Rust ragfs 作内容存储（PyO3 `ragfs_python` 绑定，全部 IO/加密打穿 Rust 层），**同时独立**使用 C++ `src/` abi3 引擎作默认本地向量后端（`_ov_engine_backend`）；两者互不调用。证据链见 [`../_notes/core-evidence.md`](../_notes/core-evidence.md) §5
- ~~`openviking/` 内 `pyagfs/` 与 `crates/ragfs-python` 的关系不明~~ **已解**：`pyagfs/__init__.py:101-128` 加载 `RAGFSBindingClient`（pip 优先、vendored .so 兜底）；pyagfs 名字里的 "abi3" 只是 PyO3 stable-ABI 后缀，与 C++ 引擎无关
- 建档时未跑任何测试/构建，全部结论来自静态读源码与文档
- 新增待核（取证中发现）：README 对 `find`/`search` 差异的描述与源码**基本吻合但有偏差**——`find` 固定 QUICK 模式、纯扁平向量检索、**不做目录递归**；"向量先找候选目录再目录内探索"只存在于 `search`（THINKING 模式）。写 `core/` 消化文档时需拦截这个误解

### 未覆盖

| 部分 | 状态 |
|----|------|
| `openviking/` 各子包逐个深潜 | 仅地图级，未取证 |
| `crates/ragfs` 内部机制 | 未分析 |
| `src/`（C++ 引擎） | 未分析 |
| `bot/`、`web-studio/`、`benchmark/` | 仅提及存在 |
| `integrations/`、`sdk/` 三语言差异 | 未分析 |

## 建档产物

- [`../README.md`](../README.md)（`_digested/` 宪法）
- [`../integration/01-start-here.md`](../integration/01-start-here.md)（接入面入口篇，第一批消化文档）
- 本记录
