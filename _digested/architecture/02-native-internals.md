# 02 原生层内部：RAGFS 的路由器/插件/git 层，与 C++ 引擎的四个 capsule

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。取证：船长自查（锚点可复核）+ 并行取证 agent A 报告（锁/加密细节见 [`../vfs/01`](../vfs/01-bridge-to-disk.md) 与 [`../_notes/vfs-platforms-evidence.md`](../_notes/vfs-platforms-evidence.md)）。姊妹篇：[`01-three-languages`](01-three-languages.md)（调用边界——本文往下挖一层）。

## 先给结论

RAGFS 的内部结构比"一个文件系统库"复杂得多：**MountableFS 路由器**（按路径前缀把操作分发给挂载的插件）+ **7 个插件**（**4 个内容存储**：`kvfs`/`localfs`/`memfs`/`s3fs` + **3 个服务面**：`queuefs`/`serverinfofs`/`sqlfs`；`crates/ragfs/src/plugins/mod.rs:14-21` 逐个 re-export）+ **一套纯 Rust 的 git 语义对象存储**（快照/commit/restore 的真正实现地）+ 加密/多写/统计三个包装器洋葱。C++ 侧则是**四个 PyCapsule 暴露的内存向量引擎**：`VolatileIndex` 全内存扫描 + x86 SIMD 变体加速距离计算，持久化靠 leveldb 的 KVStore capsule，GPU ANN 交给 cuVS 适配器——**没有 HNSW/IVF 类图索引**。调用图见 [`callgraph.svg`](callgraph.svg)。

## A. RAGFS 内部（crates/ragfs/src/）

### A1. 路由器与洋葱包装

- **MountableFS**：核心路由器，"directing filesystem operations to the appropriate mounted plugin based on the path prefix"（`core/mountable.rs:1-6` docstring 原话）——`/local` → localfs、`/queue/...` → queuefs 都由它分发。
- **包装器洋葱**（请求穿过顺序，`core/builder.rs:125-126, 273-278` 已逐行核验）：`StatsWrappedFS`（最外层统计，`builder.rs:278`）→ `PathLockWrappedFS`（路径锁，`builder.rs:273`）→ `MountableFS`（`builder.rs:196`/`:205`） → **每个挂载后端内部**再包 `MultiWriteWrappedFS`（primary+backups 多写，内含 `EncryptionWrappedFS`：HKDF(account_id) 加密 + `.encrypt` 临时文件 + replace 原子发布，`core/encryption_wrapper.rs`；多写装配在 `multibackend/factory.rs:55-93`，单后端路径 `mountable.rs:389`）→ 插件。（2026-09-13 修正：此前版本把顺序写成"MultiWrite → Encryption → Stats → MountableFS"且漏了 PathLock 层——那是未核验时的错误推断。）
- core/ 全模块：builder / context / encryption_wrapper / errors / filesystem（trait + validate_virtual_path）/ glob / internal_names（`.path.ovlock` 等常量）/ mountable / multibackend_wrapper / plugin / stats(_wrapper) / types。

### A2. 七个插件：3 内容 + 4 服务

| 插件 | 角色 | 备注 |
|---|---|---|
| localfs | 内容落盘（唯一触 OS） | Windows 专属路径 4 处，见 [`../vfs/02`](../vfs/02-platform-behavior.md) |
| s3fs | 对象存储内容 | "路径"=对象键 |
| memfs | 内存内容 | 测试/临时 |
| kvfs / queuefs / sqlfs / serverinfofs | **服务插件**：QueueFS 队列（默认 sqlite）、KV、serverinfo | 不在 `/local` 内容路径上；`supports_encrypted_publish` 只认三个内容插件（`multibackend/factory.rs:30-33`） |

### A3. git 层：不是 git，是"git 语义的纯 Rust 对象存储"

