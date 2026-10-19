# 04 session → memory 管道

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。取证原料 [core-evidence §4](../_notes/core-evidence.md)。
>
> **v0.5.0 三处反转**：① **Working Memory 默认从开改成关**（见"易误解点 0"，这是本篇最需要先知道的事）；② "热度参与检索打分"**作废**；③ 自动提交调度器默认间隔 60s → 600s，扫描策略改为限速而非批大小。

## 先给结论

session 提交（commit）是**两阶段异步管道**：Phase 1 在路径锁内切 archive/retain 并入持久化队列，Phase 2 由 QueueFS 消费者驱动**agentic 记忆抽取**——决策主体是 LLM（带合并安全策略 prompt + 预取已有记忆），代码侧只做确定性 skip 与最终执行（`MergeOp = PATCH | REPLACE | SUM | IMMUTABLE`）。**没有相似度阈值函数式的"代码判定 create/merge"**——这是与多数 memory 产品最不同的设计。

**但请先读这句**：v0.5.0 起，commit 默认**不归档 working memory**（`enable_working_memory` 默认 `False`）——这是同一管道的上游闸门，本篇后文描述的抽取逻辑没变，只是默认少了一路输入。

## commit 两阶段

入口：`openviking/session/session.py:1213` `commit()`（sync 包装，新增 `enable_working_memory` 参数 `:1218`）、`:1238` `commit_async()`（`:1243` 同参数）；docstring 明示两阶段：

| 阶段 | 内容 | 锚点 |
|---|---|---|
| **Phase 1**（Archive prep） | **`pathlock_acquire_exact(session_path)`** 精确路径锁（`:1357`）内：retention 切分（turn_budget 模式走纯规划的 `plan_retention`，`session/retention.py`）、**并发写 phase1 marker（内含可恢复 intent：SessionCommitMsg + 原始/归档/保留三份消息清单）** + `{archive_uri}/messages.jsonl`、入队 Phase 2、写 ready marker；失败写 failed marker + 内存回滚 + 重抛 | **v0.5.0 已把回滚与 marker 逻辑拆出成模块**：`session/archive_store.py`、`session/checkpoints.py`（`CheckpointPlanner`/`CheckpointRequest`）、`session/working_memory.py` |
| 入队 | `QueueManager` + `SessionCommitMsg`（msg 构造 `:1519`、入队紧随） | `session.py:1519`、`storage/queuefs/session_commit_msg.py:26`——**该 msg 新增 `memory_policy_version: int = 1`**，用于让在途任务保留提交当时的 WM 语义（`:38-41` 把无版本号的历史快照强制成 `working_memory.enabled=True`） |
| **Phase 2**（Memory extraction） | SessionCommit 队列消费者（**并发 8、1s 轮询**，`queue_manager.py:29 DEFAULT_MAX_CONCURRENT_SESSION_COMMIT = 8`、`:106 _REQUEUE_POLL_INTERVAL = 1.0`）→ `session.resume_queued_commit(msg)`；session 不存在则 fail task；**未处理完 → 重新入队 + `ProcessResult.requeued()`**（同格下方已给出准确锚点；旧文曾误写成不存在的 `report_requeue` 符号） | `queuefs/session_commit_processor.py:25`（类）、`:64-80`（missing session → tracker fail）、`:83`（`processed = await session.resume_queued_commit(msg)`）、`:84-91`（重入队）、`:116-125`（`on_dequeue` → `ProcessResult.success()/requeued()/failed()`）。**提交处理器本体已移到 `session.py:1699 resume_queued_commit`** |

Phase 2 续跑入口：`session.py:1947` `_run_memory_extraction()`；分批：`_extract_long_term_memories_with_batching()`（`:1857`，批计划 `session/extraction_batch.py:26-31`）。

自动提交策略：`session/auto_commit_policy.py:19-23`——默认 150k token / 100 条消息 / 空闲 1 天；**会话默认关闭自动提交**（`:5-6` docstring）。**执行者是服务端常驻调度器** `SessionAutoCommitScheduler`（`service/session_auto_commit.py:44-53`）。

> **v0.5.0 改了调度参数**（`openviking_cli/utils/config/memory_config.py:12-33`）：默认间隔 **60s → 600s**；`scan_batch_size`/`scan_batch_pause_seconds` **删除**，改为 `scan_rate_limit_files_per_second = 2.0` 的限速扫描（`/local` 下 `.meta.json`，`SESSION_META_SUFFIX :24`、`AGFS_SESSION_SCAN_ROOT :25`）。方向很清楚：**从"批处理式扫"改成"限速式扫"**，理由写在字段 docstring 里——"bound background IO pressure when the sessions directory is very large"。对运维的含义：自动提交的**最长延迟从 1 分钟级变成 10 分钟级**。

