# VFS 跨平台取证报告（vfs-platforms-evidence）

## v0.5.0 复核登记（2026-10-19）

- **基线**：`v0.5.0` = `20f9c1136`。原锚点基于 `0f77ab56`。
- ⚠️ **2026-10-19 更正："下一条的"全部仍有效"是把"结论"和"锚点"混为一谈，已撤回。**
  **结论层**仍有效：洋葱顺序、7 插件、`chmod` no-op、Windows `MoveFileExW` 这些判断在 `v0.5.0` 都成立。
  **锚点层基本没跟上**：§1–§2 的行号**整组仍是 `0f77ab56`**（例：`_uri_to_path` 旧 `:635-654` → 现 `:687`；`localfs resolve_path` 旧 `:81-96` → 现 `:133`；`windows_file_identity` 旧 `:98-119` → 现 `:151`；`MoveFileExW` 旧 `:1203-1246` → 现 `:1070-1100`）。本文件下方 §2.4 表格里 `chmod` 写的还是旧号 `:1257-1268`，而表头引的却是新号 `:1117-1128`——**同一文件内互斥**。
  **所以正确说法是**：本报告的"结论"可直接引用，"行号"不可以。
- ~~**净结论：本报告全部仍有效。**~~ `crates/ragfs` 在 v0.4.19 → v0.5.0 之间没有行为变化——洋葱顺序（`builder.rs:125-126, 273-278`）、7 个插件、`chmod` no-op（`localfs/mod.rs:1117-1128`）、Windows `MoveFileExW` 全部保持。
- 唯一需要重锚的是 `_ops.py` 一族（文件从约 2200 行涨到 2500+）：`read :139`、`write :178`、`mkdir :193`、`rm :215`、`mv :682`、`stat :1069`、`tree :1747`、`ls :2165`、`append_file :2116`。


- 取证范围：`/Users/bowhead/OpenViking`（只读，未执行任何 git 命令）
- 日期：2026-09-12（本次会话）
- 基线：`0f77ab56`（与 [`core-evidence`](core-evidence.md) 相同）
- 标记约定：【硬事实】= 源码可直接验证；【解释】= 基于代码结构的推断；【未定】= 证据不足
- 取证来源：① 船长本人逐文件验证；② 并行取证 agent A（Rust `crates/` 全量）；③ agent B（Python 层）；④ agent C（构建/CI/文档）。各节标注来源。

---

## 1. 分层结论：跨平台问题被压缩到唯一一层

【硬事实】（船长验证）

- `_uri_to_path()`（`openviking/storage/viking_fs/_access.py:635-654`）是纯前缀替换：`viking://{remainder}` → `/local/{account_id}/{remainder}`。产物是 **AGFS 挂载命名空间内的逻辑路径，不是 OS 路径**。
- localfs 挂载点与物理目录：`openviking/utils/agfs_utils.py:290`（`vikingfs_path = data_path / "viking"`）、`:305`（`"local_dir": str(vikingfs_path)`）、`:338`（挂载在 AGFS 路径 `/local`）。
- 组件名净化：`_safe_uri_parts()`（`_access.py:109-132`）拒绝 `.`/`..`、反斜杠、`X:` 盘符前缀段——**Python URI 层主动封死 Windows 语义的注入面**。
- 组件名长度：`_shorten_component()`（`_access.py:622-633`）按 UTF-8 255 字节截断 + sha256 前 8 位后缀（`_MAX_FILENAME_BYTES = 255`，:50）。【解释】NTFS 上限是 255 个 UTF-16 code unit，非 BMP 字符（4 UTF-8 字节/1 UTF-16 unit）下两平台容量不同，但 255 UTF-8 字节 ≥ 255 UTF-16 units 仅当全 ASCII——超长非 ASCII 名仍可能透传 OS 错误。【未定】极端用例未测。
- 加密写路径在 Python 侧的配合：`_encrypted_mount_relative_path()` / `_encrypted_temp_path()`（`_access.py:137-149`）按 POSIX `/` 分割重建 `.encrypt` 临时路径——与 Rust 侧约定一致。
- PathLock 全部下沉 Rust：`openviking/storage/transaction/__init__.py:1-8`（模块 docstring 原话 "Path-lock management has been moved to the Rust ragfs layer"）。
- 全仓（crates/）无 FUSE/WinFSP/Dokan 代码——`viking://` 永不挂载进 OS，是协议级虚拟。（船长验证）

