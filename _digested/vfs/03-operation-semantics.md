# 03 操作面语义：文件系统的动词表，哪些能迁移、哪些会翻车

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。取证原料 [vfs-platforms-evidence](../_notes/vfs-platforms-evidence.md) §1。动机：回答"它是 VFS，所以支持所有文件操作、shell 命令也能跑？"——答案是**对一半**。

>
> **v0.5.0 影响**：~~本维度讲的是 Rust ragfs 与 OS 的接缝，**v0.5.0 未改动这一层**~~
>
> ⚠️ **2026-10-19 更正：这句话是错的，已撤回。** 真正未变的是**洋葱顺序、7 插件、`chmod` no-op、Windows `MoveFileExW`** 这些"结构件"；但 `crates/ragfs/src` 实测 **34 文件 / +4481−1083**，是本轮改动第二重的层。按幅度：
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

动词表**接近**完整文件系统：Rust `FileSystem` trait 是完整 POSIX 动词集（含 offset 随机读、CAS、truncate），Python `VikingFS` 暴露 `read/write/mkdir/rm/cp/mv/ls/stat/glob/tree/grep/append_file` + 快照 + ACL。但有三条硬边界：① **shell/coreutils 够不着它**（无 OS 挂载，磁盘上是密文）；② **同名动词语义被数据库化**（`find` 是向量检索、`mv/rm` 同步向量索引、`append` 是锁下整写重写）；③ **POSIX 暗面不存在**（symlink/hardlink、权限位、byte-range 锁、mmap）。正确心智模型：**文件系统接口形状的数据库 API**。

## 能的部分：动词表盘点

### Rust trait（`crates/ragfs/src/core/filesystem.rs`：基础动词 `:203-417`，grep/glob/tree 扩展 `:442-699`）

```
create / mkdir(mode) / remove / remove_all
read(path, offset, size)          ← 字节级随机读
write(path, data, offset, flags)  ← trait 层支持 offset
compare_and_write / compare_and_remove   ← CAS 原语
read_dir / read_internal_dir / stat / exists
rename / replace（覆盖语义）/ chmod / truncate
grep / grep_file / glob_directory / tree_directory
```

### Python VikingFS（7 mixin，`storage/viking_fs/__init__.py:110-126`）

- 基础：`read`（`_ops.py:139`，offset/size 透传到 Rust）/ `write` / `mkdir(mode, exist_ok)` / `rm` / `remove_files` / `cp` / `mv` / `stat` / `exists` / `glob` / `tree` / `ls` / `read_batch` / `read_file` / `write_file` / `write_file_bytes` / `append_file` / `move_file` / `resolve_uri`
- 语义扩展：`grep`（正则内容搜索，`_grep.py:25`）、`abstract` / `overview` / `find` / `search` / `write_context`（`_semantic.py`）
- 快照（普通 FS 没有）：`commit` / `restore` / `show` / `show_blob_raw` / `diff` / `log` / `get_gitignore`（`_snapshot.py`——git 式版本控制内建）
- ACL：`grant_acl` / `revoke_acl` / `set_acl` / `get_acl` / `delete_acl`（`_access.py`）

## 会翻车的三个地方

### 1. shell 命令够不着（不是权限问题，是存在性问题）

- 无 FUSE/WinFSP/Dokan——`viking://` 不挂载进 OS。`ls/cat/find/rsync/du` 没有可操作的对象。
- 访问面只有四条：MCP 15 工具 / HTTP API / `ov` CLI / SDK（[`integration/01`](../integration/01-start-here.md)）。
- 即便绕过协议直读磁盘 `{workspace}/viking`：内容**按 account_id 加密**（HKDF 派生，`crypto/mod.rs:44-49`）+ 文档类原件默认不保留（媒体类默认保留原件，[00-the-root](../00-the-root.md) 坑 1），`cat` 出来是密文和 sidecar。

### 2. 同名不同义（coreutils 直觉迁移陷阱）

