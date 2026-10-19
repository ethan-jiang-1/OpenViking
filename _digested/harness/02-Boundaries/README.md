# 02-Boundaries — 边界评价

> **基线**：`v0.5.0`（2026-10-19 复核；建档基线 `0f77ab56`）。
>
> 评价 OpenViking 的能力边界：哪些东西设计上就是封闭的、封闭得有没有道理、有没有护栏。

## 篇目

| 篇 | 回答什么 |
|---|---|
| [2.1_closed_enums.md](2.1_closed_enums.md) | URI scope / 内容类型 / L0-L1-L2 层级 / 合并策略——四处封闭枚举的封闭性检查（v0.5.0：**四处枚举全部未变**，只有消费点迁移） |
| [2.2_version_contracts.md](2.2_version_contracts.md) | 版本契约：tag 命名空间、ovpack/OVPACK_FORMAT_VERSION、INDEX_FORMAT_VERSION、schema 兼容口径（`used` 于 **`v0.4.22`** 静默删除；~~`heartbeat` 被删除~~——**从未存在，已撤回**；`v0.5.0` 真正兑现的是 MCP 工具 15→20 的纯增量，判断被兑现**一次**） |