## 2. Rust 层（agent A 报告要点，全部【硬事实】除注明外）

### 2.1 Windows 专门代码路径（4 处）

1. **CAS 文件身份**：`crates/ragfs/src/plugins/localfs/mod.rs:98-119` `windows_file_identity()`——`GetFileInformationByHandle` 取 `dwVolumeSerialNumber + nFileIndex(64bit)`；Unix 分支 :123-142 用 dev+ino；其他平台 :158-164 直接报错（明示只支持 unix/windows 两类目标）。
2. **replace() 覆盖式移动**：`mod.rs:1203-1246`——手工 `unsafe extern "system"` 声明 `MoveFileExW`，flags = `MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH`（:1213-1214）；路径经 `encode_wide()` 转 UTF-16 宽字符（:1224-1231）。注释 :1201-1202："encrypted publish needs an overwrite-on-destination move"（因 `std::fs::rename` 在 Windows 上目标存在时失败）。非 Windows 分支 :1248-1252 直接 `fs::rename`。
3. **CAS 文件锁**：`mod.rs:191-198` 用 `filelocks` crate `LockBackend::Fcntl`；该 crate 在 Windows 上映射 `LockFileEx`（docs.rs/filelocks/0.1.0）。跨平台可用。
4. **动态插件**：`crates/ragfs/tests/dynamic_provider.rs:88,102` Windows 用 `.dll`、跳过 unix 权限断言。

### 2.2 路径转换

