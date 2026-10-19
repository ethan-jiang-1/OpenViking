# 02 三平台行为：Linux / macOS / Windows，以及 Windows 到底是怎么做的

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。取证原料 [vfs-platforms-evidence](../_notes/vfs-platforms-evidence.md) §2-§4。

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

## 先给结论

**Windows 不是"能编译"，是发布目标**：官方出 Windows x86_64 wheel（`pip install` 即用，文档明文 "OS: Linux, macOS, Windows"），Rust 层有 4 处专门 Windows 代码路径，Python 层连 Windows 原生 API 的 PID 探测都有。但**验证深度按平台分层**：Linux x86_64 是唯一进 PR 门禁的一等平台；Windows/macOS 是"发版产物 + main 分支集成测试"的二等平台；Rust 原生单测在任何平台都不进 CI。另一个诚实结论：**macOS 和 Windows 共享"大小写不敏感宿主卷"这一没有防护的坑**，不只是 Windows 特有。

## 三平台行为矩阵

| 维度 | Linux (x86_64 一等 / aarch64 CI) | macOS (arm64 + x86_64 CI) | Windows (x86_64 CI) |
|---|---|---|---|
| URI→AGFS 映射（L1-L3） | 三平台字节级相同：白名单、`_safe_uri_parts` 净化、`/local/{account}/` 前缀替换 | 同 | 同 |
| 内容落盘（L4-L5） | `{workspace}/viking` 直写 | 同 | `\\?\C:\Users\...` verbatim 路径（canonicalize 副作用，隐式长路径） |
| 覆盖移动 | `fs::rename` 静默覆盖 | 同 | `MoveFileExW(REPLACE_EXISTING\|WRITE_THROUGH)` 宽字符 |
| CAS 文件身份 | dev + ino | dev + ino | 卷序列号 + 64 位 FileIndex（Win32 句柄） |
| 文件锁 | filelocks Fcntl（OFD） | 同 | 同 crate 映射 `LockFileEx` |
| PathLock 语义 | token 侧车文件 + TTL（与平台无关） | 同 | 同 |
| PathLock 后端 | `filesystem`（默认）/ `memory` / `cache`（**Redis，v0.5.0 新增**，三平台同） | 同 | 同 |
| `rename()` 目标已存在 | **静默覆盖** | 静默覆盖 | **报错**（平台语义分裂点） |
| 大小写敏感 | 敏感（ext4 默认） | **不敏感**（APFS 默认） | **不敏感**（NTFS 默认） |
| chmod | 真实生效 | 生效 | **no-op**（`mod.rs:1257-1268`） |
| 向量引擎 | x86 三变体（sse3/avx2/avx512）或 ARM krl | Apple Silicon 走 `native` 变体 | MinGW 编译 `.pyd`（无 MSVC 分支） |
| 发布产物 | wheel + musl CLI + docker | wheel ×2 + CLI ×2 | wheel + `ov-windows-x86_64.exe` + npm win32-x64 |

## Windows 专项深挖：它到底怎么做到的

### 1. 四处专门代码路径（"买来的"可移植性）