## 抽取是 agentic 的

- 抽取主循环：`session/memory/extract_loop.py:117` `ExtractLoop`（"single LLM call with tool use" ReAct，`:4`）；操作解析 `resolve_operations` `:767`（isolation handler 落 URI，`memory_isolation_handler.py:347-400`）
- **注册表里有 3 个只读工具，但 LLM 实际只看到 1 个（或 0 个）**——这是 2026-10-19 复核修正的一处重要口径错误。注册的三个是 `read`（tools.py:174，剥 links/backlinks 隐藏字段）/ `search`（`:264`）/ `ls`（`:329`），注册语句 `:455-457`；**但 `SessionExtractContextProvider.get_tools()`（`session_extract_context_provider.py:617-622`）只返回 `["read"]`**，且在 `memory.eager_prefetch=True`（默认）时**返回空列表**——注释写明"eager_prefetch 模式下不提供工具，所有内容已在 prefetch 中加载"。`search`/`ls` 只被预取逻辑内部调用（`:565-590`），不暴露给模型；`SearchTool` 真正进工具面是**离线 compile 路径**（`consolidation_context_provider.py:74-79`），`patch_merge_context_provider.py:163` 同样返回 `[]`。
  **教训**：注册表大小 ≠ LLM 工具面。原文把 `register_tool` 的三次调用当成了模型可调用的工具集，这正是"函数存在 → 所以被用"的推论跳跃。无论如何，**LLM 没有 write 工具**这一结论成立：写入是 LLM 最终输出的结构化 operations（create/update/delete/reorganize 计划），经 resolve_operations 执行
- 抽取上下文提供者：`session/memory/session_extract_context_provider.py:54`；指令文案（`:211`）要求产出"single atomic plan to **create, update, delete, or reorganize** memories"；另有 `_eager_prefetch` 读取点 `:83`
- **抽取前先预取已有记忆**：`session_extract_context_provider.py:481` `prefetch()`（用 `MemorySearchTool`/`MemoryReadTool` 拉相关已有记忆）——LLM 看到旧记忆才决定新记忆的去向。注意这两个工具是在 **prefetch 内部**被调用的，不是作为工具暴露给模型（见上一条）
- 流式增量更新的定位：`memory/streaming_memory_updater.py:155` **不是聊天实时通道**——它是 compressor_v3 patch-merge 抽取内、ExtractLoop 产出 operations 之后的**操作合流/分批应用器**（`:155`/`:161`/`:172` 入口、分组合流 `:490 _apply_operations`、append-only 快路径 `:367 _apply_append_only_request_now`；与 extraction_id 绑定防跨快照误合并，`dataclass.py:157-163`；构造点 `compressor_v3.py:729-750`）

## 决策分工：LLM 判语义，代码守边界

**决策主体是 LLM，不是相似度阈值函数**：

- 合并安全策略作为 prompt 注入：`memory/merge_policy.py:5-19` `MEMORY_MERGE_POLICY`——"相似只是候选线索；**同 identity 才可 merge**；删除前每条事实须有归宿；不确定就保持独立"；注入点 `session_extract_context_provider.py:242`、`patch_merge_context_provider.py:148`
- 写入策略按 schema 字段定义：`memory/merge_op/base.py:121-127` `MergeOp = PATCH | REPLACE | SUM`（另有 `IMMUTABLE`，如 `prompts/templates/memory/entities.yaml:33,39`）

**代码侧只做确定性 skip**（policy/validation 层）：

