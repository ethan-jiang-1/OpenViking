# 03 检索：全局召回 + 一次精排（find 与 search 的真实区别）

> **基线**：`v0.5.0`（2026-10-19）。取证原料 [core-evidence §3](../_notes/core-evidence.md)。
>
> **本篇于 2026-10-19 重写。** 旧题《检索两级模型》描述的"THINKING 先找目录命中、再进目录递归探索"在 v0.5.0 **已被 upstream 删除**。反转变更与被删符号清单见 [`_change_log/0002` §1](../_change_log/0002-v0.4.19-to-v0.5.0.md)。旧结论不是"写得不准"，是**它描述的代码已经不存在**。

## 先给结论

v0.5.0 只有**一个**检索引擎：对每个 `TypedQuery` 做**一次全局向量召回**（scope / context_type / level 下推为索引过滤），`THINKING` 额外对召回候选做**一遍 rerank**。**不存在目录递归**——`_recursive_search`、`dir_queue`、父级分数传播、收敛判停、热度加权全部删除。

`find()` 与 `search()` 的差别因此**只剩三件**：① `find` 固定 QUICK（不精排），`search` 跟随配置；② `search` 能带 session 上下文做意图规划、拆成多条 `TypedQuery`；③ `search` 能按 `search_type` 切语义/关键词检索。

一句记住：**"聪明"来自精排与意图规划，不来自"下钻目录"。**

## 两个模式

模式枚举：`openviking/retrieve/hierarchical_retriever.py:47-49` `RetrieverMode = THINKING | QUICK`。类注释 `:53` 原话："Global retriever with dense and sparse vector support."

模式**不再是两套代码路径**，而是一个开关（`:122-126`）：

```python
if mode is None:
    mode = RetrieverMode.THINKING if self._rerank_client else RetrieverMode.QUICK
use_rerank = (mode == RetrieverMode.THINKING and self._rerank_client is not None
              and not image_query)
```

即：**THINKING 的充要条件就是"配了 rerank client"**。图像查询强制不精排。

### 唯一的一次召回

`retrieve()` 现在是 165 行的单程管道（`:92-256`），步骤固定为五步：

| 步骤 | 锚点 | 说明 |
|---|---|---|
| ① 定根与候选宽度 | `:175-183` | `root_uris` 来自 `target_dirs` 或 `default_target_directories(ctx, context_type)`；`search_limit = limit * RERANK_CANDIDATE_MULTIPLIER if use_rerank else limit`，其中 `RERANK_CANDIDATE_MULTIPLIER = 2`（`:55`） |
| ② 一次全局召回 | `:184-204` | `search_in_tenant`（语义，带 `sparse_query_vector` 混合稀疏）或 `search_by_keywords_in_tenant`（关键词）。`context_type` / `target_directories` / `extra_filter`(scope_dsl) / `level` / `limit` **全部下推为索引侧过滤** |
| ③ 按 URI 去重取最高分 | `:209-223` | 注释原话："Keep the highest-scored hit for each URI before model reranking."——**所有模式都做**，不再是 THINKING 专属 |
| ④ 可选精排 | `:226-231` | 只对已召回候选调 `_rerank_scores`，输入文本是候选的 `abstract` 标量 |
| ⑤ 阈值过滤 → 截断 | `:233-241` | 注释原话："A low vector score can still rerank highly, so filter only after reranking." 阈值**在精排之后**才应用 |

精排失败/返回非法值时回退向量分（`_rerank_scores`，约 `:309-324`）。

**被删掉的东西**（写客户端时最容易残留的旧心智）：

