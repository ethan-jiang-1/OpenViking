# 02 `ov` CLI 完整命令参考：接入面的第四条门，逐命令取证

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。取证来源：对 `crates/ov_cli/` 的全量源码枚举（并行取证 agent 报告，2026-09-12；2026-10-19 对 v0.5.0 复核），与 `docs/en/agent-integrations/16-capability-reference.md` §5.1、`docs/en/getting-started/05-cli-setup.md` 交叉验证。
> 姊妹篇：[`01-start-here`](01-start-here.md)（七种接入形态与选择）。本文回答："`ov` 到底支持什么、哪些必须 server 在跑"。

## 先给结论

`ov` 是 **Rust CLI**（`crates/ov_cli`，clap 定义集中在 `main.rs:364-1414`）——Python 包的 `ov`/`openviking` 入口只是 execv 薄包装（`pyproject.toml:196-198` 注释原话"放弃 python CLI"）。**约 18 个命令组、110+ 子命令**，覆盖文件系统操作、语义检索、session、skills、快照、ACL、admin、观测。两条最重要的使用纪律：

1. **除 5 个纯本地命令外全部要求 server 在跑**（`:1933`）——CLI 没有任何本地直连存储的后端。
2. **为 agent 设计的痕迹很重**：全局 `-o json` 机器可读输出、强制语言门（非交互未设语言 exit 2）、裸 `help` 被当作误用纠错、`--help` 才是真帮助、无任何后台自动行为。

## 身份澄清：你跑的 `ov` 是谁

| 入口 | 实际执行 | 锚点 |
|---|---|---|
| pip 装的 `ov` / `openviking` | 查找 Rust 二进制并 **execv 替换进程**（win32 因 `execv` 不换进程、破坏 TUI 键盘输入改用 `subprocess.call`，issue #587） | `openviking_cli/rust_cli.py:1-40`、`pyproject.toml:196-198` |
| npm `@openviking/cli-*` / 安装脚本 / cargo install | 直接是 Rust 二进制，零包装开销 | `crates/ov_cli/`、`rust-cli.yml:31-60` |

配置文件 `~/.openviking/ovcli.conf`；默认 `http://127.0.0.1:1933`（`config.rs:9`）、timeout 60s（`config.rs:146-148`）。

## 是否必须 server 在跑

【硬事实】`base_client.rs` 全部请求走 `{base_url}{path}` 的 reqwest HTTP（`:199-216,497+`；鉴权头 `X-OpenViking-Account/User/Actor-Peer` + Basic/Bearer，`:280-360`）。**不存在本地存储后端**。

纯本地命令仅 5 处：

| 命令 | 做什么 | 锚点 |
|---|---|---|
| `system crypto init-key` | 本地生成 32 字节 root key 文件 | `crypto.rs:39-101` |
| `skills validate` | 只读本地 SKILL.md（唯一完全离线命令） | `skills.rs:368-375` |
| `config show/list/switch/delete` | 本地 ovcli.conf 操作 | `config_wizard/` |
| `language`（lang） | 设 en/zh-CN | `main.rs` |
| `version` | 打印版本 + 3 秒尽力探测 /health | `main.rs:3642-3665` |

注意混合态：`config add/edit` 本地写文件但会向 server 发校验（`docs/en/getting-started/05-cli-setup.md:224-225` 的 exit 4/5 印证）。

## 全局 flag 与预解析管线（agent 对接时要知道的"暗规则"）

- 全局 flag（`main.rs:144-200`）：`-o/--output table|json`、`-c/--compact`（默认 true）、`--account/--user/--actor-peer-id`、`--sudo`（仅 admin/system/task 的部分子命令，`:1265-1274`）、`--profile`；遗留 `--progress/--no-progress/-v` 仅对 add-resource/add-skill/skills add 有效（`:1276-1285`）。
- 预解析管线（`main.rs:3000-3053`）：自绘 help → **语言门**（非交互未设语言 exit 2；豁免 `language` 与 `config add/edit/delete/list/switch`，`:2863-2896`）→ 裸 `help` 子命令纠错（exit 2，`:2354-2404`）→ 配置文件门（`:2087-2103`）。`ov --help` 绕过语言门（`:2979-2997`）。
- 【解释】对 agent 的实操含义：脚本里调用 `ov` 前先确保 `ov language` 设过或交互式设置过，否则 CI 里一律 exit 2；机器消费一律加 `-o json`。

