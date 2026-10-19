# OpenViking 核心机制取证报告（core-evidence）

## v0.5.0 复核登记（2026-10-19）

- **基线**：`v0.5.0` = `20f9c1136`（2026-10-09）。本报告原锚点基于 `0f77ab56`（`v0.4.19`）。
- **它已不是当前结论的唯一来源**：v0.5.0 的机制重写见 [`../_change_log/0002-v0.4.19-to-v0.5.0.md`](../_change_log/0002-v0.4.19-to-v0.5.0.md)，正文结论见 [`../core/`](../core/README.md) 五篇。
- **本报告中的已知过时项**（保留原文以存证，勿直接引用）：
  - §1 URI/scope：`agent` 命名空间已升为一等（`viking://agent/skills|endpoints|tools|payments`），见 core/01
  - §2-§3 层级/检索：两级递归已删除，`semantic_dag.py` 已删除；本报告描述的"逐层下钻"不再存在
  - §4 session→memory：working memory 默认 OFF；`hotness_score` 不再参与打分
  - §5 锚点漂移：`engine/__init__.py:9-14` → 今 `:16-21`；`_ov_engine_backend` 模块名**从基线起就是错的**（真名 `_native`/`_x86_*`）
- **仍然有效**的硬事实：Python scope 白名单逐字节相同；`ContextLevel` 三值；`_safe_uri_parts` 三重拒绝；`chmod` no-op；`ovpack v3` / `INDEX_FORMAT_VERSION=1`。


- 取证范围：`/Users/bowhead/OpenViking`（只读，未执行任何 git 命令）
- 日期：2026-07（本次会话）
- 标记约定：【硬事实】= 源码可直接验证；【解释】= 基于代码结构的推断；【未定】= 证据不足
- 所有行号基于当前工作区文件内容（未用 git，可能与远端 HEAD 有偏差）

---

## 1. viking:// URI 与虚拟文件系统

### 1.1 Namespace 集合【硬事实】

- Scope 白名单定义在 CLI 侧 `VikingURI`：`openviking_cli/utils/uri.py:58-71`
  - `LISTABLE_SCOPES = {"resources", "user", "agent"}`（uri.py:58-62）
  - `LEGACY_SCOPES = {"session"}`（uri.py:64）
  - `INTERNAL_SCOPES = {"temp", "queue", "upload"}`（uri.py:65）
  - `ALIAS_SCOPES = {"~"}`（uri.py:68，home 别名，仅在请求边界展开、不持久化）
  - `VISITABLE_SCOPES = 上述全部并集`（uri.py:71）
- 请求边界校验：`openviking/core/uri_validation.py:35-64` `validate_viking_uri()`；:52-62 scope 不在白名单即抛 `InvalidURIError`；alias scope 接受但不出现在报错文案（uri_validation.py:54-57）。
- 内容类型映射：`openviking/core/namespace.py:14-20` `_CONTENT_TYPES_BY_SCOPE`：`user`/`agent` scope 下 `memories→memory`、`resources→resource`、`skills→skill`；peer 内容段 `memories/resources`（:18）。
- URI 解析与分类：
  - `namespace.py:87-95` `uri_parts()` — 剥离 `viking://` 前缀切分段
  - `namespace.py:137-150` `classify_uri()` → `UriClassification`（scope/content_index/context_type）
  - `namespace.py:228-254` `resolve_uri()` — canonical 解析；`~` 与 legacy `session` 在此层 fail-closed（:244-251）
  - `namespace.py:257-273` `resolve_request_uri()` — 请求边界展开 `~`/`session` 别名；`viking://user/<reserved>` 无 uid 形式已废弃并报错（:302-316，`_is_reserved_user_root_segment` :450-458）