| # | 解决什么问题 | 锚点 |
|---|---|---|
| 1 | CAS 需要确认"打开的句柄仍指向该文件"（inode 等价物）：`GetFileInformationByHandle` → 卷序列号 + nFileIndex，而非路径重比 | `crates/ragfs/src/plugins/localfs/mod.rs:98-119`（unix 分支 :123-142；其他平台直接报错 :158-164——明示只支持 unix/windows 两类目标） |
| 2 | 加密发布的覆盖式移动：手工 `unsafe extern "system"` 声明 `MoveFileExW`，flags `REPLACE_EXISTING\|WRITE_THROUGH`，路径 `encode_wide()` 转 NUL 结尾 UTF-16 | `mod.rs:1203-1246`；注释原话 "encrypted publish needs an overwrite-on-destination move"（:1201-1202） |
| 3 | CAS 底层锁：`filelocks` crate 的 `LockBackend::Fcntl` 在 Windows 上映射 `LockFileEx` | `mod.rs:191-198` + [docs.rs/filelocks](https://docs.rs/filelocks/0.1.0/filelocks/) |
| 4 | 原生库形态：vendored `.abi3.pyd` 显式分支 + 引擎 `.pyd` 探测 + `os.add_dll_directory` 兜底 | `pyagfs/__init__.py:85`、`engine/__init__.py`、`setup.py:577-584` |

Python 侧还有一处容易被忽略的 Windows 专属代码：`process_lock.py:51-70` 用 `_winapi.OpenProcess(SYNCHRONIZE)` + `WaitForSingleObject` 做 PID 存活检测——注释明言 POSIX 的 `os.kill(pid,0)` 在 Windows 是发 CTRL_C_EVENT；**且有只在 Windows 上跑的单测**（`tests/unit/test_process_lock.py:140`）。

### 2. 构建链：Windows 上是 MinGW，不是 MSVC

`setup.py:454-457` 强制 `-G "MinGW Makefiles"`；`src/CMakeLists.txt` 无任何 MSVC 分支，GNU 风格 flags（`-Wno-...`、`-lpthread`）无条件注入（:42-43）。CI 的 Windows runner 也 `choco install mingw`（`_build.yml:448-452`）。【解释】这是刻意绕开 MSVC ABI/flags 泥潭的选择，代价是与主流 Windows 工具链不一致、源码编译路径只面向 MinGW。C++ 引擎依赖的 leveldb/spdlog 是仓内 vendored（无 `.gitmodules`），不引入额外平台变量。

### 3. 数据落点与长路径

- 默认数据目录 `Path.home() / ".openviking"`（`consts.py:7`）→ Windows 上即 `C:\Users\<user>\.openviking\<workspace>\viking\...`。
- 长路径能力来自 `fs::canonicalize` 的 `\\?\` verbatim 副作用（`mod.rs:124`），非显式设计。【解释】"能用但隐式"：行为依赖 std 实现细节，且日志/报错里的 `\\?\` 前缀可能困扰用户和外部工具。

### 4. 文档口径与全库零 WSL

Quickstart 明文三 OS（`docs/en/getting-started/02-quickstart.md:10`，中文同位）；agent 安装文档给 Windows 五步走、wheel 优先、失败才 MinGW 源码编译（`04-setup-for-agent.md:59-69,388-401`）；对 docs/README/RELEASE 全文 grep `wsl` **零命中**——官方 Windows 路径是原生的，不是 WSL2。changelog 里有持续多条 Windows 修复记录（`docs/en/about/02-changelog.md:36,376,477,...`），说明是长期维护目标而非一次性移植。

## 行为分裂点与风险清单（使用前必读）

| # | 风险 | 锚点 | 影响 |
|---|---|---|---|
| 1 | `rename()` 目标存在：Windows 报错 / Unix 覆盖——同一 VFS 操作两平台结果不同 | `mod.rs:1014 async fn rename`；Windows 分支 `:1073-1097` 用 `MoveFileExW(MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)`（旧基线锚 `:1171` vs `:1248-1252` 已因重写失效） | 依赖覆盖语义的上层在 Windows 会见错；应走 `replace()` |
| 2 | 大小写冲突零防护：`A.txt` vs `a.txt` 在 NTFS/APFS 上截断覆盖同一文件、ext4 上共存 | 全仓无 casefold 处理（evidence §2.4） | **macOS 与 Windows 共有**；VFS 层不救 |
| 3 | Windows 保留名/非法字符零防护：URI 组件 `CON`/`NUL` 落 NTFS 有设备语义 | 无处理代码 | 路径注入残余面（`_safe_uri_parts` 只挡 `\` 和 `X:`） |
| 4 | `chmod` 是 no-op（"For now, just return success"） | `mod.rs:1117 async fn chmod`（旧基线 `:1257-1268` 已因重写失效） | 权限模型事实上只有 URI 层 ACL；别指望 POSIX 权限位 |
| 5 | 密钥/配置文件 0600 仅 unix；Windows 无 ACL 收紧且仍打印误导性 "Key permissions set to 0600" | `ov_cli/commands/crypto.rs:92-96,99`、`crypto/config.py:73` | Windows 上同用户进程皆可读 master key |
| 6 | 加密写 `.encrypt` 临时名确定性（sha256(final_path)）；PathLock 禁用时 `remove+retry` 互删 envelope → last-writer-wins | `encryption_wrapper.rs:197-206,261-269` | 启用锁则安全；绕锁写是竞态 |
| 7 | 虚拟路径校验平台不对称：`\` 在 Windows 是分隔符、Unix 是合法文件名；`Component::Prefix` 检查仅 Windows 编译目标命中 | `core/filesystem.rs:20-28` | 跨平台数据迁移时同名路径可能落到不同文件 |
| 8 | Rust 原生单测不进 CI（全 workflows 无 `cargo test`）；`_test_full.yml` 是空壳（无 pytest 步骤、无调用方） | workflows grep；`_test_full.yml:34,79-82` | Windows 专属 Rust 代码靠 Python 集成测试间接覆盖 |
| 9 | 普通写入就地写无 temp+rename，崩溃可留半截文件 | `mod.rs:855 async fn write`（旧基线 `:1010-1043` 已因重写失效） | 三平台一致，加密路径除外（有 replace） |

## 验证深度四档（官方"支持"的真实含义）

| 档位 | 平台 | 依据 |
|---|---|---|
| **一等**（PR 门禁 + 每发版必出） | Linux x86_64 | `pr.yml`、`api_test.yml:43` PR 档、docker amd64 |
| **CI 覆盖**（发版产物 + main/schedule 3-OS api_test，不进 PR 门禁） | Linux aarch64、macOS arm64/x86_64、**Windows x86_64** | `_build.yml:10`、`api_test.yml:43`、`rust-cli.yml:31-60` |
| **仅文档** | Windows 桌面助手 beta（x64）、Docker Desktop 注意事项 | `README.md:223-229`、`13-multi-write-storage.md:133` |
| **未覆盖** | Windows ARM64、musl Python wheel、Windows 容器、BSD | 各矩阵无此项 |

【解释】给 Windows 用户的实用排序：**pip wheel（x64）> 官方 Linux 容器（Docker Desktop）> MinGW 源码编译**；ARM Windows 设备目前只能走容器路径。

## v0.5.0 复核：localfs 重写后风险表仍成立，锚点全部换代（2026-10-19）

`crates/ragfs/src/plugins/localfs/mod.rs` 在 v0.5.0 有 **819 行改动**（+381/−438，文件现 2010 行——不是被重写成 819 行；主要是 grep 去外部依赖，见 [`03`](03-operation-semantics.md) 末节）。结果：

- **9 条风险的结论全部仍然成立**——`rename` 的两平台分裂、`chmod` no-op、就地写无 temp+rename、大小写零防护等，逐条对着新代码复核过。
- **但 4 条锚点全部失效**（文件头部的 ripgrep 探测代码删除，整体行号上移）：`rename` 1171→**1014**、`chmod` 1257→**1117**、`write` 1010→**855**、`canonicalize` 63→**124**。已就地改正，旧行号保留在括号里以便对照。
- 顺带确认一条**仍然成立的关键设计**：Windows 的 `rename` 覆盖走 `MoveFileExW(MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)`（`:1094-1097`）——这与风险 1 描述的行为一致，说明"Windows 分支特殊处理过这里"是**旧版就有的实现**，不是本轮新增。

## 状态标注

- 硬事实：矩阵中全部锚点；四档划分依据
- 解释：MinGW 选择的动机归因；`\\?\` "隐式能力"定性；Windows 用户路径排序
- 未定：SMB 网络盘上 PathLock/filelocks 行为；`_test_full.yml` 空壳是有意降级还是未完成