- `resolve_path()`（`mod.rs:81-96`）：`validate_virtual_path` → strip 前导 `/` → `PathBuf::join(relative)`。**不是字符串拼 `/`**；std 在 Windows 上把 `/`、`\` 都当分隔符，join 正常工作。
- base_path 经 `fs::canonicalize`（`mod.rs:62-64`）。【解释】Windows 上 canonicalize 返回 `\\?\C:\...` verbatim 前缀——**隐式获得 >260 字符长路径能力**，是 std 副作用而非显式设计；全仓无显式 `\\?\` 处理；错误信息会泄漏 `\\?\` 前缀。
- 虚拟层内（grep exclude `mod.rs:308-318`、lock resolver `resolver.rs:106-110`、加密临时根 `encryption_wrapper.rs:185-192`）统一按 POSIX 字符串假设，只在 `resolve_path`/`replace` 边界翻译成 OS 路径。

### 2.3 PathLock 实现（与平台无关）

- **锁 token 侧车文件方案，无 fcntl/flock 主体**：目录锁 = 目录内 `.path.ovlock`；文件锁 = 父目录 `.exact.ovlock.<safe_name>.<sha1-16>`（`lock/resolver.rs:88-103`；常量 `core/internal_names.rs:8,11`）。
- `safe_name` 折叠非 `[A-Za-z0-9._-]` 为 `_` 并截 80 字符 + 全路径 SHA-1 前 16 hex 消歧（`resolver.rs:115-135`；2026-09-13 修正：白名单含连字符 `-`，此前漏写）——间接规避锁文件自身的长文件名问题。
- token 格式 `owner_id:time_ns:lock_type`（`lock/codec.rs:12`）；存储经 `LockProvider` trait（`lock/provider.rs:19-52`），FilesystemPathLockProvider（:176）通过挂载的 FileSystem 读写 token——**跟着后端走**（localfs→磁盘，memfs→内存）。
- 原子性：`try_create_token`（存在即失败）+ CAS（provider.rs:28-38）；CAS 落到 localfs 时才用 OS 文件锁（`LockFileEx` on Windows）。
- 活性：**TTL 过期回收**而非 OS 锁生命周期（`lock/manager.rs:675-677` is_stale、:911-927 强制移除）——持有者崩溃后最长 `lock_expire_secs` 内阻塞其他写者。三平台一致。
- 【未定】SMB/网络盘上 token 文件 CAS 语义无仓库内测试。

### 2.4 语义差异与风险点

| # | 发现 | 锚点 | 级别 |
|---|---|---|---|
| 1 | `rename()` 平台语义分裂：Windows 目标存在即失败，Unix 静默覆盖 | `mod.rs:1171` vs `:1248-1252` | 硬事实 |
| 2 | `chmod` 是 no-op（"For now, just return success"） | `mod.rs:1257-1268` | 硬事实 |
| 3 | 大小写不敏感/保留名（CON、NUL）/非法字符/255 字节限制零处理 | 全文件 grep 无命中 | 硬事实 |
| 4 | 加密写 `.encrypt` 临时名确定性（sha256(final_path)），`AlreadyExists→remove+retry` 在无 PathLock 时是 last-writer-wins 竞态 | `encryption_wrapper.rs:197-206, :261-269` | 硬事实+解释 |
| 5 | `validate_virtual_path` 的 `Component::Prefix` 检查仅 Windows 编译目标命中；`\` 在 Windows 被当分隔符、Unix 是合法文件名——同一路径两平台落到不同文件 | `core/filesystem.rs:20-28` | 硬事实 |
| 6 | 普通 `write()` 就地写无 temp+rename，崩溃可留半截文件 | `mod.rs:1010-1043` | 硬事实 |
| 7 | git 对象存储 tmp 名唯一+rename 竞态容忍（`git/backends/local.rs:73-93`，做法正确）；但 ref 写入用非唯一 `.tmp` 名（:235-237, :364-366），Windows 并发 ref 更新行为与 Unix 不同 | 硬事实+解释 |
| 8 | symlink/hardlink 全仓 0 处使用（ragfs 不创建不依赖链接） | grep 验证 | 硬事实 |
| 9 | ov_cli 主密钥/配置文件 0600 仅 unix（`commands/crypto.rs:92-96`、`config_wizard/store.rs:790`），Windows 无 ACL 收紧且仍打印误导性 "Key permissions set to 0600"（:99） | 硬事实 |

### 2.5 Cargo 与 CI

- `crates/ragfs/Cargo.toml:122-123` 唯一平台段：`[target.'cfg(windows)'.dependencies] windows-sys = "0.61"`（Win32_Foundation + Win32_Storage_FileSystem）；无 unix 限定段；`filelocks 0.1.0`（:66）跨平台；rusqlite bundled / fred vendored-openssl 规避平台 OpenSSL（:85-86）。
- `crates/ragfs-python/Cargo.toml` 全文 32 行无平台段；PyO3 `abi3-py310`（:22）。
- CI：`.github/workflows/_build.yml:10` 默认矩阵 5 平台（ubuntu-24.04 / ubuntu-24.04-arm / macos-14 / macos-15-intel / windows-latest）；Windows 段 :448-487（choco 装 cmake+mingw、`cargo build --target x86_64-pc-windows-msvc`）；`rust-cli.yml:55-57` 发布 `ov-windows-x86_64.exe` / npm `cli-win32-x64`。
- **`cargo test` 不在任何 workflow 中**；`_test_full.yml` 虽定义 3-OS × Py3.10-3.13 矩阵（:34），但文件止于 :82，步骤只有 `cargo check -p ragfs-python`（:79）+ `setup.py build_ext --inplace`（:82），**无 pytest 步骤且全 workflows 无调用方**（仅 workflow_dispatch 可触发）。【解释】`#[cfg(windows)]` Rust 代码仅被间接覆盖。
- Windows 真正的集成验证来自 `api_test.yml:43`：PR 档只有 ubuntu，**main push/schedule/release 扩到 `["ubuntu-24.04","macos-14","windows-latest"]`**。