| 动词 | coreutils 直觉 | 实际语义 | 锚点 |
|---|---|---|---|
| `find` | 按名字/属性找文件 | **全局语义召回**，**固定不精排** | `openviking/storage/viking_fs/_semantic.py:302-313`（`find()` 调 `retriever.retrieve(..., mode=RetrieverMode.QUICK, ...)`）、`:196 def find`；对照 `hierarchical_retriever.py:124`（`use_rerank` 只在 `THINKING` 下为真）。⚠️ **本行原文引过 `_semantic.py:306` 的 "`search_type="find", use_rerank=False`"——那句话是编的**：`use_rerank` 在全仓只存在于 `hierarchical_retriever.py`（`:124`/`:183`/`:225`），`_semantic.py` 里根本没有这个符号。**结论对（find 永远不 rerank），但原证据不成立**，已换成真正能支撑结论的两个锚点。[《 core/03](../core/03-retrieval-global-recall.md) |
| `mv` / `rm` | 移动/删除字节 | **同步向量索引的 URI 元数据**（普通 FS 没有的副作用） | `mv`：`_ops.py:682` → `:807`/`:826` `_update_vector_store_uris` → `_vector.py:60` → `vikingdb_manager.py:532 update_uri_mapping` → `viking_vector_index_backend.py:2830`（`rewrite_vector_record(mode="move")` `:2861`）；`rm`：`_ops.py:215`（向量删除失败现在**会重抛**，`_vector.py:34-36`） |
| `append_file` | O_APPEND 原子追加 | pathlock 租约下**读旧+整文件重写**（注释原话 "avoid lost updates"） | `_ops.py:2116` |
| `mkdir` | 建空容器 | 目录是**数据记录**（L0/L1 文案 + 向量） | [`core/01`](../core/01-viking-uri-and-vfs.md) |
| `ls` | 全列 | ACL 过滤，无权限条目标 `access: "denied"` 保留可见 | `_access.py:600-605` |
| `grep` | 文本搜索 | 正则内容搜索 + ACL 过滤（**v0.5.0 起不再调外部 ripgrep**，见下） | `_grep.py:25`、`localfs/mod.rs:418 grep_via_libs`、`:550 grep_file_via_searcher` |

### 3. POSIX 暗面不存在

- **symlink/hardlink**：ragfs 全仓 0 处使用（不创建不依赖链接；Windows junction 也不特殊处理）。
- **chmod**：Rust trait 有、Python 未暴露、localfs 实现**是 no-op**（`mod.rs:1257-1268`）——权限模型事实上只有 URI 层 ACL（owner_user_id / actor_peer_id 校验，`namespace.py:323-345`），不是 mode bits。
- **byte-range 文件锁（fcntl/flock 语义）**：不存在；锁是应用层 PathLock——`filesystem`/`memory` 后端是 token 侧车文件 + TTL，`cache` 后端（v0.5.0 新增）是 Redis Lua 脚本 + `PEXPIRE`（[`01`](01-bridge-to-disk.md)）。三个后端都**不支持**对一个文件的区间加锁。
- **mmap / fifo / 设备文件 / mount**：概念不存在。

## 写作/使用纪律（从上述事实推出的操作建议）

1. 追加写热点路径别用 `append_file` 高频调用——每次是整文件重写 + 一把路径锁；用 `write_context` 或批量聚合。
2. 需要覆盖语义的移动走 `replace`/`mv`（Rust 层有覆盖实现），别依赖 `rename` 的 Unix 覆盖行为——Windows 会报错（[`02`](02-platform-behavior.md) 风险 1）。
3. 权限控制只设计 ACL，别设计权限位；Windows 上密钥文件保护需自行补（0600 仅 unix）。
4. 并发写同一文件必须走 PathLock 约定路径；绕锁的加密写是 last-writer-wins（[`02`](02-platform-behavior.md) 风险 6）。

## v0.5.0 复核：grep 的外部依赖被拆掉了（2026-10-19）

原文这一行写的是"正则内容搜索 + ACL 过滤 + **rg fallback**"，锚在 `localfs/mod.rs:66-72`——那一段是构造时探测 `rg` 是否在 PATH 里（`Command::new("rg").arg("--version")`，结果存进 `has_rg` 字段），有就走 `grep_via_rg`（`Command::new("rg").arg("--json")` 子进程），没有才退回进程内实现。

**v0.5.0 把整条外部路径删了**：

| | v0.4.19（基线） | v0.5.0 |
|---|---|---|
| `has_rg` 字段与探测 | 有（`mod.rs:66-72`） | **无** |
| `grep_via_rg`（spawn 子进程） | 有（`mod.rs:364`） | **无**，全文件已无 `Command::new` |
| 进程内实现 | `grep_via_libs`（`mod.rs:561`）作为回退 | 唯一路径（`:418`），上下文收集抽到新模块 `core/grep.rs` |
| 上下文行（before/after context） | — | 新增 `GrepLineCollector`（`core/grep.rs:8`），含相邻命中与文件边界的处理 |

**判断**：这是一次**去外部依赖**的收敛——行为等价面更大（不再受"宿主机有没有装 rg"影响，三平台表现更一致），代价是丢掉 rg 的 SIMD 优化，大仓库 grep 可能变慢。文档原来那句"生产代码跨平台"的方向反而更成立了，但依据换了。

## 状态标注

- 硬事实：动词表锚点、no-op chmod、append 重写、find 固定 QUICK
- 解释："文件系统接口形状的数据库 API"定性；操作建议（写作纪律）