## 完整命令清单（类别：a=连 server ｜ b=本地 ｜ c=交互）

### 文件系统（`commands/filesystem.rs` + `content.rs`）—— 全 a

| 命令 | 职责 | 备注 |
|---|---|---|
| `ls`（别名 `list`） | 列目录 | `main.rs:476-545` |
| `tree` | 树形视图 | `main.rs:546` |
| `mkdir` / `rm`（`del`/`delete`）/ `cp` / `mv`（`rename`）/ `stat` | 常规动词 | `main.rs:609,618,639,651,661` |
| `read` / `abstract` / `overview` | 读 L2 全文 / L0 / L1 | `content.rs:9-38`、`main.rs:677-694` |
| `write` | 写文件 | `main.rs:695` |
| `get` | 下载到本地文件 | `content.rs:102` |
| `attrs get` / `set-tags` | 属性与标签 | `main.rs:265-290,753` |

### 检索（`search.rs`）—— 全 a

| 命令 | 职责 | 备注 |
|---|---|---|
| `find` | 语义检索（query 或 `--image`；`--level/--context-type/--tags/--read-content`） | `main.rs:777-845` |
| `search` | 实验性，多 `--session-id` | `main.rs:846-917` |
| `grep` | 内容 grep（`-x` 排除 URI 前缀） | `main.rs:918-969` |
| `glob` | 模式匹配 | `main.rs:970-1004` |

### 其余各组

| 组 | 子命令 | 类别 |
|---|---|---|
| `acl` | get/set/grant/revoke/rm | a（`main.rs:292-320`） |
| 导入 | `add-resource`（本地路径/URL/manifest `-m`/Connector，`--wait/--tags/--processing-mode`）、`add-skill`、`add-memory` | a（`main.rs:337-468,1010`） |
| `skills` | add/list/find/show/update/remove/validate | a；validate=b |
| `session` | new/list/get/get-session-context（`--token-budget` 默认 128000）/get-session-archive/delete/add-message(s)/config set/commit | a（`main.rs:1475-1627`） |
| `pack` | export/backup/import/restore（.ovpack，server 端打包） | a（`main.rs:1023-1090`） |
| `snapshot` | commit/restore/show/log/diff/ignore-get/set/delete | a（`snapshot.rs:11-105`） |
| `task` | status/cancel/list；`task watch` {ls/show/rm/pause/resume/update/trigger} | a（`main.rs:1301-1329,1775-1832`） |
| 观测 | `status`/`health`（healthy=false 也 exit 0，`handlers.rs:1994-2002`）/`wait`/`observer` {queue/vikingdb/models/retrieval/fs/system} / `version` | a（version 混合） |
| `compile` | `--from --to --skill`，提交任务返回 task_id | a（`compile.rs:22-31`） |
| `chat` | REPL 或 `-m` 单条，SSE 流式，走 VikingBot `/bot/v1` | a+c（`chat.rs:209-213`） |
| `tui` | 全屏 alternate-screen 文件浏览器，先探活 /health | a+c（`tui/mod.rs:23-41`） |
| `config` | 无子命令=交互向导（含 User Management）；show/validate/add/edit/delete/list/switch | c / b（add-edit 混合）（`config_wizard/wizard.rs:85`） |
| `admin`（16 子命令） | create/delete/list-accounts、migrate、register/list/remove-user、set-role、regenerate-key、group 五件套、set-account-settings | a，多数需 `--sudo`（`main.rs:1916-2084`） |
| `reindex` | 重建索引：`--mode vectors_only\|semantic_and_vectors\|prune_orphans`、`--dry-run`、`--wait` 默认 true | a，可用 `--sudo`（`main.rs:1214-1260`） |
| `system` | wait/status/health/consistency/backend sync-status/sync-retry；`crypto init-key` | a；crypto=b（`system.rs`/`crypto.rs`） |
| `privacy` | categories/list/get/upsert/versions/version/activate | a（`main.rs:1834-1914`） |
| `language`（lang） | 设 en/zh-CN | b |

## 与官方 docs 的交叉验证（以源码为准的 3 处缺漏）