## 3. 构建 / CI / 文档（agent C 完整报告要点，全部【硬事实】除注明外）

### 3.1 CI 矩阵（**26 个 workflow** 枚举结论——**这是 `v0.4.19` 的数**；`v0.5.0` 已是 **30** 个。本节关于 CI 覆盖面的结论不受影响，但“26”别当现值引用）

- `runs-on` 仅四类固定值 + matrix 变量；**无 cibuildwheel**（wheel 链路自研：setup.py + uv build + auditwheel repair，`_build.yml:290-296`）。
- **PR 门禁仅 linux x86_64**（`pr.yml:22,106,134,219`；deps 变更时经 `_build.yml` 继承 5 平台构建 `pr.yml:206`）。
- **发版必出**：sdist 1 + 5 平台 wheel（linux-x86_64 / linux-aarch64 glibc2.31 / macosx-14.0-arm64 / macosx-15.0-x86_64 / win x86_64；`release.yml:125-157` 一次性 PyPI 发布；Linux 轮在 ubuntu:20.04 容器 + auditwheel，`_build.yml:124-133`）；npm CLI 5 平台（`rust-cli.yml:31-60`，Linux musl 静态链兼容 CentOS7/Alpine :71-77）；Docker linux/amd64+arm64（`build-docker-image.yml:23-28`）。
- **测试**：api_test PR 档仅 ubuntu；**main/schedule/release 3-OS**（`api_test.yml:43`）。`_test_full.yml` 空壳（§2.5）。真正跑 pytest 的平台：Linux（PR cuVS lite、api_test、自托管 oc2ov）+ 3-OS api_test。
- Windows smoke 只 import engine、不校验 ragfs 绑定（`_build.yml:560-589`；对比 Linux/macOS :313-315/:538-540 会因 `get_binding_client() is None` 退出）。【解释】Windows wheel 的 ragfs 绑定存在性靠 `pyagfs/__init__.py:84-85` win32 `.abi3.pyd` 查找与 `engine/__init__.py:167-183` `os.add_dll_directory` 兜底。

### 3.2 C++ 引擎构建（Windows = MinGW，无 MSVC）

- leveldb/spdlog 仓内 vendored：`src/CMakeLists.txt:75,80` `add_subdirectory(../third_party/...)`；无 `.gitmodules`；sdist 经 `MANIFEST.in:2-6` graft 携带。
- 平台分支：`if(WIN32)` NOMINMAX + SABIModule（:38-40, :47-49, :200-212，缺失 FATAL_ERROR "Windows abi3 modules require..."）；`if(APPLE)` deployment target 10.15 + `-undefined dynamic_lookup`（:30-32, :214-216）；`if(MINGW)` 静态链（:246-255）；ARM 额外构建 krl（:82-94）；x86 sse3/avx2/avx512 变体（:270-296）。
- **无 MSVC 分支**：GNU 风格 flags 无条件注入（:42-43 `-Wno-... -lpthread`）、`Python3_ARCH_INCLUDE_DIR "/usr/include/...linux-gnu/"` 写死（:44）——事实上面向 MinGW/GCC/Clang；CI Windows 也 `choco install mingw`（`_build.yml:448-452`）。
- `setup.py:449-457`：darwin 设 deployment target；win32 先定位 abi3 导入库（`_get_windows_python_sabi_library` :72-104）再**强制 `-G "MinGW Makefiles"`**；Windows 二进制名 `ov.exe`（:186）。
- ragfs 绑定经 maturin 构建抽进 `openviking/lib/`（setup.py:263-388；CI `OV_REQUIRE_RAGFS_BUILD=1` `_build.yml:154,462`）；abi3 cp310（setup.py:536-543）→ 每平台一个 wheel 覆盖 py3.10+。

