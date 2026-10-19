# 问题：OpenViking 的"Agentic 式 RAG"背后到底是什么？它的根基论文是谁，有没有对比实验证明这种做法的优势？

## 背景

读 `_digested/` 和源码时注意到 OpenViking 的检索链路是"意图规划（IntentAnalyzer 生成多路 TypedQuery）→ 两级层级检索（THINKING 目录递归）→ rerank"的组合。这看起来很像业界说的 **Agentic RAG**（LLM 参与规划检索、多轮、多路），但实现上又有明显不同：它不是让 Agent 反复调检索工具的自由循环，而是**单次 LLM 规划 + 确定性的目录递归算法**。这种"像 Agentic 又不太像"的组合让人困惑，直觉上有几个问题：

1. 这种"目录感知 + 意图规划 + 自适应检索深度"的设计，其学术根基是什么？属于哪条研究线（agentic RAG / 层级检索 / 查询规划）？
2. README 的 Research 区引了三篇论文（VikingMem / Directory-Aware / VikingRAG），它们到底讲了什么，与代码实现的对应关系是什么？有没有对比实验证明这种"目录感知/按需升级多轮检索"的做法相对普通 RAG 有优势（精度、token 效率、延迟）？
3. 它和公开文献里知名的 Agentic RAG 方案（Self-RAG、CRAG、RAPTOR、Adaptive-RAG 等）是什么关系：同源、异类还是互补？

## 证据边界

- **源码**：`openviking/retrieve/hierarchical_retriever.py`、`intent_analyzer.py`、`openviking_cli/retrieve/types.py`（基线 `0f77ab56`）；官方概念文档 `docs/en/concepts/07-retrieval.md`、`03-context-layers.md`。
- **本地一手材料**：`README.md` / `README_CN.md` 的 Research 区（commit `c31e261b` #4924 引入）；`docs/en/concepts/01-architecture.md` 的设计原则。
- **网络材料**：arXiv 三篇论文（2605.29640 / 2606.16903 / 2609.11390）、docs.openviking.ai、blog.openviking.ai、以及公开的 Agentic RAG 综述与对比文献——所有网络结论须在 `research.md` 中标引来源，未验证的不写。
- **不做**：不把 README 的论文摘要当成论文正文；抓不到原文的论断一律标注 unverified。
