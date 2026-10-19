# Change Log — upstream 同步记录

> **当前基线**：`v0.5.0`（`20f9c1136`，2026-10-09）。本目录是版本谱系，不随单篇文档更新；最新一条记录是 [`0003`](0003-post-v0.5.0-audit.md)（v0.5.0 之上的行为级复核轮）。

本目录记录每次从 upstream（[volcengine/OpenViking](https://github.com/volcengine/OpenViking)）同步到本地后的变更摘要。每条记录包含：

- 版本/commit 跨度（from → to）
- commit 数量与时间跨度
- 核心变更归类
- 变更意义解读
- 对 `_digested/` 各子目录的影响评估

> 注：upstream 以 **git tag 发版**，且**不止 `v*` 一个命名空间**——截至 2026-10-19 有 `v*`（主包+服务端，最新 v0.5.0）、`python-sdk@*`（最新 0.1.15，比 v0.5.0 还晚）、`cli@*`（最新 0.4.23）、`sdk/go/*`（最新 v0.0.5）。主包版本由 `setuptools_scm` 只从 `v*` 派生（`pyproject.toml:219-223`），其余 tag 被明确排除。**引用"最新版本"时必须说清命名空间。**pyproject 用 dynamic version，README 里的 "0.3.22" 是 benchmark 报告口径、滞后于 tag。commit 范围用 hash 表达，版本参照 `git describe --match='v*'`。
>
> 口径修正 1（2026-09-12）：本文件最初写"upstream 不打 tag"，系误查 fork（origin）的 tags 所致，fetch upstream 后更正（见 [0001](./0001-baseline-v0.4.19.md) 的口径修正注）。
>
> 口径修正 2（2026-10-19）：SSH 远程在本机被环境拦截（`Connection closed by 198.18.0.19 port 22`），本轮改用 HTTPS `git fetch https://github.com/volcengine/OpenViking.git main --tags`。教训：**权威源头要在能到达的那条路上取**，网络路径同样可能是"副本"。

## 目录结构

```
_change_log/
  README.md
  0001-baseline-v0.4.19.md       # 初始基线：_digested/ 建立时的源码快照（0f77ab56）
  0002-v0.4.19-to-v0.5.0.md      # 第一次真同步：387 commit / 5 个 release
  0003-post-v0.5.0-audit.md      # v0.5.0 之上的行为级复核（工具化锚点校验 + 撤回错误概括）
  ...
```

编号递增；文件名简洁描述版本跨度。

## 与 `_digested/` 其他子目录的关系

`_change_log/` 是 `_digested/` 与 upstream 源码之间的版本历史桥梁。每次 upstream 发布新版本后：

1. **Discovery**：阅读 upstream diff、release notes、PR，写一条 sync record（`NNNN-v<from>-to-v<to>.md`），包含按领域拆解和影响评估
2. **Execution**：根据影响评估更新 `_digested/` 内受影响的专题文档，必要时创建 `_plan-N-*.md` 追踪进度

`_digested/README.md` 的顶部声明当前源码基线；正文中的机制结论描述当前 release，旧行为只记录在本目录的 sync record 中。

## 方法论守则（从 pi-mono 体系继承）

- **Discovery 与 Execution 分离**，分别留档；执行轮次用 `_plan-N-*.md`（Phase 化 + 验收标准 + 进度日志）追踪，收尾写 `_summary-*.md`。
- **失效分级按读者伤害排期**：结论级失效（主动误导）＞ 行为性错误（照做会坏）＞ 锚点漂移（行号）。
- **旧结论必须显式反转**，不能悄悄不管。
- **取证纪律**：结论锚定符号级证据（删除符号零命中 grep、逐字节比对优于计数、区分本轮引入 vs pre-existing 错误）。
- **诚实账本**：未验证的明说、defer 的记录、事故和教训留档。
- **并行 agent 纪律**：只允许读写文件，**禁止一切 git 命令**；提交由主线统一做，每 phase 完成即 commit，不积压未提交改动。
