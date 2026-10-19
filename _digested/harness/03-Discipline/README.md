# 03-Discipline — 开发纪律评价

> **基线**：`v0.5.0`（2026-10-19 复核；建档基线 `0f77ab56`）。
>
> 评价 OpenViking 的开发有没有策略和纪律：CI 守卫什么、贡献门要求什么、发布怎么组织。机制事实见 `core/`、`architecture/`，本目录只做判断。

## 篇目

| 篇 | 回答什么 |
|---|---|
| [3.1_ci_guard_chain.md](3.1_ci_guard_chain.md) | **30** 个 workflow 守卫什么、多语言原生层有没有进 CI、测试基建规模（**730** 个测试文件；主包单测仍不进 CI） |
| [3.2_contribution_gate.md](3.2_contribution_gate.md) | 贡献门里的设计哲学、PR 规模策略、发布纪律（v0.5.0：CONTRIBUTING 298 行 + 安全边界一节；**四个**真实 tag 命名空间） |
