# 02 原生层内部：RAGFS 的路由器/插件/git 层，与 C++ 引擎的四个 capsule

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。取证：船长自查（锚点可复核）+ 并行取证 agent A 报告（锁/加密细节见 [`../vfs/01`](../vfs/01-bridge-to-disk.md) 与 [`../_notes/vfs-platforms-evidence.md`](../_notes/vfs-platforms-evidence.md)）。姊妹篇：[`01-three-languages`](01-three-languages.md)（调用边界——本文往下挖一层）。

## 先给结论

RAGFS 的内部结构比"一个文件系统库"复杂得多：**MountableFS 路由器**（按路径前缀把操作分发给挂载的插件）+ **7 个插件**（`crates/ragfs/src/plugins/mod.rs:14-21` 逐个 re-export；**别用"4 内容 + 3 服务面"这种分法**——那是本文旧版的发明，代码自己的 control-plugin 集合只有 2 个：`crates/ragfs/src/core/mountable.rs:356` 的 `matches!(name, "queuefs" | "serverinfofs")`，而 `kvfs` 自述就是通用 KV 内容存储、`sqlfs` 自述是 SQL 后端的**文件系统**，两者都不是"服务面"。按代码口径只能说：**`localfs`/`s3fs`/`memfs`/`kvfs`/`sqlfs` 是内容或持久化后端，`queuefs`/`serverinfofs` 是控制面**）+ **一套纯 Rust 的 git 语义对象存储**（快照/commit/restore 的真正实现地）+ 加密/多写/统计三个包装器洋葱。C++ 侧则是**四个 PyCapsule**（`IndexEngine`/`KVStore`/`Schema`/`BytesRow`，`src/abi3_engine_backend.cpp:25-28`）暴露的引擎：索引引擎 `IndexEngine` + 内存 KV 后端 `VolatileStore`（`src/store/volatile_store.h:13`，内部是 `std::map<std::string,std::string> data_`，`:39`）+ 持久化靠 leveldb 的 `KVStore` capsule，距离计算有 x86 SIMD 变体，GPU 场景走 cuVS 适配器。

## A. RAGFS 内部（crates/ragfs/src/）

### A1. 路由器与洋葱包装

- **MountableFS**：核心路由器，"directing filesystem operations to the appropriate mounted plugin based on the path prefix"（`core/mountable.rs:1-6` docstring 原话）——`/local` → localfs、`/queue/...` → queuefs 都由它分发。
- **包装器洋葱**（请求穿过顺序，`core/builder.rs:125-126, 273-278` 已逐行核验）：`StatsWrappedFS`（最外层统计，`builder.rs:278`）→ `PathLockWrappedFS`（路径锁，`builder.rs:273`）→ `MountableFS`（`builder.rs:196`/`:205`） → **每个挂载后端内部**再包 `MultiWriteWrappedFS`（primary+backups 多写，内含 `EncryptionWrappedFS`：HKDF(account_id) 加密 + `.encrypt` 临时文件 + replace 原子发布，`core/encryption_wrapper.rs`；多写装配在 `multibackend/factory.rs:55-93`，单后端路径 `mountable.rs:389`）→ 插件。（2026-09-13 修正：此前版本把顺序写成"MultiWrite → Encryption → Stats → MountableFS"且漏了 PathLock 层——那是未核验时的错误推断。）
- core/ 全模块：builder / context / encryption_wrapper / errors / filesystem（trait + validate_virtual_path）/ glob / internal_names（`.path.ovlock` 等常量）/ mountable / multibackend_wrapper / plugin / stats(_wrapper) / types。

### A2. 七个插件：5 内容/持久化后端 + 2 控制面
> ⚠️ **2026-10-19 第五轮修正**：本节标题原写“3 内容 + 4 服务”，与本文 `:7` 明令禁止的“4 内容 + 3 服务面”是同一个发明的两次换皮——**数字对调、错误照旧**。代码里 `is_control_plugin` 只认 2 个（`queuefs`/`serverinfofs`），`kvfs`/`sqlfs` 是内容/持久化后端。本文 `:7` 早就写对了，这一节没跟上。


