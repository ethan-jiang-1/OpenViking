# 05 一条数据的完整生命周期：从 add-resource 到 find 命中到 memory 沉淀

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。取证：船长自查 + 数据生命周期深挖 agent。
>
> **v0.5.0 结构性重写点**：① **`semantic_dag.py` 被删除**，语义段改由 `semantic_executor.py` + `semantic_work.py` 驱动；② 队列 **7 → 8**（新增 `Reindex`，`UserDeletion` 代码改名 `DATA_CLEANUP`）；③ **队列完成语义重定义**（后端快照判定，不再是 `/size` + 进程内计数器）；④ 读路径的"三处修正"整体作废（递归已删）。图示：[`lifecycle.svg`](lifecycle.svg)。姊妹篇：01（寻址）、02（分层）、03（检索）、04（记忆）。

## 先给结论

OpenViking 里一切数据走**同一条异步主干**：写路径把"内容落库"与"语义加工/向量化"用 QueueFS 切成五段（同步请求 → AddResource worker → Semantic 执行器 → Embedding handler），每段之间都是 sqlite 持久化队列——**at-least-once、无死信队列，瞬时错误无限重入队靠熔断 + 合并窗口压制**。队列是系统的脊柱：它解释了 `--wait` 为什么存在、server 重启为什么不丢任务、以及 `mkdir` 之后为什么 ls 可见但 find 找不到。

## 写路径（同步段：请求线程内的五步）

入口三分支纯转发：Rust CLI（`crates/ov_cli/src/client.rs:824`）、HTTP（`server/routers/resources.py:223`，**服务端禁本地路径** `server/local_input_guard.py`）、MCP（`mcp_endpoint.py:999-1054`，本地路径→签发 TTL 上传 token，不读盘）。

`ResourceService._submit_resource_ingestion`（`service/resource_service.py:1615`，到 `:2056 _execute_resource_ingestion` 之前）：

1. 校验/规范化（tag 策略、to/parent 互斥、git URL 拒 userinfo，`:1575-1618`）
2. 源预检+固化：git 走 `ls-remote` 预检（10s 超时）；其余 `stage_source()` 把字节暂存 `viking://temp/`
3. 目标规划：`resolve_target_uri` + 冲突自增候选 `_1.._100`，全忙抛 retryable `ResourceBusyError`（`utils/resource_processor.py:839-883`）；**pathlock 随消息移交所有权**（`:671-673`）
4. `AddResourceMsg(job_phase=SOURCE|POST_PROCESS)` 两相消息入队（`queuefs/add_resource_msg.py:12-94`）
5. 响应只含 task_id/root_uri——**同步/异步边界①**；`--wait` 的精确语义 = `RequestWaitTracker`（`telemetry/request_wait_tracker.py:38`）阻塞到 **Semantic 与 Embedding 两条队列都结算**（`wait_for_request:266`），并把 queue_status 注入响应（`build_queue_status:306`）。对应调用与等待在 `resource_service.py:2297-2310`、`:2545-2565`

⚠️ 现状 vs 注释警示（回扫确认）：`parse/tree_builder.py:60` "Direct vectorization in SemanticProcessor (no EmbeddingQueue)" **已过时**（v0.5.0 依然没改）——实际仍经 EmbeddingQueue；`embedding.batch_size=32` 配置存在但全库无消费点。

## 写路径（异步段：AddResource worker → Semantic DAG → Embedding）