- 可见根：`namespace.py:183-191` `AGENT_SHARED_ROOTS = ("viking://agent/skills",)`；`visible_roots()` 返回 `viking://resources`、`viking://agent/skills`、`viking://user/{user_id}`。
- 访问控制：`namespace.py:323-345` `is_accessible()` — root 全放行；`resources/temp/queue` 公共；`user` scope 校验 owner_user_id（:336-339）；`agent` scope 校验 actor_peer_id（:340-344）；`upload` 拒绝（:334-335）。

### 1.2 目录树构建【硬事实】

- 预设目录定义：`openviking/core/directories.py:53-155` `PRESET_DIRECTORIES` — `user` scope 预置 `memories/`（下含 preferences/entities/events/cases/patterns/tools/skills/trajectories/experiences，:59-119）、`resources/`、`privacy/`、`peers/`、`skills/`、`sessions/`；`resources` scope 无预置子目录（:149-155）。每个目录带 `abstract`（L0）与 `overview`（L1）文案（`DirectoryDefinition` :33-40）。
- 初始化：`directories.py:158` `DirectoryInitializer`；:176-205 `initialize_account_workspace()` 并发创建 account 根 + user 根及一级子目录；:219-242 `initialize_user_directories()`（叶子 namespace 惰性创建，:221-225 注释）；:244-283 `_account_directory_target`/`_user_directory_targets`；:303-329 `_ensure_agfs_directory()` 存在性检查 + 创建；:390-400 `_create_agfs_structure()` 调 `VikingFS.write_context()` 落盘 L0/L1。
- 目录即数据记录：directories.py:6-8 模块 docstring "all directories are data records"。
- 预设目录同时播种 L0/L1 向量：`directories.py:331-373` `_ensure_directory_l0_l1_vectors()`（level 0/1 → `vector_record_id` → `enqueue_embedding_msg`）。
- ingest 阶段的树容器：`openviking/core/building_tree.py:11-105` `BuildingTree`（`add_context` :34、`get_children` :62、`to_directory_structure` :78-99，用 `meta.semantic_title/source_title` 渲染目录名）。
- parse 侧树构建：`openviking/parse/tree_builder.py:39-60` `TreeBuilder`（v5.0：Parser 建 temp 目录结构 → TreeBuilder 建 URI 元数据 → ResourceProcessor 提交 → SemanticProcessor 异步生成语义）。

### 1.3 「像文件一样操作」的操作面【硬事实】

实现主体是 `VikingFS`（7 个 mixin 组合）：`openviking/storage/viking_fs/__init__.py:110-126`

- 类 docstring（:119-126）：RAGFS 基础命令直传（read/ls/write/mkdir/rm/mv/grep/stat）+ VikingFS 特有能力（abstract/overview/find/search）。
- `_ops.py`（Core filesystem operations mixin，:62-63）：
  - `read()` `_ops.py:67-104`（接受 viking URI 或 32 位 hex 向量记录 id；加密/切片下沉到 ragfs 层，:80-82 注释）
  - `write()` :106-119；`glob()` :1112；`tree()` :1345；`ls()` :1793
- `grep`：`_grep.py:25` `grep()`（内部 `search_recursive` :625）
- 语义检索操作：`_semantic.py:187` `find()`、:369 `search()`、:516 `write_context()`（写 L0/L1/L2 三件套）
- 服务层暴露：`openviking/service/fs_service.py:227` `ls()`、:875 `tree()`；`search_service.py:91` `search()`、:139 `find()`
- URI→物理路径映射见 `_ops.py:78` `_uri_to_path()`；文档描述的映射 `viking://resources/x → /local/{account_id}/...` 见 `docs/en/concepts/05-storage.md`（URI Mapping 一节）。

---

## 2. L0/L1/L2 三层加载

### 2.1 层定义【硬事实】

- `openviking/core/context.py:34-39` `ContextLevel`：`ABSTRACT=0`（L0）、`OVERVIEW=1`（L1）、`DETAIL=2`（L2）。
- sidecar 文件名常量：`openviking/storage/abstract_overview.py:29` `ABSTRACT_OVERVIEW_FILENAMES = {".abstract.md", ".overview.md"}`。

