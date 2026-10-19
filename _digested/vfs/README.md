# vfs · 虚拟文件系统的落盘与跨平台

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。取证原料 [`_notes/vfs-platforms-evidence`](../_notes/vfs-platforms-evidence.md)。本维度是 [`core/01`](../core/01-viking-uri-and-vfs.md)（命名空间与操作面）向下补的一层：**viking:// 到底怎么落到磁盘、在三个 OS 上分别怎么表现**——这正是 core-evidence 附录"未深挖清单"第 2 条（Rust ragfs 内部）的落地。

>
> **v0.5.0 影响**：~~本维度讲的是 Rust ragfs 与 OS 的接缝，**v0.5.0 未改动这一层**~~
>
> ⚠️ **2026-10-19 更正：这句话是错的，已撤回。** 真正未变的是**洋葱顺序、7 插件、`chmod` no-op、Windows `MoveFileExW`** 这些"结构件"；但 `crates/ragfs/src` 实测 **34 文件 / +4481−1083**（**基线 `0f77ab56`→`v0.5.0`**；若按发布 tag `v0.4.19`→`v0.5.0` 则是 **+4491−1084**——两个数都真实，差别只在起点，引用时必须写明用哪个），是本轮改动第二重的层。按幅度：
>
> | 变化 | 证据 |
> |---|---|
> | PathLock 后端从 **2 个变 3 个**：新增 Redis 后端 `RedisPathLockProvider` | `lock/cache_provder.rs` **文件新增**（内容 1869 行），`lock/mod.rs:27` 导出 |
> | 锁配置长出 `provider` 三选一 + `namespace` | `openviking_cli/utils/config/agfs_config.py:308-348`（`filesystem`/`memory`/`cache`，`cache` 必填 namespace 且限 ASCII） |
> | `localfs` 插件重写 **819 行改动**（+381/−438；文件现 2010 行） | `crates/ragfs/src/plugins/localfs/mod.rs` |
> | 锁管理器运营改动 **397 行**（+254/−143）、wrapper **+174/−31**；**`lock/metrics.rs` 只改 8 行**（42 行的文件，仅把 `*_duration_ms` 换成 `*_duration_ns`） | `lock/manager.rs`、`lock/metrics.rs`、`lock/wrapper.rs` |
>
> **对本文的影响**：下面凡涉及"锁"的论断，都是**按 `filesystem` 单后端写的**。真正跨进程/跨机器时，现在可以选 Redis——那时的原子性和活性保证由 `cache_provder.rs` 提供而非本地文件系统。`viking://agent` 命名空间的变化见 [`core/01`](../core/01-viking-uri-and-vfs.md)。

## 这个维度回答的问题

1. `viking://` 的"虚拟"虚拟在哪一层？OS 能看到它吗？（→ 不能，协议级虚拟）
2. 同一份 URI 在 Linux / macOS / Windows 上分别发生什么？Windows 是怎么被支持的？
3. "VFS 所以支持一切文件操作、shell 命令也能跑"对不对？（→ 对一半，见 03）

## 篇目

| 篇 | 聚焦 | 一句话 |
|---|---|---|
| [`01-bridge-to-disk`](01-bridge-to-disk.md) | 五层栈 | URI→`/local/{account}/`→RAGFS 挂载→插件→OS，跨平台难度被压缩到 localfs 唯一翻译边界 |
| [`02-platform-behavior`](02-platform-behavior.md) | 三平台行为 | Windows 是发布目标（原生 wheel + 4 处专属代码路径 + MinGW），但验证深度分四档；9 条风险清单 |
| [`03-operation-semantics`](03-operation-semantics.md) | 操作面语义 | 动词表接近完整；`find`/`append`/`chmod` 三处 coreutils 直觉会翻车 |
| [`04-why-agent-sees-fs`](04-why-agent-sees-fs.md) | Agent 视角 | 四个示能同构（地址/导航/渐进披露/检索）——agent 不是被"模拟"，是直觉直接可用 |
| [`05-uri-across-os`](05-uri-across-os.md) | URI 与 OS | `viking://` 是应用层 scheme，三平台字节级相同地 work；OS scheme 注册机制与 Windows 长路径时间线的澄清 |
| [`agent-view.svg`](agent-view.svg) | 图示 | Agent 眼中的 viking://（工具动词 + 一次真实导航 + 四示能对照） |
| [`stack.svg`](stack.svg) | 图示 | 五层技术路线三平台横切面（含并行向量通道与 Windows 4 处专属路径） |

## 一屏结论

- **协议级虚拟，非 OS 挂载**：全仓无 FUSE/WinFSP/Dokan；访问面只有 MCP/HTTP/CLI/SDK。
- **Python 层零 OS 路径**：`_uri_to_path` 产出的 `/local/{account_id}/...` 是 AGFS 逻辑路径；接触磁盘的只有 Rust localfs 的 `resolve_path`/`replace` 两个翻译点。
- **Windows 是一等发布目标、二等验证深度**：官方 Windows x64 wheel（pip 即用，全库零 WSL 字样）；Rust 有 `MoveFileExW`/Win32 文件身份/`LockFileEx`/`.pyd` 四处专属路径；但 Rust 单测不进 CI、PR 门禁只有 Linux x86_64。
- **C++ 向量引擎在 Windows 上是 MinGW 构建**（`setup.py:457` 强制），无 MSVC 分支。
- **macOS 与 Windows 共有**大小写不敏感宿主卷这个零防护坑；Linux x86_64 是唯一"一等"平台。

## 与其他维度的关系

- 上游：[`core/01`](../core/01-viking-uri-and-vfs.md) 讲"是什么、怎么寻址"；本维度讲"落到哪里、平台上怎么不一样"。
- 平行：[`architecture/01`](../architecture/01-three-languages.md) 讲三语言调用图；本维度把其中的 "RAGFS 内容存储" 一格展开到 OS 边界。
- 下游待建：s3fs/memfs 后端下的锁与加密行为；SMB/网络盘场景（evidence 待深挖清单）。