| 插件 | 角色 | 备注 |
|---|---|---|
| localfs | 内容落盘（唯一触 OS） | Windows 专属路径 4 处，见 [`../vfs/02`](../vfs/02-platform-behavior.md) |
| s3fs | 对象存储内容 | "路径"=对象键 |
| memfs | 内存内容 | 测试/临时 |
| queuefs / serverinfofs | **控制面插件**（代码里唯一被判定为 control 的两个） | `crates/ragfs/src/core/mountable.rs:356` `matches!(name, "queuefs" | "serverinfofs")`；
| kvfs / sqlfs | **持久化后端**（不是控制面） | 旧版把这两个也算成“服务面”，与代码的 control 判定不符；`supports_encrypted_publish` 只认三个内容插件（`multibackend/factory.rs:30-33`） |

### A3. git 层：不是 git，是"git 语义的纯 Rust 对象存储"

- 依赖：`gix-hash` / `gix-object` / `gix-features(zlib)`（`Cargo.toml:54-56`）+ `gix-actor`（:57）/ `gix-date`（:58）/ `flate2`（:62）——借 git 的对象哈希与 zlib 打包格式，**不是** checkout 一个真 git 仓库。
- 模块布局（`crates/ragfs/src/git/`）：`object_store.rs`（内容寻址对象；写入用"唯一 tmp 名 + rename + 竞态容忍"，`backends/local.rs:73-93`）、`ref_store.rs`（41 行纯 RefStore **trait**，无写入实现；ref 的非唯一 `.tmp` 写入实现在 `backends/local.rs:235,:364`（LocalRefStore cas_update 等），Windows 并发下与对象写入的"唯一 tmp 名"形成语义差异对照，见 [`../vfs/02`](../vfs/02-platform-behavior.md) 风险表——2026-09-13 修正：此前版本把这两处锚到 `ref_store.rs`，文件错了）、`commit.rs` / `tree_builder.rs` / `enumerate.rs` / `ignore.rs` / `index_store.rs`（**INDEX_FORMAT_VERSION=1**，`:138` 定义；`:185` mismatch 时静默 `Ok(None)` 而非硬报错——与 ovpack v3 的 manifest 精确相等拒绝（那处是硬错）不同档，见 [`../harness/02-Boundaries/2.2`](../harness/02-Boundaries/2.2_version_contracts.md)）、`service.rs`。
- 【解释】Python `VikingFS` 的 snapshot 方法（commit/restore/diff/log，`_snapshot.py`）只是这层的 HTTP/绑定皮——**快照的真实实现完全在 Rust 层**，且与内容存储同后端（localfs→本地、s3fs→远端）。

### A4. PyO3 方法面（`crates/ragfs-python/src/lib.rs`）

`RAGFSBindingClient` 的 `#[pymethods]` 块（`lib.rs:1502` 起）暴露 **52 个方法**，其中 **15 个是 `pathlock_*`**：`acquire_exact`/`acquire_exact_batch`/`acquire_exact_tree_batch`/`acquire_tree`/`acquire_tree_batch`/`acquire_batch`/`release`/`release_selected`/`handoff`/`to_handoff`/`adopt`/`observe`/`refresh`/`is_locked`/`as_borrowed`。**原文写"约 49 个方法、含 8 个 `pathlock_*`"——方法数基本对（52），`pathlock_*` 数少了一半（8→15）**，与 `vfs/01` 记录的"PathLock 从 2 后端扩到 3 后端、新增整套批量/CAS/adopt/handoff 动作"对不上。此外还有 5 个 `git_*`、`system_sync_*` 等。

> **锚点漂移说明（2026-10-19 已逐个复核，不再是"未定"）**：旧版这一段锚的全是 `0f77ab56` 行号，在 v0.5.0 上**整体下移**，但**偏移量不均匀**（不是固定 189 行——此前版本曾写作"-189 偏移"，方向与量都不对）。实测四个方法（v0.5.0 行号）：`mkdir` **1954**（旧 1773，+181）、`copy_within_mount` **2071**（旧 1891，+180）、`mount` **2174**（旧 1993，+181）、`grep` **2272**（旧 2088，+184）；`read` **1862**（旧 1673，+189）。`pathlock_*` 类方法实际 **15 个**（旧版记 8 个，见上），`#[pymethods]` 块自 `lib.rs:1502` 起、共 52 个方法。**教训**：跨版本引行号时不要用"整体 ±N"概括——不同方法的插入点不同，逐个 grep 才是唯一可靠办法。