### 2.2 谁生成 L0/L1【硬事实】

三条生成路径：

1. **异步语义生成（主路径）**：`openviking/storage/queuefs/semantic_processor.py:3`（模块 docstring "generates .abstract.md and .overview.md"）、:81-86（bottom-up：先并发生成目录内文件摘要 → 收集子目录 .abstract.md → 生成本目录两文件）、:715 `_generate_single_file_summary`、:814 `write_abstract_overview()`。队列定义 `semantic_queue.py:34`。架构说明 `parse/tree_builder.py:50-59`（v5.0：SemanticProcessor 异步生成 + 直接向量化）。
2. **同步直接写入**：`VikingFS.write_context` `_semantic.py:516-577` — 显式传 abstract/overview 时分别写 `.abstract.md`/`.overview.md`（:543-559、:561-577），内容经 `render_abstract_overview()` 渲染成 OKF 格式。
3. **预设目录播种**：`directories.py:390-400`（见 1.2）。

### 2.3 读取时按层裁剪【硬事实】

- 向量记录按 level 存储（L0/L1/L2 各一条记录）；检索结果按 level 过滤：`hierarchical_retriever.py:301-307`（level filter）、:542。
- L0/L1 结果的展示 URI 会拼上 sidecar 后缀：`hierarchical_retriever.py:60` `LEVEL_URI_SUFFIX = {0: ".abstract.md", 1: ".overview.md"}`；:661-672 `_append_level_suffix()`；:632-640 L0/L1 的 abstract 预览经 `body_for_preview()` 只留可见正文（剥 frontmatter）。
- OKF frontmatter 解析/渲染/写保护：`abstract_overview.py:177-222` `parse_abstract_overview()`（兼容无 frontmatter 旧内容 :196，frontmatter 必须含 directory :215）；:225-250 `render_abstract_overview()`（YAML frontmatter + body）；:306-344 `prepare_abstract_overview_write()`（公开写只能改 body，改 metadata 抛 `AbstractOverviewMetadataError` :332-333）。
- 目录 overview 读取：`_semantic.py:173-185` 直接读 `{dir}/.overview.md`，缺失时返回占位 `[Directory overview is not ready]`（:183）。

### 2.4 设计稿 vs 已实现【硬事实 + 解释】

对照 ~~`docs/design/l0-l1-okf-sidecars-rfc.md`~~：

- RFC 提案（RFC Summary 行 7-22）将 `.abstract.md`/`.overview.md` 升级为 OKF 格式（YAML frontmatter + body）。**已实现**：`parse_abstract_overview`/`render_abstract_overview`/`_normalize_metadata`（abstract_overview.py:92-135 规范化 directory/source/generated_by/freshness 四组字段）与 RFC "Metadata Fields" 一一对应。
- RFC Goals「metadata 对 embedding 默认排除」→ 实现于 `abstract_overview.py:358-384` `body_for_embedding()`/`embedding_text_for_body()`。
- RFC Decisions（行 251-255）：不做 `read_metadata()` API、directory 进 embedding、frontmatter 原样进 git diff —— 前两点与代码一致；第三点（git diff）未见验证。
- RFC "Future Work: Freshness-Aware Parent Bubbling"（行 257+）：**部分已实现** —— `plan_abstract_overview_refresh()`（abstract_overview.py:544）+ `semantic_processor.py:270-280`（父刷新前先做 refresh 决策）与 freshness metadata（:405-422）存在；是否已改为「仅在子摘要变化时冒泡」【未定】（RFC 该节描述的"unconditional bubbling is not the intended final scheduling policy"与代码决策函数并存，未见明确开关语义）。
- 【解释】总体判断：RFC 的存储格式与读路径部分已落地（Stage: RFC 状态仍标 Draft，行 3），实现与设计稿高度同步。

---

## 3. 检索两级模型

### 3.1 两种模式【硬事实】