【硬事实】对照 `docs/en/agent-integrations/16-capability-reference.md` §5.1 与 `05-cli-setup.md`：一致项很多（默认端口、语言门、exit code 2-6、skills validate 唯一离线、health 恒 exit 0、"doctor 不在 Rust 二进制中"）。**不一致（docs 缺漏）**：

1. docs "Writing data" 漏了 `cp`（`main.rs:639`）；
2. docs 完全没提 `acl` 组（`main.rs:292-320`）；
3. docs 的 admin 列表缺 6 个 group 子命令与 `set-account-settings`（`main.rs:1993-2083`）。

内部小瑕疵（无行为影响）：`main.rs:2689` observer 子命令表含 "transaction"，但实际 ObserverCommands 无此子命令——配置门死分支。

## 设计点（为什么说它是"agent 友好"的兜底入口）

1. **机器可读**：全局 `-o json` + `-c` 压缩。⚠️ **JSON 有两种形状**：config 族输出 `{"status":"ok","result":…}`，普通命令 compact 下是 `{"ok":true,"result":…}`——写解析器时别假设统一（docs §5.2 也提醒了这点）。
2. **i18n 强制**：语言门保证输出语言确定（en/zh-CN），CI 未设置即 fail-fast（exit 2）——宁可报错不给猜测性输出。
3. **无后台自动行为**：一次性进程；`task watch`/`compile` 的调度都在 server 端，CLI 只提交与查询（与 [`01-start-here`](01-start-here.md) 的"全部显式调用"口径一致）。
4. **密钥不入 argv**：`--api-key-stdin` / `--api-key-env` 注入。
5. **agent 例外通道**：`find/search/grep/glob/add-resource/add-skill/add-memory` 允许把查询/URI 当作第一个裸位置参数，不会被预解析器误判为 help 误用（`main.rs:2450-2455`）——这就是"裸 `ov 用户问题` 式调用"能工作的原因。
6. 【解释】回到 [`03-operation-semantics`](../vfs/03-operation-semantics.md) 的语义陷阱：CLI 的 `find` 同样是语义检索（不是按名找文件，但支持 `--image` 图像查询与 `--threshold/--after/--before` 过滤），`mv/rm` 同样同步向量索引——CLI 只是 HTTP API 的皮，server 语义不变。

## v0.5.0 复核（2026-10-19）

**44 个顶层命令：一个没增、没删、没改名。** 这是本轮同步里少见的"零 breaking 面"——对照同期 MCP 工具 +5、pi 工具名全改、Watch 语义收紧，CLI 是稳定的那一面。

> **口径说明**：44 = `enum Commands` 的**顶层变体数**，实测方式是对 `crates/ov_cli/src/main.rs:364-1414` 的枚举体做变体名提取；**`0f77ab56` 与 `v0.5.0` 逐个比对，44 个变体名字集合完全一致**。此前草稿曾误记 41，是手工清点遗漏。与第 8 行的"约 18 个命令组、110+ 子命令"并不矛盾——那两个数是**含嵌套子命令**的另一口径，引用时勿混。

新增两个参数/语义：

| 变更 | 说明 | 锚点 |
|---|---|---|
| `--search-type semantic\|keywords` | 语义检索可切全文关键词检索（BM25，需后端有全文索引） | `crates/ov_cli/src/main.rs:975-981` |
| `ov compile --skill memory` 哨兵值 | 省略 `--to`，就地整合当前目录 | `main.rs:1285` 注释；测试 `:4332`、`:4340` |
| 安装方式 | 统一安装器现在**默认从 npm 装** `@openviking/cli` | `examples/memory-plugin-shared/install.sh:10-11,229` |

**仍然存在的老问题**（v0.5.0 未修）：observer 里的 `"transaction"` 死分支（`main.rs:2842`）——该值永远不会被产生。


## 状态标注

- 硬事实：全部命令枚举与锚点（源码可复核）；与 docs 的 3 处缺漏
- 解释：对 agent 实操含义的推演（语言门/`-o json` 的用法建议）、"agent 友好"定性
- 未定：`chat`/`tui` 的 TUI 在 Windows 终端下的兼容细节（wrapper 用 subprocess.call 规避，issue #587，未实测）
