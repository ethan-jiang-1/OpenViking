# ⚠️ v0.5.0 反转通告：本目录的机制描述已过期

> **这份文件是给 `_faq_on_digested/05_directory-aware-usage/` 下所有 `scenarios/*.md` 与上级 `README.md` 补的删除戳。**
> 2026-10-19 的 `v0.5.0` 复核只改了 `answer.md` 与顶层 `README.md`，**场景文档与 上级 `README.md`（本目录） 从未被复核**，
> 因此它们仍把已删除的机制当现在时描述。**读任何场景文档前先读这张表。**

## 一句话结论

`v0.5.0` 的 `HierarchicalRetriever` 是**单次全局向量检索 + 可选 rerank**。
`v0.4.x` 那套"L0/L1 第一跳 → 递归下钻 → 分数传播 → 收敛停止"的两级检索**已被整个删除**。

## 已删除 vs 仍成立

| 场景文档里写的 | 现状 | 证据 |
|---|---|---|
| "第一跳只搜 `level=[0,1]`" | **不存在**。`level` 是**调用方传入的结果过滤器**，不是内部检索路径 | `grep -rn 'level=\[0' openviking` → 零命中；`hierarchical_retriever.py:101` 是 `level: Optional[List[int]] = None` 形参 |
| "`hierarchical_retriever.py:227` 只搜 L0/L1" | **行号与语义都错**。`:227` 是 rerank 打分调用 | `hierarchical_retriever.py:227` = `scores = await self._rerank_scores(` |
| "目录递归下钻" | **已删除** | `grep -nE "recurs\|priority\|converg\|score_propag" openviking/retrieve/hierarchical_retriever.py` → 零命中 |
| "并发进入子目录 ≤4"（`MAX_PARALLEL_CHILD_SEARCHES`） | **已删除**，全仓零命中 | 同上 |
| "topk 连续 3 轮不变收敛停"（`MAX_CONVERGENCE_ROUNDS`） | **已删除**，全仓零命中 | 同上 |
| "分数传播"（`score_propagation_alpha`） | **已删除**，全仓零命中 | 同上 |
| THINKING / QUICK 两种模式 | **仍存在，但语义变了**：只表示"召回后要不要 rerank"，与递归无关 | `hierarchical_retriever.py:122-123` |
| DSQ 作用域检索（`target_uri`/`scope_dsl`） | **仍成立，且是现在的主路径** | `openviking/core/retrieval_targets.py:28-83`、`_build_scope_filter` |
| DSM（MOVE 后向量 URI 重写） | **仍成立** | 重写链完整 |
| `freshness` 父级刷新 | **仍成立** | `openviking/storage/abstract_overview.py:671` |

官方文档现在明说这件事（`docs/en/concepts/07-retrieval.md:82`）：

> `HierarchicalRetriever` runs one global vector search per query. … Without an explicit `level`, text queries can directly match L0/L1/L2 records; **retrieval does not navigate directories recursively.**

## 场景文档里还剩什么有效

这些文档的**用法建议**大多仍成立，**机制解释**大多不成立。区分办法：

- ✅ 仍成立：把目录按主题拆好、写好 L0 摘要、用 `target_uri` 限定作用域、结构可演化（MOVE 成本低）——这些是**数据组织**建议，与检索实现无关。
- ❌ 不成立：凡是以"第一跳""递归""收敛""分数传播""并发子目录"解释**为什么**这些建议有效的段落。
- ⚠️ 论文数字（Table IV/VII 等）本身没错，但描述的是**论文里的 TrieHI 递归访问**，在 `v0.5.0` 的代码里**没有对应实现**。不能用它论证本仓库的行为。

## 为什么这张表要单独成文件

`answer.md` 有一张同样的反转表，但**场景文档没人读得到它**——它们是独立的、可单独引用的文档。把反转说明放在每个文件里会立刻失同步，放在 `answer.md` 里又管不到它们。共享一份、每个场景文件顶部链过来，是唯一不会腐化的摆法。

> **这条经验属于结构层面**：一个子目录里的文档如果"可以单独读、单独引用"，那它就不能依赖同级某一份文档里的免责声明。免责声明必须和它一起走。
