# architecture/ — 工程结构与实现边界

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。本目录回答：**OpenViking 的多语言 monorepo 里，每一层到底负责什么、谁调用谁、哪些"看起来是一回事"的名字其实无关？**

## 这是什么

`core/` 讲机制语义（viking:// 怎么运转），`integration/` 讲外部怎么接进来，本目录讲**实现边界**：机制落在哪一层代码、哪个语言、哪个进程内组件上。它是 [`../core/`](../core/) 的"往下挖一层"，也是评价层 [`../harness/01-Architecture/`](../harness/01-Architecture/README.md) 的事实基础。

## 篇目

| 篇 | 回答什么 |
|---|---|
| [01-three-languages.md](01-three-languages.md) | Python / Rust / C++ 三层的真实边界与调用图；两组"abi3"撞名陷阱；双层存储架构（图示：[callgraph.svg](callgraph.svg)）；**含一处 baseline 即错的锚点更正**（C++ 扩展真名是 `_native`/`_x86_*`，不是 `_ov_engine_backend`） |
| [02-native-internals.md](02-native-internals.md) | 原生层内部：MountableFS 路由器、包装器洋葱、7 插件、git 语义对象存储、PyO3 方法面、C++ 四 capsule 与"内存扫描+SIMD"索引 |

## 与其他维度的关系

- 机制语义（这些边界**为什么**长这样）：[`../core/`](../core/README.md)
- 外部接入面（这些边界对外**暴露成什么**）：[`../integration/`](../integration/README.md)
- 平台评价（这些边界**好不好**）：[`../harness/01-Architecture/`](../harness/01-Architecture/README.md)
- 落盘与跨平台（内容层 Rust 侧的**行为细节**）：[`../vfs/`](../vfs/README.md)
- 取证底账：[`../_notes/core-evidence.md`](../_notes/core-evidence.md) §5-§6（两篇正文的主要证据来源）

## 待补

- `crates/ov_cli`（Rust CLI）命令面内部——接入侧已有 [`../integration/02-ov-cli-reference.md`](../integration/02-ov-cli-reference.md)，实现侧（TUI/wizard/compile 管线）未深挖
- `bot/`（VikingBot）与 `web-studio/` 的工程结构
- **`openviking_gateway/`（v0.5.0 新增的第七种接入形态，约 7k 行纯 Python ASGI）的工程结构**——它刻意与内核零代码耦合，值得作为"内核外围进程"的样本单独看