- `memory/dataclass.py:173-184` `MemoryOperationSkipCode` 9 种：memory_type_filtered / self_memory_disabled / peer_memory_disabled / invalid_peer_id / peer_not_allowed / invalid_ranges / ambiguous_target / no_writable_target / page_id_type_mismatch
- 结构化记录 `SkippedMemoryOperation`（:194-204）；处理优先级 `memory/memory_isolation_handler.py:26-44`
- 合并执行：`memory/merge_op/`（patch/replace/sum/immutable/link_merge，工厂 `factory.py`）；**执行语义是 per-URI 先读盘上最新内容再逐字段 apply**（同批连续 patch 可见彼此，`memory_updater.py:1089-1130`）；链接写入 `memory_updater.py:104` `write_stored_links()`
- **闭环**：memory 写入后 `enqueue_embedding_msg(level=DETAIL)` 复用与资源同一条 Embedding 队列（`memory_updater.py:1874`）+ 父目录 SemanticMsg（45s 去重窗口，`semantic_queue.py:17`）刷新 overview——完整链见 [05](05-lifecycle-deep.md)
- **Phase 2 还能产 skill**：compressor_v3 支持可选 skill 抽取（`session/compressor_v3.py:56-58` 注册表、`:251-258` 注入），落盘经 `session/skill/skill_operation_updater.py`——记忆九分类之外的第二条输出支线
- **session 的物理形态也是 VFS 数据记录**：`{session_uri}/history/archive_NNN/messages.jsonl` + `.meta.json` + phase1/ready/done marker（命名与构造见 `session.py:1519` 与 `session/archive_store.py`、`session/working_memory.py`）——与 [01](01-viking-uri-and-vfs.md) "目录即数据记录"呼应

## 易误解点

0. **Working Memory 默认关闭（v0.5.0，本篇最重要的一条）**。`MemoryPolicy.enable_working_memory` 默认 `False`（`session/memory_policy.py:94`，旧名 `working_memory_enabled` 默认 `True`）。要点：
   - 想开就显式设策略，或 **per-commit 覆盖**：`enable_working_memory`（`session.py:1218/1243` → `service/session_service.py:375/398/413/439` → REST `server/routers/sessions.py:590`）。严格 bool：`null` = 跟随策略，字符串/数字拒绝。
   - **`to_dict()` 现在总是输出 `working_memory` 键**（`:131-140`，注释说"Queue and recovery snapshots must preserve explicit opt-in across default changes"）。这是为了不再重演"旧序列化器没写字段 → 显式 true 被读成默认 false"那个坑。
   - 老的持久化快照没有这个字段，走 `memory_policy_version=0` 路径被强制 `True`（`session_commit_msg.py:38-41`）——**在途任务不受默认值翻转影响**。
   - **没变的是**：原始消息归档、长期记忆抽取、profile、recall。变的只是 working memory 这一路。
   - 官方升级说明：`docs/en/guides/working-memory-default-off.md`。
1. **"记忆合并"没有相似度阈值**：merge 的守门人是注入 prompt 的 `MEMORY_MERGE_POLICY`（identity 相同才 merge），不是余弦相似度切线。检索侧的相似度只影响"预取哪些旧记忆给 LLM 看"。
2. **commit 不是同步写记忆**：`commit()` 返回时只保证 Phase 1（archive 落盘 + 入队）；记忆要等 Phase 2 异步消费完才存在。
3. **热度已退出检索打分（v0.5.0 反转）**：`retrieve/memory_lifecycle.py:18` `hotness_score()`（sigmoid 访问频次 × 指数时间衰减，半衰期默认 7 天）仍然存在，但**唯一消费者是 `storage/stats_aggregator.py:96`**——它进的是记忆健康度统计面板。`HierarchicalRetriever` 里已经没有 hotness 项、没有 `apply_hotness`、没有 `hotness_alpha`。旧文"仅 THINKING 模式混入检索打分"**作废**。
4. **账号级记忆模板（v0.5.0 新增）**：`/local/{account_id}/_system/memory_templates/{memory_type}.yaml`（`session/memory/account_templates.py:66`），可编辑字段限 `profile/events/preferences/entities/soul/identity`（`:45-52`），1 MiB 上限、jinja 校验、短锁；管理面 `server/routers/admin.py:680/706/728/752`（`GET/PUT/DELETE /api/v1/admin/accounts/{account_id}/memory-templates[/{memory_type}]`）。这意味着**记忆的抽取口径可以按账号定制**，不再只有全局 prompt。

## 状态标注

- 硬事实：两阶段流程、队列消费者、agentic 工具集、9 种 skip code、MergeOp 枚举、默认自动提交参数（core-evidence §4 + 2026-09-12 深挖复核）
- 已展开（原"未展开"项）：streaming_memory_updater 定位（操作合流器，非实时通道）；工具面只读性
- 未展开：`MEMORY_MERGE_POLICY` 的完整 prompt 文本逐句分析；账号级模板与全局 prompt 的合并优先级
- 反转记录（2026-10-19，v0.5.0）：WM 默认关闭；热度退出检索打分；自动提交间隔 600s/限速扫描；`MergeOp` 补 `IMMUTABLE`；session.py 锚点整体前移约 600 行，marker/回滚逻辑拆入单独模块
