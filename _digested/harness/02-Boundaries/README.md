# 02-Boundaries — 边界评价

> **基线**：`v0.5.0`（2026-10-19 复核；建档基线 `0f77ab56`）。
>
> 评价 OpenViking 的能力边界：哪些东西设计上就是封闭的、封闭得有没有道理、有没有护栏。

## 篇目

| 篇 | 回答什么 |
|---|---|
| [2.1_closed_enums.md](2.1_closed_enums.md) | URI scope / 内容类型 / L0-L1-L2 层级 / 合并策略——四处封闭枚举的封闭性检查（v0.5.0：**四处枚举全部未变**，只有消费点迁移） |
| [2.2_version_contracts.md](2.2_version_contracts.md) | 版本契约：tag 命名空间、ovpack/OVPACK_FORMAT_VERSION、INDEX_FORMAT_VERSION、schema 兼容口径（v0.5.0：`used` 与 `heartbeat` 被静默删除，判断被两次兑现） |
