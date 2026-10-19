# core/ — Agent 内核机制：viking:// 文件系统、上下文分层、检索、记忆

> **基线**：OpenViking `v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56` = v0.4.19 + 57，变更见 [`../_change_log/0002`](../_change_log/0002-v0.4.19-to-v0.5.0.md)）。本目录回答：**OpenViking 内部是怎么把"上下文"组织成文件系统、怎么分层加载、怎么检索、session 怎么变成记忆的？**
>
> 取证原料：[`../_notes/core-evidence.md`](../_notes/core-evidence.md)（符号级证据链，201 行）。

## 写作定调

机制解剖文档（对齐 pi-mono `agent/` 的定位），评价视角（好不好、纪律如何）在 `harness/`（已建成，见 [`../harness/README.md`](../harness/README.md)）。

每篇默认顺序：**先给结论 → 机制拆解（带 文件:行号 锚点）→ 易误解点 → 状态标注（硬事实/解释/未定）**。

## 篇目

| 篇 | 回答什么 |
|---|---|
| [01-viking-uri-and-vfs.md](01-viking-uri-and-vfs.md) | viking:// URI 的命名空间与白名单、目录树怎么来、"像文件一样操作"的操作面在哪实现 |
| [02-context-layers.md](02-context-layers.md) | L0/L1/L2 三层是什么、谁生成、读取时怎么按层裁剪、设计稿与实现的同步程度 |
| [03-retrieval-global-recall.md](03-retrieval-global-recall.md) | find 与 search 的真实区别（QUICK vs THINKING = 是否精排）——v0.5.0 删除目录递归后重写 |
| [04-session-to-memory.md](04-session-to-memory.md) | commit 两阶段管道、agentic 记忆抽取、create/merge/skip 的决策主体 |
| [05-lifecycle-deep.md](05-lifecycle-deep.md) | 深潜：一条数据的完整生命周期（**八队列**、同步/异步边界、queuefs 机制、向量化与 rm/mv 语义）——图示 [lifecycle.svg](lifecycle.svg) |

## 阅读路径

1. 新人捷径：先看本目录 [lifecycle.svg](lifecycle.svg)（30 秒建立"五段"的空间感——**"五段"指一条数据走过的五个阶段**：同步请求 → AddResource → Semantic → 向量化 → 读路径。**别把它和队列数搞混**：QueueFS 里是 **8 个标准队列**；`queue-state.svg` 早先误写 7、`lifecycle.svg` 里的异步段早先误画成已删除的 `semantic_dag.py`，两者均已更正），再按下面顺序读
2. 先读 01 建立「目录即数据记录」的世界观
3. 再读 02 理解为什么检索天然是分层的（L0/L1 向量本身就是检索的一类记录）
4. 03 是全文的枢纽：理解 QUICK/THINKING（= 是否精排）后，01 的操作面和 02 的分层会在检索里汇合
5. 04 独立成篇，回答"记忆是怎么长出来的"
6. 05 把 01-04 的机制按时间轴串成一条链，并修正 03/04 的三处精度问题