【解释】值得注意：**绑定层的方法面比 `VikingFS` 更宽，但宽出来的部分是桩**。`chmod` 是真实现（`lib.rs:2093` 调到 `top.chmod()`，返回 `chmod ok`）；而 `digest` 是**桩**——`lib.rs:2490-2494` 直接 `Err(PyRuntimeError::new_err("digest not yet implemented in ragfs-python"))`；`read(stream=true)` 同样是桩（`lib.rs:1871` `"Streaming not supported in binding mode"`）。所以「绑定层更宽」指的是**方法签名存在**，不是**能力可用**——引用这些方法名时别当成已实现的功能。反向的缺口也存在：`VikingFS.find()`（语义检索，`openviking/storage/viking_fs/_semantic.py:196`）在绑定层没有对应方法。Python 操作面的裁剪（无 chmod、find=语义）是产品决策不是能力边界（呼应 [`../vfs/03`](../vfs/03-operation-semantics.md)）。

## B. C++ 引擎内部（src/）

### B1. 四个 capsule（`src/abi3_engine_backend.cpp:24-27`）

| capsule | 能力 | Python 使用者 |
|---|---|---|
| `openviking.vectordb.IndexEngine` | 向量索引核心 | `index/local_index.py` 的 IndexEngineProxy（RWLock 包裹，`:62,107`） |
| `openviking.vectordb.KVStore` | leveldb 持久化 KV | `store/local_store.py` |
| `openviking.vectordb.Schema` | collection schema 定义 | `store/serializable.py:10`（**这一行是 import 语句**：`from openviking.storage.vectordb.store.bytes_row import BytesRow, FieldType, Schema`——真正的别名在 `bytes_row.py:335` `Schema = engine.Schema`，引擎不可用时 `:340` 回落到 `_PySchema`；`collection_schemas.py` 只定义字段 dict，不 import engine） |
| `openviking.vectordb.BytesRow` | 行编码 | `store/bytes_row.py` |

### B2. 索引结构：内存扫描 + SIMD，无图索引

- Python 侧索引类层级：`LocalIndex`（基类，`local_index.py:358`）→ `VolatileIndex`（内存态，`:1280`）；`IndexEngineProxy` 用读写锁包 C++ 核心，并预留 `CuVSBackgroundRebuildPending`（`:103`，GPU 重建异步化）。
- **全仓 `src/` grep 无近似 ANN 索引**（`hnsw`/`IVF`/`faiss`/`kmeans` 全零命中）——这是源码级硬事实，成立。**但别说成"全内存扫描"或"无任何 tree index"**：`VolatileStore` 内部是 `std::map`（红黑树，`src/store/volatile_store.h:39`），持久化用 leveldb（其 memtable 也是跳表/有序结构），所以**有序结构是有的，缺的是近似最近邻**。另外 C++ 侧**没有叫 `VolatileIndex` 的类型**——`grep -rn VolatileIndex src/` 零命中，那个名字只存在于 Python（`openviking/storage/vectordb/index/local_index.py:1280`）；C++ 的类型是 `VolatileStore`。距离计算走 x86 SIMD 三变体（`src/CMakeLists.txt:270-296`），GPU 场景走 cuVS 适配器（`vectordb_adapters/factory.py` 白名单之一）。
- 【解释】这解释了两个现象：① 为什么 `ov status` 之外还有 `system consistency` 命令（索引与内容是两套持久化，需要对账）；② 为什么大规模数据的"local"后端定位是单机中小规模——扫描型索引的查询延迟随向量数线性，云上规模要靠 vikingdb/cuvs。
- collection schema 关键字段：`uri(path)` / `level(int64)`（L0=.abstract.md、L1=.overview.md、L2=原文，`openviking/storage/collection_schemas.py:115-119` 注释原话——注意模块在 `openviking/storage/` 下，**不在** `vectordb/store/`）/ `content(text)` / 向量字段。

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
