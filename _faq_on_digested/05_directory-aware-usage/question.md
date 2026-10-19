# 问题：Directory-Aware Query and Maintenance in Vector Databases（TrieHI/DSQ/DSM）这套设计，在"用法"上到底有什么要求？怎么组织内容、怎么利用，才能最大发挥它的优势？

> ⚠️ **本问题是按建档基线 `0f77ab56`（≈`v0.4.19`）提出的，其中一部分机制前提在 `v0.5.0` 已不成立。**
> 具体说：文中提到的“目录递归 / 递归收敛 / 分数传播”在 `v0.5.0` **已被删除**（`hierarchical_retriever.py` 从 672 行缩到 381 行；`recurs`/`converg`/`score_propag` 全仓零命中）。
> **问题原文保留**，因为它是当时真实提出的问题；但读它时必须对照 [`answer.md`](answer.md) 的“反转记录”与 [`scenarios/_V050_RETRACTION.md`](scenarios/_V050_RETRACTION.md)。
> 换句话说：**这个问题的第 3 问，有一部分是在问一个已经不存在的机制该怎么用好**——本套文档最该讲清楚的就是这件事。

## 背景

`04_agentic-rag-foundation/` 已确认 Directory-Aware 论文（arXiv:2606.16903）是 OpenViking 目录感知检索的形式化根基：DSQ（目录语义查询）/ DSM（目录语义维护）算子 + TrieHI（原生前缀树索引），且论文 IV-C 节就是 "Deployment in OpenViking"。但它描述的是一套**抽象机制**，不是使用指南。真正的问题在用法层：

1. 什么样的场景能吃这套设计的红利？什么场景下它不划算甚至更差？
2. 内容应该怎么组织（目录粒度、命名、深度、类型分区），才能让"目录级 L0/L1 第一跳 + 目录递归"打中？
3. 检索/维护时怎么利用（scoped 查询、THINKING vs QUICK、重组）？
4. 为了吃到红利，配置/流程上有哪些前提（rerank、VLM 摘要、语义处理时序）？

## 证据边界

- **论文**：`_faq_on_digested/04_agentic-rag-foundation/_raw/directory_aware.txt`（全文，IV-B 成本模型 / IV-C 部署 / V-C 维护 / V-E 深度敏感性 / V-F OpenViking 端到端）+ `research.md` 对应章节。
- **源码**：`openviking/retrieve/hierarchical_retriever.py`（THINKING/QUICK 判定、L0/L1 第一跳——**这两条 `v0.5.0` 仍成立**；~~递归收敛、分数传播~~——**`v0.5.0` 已删，非死锚，是该能力被移除了**）；`docs/en/concepts/03-context-layers.md`（L0/L1 生成与白名单）、`07-retrieval.md`（context_type→根目录映射、score_propagation_alpha 默认 1.0）。
- **前序条目**：`03_rag-stack-volcano-vs-configurable/answer.md`（配置自由度，本条目只点到为止）、`04_agentic-rag-foundation/answer.md`（论文验证与对比数字）。
- **答案形态**：`answer.md` 为总纲；**按场景拆分的图文版**（Mermaid 检索链路图 + 目录组织树 + 示例命令）在 [`scenarios/`](scenarios/)（01 项目子树 / 02 记忆按人 / 03 多跳 QA / 04 重组 DSM / 05 反模式），入口看 [README.md](README.md)。
- **不做**：不评测具体库的实际最优层数/参数（无公开指南）；不重复 03 的配置全景。