- **AddResourceProcessor**（`queuefs/add_resource_processor.py:35` 类、`:430 on_dequeue`；文件从 391 行涨到 443 行）：锁接手（失败重排队 ≤2 次）→ 物化 StagedSource → **UnifiedResourceProcessor**：Accessor 层（git/web-feed/http/feishu/local）→ Parser 层（pdf=pdfplumber/MinerU 双策略；markdown 切节 2048；**anydoc.py 转 Office/EPUB 20 种扩展**；code=git 浅克隆+.gitignore 过滤+**解析期零 LLM**；**媒体 parser 是 placeholder**——真处理在语义段）→ `persist_temp_tree` 把加密字节 cp 到正式路径 + 删 temp（`viking_fs/_ops.py:2504`）——**边界②：资源可见**。业务失败 task fail 不重试。
- **SemanticProcessor + SemanticTreeExecutor**（`queuefs/semantic_processor.py:439 on_dequeue`、`:55` 导入 `SemanticTreeExecutor`）。**`semantic_dag.py` 已被删除**，替换为 `queuefs/semantic_executor.py`（类 docstring："Semantic DAG executor with event-driven lazy dispatch"）+ `queuefs/semantic_work.py`（逐消息生命周期/取消/锁）+ `process_result.py` + `queue_middleware.py`。逻辑仍是事件驱动自底向上——文件摘要（文本 prompt；**图片=VLM caption，无独立 OCR；音视频=VLM media completion，无 ASR**（audio.py:4-14 列为 Planned），失败降级空 summary）→ L2 即时向量化 → 目录 overview → `write_abstract_overview`（`abstract_overview.py:533`，`semantic_processor.py:1836` 调用）原子写 sidecar → **body digest（sha256）变化才触发 L0/L1 向量化**——**边界③④**。父目录刷新经 `_enqueue_parent_refresh :344` / `plan_abstract_overview_refresh :374`。
- **Embedding handler**（`storage/collection_schemas.py`，已涨到 1102 行；并发 `embedding_config.py:654-658 max_concurrent=10`）：默认模型 **local bge-small-zh-v1.5-f16**（`models/embedder/local_embedders.py:23`，13 种 provider 可换）；**单一统一 collection（默认名 `context`：`vectordb_config.py:9`、`viking_vector_index_backend.py:325`），L0/L1/L2 靠 level 字段区分**；**确定性主键 `vector_record_id=md5(account,uri,level)`** 幂等 upsert（`vector_ids.py:52-60`）；L2 文本截 4096 token（CJK 1 字 1 token），**图片是多模态 embedding**（summary+image data-uri，`embedding_utils.py:607-618`）；无内容 hash 缓存。
- 失败语义：瞬时错误**无限重入队**，靠熔断（`failure_threshold=5` / `reset_timeout=60` / `max_reset_timeout=600`，`embedding_config.py:611-626`——数值不变，行号变了）+ SemanticQueue 的 45s 去重窗口 + coalesce_key 合并（`semantic_queue.py:17`）；终止类错误分三类：PERMANENT（`collection_schemas.py:803`）、AUTH（`:810`，不重试防死循环）、瞬时重入队（`:823-835`）。**无死信队列**。

## 队列机制（重要修正：queuefs 是 AGFS 插件，不是 Python 直管 sqlite）

QueueFS 挂载在 AGFS `/queue`（挂载点解析 `agfs_utils.py:215-245 resolve_queuefs_mount_point`、插件配置 `:248-253`（默认 db 路径 `:250`、backend sqlite `:253`）、config 段 `:290-294`、挂载 `:664`），DB 在 `{data_path}/_system/queue/queue.db`——**表结构编译进 Rust 扩展，不在本仓库**。Python 侧只有文件语义控制面：`named_queue.py:174 enqueue / :185 ack / :224 dequeue / :254 dequeue_raw / :323 peek / :342 size / :140 get_status`，消息格式 `{"id":uuid,"data":{…}}`。投递语义 **at-least-once**：崩溃未 ack 由 RecoverStale 重排队。

**8 个标准队列与并发度（`queue_manager.py:93-104` 名称、`:262-276` 并发映射、构造默认 `:39-45`）**：Embedding=10、**Semantic=32**、ExternalParse=4、AddResource=4、**Reindex=4（新增）**、SessionCommit=8、ExternalTask=10、**DATA_CLEANUP=1**（`UserDeletion` 的代码名，持久化名保留 `"UserDeletion"` 以让升级前排队的消息原地恢复——`queue_manager.py:104` 注释原话）。每队列独立线程+事件循环。消息状态机（pending→processing→ack/RecoverStale/自我重入队/丢弃）见 [`queue-state.svg`](queue-state.svg)。

