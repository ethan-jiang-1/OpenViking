# 01-Architecture — 结构与接缝评价

> **基线**：`v0.5.0`（2026-10-19 复核；建档基线 `0f77ab56`）。
>
> 评价 OpenViking 的扩展接缝设计。机制事实见 [`core/`](../../core/) 与 [`architecture/`](../../architecture/)，本目录只做判断。

## 篇目

| 篇 | 回答什么 |
|---|---|
| [1.1_extension_seams.md](1.1_extension_seams.md) | 第三方能插入的点有哪些、用什么机制插入、哪些是"暗门"（v0.5.0：adapter 白名单 5→6、MCP 15→20） |
| [1.2_layering_discipline.md](1.2_layering_discipline.md) | service/core/storage/retrieve 的依赖方向：两处实证的反向边与"CLI 外衣的共享内核"（v0.5.0：反向 import 282→**319**，恶化） |
| [1.3_data_seams.md](1.3_data_seams.md) | 数据三道接缝的开放度梯度：provider 宽（配置即换）、ingest 中（公开装饰器）、parse 窄（私有注册）（v0.5.0：ingest **6→8**，唯一真长出新适配器的接缝） |
