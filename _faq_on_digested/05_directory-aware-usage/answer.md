# 答案（总纲）：它是一套"使用契约"，不是"检索选项"——详细分析按场景拆分在 [`scenarios/`](scenarios/)（图文版）

## 一句话判断

Directory-Aware（TrieHI/DSQ/DSM）优化的不是"能不能搜到"，而是**"在目录作用域上做检索与维护"这件事本身**。它隐含三条使用要求：① 内容按**目录组织**，且目录名 + L0 摘要是检索第一跳的全部信号（**注意：这一条在 OpenViking v0.5.0 已不成立**，见下方反转记录；此处保留的是论文侧的适用前提）；② 查询表达成**带作用域的检索**（论文 IV-C 的适用前提：*"Queries often start from a directory scope and request coherent descendants, such as a project subtree or a user-memory branch."*）；③ **结构会演化**（MOVE/MERGE 是设计目标）。不满足这三条的用法（平铺内容、泛化目录名、全库查询、只走 find/QUICK）吃不到红利，还可能更慢。

## 场景化文档（图文版，一个场景一个 MD）

| # | 场景 | 何时读 |
|---|---|---|
| [场景 1](scenarios/01-project-subtree.md) | 项目/工作区子树检索 | 知识库按项目组织，"在某项目里找 X" |
| [场景 2](scenarios/02-user-memory.md) | 记忆按人/会话检索 | 用户偏好/历史经历跨会话复用 |
| [场景 3](scenarios/03-multi-hop-qa.md) | 多跳知识库 QA | 证据分散在多目录，需要组合 |
| [场景 4](scenarios/04-namespace-evolution.md) | 结构演化/重组（DSM） | 归档、搬迁、合并目录 |
| [场景 5](scenarios/05-anti-patterns.md) | 反模式 | 什么时候别用/救不了你 |
| [README](README.md) | 场景地图 + 选择速查 | 先看这里 |

## 三条使用契约（跨场景总纲）

1. ~~**目录 = 语义容器**：THINKING 第一跳只向量检索 L0/L1 目录记录（`hierarchical_retriever.py:227`，`level=[0,1]`），rerank 打目录 abstract（`:279-283`）~~ **v0.5.0 起这条作废，且原文的锚点是错的**（2026-10-19 修正）：全文已无 `level=[0,1]` 这个常量，`level` 现在**只来自调用方**（`hierarchical_retriever.py:101` 入参、`:191`/`:201` 透传），唯一的内部覆盖是 `:136-137` 的图像查询 `level=[2]`；不传 `level` 就是**全层召回，L0/L1 不再是"第一跳"**。原文引的 `:227` 在 v0.5.0 是 rerank 打分循环，`:279-283` 也已不是那个位置。
   **仍然成立的半条**：embedding 白名单只有 `directory` 字段（`03-context-layers.md:128-138`），元数据靠 `scope_dsl` 过滤——即"目录名要有区分度"这个**写作建议**依然有效，但它的机制基础（L0/L1 独立第一跳）没了。
2. **查询 = 作用域检索**：带 `target_uri`/`scope_dsl` = 论文的 DSQ；论文 Figure 11：*"retrieval quality generally improves as the query path becomes more specific"*——**作用域越具体，质量越高**；~~目录红利只在 THINKING（`search()`；`find()` 固定 QUICK 无递归，`_semantic.py:285`；没配 rerank 默认 QUICK，`hierarchical_retriever.py:126-127`）~~ **v0.5.0 起这条作废**：`THINKING`/`QUICK` 现在只决定"recall 之后要不要 rerank"，**没有任何递归**（`hierarchical_retriever.py:110-113`）；`find()` 仍固定 `mode=QUICK`（`_semantic.py:305-306`），`search()` 没配 reranker 时仍默认 `QUICK`（`hierarchical_retriever.py:122-123`），但两者的差别只剩 rerank，不再是"目录递归 vs 扁平"。
3. **结构 = 可演化**：MOVE/MERGE 是 DSM 的目标负载（TrieHI 下 tree-local：子树重挂 + 祖先聚合更新，论文 V-C）；重组后等 `freshness` 冒泡（`pending_child_changes`）再检索。

## 配置/流程前提（详见 [FAQ 03](../03_rag-stack-volcano-vs-configurable/answer.md)）