- `RetrieverMode`：`openviking/retrieve/hierarchical_retriever.py:48-50` — `THINKING`/`QUICK`。
- **QUICK 模式 = 纯扁平向量检索，无目录递归**：`hierarchical_retriever.py:175-217`（一次 `search_in_tenant` :180-188，按 URI 去重取最高分 :193-209）。`find()` 固定用 QUICK：`_semantic.py:285`（`mode=RetrieverMode.QUICK`）。
- **THINKING 模式 = 「先目录后探索」两级模型**（这才是"向量先找候选目录，再在目录内探索"的体现）：
  - Step 2 全局向量检索 L0/L1 目录记录：`hierarchical_retriever.py:220-229`（`level=[0,1]`）；L2 叶子命中另查（:234-247）并 rerank（:248-257）。
  - Step 3 选递归入口：目录命中 + 显式 root（:276-297）。
  - Step 4 递归搜索 `_recursive_search`（:309-326 调用；:421-580 实现）：
    - 优先队列 `dir_queue`（:452、:480-482）；并行子目录搜索 `search_children` → `vector_proxy.search_children_in_tenant`（:484-493，并发上限 `MAX_PARALLEL_CHILD_SEARCHES=4` :495）。
    - 分数传播：`final_score = alpha*score + (1-alpha)*parent_score`（:531-533）。
    - 只对目录（level≠2）继续入队递归；L2 是终点（:554-556 注释）。
    - 收敛判停：topk 不变连续 `MAX_CONVERGENCE_ROUNDS=3` 轮即停（:558-580，常量 :56）。
- 模式选择：`retrieve()` 未传 mode 时，有 rerank client 用 THINKING，否则 QUICK（:126-127）。`search()` 不传 mode（`_semantic.py:484-491`），因此配置 rerank 后 search 默认走两级递归；【解释】README 说的 search"更聪明"主要来自 THINKING 递归 + rerank，而非仅 session context。

### 3.2 find 与 search 的区别【硬事实】

- `find()`（`_semantic.py:187-307`）：纯语义检索，无 session 信息，固定 QUICK，返回 `FindResult`；支持 filter-only 查询（:218-245，`_find_by_filter` :309-367）。
- `search()`（`_semantic.py:369-514`）：接受 `session_info`（`latest_archive_overview` + `current_messages`，:408-411）；当有 session 上下文且 intent 开启时调用 `IntentAnalyzer`（:443-452）生成多路 `TypedQuery` 计划（QueryPlan），并发执行后聚合（:478-514）；还会读目标目录 abstract 作为规划上下文（:417-424）。
- `IntentAnalyzer`：`openviking/retrieve/intent_analyzer.py:38-46`（职责：整合 compression summary + 近期消息 + 当前消息，调 LLM 产出针对 memory/resource/skill 的多条 TypedQuery）；支持按模型映射专用 prompt（:24-27）。
- 服务层入口：`search_service.py:91 search` / `:139 find`。

---

## 4. session → memory 管道

### 4.1 commit 流程【硬事实】

- 入口：`openviking/session/session.py:1828` `commit()`（sync 包装）、`:1851` `commit_async()`。docstring（:1865-1872）明示两阶段：
  - **Phase 1（Archive prep，路径锁保护）**：消息切 archive/retain、持久化可恢复 intent 与 archive 原文、入队 Phase 2、发布 `phase1.status=ready`（分布式文件锁跨 worker/process）。
  - **Phase 2（Memory extraction）**：走持久化 QueueFS 队列。
- 入队：`session.py:1897-1899` 引入 `QueueManager` + `SessionCommitMsg`（`openviking/storage/queuefs/session_commit_msg.py:10`）。
- 消费：`openviking/storage/queuefs/session_commit_processor.py:47-88` `_process()` → `session.resume_queued_commit(msg)`（:78）；session 不存在则 fail task（:60-75），未处理完则重新入队（:80-86）。
- Phase 2 续跑：`session.py:2423` `await self._run_memory_extraction(...)`；分批：`session.py:2462-2539` `_extract_long_term_memories_with_batching()`（`plan_extraction_batches` 来自 `openviking/session/extraction_batch.py:26-31`）。
- 自动提交策略：`openviking/session/auto_commit_policy.py:11-21`（默认 150k token / 100 条消息 / 空闲 1 天；会话默认关闭自动提交，:5-7 docstring）。