### 队列完成语义（v0.5.0 重定义）

**完成判定不再由 Python 侧拼装**。`NamedQueue.get_status()`（`named_queue.py:140-151`）读一次后端状态快照，把后端的 `pending`/`processing` 映射成 `QueueStatus.pending`/`in_progress`；队列完成 = `pending == 0 and in_progress == 0`。`processed`/`requeue_count`/`error_count` 是**纯遥测**，不参与判定。

为什么重要：旧口径下 `size()` 与进程内计数器是两个不可原子读的来源，`--wait` 可能在"队列已空但计数器还没归零"或反之的窗口里判错。upstream 为此专门写了一篇概念页 `docs/en/concepts/16-queue-lifecycle.md`（`:46-52`、`:58-76`）——**这是本项目少见的"先写文档定义语义"的做法**。

两个"谁在驱动"的补充：自动 commit 的执行者是服务端常驻调度器 `SessionAutoCommitScheduler`（`service/session_auto_commit.py:44-53`；**v0.5.0 起默认 600s 间隔、限速扫描 2 files/s**，见 [04](04-session-to-memory.md)）；外部解析任务（MinerU 等）由 `ExternalTaskProcessor` 消费（校验 task ownership）。

## 读路径

调用链：HTTP（`server/routers/search.py`）→ `search_service.py:108/:166/:211` → `VikingFS.find/search`（`_semantic.py:196-331/:393-564`）→ `HierarchicalRetriever.retrieve`（`hierarchical_retriever.py:92-256`，**单程 165 行**）→ `vikingdb_manager.py:426 search_in_tenant`（租户过滤；另有关键词路径 `:456 search_by_keywords_in_tenant`、过滤路径 `:477 filter_in_tenant`、`:496 get_context_by_uri`）→ FindResult(memories/resources/skills)。

> **旧链漏了一条独立路径**：`filter_in_tenant` 是**第三个**查询路径（`_semantic.py:333 _find_by_filter`），旧的"语义检索链"描述里没有它。

> **v0.5.0 反转：原"修正 1/2/3"全部作废。** 收敛判停、dir_queue 优先队列、hotness 混入都已随递归一起删除——它们描述的机制**现已不存在**，不是"精度问题"。当前检索只有一条单程管道，详见 [03](03-retrieval-global-recall.md)。以下两条仍有效（已重锚）：
- **（仍有效）scope/ACL 过滤在向量查询层，不是查后过滤**：`_build_scope_filter`（`storage/viking_vector_index_backend.py:2951-2991`）= `Eq(context_type)` + 租户 `Eq(account_id)`（`:3007`）+ visible_roots 的多目标 `Or(PathScope(...))`（`:2975-2980`）+ `In(level)`（`:2988-2989`），全在 filter 里；**ACL 开启时**再注入 `acl_direct_grants/acl_inherited_grants` 的 `In` 过滤——这与 core/01 的 URI 层 ACL 是**两层不同的防线**（查询层过滤 vs 读取边界）。检索返回字段面 9 个：`RETRIEVAL_OUTPUT_FIELDS`（`:60-68`）。
- 补充事实（已重锚）：image_query **强制 QUICK 不精排**（`hierarchical_retriever.py:124-126` 的 `use_rerank` 含 `not image_query`）且 context_type 兜底为 resource（`:136-137`）。
- **作废**："L2 叶子预检索仅 ACL 开启时发生"——递归删除后没有"预检索"这一步；"rerank 看的是 L1 文本，依据 `embedding_utils.py:445-446`"——该区域现在是 abstract 字节截断注释，官方 `docs/en/concepts/03-context-layers.md` 明确 "The L1 rerank scalar remains the plain L1 body"。

## 记忆路径（core/04 的三处修正 + 闭环）

