# 问题：OpenWiki（Google 的 OKF？"一种帮 agent 探索结构化知识的协议"）和 OpenViking 是什么关系？我们支持吗？谁更好？

## 背景

在调研中遇到 [OpenWiki](https://github.com/langchain-ai/openwiki)（`langchain-ai/openwiki`，npm `openwiki`）：一个"self-maintaining wiki" CLI——agent 读代码库/个人知识源，合成并持续维护一套 linked Markdown wiki，宣称 "Built for agents, explored by humans"。记忆里它是"Google 出来的、帮 agent 探索结构化知识的协议"，与 OpenViking 的 viking:// 上下文文件系统似乎在解决相邻的问题。

两个项目各自的关键事实（调研中确认）：

- **OpenWiki**（`langchain-ai/openwiki`）由 LangChain 维护；其输出的 **Open Knowledge Format（OKF）v0.2** 规范出自 Google（[GoogleCloudPlatform/knowledge-catalog](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)）。
- **OpenViking 的 L0/L1 sidecar 用的正是 "minimal OKF-style Markdown"**（`docs/design/l0-l1-okf-sidecars-rfc.md:1-12`）：YAML frontmatter + body，且 RFC 自述 "intentionally narrower than general OKF wiki pages"（:121）。两个项目在**同一个格式家族**里出现了。

## 具体困惑

1. OpenWiki 到底是什么品类？（协议？工具？数据库？）它和 OpenViking 是竞品、同族，还是互补层？
2. "我们支持它吗"——OpenViking 能不能消费/兼容 OpenWiki 的产出？
3. 两边都叫 OKF：是显式的规范遵循，还是巧合的命名趋同？（OpenViking 的 RFC 里 grep 不到对 Google spec 的任何引用）
4. 如果只选一个，判据是什么？

## 证据边界

- **OpenViking 侧**：`_digested/`（`00-the-root` / `core/01-04` / `integration/01-02`）+ 源码 ~~`docs/design/l0-l1-okf-sidecars-rfc.md`~~、`openviking/storage/abstract_overview.py`（基线 `0f77ab56`）。
- **OpenWiki 侧**：仅依据其官方 README（GitHub raw，2026-09 抓取）与 OKF spec 链接，**未做源码审计**。
- 本问题涉及外部项目，凡引用 OpenWiki 行为均标【外部事实】；凡涉及两格式同源性的判断均标【解释/未定】。