- 依赖：`gix-hash` / `gix-object` / `gix-features(zlib)`（`Cargo.toml:54-56`）+ `gix-actor`（:57）/ `gix-date`（:58）/ `flate2`（:62）——借 git 的对象哈希与 zlib 打包格式，**不是** checkout 一个真 git 仓库。
- 模块布局（`crates/ragfs/src/git/`）：`object_store.rs`（内容寻址对象；写入用"唯一 tmp 名 + rename + 竞态容忍"，`backends/local.rs:73-93`）、`ref_store.rs`（41 行纯 RefStore **trait**，无写入实现；ref 的非唯一 `.tmp` 写入实现在 `backends/local.rs:235,:364`（LocalRefStore cas_update 等），Windows 并发下与对象写入的"唯一 tmp 名"形成语义差异对照，见 [`../vfs/02`](../vfs/02-platform-behavior.md) 风险表——2026-09-13 修正：此前版本把这两处锚到 `ref_store.rs`，文件错了）、`commit.rs` / `tree_builder.rs` / `enumerate.rs` / `ignore.rs` / `index_store.rs`（**INDEX_FORMAT_VERSION=1**，`:138` 定义；`:185` mismatch 时静默 `Ok(None)` 而非硬报错——与 ovpack v3 的 manifest 精确相等拒绝（那处是硬错）不同档，见 [`../harness/02-Boundaries/2.2`](../harness/02-Boundaries/2.2_version_contracts.md)）、`service.rs`。
- 【解释】Python `VikingFS` 的 snapshot 方法（commit/restore/diff/log，`_snapshot.py`）只是这层的 HTTP/绑定皮——**快照的真实实现完全在 Rust 层**，且与内容存储同后端（localfs→本地、s3fs→远端）。

### A4. PyO3 方法面（`crates/ragfs-python/src/lib.rs`）

`RAGFSBindingClient` 的 `#[pymethods]` 块（`lib.rs:1502` 起）暴露 **52 个方法**，其中 **15 个是 `pathlock_*`**：`acquire_exact`/`acquire_exact_batch`/`acquire_exact_tree_batch`/`acquire_tree`/`acquire_tree_batch`/`acquire_batch`/`release`/`release_selected`/`handoff`/`to_handoff`/`adopt`/`observe`/`refresh`/`is_locked`/`as_borrowed`。**原文写"约 49 个方法、含 8 个 `pathlock_*`"——方法数基本对（52），`pathlock_*` 数少了一半（8→15）**，与 `vfs/01` 记录的"PathLock 从 2 后端扩到 3 后端、新增整套批量/CAS/adopt/handoff 动作"对不上。此外还有 5 个 `git_*`、`system_sync_*` 等。

> **锚点漂移说明**：旧版这一段的 `:1681 :1733 :1773 :1825 …` 全部是 `0f77ab56` 的行号，**在 v0.5.0 上整体下移约 180 行**（`read` 1681→1862）。旧版另外还锚了 `mkdir :1773`、`copy_within_mount :1891`、`mount :1993`、`grep :2088` 与当时记的 8 个 `pathlock_*` 具体行号（实际有 15 个，见上）——这些在 v0.5.0 未逐个复核，**按未定处理，引用前请自行 grep**。

【解释】值得注意：**绑定层比 VikingFS 暴露面更宽**（如 `chmod`、`digest`、`stream` 读）——Python 操作面的裁剪（无 chmod、find=语义）是产品决策不是能力边界（呼应 [`../vfs/03`](../vfs/03-operation-semantics.md)）。

## B. C++ 引擎内部（src/）

### B1. 四个 capsule（`src/abi3_engine_backend.cpp:24-27`）

| capsule | 能力 | Python 使用者 |
|---|---|---|
| `openviking.vectordb.IndexEngine` | 向量索引核心 | `index/local_index.py` 的 IndexEngineProxy（RWLock 包裹，`:62,107`） |
| `openviking.vectordb.KVStore` | leveldb 持久化 KV | `store/local_store.py` |
| `openviking.vectordb.Schema` | collection schema 定义 | `store/serializable.py:10`（经 `bytes_row.py:310` `Schema = engine.Schema`；`collection_schemas.py` 只定义字段 dict，不 import engine） |
| `openviking.vectordb.BytesRow` | 行编码 | `store/bytes_row.py` |

### B2. 索引结构：内存扫描 + SIMD，无图索引

- Python 侧索引类层级：`LocalIndex`（基类，`local_index.py:347`）→ `VolatileIndex`（内存态，`:1257`）；`IndexEngineProxy` 用读写锁包 C++ 核心，并预留 `CuVSBackgroundRebuildPending`（`:103`，GPU 重建异步化）。
- **全仓 `src/` grep 无 HNSW/IVF**——距离计算是**内存全量扫描 + x86 SIMD**（CMake 的 sse3/avx2/avx512 三变体正是为此，`src/CMakeLists.txt:270-296`）；GPU 场景走 cuVS 适配器（factory.py 白名单之一）。
- 【解释】这解释了两个现象：① 为什么 `ov status` 之外还有 `system consistency` 命令（索引与内容是两套持久化，需要对账）；② 为什么大规模数据的"local"后端定位是单机中小规模——扫描型索引的查询延迟随向量数线性，云上规模要靠 vikingdb/cuvs。
- collection schema 关键字段：`uri(path)` / `level(int64)`（L0=.abstract.md、L1=.overview.md、L2=原文，`collection_schemas.py:103-114` 注释原话）/ `content(text)` / 向量字段。