### 4.2 后台抽取在哪实现【硬事实】

- 抽取主循环：`openviking/session/memory/extract_loop.py:110` `ExtractLoop`（`run()` :188；操作解析 `resolve_operations` :766；`finalize_operations` :976；LLM 工具调用 `_execute_tool_calls` :1043；工具实现 `openviking/session/memory/tools.py` — `MemoryReadTool` :174、`MemorySearchTool` :261、`MemoryLsTool` :326）。
- 抽取上下文提供者：`openviking/session/memory/session_extract_context_provider.py:54` `SessionExtractContextProvider`；指令文案（:211）："memory extraction and maintenance agent ... produce a single atomic plan to **create, update, delete, or reorganize** memories"。
- 另有流式增量更新：`openviking/session/memory/streaming_memory_updater.py`（与 extraction_id 绑定防跨快照误合并，见 dataclass.py:157-163 注释）。

### 4.3 create / merge / skip 的比较逻辑【硬事实 + 解释】

- **决策主体是 LLM（agentic），不是代码里的相似度阈值函数**：
  - 抽取前先预取已有记忆：`session_extract_context_provider.py:471` `prefetch()`（用 `MemorySearchTool`/`MemoryReadTool` 拉相关已有记忆，`_build_prefetch_search_query` :353）。
  - 合并安全策略作为 prompt 注入：`openviking/session/memory/merge_policy.py:5-19` `MEMORY_MERGE_POLICY`（"相似只是候选线索；同 identity 才可 merge；删除前每条事实须有归宿；不确定就保持独立"），注入点 `session_extract_context_provider.py:242`、`patch_merge_context_provider.py:148`。
  - 写入策略按 schema 字段定义：`merge_op/base.py:121-126` `MergeOp = PATCH | REPLACE | SUM`（另有 `immutable`，如 `prompts/templates/memory/entities.yaml:33,39`；`MEMORY_MERGE_POLICY` 引用链见上文）。
- **skip 是代码侧的确定性过滤**（policy/validation 层）：`openviking/session/memory/dataclass.py:173-184` `MemoryOperationSkipCode`（memory_type_filtered / self_memory_disabled / peer_memory_disabled / invalid_peer_id / peer_not_allowed / invalid_ranges / ambiguous_target / no_writable_target / page_id_type_mismatch）；结构化记录 `SkippedMemoryOperation`（:194-204）；处理与优先级在 `memory/memory_isolation_handler.py:26-44`。
- **合并操作的执行**：`memory/merge_op/`（patch.py/replace.py/sum.py/immutable.py/link_merge.py，工厂 `factory.py`）；链接写入 `memory/memory_updater.py:104` `write_stored_links()`。
- 检索侧冷热生命周期（非 merge）：`openviking/retrieve/memory_lifecycle.py:20` `hotness_score()`（sigmoid(访问频次) × 指数时间衰减，半衰期默认 7 天）；检索混合打分 `hierarchical_retriever.py:620-628`（旧基线行号；该文件在 v0.5.0 已缩到 381 行，热度混合打分**随递归一并删除**）。

---

## 5. 多语言真实边界（Python / Rust / C++）—— 最易误解点

### 结论（明确判断）

【硬事实】Python 运行时**确实使用** Rust 的 ragfs（作为内容存储 AGFS 的实现），并且**同时**使用 C++ abi3 引擎（作为本地向量索引后端）。两者是两个互相独立的原生组件，都从 Python 侧直接加载，互不通过对方调用。

### 证据链 A：Python → Rust ragfs（内容存储）