### 3.3 Docker / 部署

- Dockerfile 全 Debian trixie 纯 Linux（`Dockerfile:5,8,20,100`）；镜像仅 linux/amd64+arm64；docker-compose 无 `platform:` 锁定（`docker-compose.yml:20`）；Helm 同镜像（`deploy/helm/openviking/values.yaml:5-13`）；cuVS dev 镜像同样 Linux（`docker/cuvs-dev/Dockerfile:3`）。
- 【解释】官方服务端发布形态事实上是 "Linux 容器"；Windows/macOS 经 Docker Desktop 消费（文档明说 Docker Desktop 不支持 `--network host`，`docs/en/guides/13-multi-write-storage.md:133`）。

### 3.4 文档口径

- Quickstart 双语明文 "OS: Linux, macOS, Windows"（`docs/en/getting-started/02-quickstart.md:10`、zh 同位）；安装不分叉 OS。
- agent 安装文档 Windows 五步走："Prefer the prebuilt-wheel path... Only enter the Windows local-build path if wheels are unavailable"（`04-setup-for-agent.md:59-69`；PowerShell/cmd 环境变量示例 :268-283；失败排查 Case 6 :394-401；"on Windows, local compilation usually means CMake and MinGW" :388-393）。
- **全库零 WSL 字样**——Windows 官方路径是原生 wheel / MinGW 本地编译，不是 WSL2。
- 无平台矩阵页；FAQ 只提 "(if installing from source or on unsupported platforms): Rust/Cargo, GCC 9+ or Clang 11+"（`docs/en/faq/faq.md:64`），"不支持的平台"存在但未列名单。
- changelog 多条 Windows 修复记录（`docs/en/about/02-changelog.md:36,376,477,501,...`："Windows vector backends / .bat 修复 / skipped FUSE-incompatible filesystem tests on Windows / Windows engine wheel runtime packaging"）——Windows 是持续维护目标。
- 桌面助手：mac/win x64 beta（`README.md:223-229`）。

### 3.5 验证矩阵四档（agent C 结论）

| 档位 | 平台 |
|---|---|
| 一等支持（PR 门禁 + 每发版必出） | Linux x86_64 (glibc 2.31) |
| CI 覆盖（发版产物 + main/schedule api_test，不进 PR 门禁） | Linux aarch64、macOS arm64/x86_64、Windows x86_64 |
| 仅文档提及 | Windows 桌面助手 beta、Docker Desktop 注意事项、"unsupported platforms"（未列名单） |
| 完全未覆盖 | Windows ARM64、BSD、musl Python wheel（musl 用户只有 CLI）、Windows 容器 |

### 3.6 Windows 用户三条实际路径

1. **原生 pip wheel（x64）**——文档推荐（`04-setup-for-agent.md:59-69`）。
2. **官方 Linux 容器**（Docker Desktop / 服务器）——server 部署主路径。
3. **本地源码编译**：Rust + CMake + **MinGW**（非 MSVC），仅 wheel 不可用时引导（`04-setup-for-agent.md:69,388-401`）。

## 4. Python 层（agent B 失败，船长补验，全部【硬事实】除注明外）

### 4.1 原生库加载（pyagfs + engine）