- **rerank 必配**：不配则 search 默认 QUICK——**v0.5.0 语义已变**：不是"目录递归消失"，而是"候选不做 rerank 精排、直接按向量分返回"；
- **VLM 必配**（7 provider 任一）：L0/L1 摘要依赖它生成，且是异步时序（ingest 后等 SemanticProcessor 完成）；
- **local 后端无 BM25**：关键词召回需 VikingDB 系；
- ~~可调：`retrieval.score_propagation_alpha`（默认 1.0）、`MAX_CONVERGENCE_ROUNDS=3`、`GLOBAL_SEARCH_TOPK=10`~~ **v0.5.0：这三个旋钮全部消失**——`score_propagation_alpha` 全仓零命中，`RetrievalConfig` 只剩 `recall_intent_timeout_s` / `recall_rewrite_timeout_s` / `enable_intent` 三个字段（`openviking_cli/utils/config/retrieval_config.py:9-23`）。可调的检索参数现在是 `find/search` 的 `--search-type`、`--threshold`、`--level`、`--after/--before`。

## 状态标注

- 【硬事实】THINKING/QUICK 判定与 find 固定 QUICK（`hierarchical_retriever.py:122-123`、`_semantic.py:305-306`）、L0/L1 第一跳（旧 `:227`）、递归收敛与 L2 终点（旧 `:554-588`）、并发上限（旧 `:495`）、context_type→根目录映射（旧引 `docs/en/concepts/07-retrieval.md`；今 `openviking/core/retrieval_targets.py:56-83`）、embedding 白名单（`03-context-layers.md:128-138`）——**基线 `0f77ab56`；其中"递归/第一跳/并发"三项在 `v0.5.0` 已删除，见下方反转记录**
- 【外部事实·已验证】TrieHI 成本模型（论文 IV-B）、适用前提（IV-C）、DSM tree-local（V-C）、深度敏感性（V-E）、端到端数字（V-F Table VI/VII）——`04_agentic-rag-foundation/_raw/directory_aware.txt`
- 【解释】"使用契约"归纳；场景划分；粒度/深度建议（2–5 层）为经验性判断
- 【未定】深度×后端（PG/IVF）×数据量的最优配置无公开指南；freshness 冒泡实际收敛时延未实测

---

## 反转记录（2026-10-19，v0.5.0 复核）

**结论级：本 FAQ 的核心使用契约"按目录组织 + 作用域检索 + 结构演化"在 v0.5.0 失去了它所依附的机制。**

| 本 FAQ 依赖的东西 | v0.5.0 状态 | 证据 |
|---|---|---|
| THINKING 目录递归（多轮优先队列下钻） | **删除** | `hierarchical_retriever.py` 672 行 → 381 行，全文件无递归/depth/收敛逻辑 |
| L0/L1 作为"检索第一跳" | **不再是检索路径** | 单次全局 recall（`:184-204`），`level` 只是过滤条件 |
| `score_propagation_alpha` 分数传播 | **删除** | 全仓零命中 |
| `MAX_CONVERGENCE_ROUNDS=3` / `GLOBAL_SEARCH_TOPK=10` | **删除** | 全仓零命中 |
| `freshness` 父冒泡等待（场景 4 的"重组后等冒泡"） | **仍存在** | `abstract_overview.py:671 plan_abstract_overview_refresh` |
| DSQ（作用域检索 `target_uri`/`scope_dsl`） | **仍存在且更核心** | `core/retrieval_targets.py:28-83`、`_build_scope_filter` |
| DSM（MOVE 后结构演化） | **仍存在** | 向量 URI 重写链完整 |

**净判断**：DSQ 与 DSM 仍然成立，**TrieHI 的"递归下钻"形态已不存在**。因此本文的"三条使用契约"里，**第 1 条（目录名 + L0 摘要就是第一跳信号）和第 2 条的后半句（目录红利只在 THINKING）不再成立**；第 3 条（结构可演化）仍成立。

论文侧的结论（TrieHI/DSQ/DSM 的适用前提）**是外部事实、不受上游改动影响**——但"OpenViking 现在是否按论文那样实现"的答案已经变成**部分不再**。完整的机制现状见 [`_digested/core/03-retrieval-global-recall.md`](../../_digested/core/03-retrieval-global-recall.md)。