- PyO3 绑定类：`crates/ragfs-python/Cargo.toml:10`（`lib.name = "ragfs_python"`）、:22（`pyo3 ... features=["abi3","abi3-py310"]`）；`crates/ragfs-python/src/lib.rs:3`（"Provides `RAGFSBindingClient`, a PyO3 native class"）。
- Python 侧加载：`openviking/pyagfs/__init__.py:101-128` `_load_rust_binding()`（优先 pip 安装的 `ragfs_python`，:109；否则加载 vendored `openviking/lib/ragfs_python*.so|.dylib|.pyd`，:115-126；ABI 兼容检查 :51-69）；:131-142 `get_binding_client()`；:164-177 import 时就尝试加载，失败则 `RAGFSBindingClient=None` 并告警。
- 异步适配：`openviking/pyagfs/async_client.py:81-96` `AsyncAGFSClient` 把同步 `RAGFSBindingClient` 方法丢进 `asyncio.to_thread`。
- 客户端构造：`openviking/utils/agfs_utils.py:545-595` `create_agfs_client()` — 直接 `RAGFSBindingClient(config_path, config=binding_dict)`（:587-590）并 `mount_agfs_backend`（:593）；绑定不可用时直接 `ImportError` 要求重建（:569-574）。
- VikingFS 声明：`openviking/storage/viking_fs/__init__.py:119-126`（"Uses Rust binding mode: Use RAGFSBindingClient to directly use RAGFS implementation"）；`:141` `self._async_agfs = AsyncAGFSClient(agfs)`。
- 所有文件读写都打穿到 ragfs 层（含加密）：`_ops.py:80-82, 88, 118-119`（"Encryption ... happens inside the ragfs layer keyed by account_id"）；PathLock 也走 Rust：`openviking/storage/transaction/__init__.py:7`。
- 【解释】因此 "pyagfs 只是 HTTP SDK" 的说法不成立：`pyagfs` 同时承载 PyO3 binding 客户端与 async 适配层；AGFS 内容存储的实际实现是 Rust `crates/ragfs`（localfs/s3fs/memfs 后端插件，`crates/ragfs/src/multibackend/factory.rs:30`）。

### 证据链 B：Python → C++ abi3 引擎（本地向量索引）

- C++ 侧：`src/abi3_engine_backend.cpp:10`（`#define Py_LIMITED_API 0x030A0000`）、:24-28（`namespace vdb = vectordb`；capsule 名 `openviking.vectordb.IndexEngine/KVStore/Schema/BytesRow`）、:2063-2064（模块名 `_ov_engine_backend`，"OpenViking abi3 vectordb backend"）。构建见 `src/CMakeLists.txt:124-129`（engine_common 静态库，链 leveldb）、:224-239（按 x86 变体构建 MODULE：`_x86_sse3/_x86_avx2/_x86_avx512/_native` + `_x86_caps` :297）。
- Python 侧加载：`openviking/storage/vectordb/engine/__init__.py:9-14` `_BACKEND_MODULES`；:52-77 变体探测与 `OV_ENGINE_VARIANT` 选择；:156-176 `_load_backend()`（加载 abi3 后缀扩展）；:187-188 校验 `_ENGINE_BACKEND_API == "abi3-v1"` 后经 `build_abi3_exports`（`_python_api.py:452`）导出。
- 调用方：`openviking/storage/vectordb/index/local_index.py:14`、`store/local_store.py:5`、`store/bytes_row.py:303-306`（`import openviking.storage.vectordb.engine as engine`）。
- 默认后端：`openviking_cli/utils/config/open_viking_config.py:778`（`storage.vectordb.backend` 默认 `"local"`）→ 即默认向量索引就是这套 C++ 引擎；适配器注册表 `openviking/storage/vectordb_adapters/factory.py:8-15`（local / cuvs / http / volcengine / vikingdb）。
- 【解释】Rust ragfs 不调用 C++ 引擎（`crates/ragfs/src` 无 engine/vectordb 引用；仅 `crypto/mod.rs` 字符串撞名）；`openviking/pyagfs/__init__.py:61-66` 里的 "abi3" 是 PyO3 绑定的 stable-ABI 后缀，与 C++ abi3 引擎只是同名机制，无关联。

