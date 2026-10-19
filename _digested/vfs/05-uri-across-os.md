# 05 viking:// 与三个操作系统：URI 在 macOS / Linux / Windows 上到底怎么"work"

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。前置：[`01-bridge-to-disk`](01-bridge-to-disk.md)（五层栈）、[`agent-view.svg`](agent-view.svg)。

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
> 标记约定：**【仓内事实】**= 源码可直接验证；**【外部事实】**= OS 机制的一般知识（非本仓源码，附权威出处）；**【解释】**= 推断。

## 先给结论

**你的问题的前提需要拆掉一层：`viking://` 不需要任何操作系统"支持"。**它是纯应用层的 URI scheme——解析它的代码是 OpenViking 自己的 Python 字符串处理（`openviking/core/namespace.py:90` 一行 `startswith("viking://")`），这个 URI **从不进入** macOS Finder、Linux 内核、Windows 资源管理器或任何 OS 的路径解析器。所以答案是：**三平台上以字节级完全相同的方式 work，Windows 不需要任何"最近的更新"来配合它**。

你记忆中"Windows 历史上没这么回事儿、最近才支持特殊路径"的感觉是对的，但你想到的那个东西（Windows 放开长路径 260 限制、`\\?\` 前缀）是**另一件事**——它影响的是 L5 落盘，不影响 URI。下面把这三件经常被混在一起的事彻底分开。

## 一、三个经常被混为一谈的概念

| 概念 | 谁来解析 | 例子 | viking:// 属于哪类？ |
|---|---|---|---|
| **A. 应用层自定义 URI scheme** | 应用自己的代码 | `viking://`、`spotify://`、`vscode://`、PowerShell 的 `HKLM:\` | ✅ 就是这类 |
| **B. OS 注册的 scheme handler** | OS + 浏览器/Explorer（点链接唤起 app） | Windows 注册表 `URL Protocol`、macOS `CFBundleURLTypes`、Linux `x-scheme-handler` | ❌ OpenViking **没有注册**（【仓内事实】全仓无 `CFBundleURLTypes` / `x-scheme-handler` / `URL Protocol` 痕迹） |
| **C. OS 原生路径语法** | 内核 / C 库 | `C:\Users\...`、`\\?\C:\...`、`\\server\share`、`/home/...` | ❌ 仅 L5 落盘时短暂接触 |

