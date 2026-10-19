# FAQ on Digested · 基于消化材料的二次研究

这个目录不是面向学习者的 FAQ。这里的每一个问题是我们在阅读消化材料、翻源码的过程中**自己产生的困惑**，答案需要跨越多个 `_digested/` 条目、甚至结合源码才能综合出来。

简单说：**一子目录 = 一个探究过的问题，答案是自己综合出来的，不是从某一份材料里直接抄的。**

> **当前研究基线（2026-10-19 起）**：涉及运行时行为的结论以 OpenViking **`v0.5.0`（`20f9c1136`，2026-10-09）**为准；pi-mono 侧以 `v0.85.1`（`d981de122`）的消化材料为准。旧版本仅用于变更史解释。
>
> ⚠️ **本目录的 answer.md 大多写于 `0f77ab56`（= v0.4.19 + 57）基线**。v0.5.0 对检索层做了结论级破坏性改动（两级递归 → 单遍全局召回，~~`semantic_dag.py`~~ 删除），因此 **01–05 每一篇都在文末加了「反转记录」段落**，标明哪些结论仍成立、哪些作废。读答案前先读反转记录。
>
> 另注（2026-10-19 更新）：`ethan` 分支已搬迁到 **`v0.5.0` 源码之上**，工作树就是 `20f9c1136`，**本文里的 v0.5.0 锚点现在可以直接在工作树里核对**。搬迁前的纯文档分支留档在 `backup/ethan-before-v050`。

## 和 `_digested/` 的区别

| | `_digested/` | `_faq_on_digested/` |
|---|---|---|
| 读者 | 第一次研究 OpenViking 的人 | 我自己（产出者） |
| 答案来源 | 源码消化 + 整理 | 跨多份消化材料 + 源码的综合推断 |
| 本质 | 文档 | 研究过程的归档 |
| 粒度 | 按主题分 section | 一个问题一个子目录 |

## 目录结构

```
_faq_on_digested/
├── README.md
└── <NN_question-slug>/
    ├── question.md        # 问题描述 + 背景 + 证据边界（必有）
    ├── answer.md          # 答案 / 分析 / 结论（必有）
    ├── research.md        # 可选：原始研究过程，比 answer 粗糙，04 有
    ├── README.md          # 可选：问题本身需要多篇子文档时作导航，05 有
    ├── scenarios/         # 可选：05 的场景化展开
    └── _raw/              # 可选：原始素材，04 有
```

> 上面标"可选"的三项目前只有 04、05 用到，**不是所有问题都必须有**——`question.md` + `answer.md` 是唯一硬约定。

## 命名约定

- `NN_` 数字前缀按创建时间排序；slug 用英文
- 引用 `_digested/` 材料用相对路径；引用源码标 commit hash 或 tag

## 已有问题

- [`01_server_first_vs_library_first/`](01_server_first_vs_library_first/question.md) — 为什么 pi-mono 刻意不做 HTTP server，而 OpenViking 一切接入都必须有 server？两种"灵活"的取向差异是什么？
- [`02_openwiki-okf-vs-viking/`](02_openwiki-okf-vs-viking/question.md) — OpenWiki（LangChain）与 Google OKF 和 OpenViking 是什么关系？竞品、同族还是互补层？"我们支持吗"？
- [`03_rag-stack-volcano-vs-configurable/`](03_rag-stack-volcano-vs-configurable/question.md) — OpenViking 的 RAG 栈（embedding/rerank/VLM/向量库/BM25）是完全依赖火山吗？可自配到什么程度？"有 BM25 吗"的准确答案是什么？
- [`04_agentic-rag-foundation/`](04_agentic-rag-foundation/question.md) — OpenViking "Agentic 式 RAG"的根基是什么？官方三篇论文（VikingMem / Directory-Aware / VikingRAG）讲了什么，有没有对比实验证明这种"目录感知 + 按需升级检索"的做法有优势？
- [`05_directory-aware-usage/`](05_directory-aware-usage/question.md) — Directory-Aware（TrieHI/DSQ/DSM）在用法上有什么要求？[`scenarios/`](05_directory-aware-usage/scenarios/) 按场景拆分为图文版（项目子树 / 记忆按人 / 多跳 QA / 重组 DSM / 反模式），说明典型场景、内容组织方式、检索与维护姿势。

## v0.5.0 一致性复核结论（2026-10-19）

- **链接完整性**：本目录 19 个 md + `_digested/` 46 个 md = 共 **65** 个 md，内部相对链接 **0 处失效**（2026-10-19 实测；此前写 61，漏数）。
- **结论级作废**：`04`、`05` 的核心机制论证（目录递归 / L0-L1 第一跳 / 分数传播）在 v0.5.0 已无对应实现；`02`、`03` 只作废了「两级检索」这一句前提。
- **仍然完全成立**：`01`（server-first 对照，且因 gateway 更强）、`03` 的全部 provider/BM25 结论、`04` 的意图分析部分、`05` 的论文侧外部事实与 DSQ/DSM 部分。
- **一手来源损失**：`02` 依赖的 ~~`docs/design/l0-l1-okf-sidecars-rfc.md`~~ 已随 `docs/design/` 整目录被 upstream 删除。