### 关系一句话

```
VikingFS (Python) --AsyncAGFSClient--> RAGFSBindingClient (Rust, PyO3)  → 内容存储 (localfs/s3fs/memfs + 多写)
VikingDBManager/vectordb --LocalCollectionAdapter--> vectordb.engine (C++ abi3) → 本地向量索引
云上路径：vectordb_adapters volcengine/vikingdb/http 适配器（不走 C++ 引擎）
```

---

## 6. 存储后端

### 6.1 内容存储（AGFS/RAGFS）【硬事实】

- 后端选择：`openviking_cli/utils/config/agfs_config.py:387` — `backend` 默认 `"local"`，取值 `'local' | 's3' | 'memory'`。
- 映射到 Rust 插件：`openviking/utils/agfs_utils.py:327-338`（local→localfs、s3→s3fs、memory→memfs，:383-391 `_map_backend_to_plugin_name`）；Rust 侧合法插件集 `crates/ragfs/src/multibackend/factory.rs:30`（`"localfs" | "s3fs" | "memfs"`）。
- S3（对象存储）参数序列化：`agfs_utils.py:406-437` `_serialize_s3_plugin_params`（bucket/region/endpoint/prefix/path-style/directory_marker_mode 等）。
- **多写（multi-write）**：配置 `agfs.backups` + 可选 `agfs.redirects`（`agfs_utils.py:292-324`：redirects 必须有 backups，:296-299；`_serialize_backups_config`）；写路径 primary→backups、读路径仅声明 read 的 backup 参与、sync/async 一致性模式与 `write_ack_count/write_ack_timeout_ms` —— 与 `docs/en/concepts/14-multi-write-storage.md` 描述一致；Rust 侧实现位于 `crates/ragfs/src/multibackend/`（factory.rs 支持多后端挂载）。
- 队列/缓存后端：QueueFS 支持 `sqlite`/`cache` 等（`agfs_utils.py:244-263`）；CacheFS `local|cache`（:41-47）。

### 6.2 索引存储（向量库）【硬事实】

- 双层存储架构（内容 AGFS vs 索引 Vector Index）：`docs/en/concepts/05-storage.md` Overview 图与表格；代码对应 `viking_vector_index_backend.py` + `vikingdb_manager.py`。
- 向量后端注册表：`openviking/storage/vectordb_adapters/factory.py:8-15` — `local`（C++ abi3 引擎）、`cuvs`（NVIDIA GPU，配置见 `vectordb_config.py:88`）、`http`、`volcengine`、`vikingdb`（火山引擎 VikingDB 私有化/云）；默认 `local`（`open_viking_config.py:778`）。
- 集合 schema 定义：`openviking/storage/collection_schemas.py`（含 L0/L1 sidecar 字段映射）。
- 【解释】"支持对象存储吗？" —— 是：内容层 s3fs（S3 兼容对象存储，含多写 backup），索引层本地引擎或云上 VikingDB；两层可独立组合与扩展。

---

## 附：未定 / 待深挖清单

1. RFC "Freshness-Aware Parent Bubbling" 是否完全落地（`plan_abstract_overview_refresh` 的决策语义未逐行验证）。
2. `docs/en/concepts/05-storage.md` 提到 "AGFS has been rewritten as a Rust implementation (RAGFS)" —— 本报告已验证 Python→Rust 绑定链，但 Rust 内部实现细节（mount/plugins/git 层）未深挖。
3. QUICK 模式无目录递归 —— README 若声称 find 也做"先目录后探索"，与代码不符（find 固定 QUICK，`_semantic.py:285`）；README 原文措辞未逐字核对。
4. `viking://agent/skills` 共享根的写入路径与 ACL 细节未展开（仅验证 `is_accessible` 的 agent 分支，`namespace.py:340-344`）。