**判定方法（谁都能做）**：把 `viking://user/u1` 粘进 Windows 资源管理器地址栏 / macOS Finder「前往文件夹」/ 浏览器——三处都会告诉你"不认识这个地址"。这就是"属于 A 而不属于 B"的直接证明。对比：粘 `file:///tmp` 三处都认，因为 `file://` 是唯一一个三平台系统层都内置理解的 scheme（【外部事实】[WHATWG File URL 标准](https://url.spec.whatwg.org/#file-url-syntax)、IANA 注册）。

## 二、`viking://` 在三平台为什么行为完全一致

`viking://` 的一生只在 OpenViking server 进程内：

```
请求边界：字符串校验 + 白名单（namespace.py:90 起的纯字符串操作，无 OS 参与）
    ↓
_uri_to_path：viking://user/u1/x → /local/{account_id}/user/u1/x（_access.py:635）
    ↓                                ↑ 这个"路径"仍是应用内字符串
localfs.resolve_path：strip('/') → PathBuf::join   ← 这里才第一次产生 OS 路径
```

【仓内事实】三平台的差异被 architecture 推迟到最后一行。前两步是纯字符串协议——这正是 `01` 篇"协议级虚拟"的含义。有意思的旁证：`_safe_uri_parts`（`_access.py:109-132`）**主动拒绝 `\` 和 `X:` 段**——它防的是"以后落盘到 Windows 卷时"的注入，也就是说 OpenViking 在 URI 层就替 Windows 把关，而不是等 Windows 来处理。

## 三、三平台对"自定义 URI scheme"的真实机制（如果你真想让 OS 认识一个 scheme）

三个平台的注册机制都**历史悠久，不是新东西**（【外部事实】）：

| 平台 | 注册位置 | 历史 |
|---|---|---|
| Windows | 注册表 `HKCU\Software\Classes\<scheme>` 下建空值 `"URL Protocol"` + `shell\open\command`；打包(UWP/MSIX)应用改在 manifest 里声明 `<uap:Protocol>` | **IE 3 时代（1996）就有**，[Microsoft Learn: 自定义 URL 协议](https://learn.microsoft.com/en-us/previous-versions/windows/internet-explorer/ie-developer/platform-apis/aa767914(v=vs.85)) |
| macOS | App bundle `Info.plist` 的 `CFBundleURLTypes` → LaunchServices 登记卡 | NeXTSTEP/OS X 早期就有，[Apple: Defining a Custom URL Scheme](https://developer.apple.com/documentation/xcode/defining-a-custom-url-scheme-for-your-app) |
| Linux | freedesktop 惯例：`.desktop` 文件 `MimeType=x-scheme-handler/viking;` + `xdg-mime default` | [freedesktop Desktop Entry 规范](https://specifications.freedesktop.org/desktop-entry-spec/latest/) |

【解释】OpenViking 刻意不做这个注册：`viking://` 的合法消费者是 MCP client / SDK / CLI——它们直连 server，不需要 OS 帮忙唤起。注册了反而扩大攻击面（任何网页都能尝试唤起你的存储）。

## 四、你记忆里"最近的 Windows 支持特殊路径"：那件事真实存在，但在另一层

【外部事实】Windows 路径机制的真实时间线（这大概是你记忆的来源）：

| 年代 | 机制 | 说明 |
|---|---|---|
| 1993（NT 3.1） | `\\server\share` UNC 路径 | 网络路径，很早就有 |
| （NT 内核一直有） | **`\\?\` verbatim 前缀** | 绕过 Win32 层的所有路径解析（不展开 `..`、不认 `/`、不做大小写归一），长度上限 32767 字符，[Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation) |
| 2016（Win10 1607） | 组策略放开 MAX_PATH=260 | 需应用 manifest 声明 `longPathAware` |
| 2019（Win10 1903） | `LongPathsEnabled` 注册表 + manifest 成为常规手段 | **"最近的 Windows 支持"指的就是这个：长路径，不是 URI** |

**这和 OpenViking 的唯一接触点**（【仓内事实】+【解释】）：localfs 的 base_path 经 `fs::canonicalize`（`crates/ragfs/src/plugins/localfs/mod.rs:62-64`）——Rust 标准库在 Windows 上返回的正是 `\\?\C:\Users\...` verbatim 形式。副作用是 OpenViking 的物理存储路径**天然免疫 260 限制**：哪怕你的 `~/.openviking/...` 层级很深、URI 组件很长（255 字节截断后仍可能堆出深路径），Windows 上也能落盘。这不是 OpenViking 显式写的代码（全仓无 `\\?\` 处理），是 std 的行为——"能用但隐式"，日志里会看到 `\\?\` 前缀。

## 五、三平台对照总表

| 维度 | macOS | Linux | Windows |
|---|---|---|---|
| `viking://` 解析 | 进程内字符串，三平台**字节级相同** | 同 | 同 |
| OS 是否认识这个 scheme | ❌（未注册 handler） | ❌ | ❌ |
| 粘到 Explorer/Finder/浏览器 | 无处可去 | 无处可去 | 无处可去 |
| 谁真正消费它 | MCP / HTTP API / ov CLI / SDK（三平台同一套） | 同 | 同 |
| L5 落盘的原生路径 | `/Users/.../.openviking/...`（APFS） | `/home/.../.openviking/...`（ext4） | `\\?\C:\Users\...\.openviking\...`（NTFS，verbatim） |
| 深路径风险 | 无 260 类限制 | 无 | **被 canonicalize 的 verbatim 副作用绕开** |
| 记忆中"最近的更新"相关的点 | 不适用 | 不适用 | 长路径放开（2016/2019）——OpenViking 经 std 间接受益，非显式依赖 |

## 六、快速自测（每个平台 30 秒）

1. `ov ls viking://user/u1` ——三平台都 work（URI 走 OpenViking 自己的解析 + server）。
2. 把 `viking://user/u1` 粘进系统文件管理器/浏览器——三平台都失败（证明它不依赖 OS 的 scheme 机制）。
3. Windows 上 `ov` 跑起来后查 `{workspace}/viking` 的实际路径——会看到 `\\?\` 前缀（第四节机制的可见证据）。

## 状态标注

- 仓内事实：`namespace.py:90`、`_access.py:109-132,635`、`localfs/mod.rs:62-64`、全仓无 scheme 注册痕迹——锚点均可复核
- 外部事实：三平台 scheme 注册机制、Windows 路径时间线（附 Microsoft/Apple/freedesktop 官方链接，日期以链接页为准）
- 解释：OpenViking 不注册 handler 的动机归因；verbatim 副作用"隐式受益"的定性