| 旧机制 | v0.4.19 锚点 | 现状 |
|---|---|---|
| `_recursive_search()` | `:421-580` | 删除 |
| 优先队列 `dir_queue`（`(-score, uri)` 堆） | `:452`、`:480-482` | 删除 |
| `MAX_PARALLEL_CHILD_SEARCHES = 4` | `:495` | 删除 |
| 分数传播 `final = α·score + (1-α)·parent_score` | `:531-533` | 删除 |
| 配置项 `retrieval.score_propagation_alpha` | `retrieval_config.py:82-83`（旧基线行号；该文件现已缩到 28 行） | **删除** |
| 配置项 `retrieval.hotness_alpha` + `apply_hotness` | THINKING 专属加权 | **删除** |
| 双条件收敛判停 `MAX_CONVERGENCE_ROUNDS=3` | `:558-581` | 删除 |
| THINKING 只召回 `level=[0,1]` 目录记录 | `:220-229` | 删除（现无 level 限制，除非调用方显式传） |

`openviking_cli/utils/config/retrieval_config.py` 现在只剩三项：`enable_intent`、`recall_intent_timeout_s`、`recall_rewrite_timeout_s`。

> **热度去哪了**：`retrieve/memory_lifecycle.py:18 hotness_score()` 仍存在，但唯一消费者是 `storage/stats_aggregator.py:96`——它进的是**统计面板**，不进检索打分。见 [04](04-session-to-memory.md)。

## 两种检索类型（v0.5.0 新增）

`search_type` 是第二根独立轴（`openviking/core/retrieval_types.py:7`）：

- `"semantic"`（默认）：向量召回，可混稀疏向量。
- `"keywords"`：BM25 全量文本检索，走 `search_by_keywords_in_tenant`（`hierarchical_retriever.py:185-193`）。**只有配了全文索引的后端支持**（volcengine / vikingdb）；图像查询被拒绝。

**Python 层两条路径都接受 `search_type`**（`_semantic.py:208` 的 `find` 签名、`hierarchical_retriever.py:104`），但**对外暴露并不对称**——这一点原文写笼统了（2026-10-19 修正）：

| 入口 | 能不能传 `search_type` |
|---|---|
| Python `find()` / `search()` | ✅ 都能（`_semantic.py:207`、`search_service.py:120`） |
| REST `POST /search` | ✅ `search_service.py:120` 有 |
| REST find | ❌ `FindRequest`（`server/routers/search.py:124-150`）**无此字段** |
| CLI `ov search` | ✅ `--search-type semantic\|keywords`（`crates/ov_cli/src/main.rs:975-982`） |
| CLI `ov find` | ❌ `Find` 子命令没有该参数，`handle_find` 也不接收（`main.rs:3915-3930`） |
| MCP `find`/`search` | ❌ 两者都没有该参数 |

**所以"关键词检索"这条能力在产品面上只能从 `search` 进入，`find` 永远走 semantic。** 原文写"`find` 与 `search` 都接受"，只在 Python 层成立。

## find 与 search

| | `find()` | `search()` |
|---|---|---|
| 锚点 | `_semantic.py:196-331` | `_semantic.py:393-564` |
| session 上下文 | 无 | 有（`latest_archive_overview` + `current_messages`） |
| 模式 | **固定 QUICK**（`_semantic.py:306` `mode=RetrieverMode.QUICK`） | 不传 mode → 有 rerank client 则 THINKING（`hierarchical_retriever.py:122-126`） |
| 意图规划 | 无 | 需要 `retrieval.enable_intent` **且** session 有 summary/messages 才触发（`:459-476`）；产出多条 `TypedQuery`，`asyncio.gather` 全并发（`:543`）后聚合 |
| 附加 | 支持 filter-only 查询（不走向量，`_find_by_filter`，`:333`） | 读目标目录 abstract 作为规划上下文（`:451-457`） |

`IntentAnalyzer`：`openviking/retrieve/intent_analyzer.py:38`，构造签名 `__init__(max_recent_messages=5, *, query_planner: VLMHandle)`（`:51`）——**planner 未解析时直接抛错**，不再是可空依赖。专用 prompt 由 `resolve_intent_analysis_prompt_id` 映射（约 `:30`）。

`TypedQuery.priority`(1-5) 仍然只是计划元数据，**不参与调度**——这条旧结论在 v0.5.0 反而更好证：现在压根没有调度队列了。