### B3. 持久化

leveldb 为仓内 vendored 静态库（`CMakeLists.txt:75`），经 KVStore capsule 提供 KV 持久化；向量数据在内存中服务查询、落盘交给 KVStore——崩掉后由 Python 侧重建/加载（与内容层 AGFS **可分别配置**）。

> ⚠️ **2026-10-19 更正：原文在这里引了一句官方原文，那句话并不存在**。原文写："与内容层 AGFS 完全独立，"Single data source: All content read from AGFS" 的官方设计口径，`docs/en/concepts/05-storage.md:32`"。实测：
> - `docs/` 全树搜 `single data source` / `all content read from AGFS` **零命中**；`05-storage.md:32` 是 URI 映射代码块（`viking://resources/docs/auth → /local/{account_id}/...`），不是这句话。
> - 官方真正的同义表述在 `docs/en/concepts/01-architecture.md:142`：*"**Single Data Source** | RAGFS holds source files; vector records retain the text and metadata needed for retrieval"*——意思是"源文件只有一份在 RAGFS"，**不是**"两套存储完全独立"。
> - 而且紧接着的 `docs/en/concepts/05-storage.md:18` 明说：*"Memory records store their body text in the abstract field, capped at 50,000 bytes, so the vector index can contain readable text."* ——**向量库里确实有可读正文**。所以"完全独立"这个结论本身也是错的，官方口径恰恰是"两套存储都要备份、都要管访问控制"（`:20`）。
>
> **正确的表述**：AGFS 与向量库是**两个可独立配置的后端**，源文件在 AGFS、检索所需的文本与元数据（含 ≤50 KB 的记忆正文）在向量库——**存在有意的数据冗余，不是完全独立**。

## C. 修正与加深 architecture/01 的两点

1. 01 说"互不调用、在 Python 服务层汇合"——仍然正确，但应补一句：**汇合点不止是 import，还有事务语义**（PathLock 在 Rust 层、向量同步在 Python 层，`mv/rm` 的"内容+索引"原子性靠 VikingFS 编排，见 [`../vfs/03`](../vfs/03-operation-semantics.md)）。
2. 01 的"双层存储"表格应加第三行：**队列层（QueueFS/sqlite）**——它是写路径异步化的骨架（[`integration/03`](../integration/03-server-topology.md)），与内容/索引平级但独立持久化。

## 状态标注

- 硬事实：A1（洋葱顺序已于 2026-09-13 在 builder.rs 逐行核验并改写；2026-10-19 复核 v0.5.0 行号 `builder.rs:125-126,273-278`，**顺序未变**）、A2、B1-B3 锚点
- 解释："内存扫描+SIMD"的定性（无 HNSW 为 grep 级硬事实，性能含义为解释）；git 层与内容层同后端的判断
- 未定：IndexEngine 内部是否有多线程分片扫描；s3fs 下 git 对象存储的布局
- 反转记录（2026-10-19，v0.5.0）：**此前写的"原生层无行为变化"是错的，已作废**。实测 `crates/ragfs/src` **34 个文件变更、+4481/−1083**，`crates/ragfs-python/src/lib.rs` +431/−71。
  - **仍然成立**：A1 洋葱顺序（`builder.rs:125-126,273-278`，逐行比对基线完全一致）、`chmod` no-op（`localfs/mod.rs:1117`）、7 个插件结构、四 capsule 面、`INDEX_FORMAT_VERSION=1`。
  - **变化最大的三块**：① 新增 `lock/cache_provder.rs`（**1869 行**，全仓最大新增文件）；② `localfs/mod.rs` 819 行重写；③ `lock/manager.rs` 397 行改动。另有新模块 `core/grep.rs`、`metrics/mod.rs`（193 行）。
  - **结论**：v0.5.0 的原生层变化集中在**锁与本地文件系统**，不在 C++ 引擎——"变化集中在 Python 服务层"这个概括需要改成"Python 服务层 + Rust 锁/本地存储层"。