- **抽取 LLM 只有 3 个只读工具**：`read/search/ls`（`session/memory/tools.py:441-451`）——**没有 write 工具**；写入靠 LLM 最终输出的结构化 operations 经 `resolve_operations`（`extract_loop.py:767`）+ isolation handler 落 URI（`memory_isolation_handler.py:347-400`，9 种 skip code）。
- **streaming_memory_updater 不是聊天实时通道**：它是 compressor_v3 patch-merge 抽取内的**分组合流/append-only 快路径应用器**（`streaming_memory_updater.py:367,490`、`compressor_v3.py:729-750`）。
- **热度不参与打分（v0.5.0）**：`hotness_score()`（`retrieve/memory_lifecycle.py:18`）唯一消费者是 `storage/stats_aggregator.py:96`（统计面板）。旧文"hotness 混入检索打分"作废。
- **merge 执行**：per-URI 先读盘上最新内容再逐字段 apply（同批连续 patch 可见彼此，`memory_updater.py:1089-1130`）——MergeOp=PATCH/REPLACE/SUM/IMMUTABLE。
- **闭环**：memory 写入后 `enqueue_embedding_msg(level=DETAIL)` 复用与资源**同一条 Embedding 队列**（`memory_updater.py:1874`）+ 父目录 SemanticMsg（45s 去重）刷新 overview——记忆与资源在向量化层汇合。

## 删除与移动（修正 + 风险点）

- **rm：先删向量后删文件**（`_ops.py:215 rm`、估算 `:250-258`、向量删除 `:280`/`:323`、AGFS rm `:325`、孤儿索引清理 `:275-281`；向量删除失败**现在会重抛**——`_vector.py:18-36`，日志后 `:34-36 raise`，不再静默）。mv 在 `:682`；底层按 `And(account, Or(Eq(uri), In(uri/)))` 过滤删。⚠️ 此前版本曾写"唯一静默丢删点：`delete(ids)` 异常静默返回 0（`vectordb_adapters/base.py:636-648`）"——2026-09-13 复核**撤回**：该文件仅 631 行（锚点越界），适配层 `delete()`（:523-549）无吞异常逻辑；适配层之下（引擎绑定/云适配器）是否有静默丢删未验证，暂按"未见静默丢删点"口径。
- **mv = URI 重写（不重算 embedding）**：`rewrite_vector_record(mode="move")` 分批 upsert 新 id + 按旧 id 删源，双向补偿回滚（调用 `viking_vector_index_backend.py:2861-2866`，定义 `storage/vector_migration.py:68`）；异步部分只有父目录摘要刷新。
- 无自动 GC：`system consistency` 只报不修（`index_consistency.py:204-229`，**此锚点仍精确**）。**`reindex --mode prune_orphans` 已删除**：`SUPPORTED_MODES_BY_TYPE` 只剩 `{"vectors_only","semantic_and_vectors"}`（`reindex_executor.py:132-139`；v0.4.19 时 `prune_orphans` 在 `:136-141`）。即"孤儿清理"这条路被主动收窄了——类 docstring 现在写 "Non-destructive reindex orchestration"。
- **`service/user_deletion.py` 被删除**，改为 `service/deletion.py`（`DeletionService :62`、`_process :269`、`_DeletionProcessor :447`），并新增 `service/gateway_deletion.py`（gateway 侧数据清理）；队列名见上文 `DATA_CLEANUP`。
- **rm 资源会级联清理 memory 引用**：grep 扫引用→特殊 commit 让 LLM 改写，失败不阻塞；该服务结构性改动（peer-aware 策略 helper `:57-118`，`resource_memory_link_service.py`）。

## 状态标注

- 硬事实：全部锚点（含 agent 第一手取证段）
- 解释：队列是脊柱的定性；"mkdir 后 find 找不到是设计"；leveldb/RocksDB 命名漂移的判断（`stale_lock.py` 清的是 leveldb 的 LOCK，RocksDB 是遗留名）；upstream 为何在 v0.5.0 放弃破坏性 reindex 模式——**未取官方说明**
- 反转记录（2026-10-19，v0.5.0）：`semantic_dag.py` 删除；队列 7→8；队列完成语义重定义；原"修正 1/2/3"整体作废；`prune_orphans` 删除；`user_deletion.py` → `deletion.py`
- 未定：queuefs sqlite 表结构（在 Rust 扩展内）；IndexEngine 内部并发扫描细节