服务层入口：`service/search_service.py:108`（search）/ `:166`（find）/ `:211`（`find_skills`，见下）。

## skill 检索是包级折叠（v0.5.0 新增）

Skills 不走通用检索：`SkillPackageRetriever` 分页拉向量命中，然后**按 skill 根目录折叠成每包一条最佳命中**（`{root}/SKILL.md`），并过滤掉不可读的根。

- `openviking/retrieve/skill_package_retriever.py:20-37`
- `openviking/retrieve/skill_results.py:19-39`（折叠）、`:66-93`、`:96-127`
- `find_skills` 定义在 `service/search_service.py:211-253`，**调用方不止 Skills API**（2026-10-19 修正）：① Skills REST 路由 `server/routers/skills.py:611/642/654`；② **MCP `find` 在 `context_type="skill"` 时也走它**（`server/mcp_endpoint.py:476-477`）；③ 检索装配器的 skill 桶 `retrieve/context_assembler/gather.py:334`（经 `_safe_find`）。原文写"调用方只有 Skills API"，漏掉了 MCP 与检索装配两条。

理由很直白：一个 skill 包里可能有很多文件命中，agent 需要的是"哪个 skill 相关"，不是"哪个文件相关"。

## 易误解点

1. **旧README的偏差已被 upstream 自己修掉——但你的本地树可能还是旧的**。v0.4.19 的 README 写 "Vector search finds candidate directories, then explores their contents"；v0.5.0 `README.md:60` 改成 "**Search a directory, not the whole index.** … `find` runs a query directly; `search` plans retrieval from session context"。**本文旧版花在纠正这句话上的篇幅已全部作废**。（搬迁到 v0.5.0 之后工作树的 `README.md:60` 同样是新句，旧句已不存在。）
2. **"search 更聪明"现在来自两件事，不是三件**：rerank + IntentAnalyzer 多路查询。第三条"目录递归"已不存在。
3. **`level` 过滤改为索引下推**：v0.4.19 里 level 主要出现在递归路径上；v0.5.0 由 `search_in_tenant(level=...)` 一路传到 `viking_vector_index_backend.py:2988-2989` 的 `In("level", ...)`。分层仍然"先于检索存在"，但它现在是**过滤条件**而非**递归骨架**（[02](02-context-layers.md)）。
4. **`find` 的"固定 QUICK"没变**（`_semantic.py:306`）——这条 v0.4.19 结论仍然成立，别跟着一起反掉。
5. **精排的输入是 abstract，不是全文**：候选携带的 `abstract` 标量送进 reranker（`:228-231`）。官方的 `docs/en/concepts/03-context-layers.md` 明确 "The L1 rerank scalar remains the plain L1 body"——旧版本这里还有一句"rerank 看到的是 L1 文本"出自 `embedding_utils.py:445-446`，该区域现在是 abstract 字节截断注释，**引用作废**。

## 状态标注

- 硬事实：单程管道五步、`RERANK_CANDIDATE_MULTIPLIER=2`、THINKING⇔rerank 配置、`find` 固定 QUICK、去重与阈值顺序、递归符号全删、`keywords` 检索类型、skill 包级折叠（2026-10-19 对 `v0.5.0` 快照逐个锚点复核）
- 解释：upstream 为什么放弃递归——从 `69e71e4ff` 的提交说明读取，属**官方自述动机**，本文未独立验证"全局召回确实更优"
- 未定：`keywords` 检索在各后端上的实际召回质量；`SkillPackageRetriever` 的分页策略在大 skill 集下的表现
- 修正记录（2026-09-12）：收敛判停补为双条件；QUICK 无 rerank/hotness 补锚点；alpha 为配置项；TypedQuery priority 消歧；L2 预检索仅 ACL 开启
- **反转记录（2026-10-19，v0.5.0）**：两级递归模型整体作废并重写本篇。"README 口径偏差"条目作废（upstream 已改文）。（旧句已随搬迁消失。）