- `openviking/pyagfs/__init__.py:72-98` `_find_ragfs_so()`：**显式 win32 分支** `:85` `if sys.platform == "win32": abi3_suffix = ".abi3.pyd"`；查找序 = 精确 EXT_SUFFIX → `.abi3.so/.abi3.pyd` → glob 兜底（2026-09-13 重锚：此前写 :81-96）。
- ABI 兼容门禁 `:51-69` `_is_compatible_ragfs_extension()`：CPython 版本专属产物必须精确匹配当前 EXT_SUFFIX（拒 `.cpython-312-...`/Windows 风格 `.cp312-...`），`.abi3.` 产物跨解释器可载（2026-09-13 重锚 + 函数名勘误：此前写 `:47-70` `_is_compatible_rugfs_extension`）。
- 加载序 `_load_rust_binding()` `:103-129`：pip 安装的 `ragfs_python` 优先 → vendored `openviking/lib/` → **ImportError（无纯 Python 回退）**。`_LIB_DIR = <pkg>/lib`（:47）。
- C++ 引擎 `openviking/storage/vectordb/engine/__init__.py`：非 x86（Apple Silicon 等）只有 `native` 变体（`_available_variants` :55-58）；win32 检查 `.pyd/.abi3.pyd` 文件名（:52-60 一带 `_module_exists`）；x86 变体经 `_x86_caps` 探测（:60-77）。
- 引擎加载有**跨平台仿真测试**：`tests/misc/test_vectordb_engine_loader.py:151,163,176` 用 monkeypatch `sys_platform="win32"` 在任意平台验证 win32 加载逻辑。

### 4.2 Windows 专属 Python 代码（3 处）

1. `openviking/utils/process_lock.py:51-70`：Windows PID 存活检测用 `_winapi.OpenProcess(SYNCHRONIZE)` + `WaitForSingleObject`——注释明言 POSIX `os.kill(pid,0)` 在 Windows 是发 CTRL_C_EVENT，不能直接用；且区分 winerror 87（PID 不存在）与 access denied（不丢弃活锁）。**配套 Windows 原生测试存在**：`tests/unit/test_process_lock.py:140` `skipif(sys.platform != "win32", reason="requires native Windows APIs")`。
2. `openviking/crypto/config.py:73`：`os.name != "nt"` 跳过权限检查（Windows 不做 0600 校验——与 Rust 侧 ov_cli key 文件行为一致）。
3. `openviking/server/openviking_assets.py:350,359`：进程组语义 `start_new_session=os.name == "posix"`（POSIX-only，Windows 单进程）。

### 4.3 路径与数据目录

- 默认数据目录：`openviking_cli/utils/config/consts.py:7` `DEFAULT_CONFIG_DIR = Path.home() / ".openviking"`——经 `Path.home()`，Windows 落 `C:\Users\<user>\.openviking`。localfs 物理目录 = `<workspace>/viking`（`agfs_utils.py:290`，workspace 可 override，`open_viking_config.py:781` `Path(path).expanduser().resolve()`）。
- master key 默认 `~/.openviking/master.key`（`encryption_config.py:16`）。
- QueueFS 默认 backend `sqlite`（`agfs_utils.py:244`）。【未定】sqlite 文件具体落点未逐行验证。
- AGFS 路径在 Python 层始终是 POSIX 风格字符串（`_uri_to_path`/`_encrypted_*` 均按 `/` 切分），**Python 层零 OS 路径拼接**（viking_fs 内 pathlib 仅用于库目录等宿主侧）。

### 4.4 打包与测试面

- `pyproject.toml:21-30` classifiers 只有 Python 版本，**无 OS classifier**（OS 支持事实由 wheel 矩阵承载）。
- 测试平台分支：Windows 专属测试存在（`tests/misc/test_extract_zip.py:108` skipif `os.name != "nt"`；`tests/unit/test_process_lock.py:140` win32-only）；POSIX-only 测试打 skipif 不阻塞 Windows（`tests/server/test_openviking_assets.py:364,404`、`tests/utils/test_process_lock.py:27`、`tests/service/test_resource_service_git_preflight.py:15`）。
- 【解释】测试布局是"三平台可跑同一套 pytest + 平台专属用例 skipif 隔离"，而非分平台测试套件。

## 附：待深挖清单

1. memfs/s3fs 路径下 PathLock token 存储的平台无关性验证深度。
2. `write_context`/sidecar 在大小写不敏感 FS 上与用户同名文件（如 `.Abstract.md`）的冲突面。
3. Windows 共享盘（SMB）上 PathLock token CAS + filelocks Fcntl backend 的行为（仓库无测试）。
