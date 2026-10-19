# OpenViking 开发纪律与自描述取证报告（原料）

## v0.5.0 复核登记（2026-10-19）

- **基线**：`v0.5.0` = `20f9c1136`。原锚点基于 `0f77ab56`。
- **计数变化**：CI workflow 26 → **30**；测试文件 655 → **730**（728 `test_*.py` + 2 `*_test.py`）；`tests/` 顶层子目录 29 → **31**；`skipif` 18（`pytest.mark.skipif` 实测 18 处）；`pytest.mark.skip` 仍 3。
- **结构变化**：`docs/design/`、`docs/plans/`、`docs/superpowers/` **整目录删除**——本报告里凡引用设计稿的段落，都已无一手来源可核。多语 README/CONTRIBUTING/RELEASE 移入 `docs/repository/`。官方 docs 只剩 en/zh（各 110 个 md）。
- **新增守卫**：`_docs.yml` 现有四道检查（theme 测试、双语一致性、API 参考、构建后锚点）；`gateway.yml` 是第一个给核心域之外的 Python 子系统接 pytest 的 workflow。
- **未修复**：`_test_full.yml` 仍无 pytest 且无 workflow 调用它；根级 `AGENTS.md` 仍不存在；`README.md:111` 仍写 "0.3.22"。


- 取证日期：本地工作区快照（2026-09-12 时间戳），仓库 /Users/bowhead/OpenViking
- 取证方式：只读（未执行任何 git 命令，未运行任何仓库代码），仅本报告为写入产物
- 评价目的：评估「开发有没有纪律」与「对自己上面的 coding agent / 使用者自描述够不够」
- 标注约定：【硬事实】= 文件内容直接可见；【解释】= 基于硬事实的推断；【未定】= 证据不足、需外部信息（如 GitHub 历史）才能定论

---

## A. 工程纪律

### A1. CI（.github/workflows/）

【硬事实】共 **30** 个 workflow 文件（`v0.5.0`；`ls .github/workflows/*.yml *.yaml | wc -l`）。⚠️ **2026-10-19 更正**：原文写"26 个（2026-09-13 修正：此前写 27，系误计）"——26 是 `v0.4.19` 的数，本文件表头 `:6` 已写"26 → **30**"，正文列表却没跟改，**头/体打架**。下面的编号列表按 30 个读。，主流程用编号命名形成显式流水线序列：
- 01 PR Checks（pr.yml:1）、02 Main Branch Checks（ci.yml:1）、03 Release（release.yml:1）、04 Weekly Security Scan（schedule.yml:1）、05 OpenClaw2OpenViking Memory Tests（oc2ov_test.yml:1）、06 API & CLI Integration Tests（api_test.yml:1）、07 API Effect Tests（api_test_effect.yml:1）、12/13 _Test Suite Lite/Full（_test_lite.yml:1 / _test_full.yml:1）、14 _CodeQL Scan（_codeql.yml:1）、15 _Build Distribution（_build.yml:1）、16 _Publish、17 Docs/_Docs Build、18 _Docs Deploy、19 Docs TOS、20 Release TOS Upload（release-tos.yml:1）。
- 编号 08–11 缺失（01–07、12–20 连续出现，08–11 跳号）。【未定】无法用 git 历史确认是删除了 workflow（很可能是被移除的 lint/unit-test 类 workflow）还是预留。

【硬事实】PR 触发的主检查内容（pr.yml）：
- `plugin-tests`（pr.yml:21）：约 60 个 JS/TS 插件测试文件经 `node --test` 运行（claude-code/codex/cursor/trae/zcode/dsh/opencode/pi 等 memory-plugin），并对 6 个安装脚本跑 `bash -n` 语法检查。
- `openclaw-tests`（pr.yml:103）：Vitest 套件，且注释里明确记录了被排除的测试文件与原因（"#4720/#4731/#4732 预存失败"，"44 files / 690 tests"）——排除项有编号、有解释。
- `check-deps`（pr.yml:136 附近）：按变更路径门控——只有动了 pyproject/setup.py/uv.lock/src CMake/third_party/crates/_build.yml 才触发 `_build.yml`；动了 cuVS 相关路径才跑 `_test_lite`；动了 langchain 才跑 langchain 测试；动了 openclaw 才跑 openclaw。这是显式的路径门控（path-filtered CI）设计。
- `langchain-tests`（pr.yml:216）是该 workflow 里唯一运行 `ruff format --check` / `ruff check` / `mypy` 的地方，但只针对 `integrations/langchain` 等路径（pr.yml:244–259）。

【硬事实·关键缺口】**主 Python 包（openviking/openviking_cli）的单测主体在 CI 中没有入口**（⚠️ 原文写“从未运行”，假全称：`pr.yml` 的 `langchain-tests` job 会跑 `tests/unit/test_langchain*.py` 7 个文件、160 个 test，但条件触发）：
- 全部 workflow 中出现 `pytest` 的只有：`_test_lite.yml`（仅 4 个 cuVS 测试文件，_test_lite.yml:86–90）、`api_test.yml`（tests/api_test 与 tests/cli 的集成测试，api_test.yml:455–550，定时+PR 触发）、`oc2ov_test.yml`（tests/oc2ov_test P0）、`api_test_effect.yml`、`pr.yml`（langchain）。
- `_test_full.yml`（82 行）名为 "13. _Test Suite (Full)"，内容却只有：装依赖（含 `--extra test`）、`cargo check -p ragfs-python`、`uv run python setup.py build_ext --inplace`（_test_full.yml:79–82），**没有任何 pytest/lint 步骤**；且全仓库没有任何 workflow 调用它（grep `uses: ./.github/workflows/` 只有 _codeql/_docs/_docs-deploy/_build/_test_lite 五个被引用）。它是个孤儿 workflow。
- 主包的 ruff/mypy 同样无 CI 入口（ruff/mypy 在 workflows 中只出现在 pr.yml:244–259 的 langchain job）。
- Rust 层（crates/，含 ov_cli、ragfs、ragfs-python）：`rust-cli.yml` 与 `_build.yml` 只做 `cargo build/check`，无 `cargo test`、无 clippy、无 rustfmt（对全 workflows grep `clippy|cargo fmt` 零命中）。
- C++ 原生层（src/，setup.py build_ext）：CI 只编译不测；tests/engine/ 下有 C++ 测试（test_common.cpp、test_index_engine.cpp、CMakeLists.txt）但无任何 workflow 编译运行它们。
- CodeQL 扫 python+cpp（_codeql.yml:19），不含 Rust。

【解释】这是一个"分层 CI"策略：PR 门禁集中在插件/示例（JS 层）与可复现构建上，主包质量靠 scheduled 的 API 集成测试（api_test.yml 每日 4 次）+ CodeQL + 贡献者本地自查兜底。对"给上面的 coding agent 用"的项目而言，PR 上连主包单测都不跑是明显纪律缺口：AI 批量提交时最需要机器门禁而非自觉。`_test_full.yml` 名不副实（名为 Full Test 实为 Full Build）且无人调用，是被"去测试化"或迁移中途的残留——两种解读都指向 CI 曾有回归。

### A2. CONTRIBUTING.md（中/日/英三份）

【硬事实】三份文件（CONTRIBUTING.md 11KB / CN 9.9KB / JA 14KB），`## ` 一级小节数量 8=8=8，结构对齐；文首有互链（CONTRIBUTING.md:3）。

【硬事实】内容要点（行号以英文版为准）：
- 明确的价值观条款："smallest complete change"、反对投机性抽象（CONTRIBUTING.md:9–24）。
- PR 审查优先级与行数挂钩：≤100 行更快、≤200 行优先（:35–36），且声明这是优先级不是硬限制（:38）。
- 设计门槛清单：动公共 REST/SDK/CLI/MCP/配置语义、持久化 schema、任务所有权、检索语义等必须先开 issue/discussion（:47–56）。
- **维护者领域表**：按 Domain/Area/路径/活跃 maintainer 列出 11 行路由表，含时间范围"June 24 through August 24, 2026"（:78）。
- 开发环境：Python 3.10+ / Rust 1.91.1+ / Go 1.22+（仅 sdk/go）/ C++17（GCC9+/Clang11+）/ CMake 3.15+（:104–108），与 Makefile 的版本检查一致（Makefile:12–17 MIN_PYTHON_VERSION=3.10、MIN_RUST_VERSION=1.91.1 等）。
- 代码风格：Ruff + mypy，行宽 100（:175–184）；测试哲学非常特别：**"Do not add a new unit test or test file by default"**，要求验证最小公共契约、禁止测私有 helper/mock 调用顺序（:195–204），临时脚本放 `test_scripts/`。
- Commit 约定：Conventional Commits（:224–230），给出示例格式。
- AI 协作条款：PR 模板有 **Human Involvement** 必填字段（PULL_REQUEST_TEMPLATE.md:5–8，二选一：人类参与循环 / 完全由 AI 生成无人类参与）；CONTRIBUTING.md:243 要求如实标注，作者对 AI 辅助的变更负解释责任。
- 要求 PR 描述给出"验证过的确切命令"，"Report skipped checks and the concrete reason; do not claim tests that were not run"（:249 附近）。

【硬事实】**无 DCO/CLA**：对 CONTRIBUTING*.md 与 .github/（除 workflows）grep `DCO|Signed-off|CLA` 零命中；PR 模板也没有 sign-off 要求。

【解释】这份 CONTRIBUTING 的质量明显高于常见开源项目：有量化的审查优先级、有设计边界门槛、有维护者路由表、有针对 AI 时代贡献的 Human Involvement 制度。测试哲学（默认不加新单测、契约测试优先）与 A1 的 CI 缺口自洽——项目有意识地选择了"少而准的测试"，但这使主包质量更依赖 review 而非机器门禁。缺 DCO/CLA 对 Apache 式治理是常见简化，AGPL-3.0 项目（pyproject.toml:20）不签 CLA 也说得通，但属于需要指出的空白。

### A3. scripts/ 目录与守卫脚本

【硬事实】根 `scripts/` 目录只有一个子目录 `maintenance/vikingdb_content_backfill/`（backfill_vikingdb_content.py + README.md）——**没有 monorepo 式的 check 链脚本**。

【硬事实】守卫逻辑分散在别处：
- 文档一致性检查存在：`docs/scripts/check-api-reference.mjs`，从 `openviking/server/routers` 提取路由，与 docs/{zh,en}/api/*.md 的端点文档做双向比对（文件头 1–20 行可读出 routerDir 与 locales 逻辑），在 CI 中以 `npm run check:api` 执行（_docs.yml:36–38，工作目录 docs）。同时还有 `npm run test:theme` 测试文档主题（_docs.yml:33–35）。
- 生成代码守卫：`.gitattributes` 把 7 组 `examples/*/scripts/shared/*.mjs` 与 `agent-plugins/servers/shared/*.mjs` 标记为 linguist-generated，注明由 `examples/memory-plugin-shared/sync.mjs` 生成，并显式豁免一个文件（"Pi owns this module"）。
- 安装脚本语法守卫：pr.yml 的 `bash -n` 检查。
- `.pr_agent.toml`（17KB）是 AI 代码审查的守卫配置：注释说明规则来源是真实 bug 历史（PR #505/#728/#749/#740/#745）+ CI 管线，含针对 async 阻塞调用（commit() → commit_async()）的 BLOCKING 级审查指令（:303–307）。

【解释】项目没有把"守卫"集中成一个 check 脚本（对比 uv/pandas 等 monorepo 惯例），而是把 API 文档一致性做成了 CI 硬门禁（这是文档纪律上的亮点），把代码模式守卫外包给了 PR-Agent 的 AI 审查。守卫分散意味着本地很难一条命令复现 CI。

### A4. 测试基建

【硬事实】tests/ 目录组织（tests/README.md:5–16 有目录说明）：**31 个子目录**（`ls -d tests/*/ | wc -l`；`v0.4.19` 时为 29）+ 根级 `test_*.py`；**共 730 个测试文件**（728 个 `test_*.py` + 2 个 `*_test.py`，两口径需分开报）。分布（`v0.5.0` 实测，仅列前几名）：unit/ 143、api_test/ 118、server/ 71、storage/ 61、session/ 52、parse/ 39、misc/ 31、vectordb/ 26、integration/ 22 等。⚠️ 本句原列 unit/ 129、api_test/ 120、server/ 61、session/ 48、storage/ 47、parse/ 36、misc/ 31、vectordb/ 21、integration/ 21——**全是 `v0.4.19` 的分布**，且九项之和 514 远小于当时的 655，说明原文那个“等”字掩盖了漏项。**分项与总数不同源时，必须两边都标版本**。
- tests/README.md 声明的目录（client/server/session/vectordb/misc/engine/integration）与实际 31 个子目录明显不符——README 只列了 7 个，缺 unit/api_test/parse/storage 等 20+ 个（tests/README.md:7–16）。【解释】测试 README 滞后于测试目录扩张，属文档腐化。
- **没有 conformance 专项目录**，但有契约式测试：tests/metrics/collectors/test_collector_contracts.py、tests/prompts/test_retrieval_intent_prompt_contract.py。
- 跳过测试纪律总体良好：19 处 `pytest.mark.skipif(..., reason=...)` 条件跳过（如 tests/misc/test_extract_zip.py:108 "Windows-specific"、tests/agfs/test_git_binding_s3.py:84 依赖外部 S3、tests/integration/conftest.py:36–67 按 API key/Vault/KMS 门控）；但另有 3 处无条件裸 `pytest.mark.skip(reason=...)`（tests/storage/test_viking_fs_git.py:49、tests/cli/test_cli_system.py:37、tests/cli/conftest.py:358）——2026-09-13 修正：此前写"22 处 skip 均为 skipif、无裸 skip"系误计。
- pytest 配置（pyproject.toml:249–258）：testpaths=tests、asyncio_mode=auto、两个 marker（integration、cli_remote）有声明，`norecursedirs = ["api_test","oc2ov_test"]` 把重型集成测试排除出默认收集。
- **矛盾点**：pyproject.toml:256 `addopts = "-v --cov=openviking --cov-report=term-missing"` 强制覆盖率插件；[dependency-groups].dev 只装 pytest>=9.0.2（pyproject.toml:296–298），pytest-cov 在 [project.optional-dependencies].test 里（pytest>=7，:99–103）。即 `uv sync` 后直接 `uv run pytest` 会因缺 pytest-cov 失败，必须 `--extra test`。CONTRIBUTING.md:48 用的是 `uv sync --all-extras` 所以能跑，但这是配置内部的不一致。【硬事实】
- tests/transaction/ 只有 __init__.py + conftest.py，无实际测试文件；tests/engine/ 只有 C++ 测试且 CI 不跑（见 A1）。【硬事实】

【解释】655 个测试文件、跳过必须有 reason、marker 有声明——测试侧的纪律不差；问题在 A1 所述：这些测试大部分只有贡献者本地跑，CI 不兜底。与 CONTRIBUTING "默认不加新单测"的哲学合起来看，是"契约优先、少测试、本地验证"的一贯风格，但对外部贡献者和 AI agent 来说门槛更高（需要自觉）。

### A5. 版本与发布

【硬事实】版本来源：pyproject.toml:13 `dynamic = ["version"]`；:202–207 `[tool.setuptools_scm]` `write_to = "openviking/_version.py"`，`tag_regex = "^v(...)$"`，`git_describe_command = "git describe --dirty --tags --long --match v[0-9]*"`。即主包版本完全由 `vX.Y.Z` git tag 经 setuptools_scm 派生，无手写版本号。
- Rust CLI 版本独立：`_build.yml` 通过 `build_support/versioning.resolve_openviking_version()` 解析后注入（_build.yml Linux job "Resolve OpenViking version for Rust CLI" 步骤）；`rust-cli.yml` 用 `cli@*` tag sed 注入 crates/ov_cli/Cargo.toml（原值 `version = "0.0.0"`）。
- 多 tag 命名空间：RELEASE.md 的表格明确 `vX.Y.Z`（主包）/ `python-sdk@X.Y.Z` / `typescript-sdk@X.Y.Z` / `cli@X.Y.Z` / `YYYY.M.D`（ClawHub）各自的 tag 与 workflow 对应关系，且注明 setuptools_scm 的两套 tag_regex 互不冲突（RELEASE.md "Version and Tag Conventions" 节）。
- 发布流：GitHub Release(published) → `03. Release`（release.yml:47–56 仅对 `v*` tag 生效）→ 复用 `_build.yml` 建 5 平台 wheel+ sdist（含 Linux 下源码编译 CPython、auditwheel repair、对 wheel 做 import smoke test 且校验 filter ABI 符号与 web-studio 产物——_build.yml "Smoke test built wheel" 步骤）→ PyPI trusted publishing（release.yml:97–115, environment pypi + skip-existing）→ Docker 构建校验（release.yml:188–215 等待 build-docker-image run 完成、断言 version tag 与 latest digest 一致）→ TOS 上传（release-tos.yml）。TestPyPI 手动通道有 actor 权限检查（release.yml:59–90，admin/maintain/write）。
- RELEASE.md 是"从 workflow 反推写成的"（自述："It is based on the tracked GitHub Actions workflows..."），与代码逐条对得上：我抽查了 tag 正则（pyproject.toml:205）、cli@ tag 注入（rust-cli.yml "Inject version from tag"）、skip-existing、environment 名——全部一致。
- RELEASE.md 还显式记录了负面事实：VikingBot 不再独立发版、"former First Release to PyPI workflow has been removed"、bot/ 下无 pyproject 不可独立发布（"VikingBot Release Notes" 节）。

【解释】版本/发布是全仓库纪律最强的部分：单一事实来源（tag）、多组件命名空间互斥、构建后 smoke test 校验原生 ABI、发布后 digest 校验、失败恢复路径（_publish.yml）成文，且文档与实现同步度高。这不是摆设文档，是实际执行的发布契约。

### A6. 代码规范与类型标注

【硬事实】lint/类型配置（pyproject.toml）：
- ruff：line-length=100（:259），select E/W/F/I/C/B（:261–268），但 ignore 掉了 E722（裸 except）、B006、B904、C901 等较有价值的规则（:269–279）；exclude third_party。
- mypy：`disallow_untyped_defs = false`、`disallow_incomplete_defs = false`、`check_untyped_defs = true`、`ignore_missing_imports = true`（:235–243）——宽松档位。
- 无 clippy/rustfmt 配置文件（根目录无 rustfmt.toml/clippy.toml；Cargo.toml 无 [workspace.lints]，Cargo.toml 全文 16 行只有 members + release profile）。web-studio 有 eslint9 + prettier（web-studio/package.json:13–15, 86–97，且 lint 排除生成目录）；sdk/typescript 有 tsc --noEmit + vitest + prettier check（sdk/typescript/package.json:20–27）。
- C++ 有 .clang-format（根目录，757B）。

【硬事实】openviking/core 全部 11 个文件的 AST 抽查（函数级统计）：参数注解覆盖率 100%（117 个函数中 no_param_ann=0，仅 uri_validation.py 有 2 个缺参注解的特例计入）；返回注解约 85%（8/117 缺）。抽查目视：building_tree.py:34 `def add_context(self, context: "Context") -> None`、uri_validation.py:23–35 带 `-> frozenset[str]`。

【解释】类型纪律是"核心严、配置松"：core 模块实际写满了类型，但 mypy 配置不强制、CI 不跑，靠自觉维持。ruff 忽略 E722/B904 属于常见但值得注意的放松。

---

## B. 自描述

### B1. 给 AI 的说明文件（AGENTS.md / CLAUDE.md 等）

【硬事实】全仓库（排除 node_modules/.git）`AGENTS.md`、`CLAUDE.md`、`.cursorrules`、`GEMINI.md`、`.clinerules` 均**不存在**。存在的 agent 相关元文件：
- `.claude-plugin/marketplace.json` 与 `.agents/plugins/marketplace.json`：内容为发布 Claude Code memory 插件的 marketplace 清单（source 指向 examples/claude-code-memory-plugin），是分发配置而非给 agent 的仓库说明书。
- `.pr_agent.toml`：给 PR-Agent AI 审查者的高度定制说明（见 A3），等于一份"给 AI 审查者的代码规范"，含真实 bug 案例编号。
- `agent-plugins/skills/*/SKILL.md`（见 B4）：给使用 OpenViking 的 agent 的行为说明书，质量很高。

【解释】项目"对外部 agent 说得很清楚"（SKILL.md、MCP 文档、plugin examples），但"对在自己仓库里干活的 coding agent 什么都没说"：没有 AGENTS.md/CLAUDE.md，意味着 Claude Code/Cursor 等进入本仓库时拿不到任何项目级指引，只能靠 CONTRIBUTING.md（人写的，但也完全可读）与 .pr_agent.toml（只作用于 PR-Agent）。对一个以 "Agent-native" 为卖点的项目，这是自描述上最刺眼的空白。

### B2. docs/ 组织

【硬事实】docs/ 顶层：en/、zh/、design/、plans/、superpowers/、scripts/、images/、index.md、WeChat_article/。文档站为 VitePress（docs/package.json: scripts docs:dev/build、vitepress 1.6.4）。

- **IA 结构**：en 与 zh 完全镜像（about/agent-integrations/api/concepts/configuration/context-compilation/faq/getting-started/guides/migration 十个栏目，两边目录名一一相同）。en 93 个 md，zh 94 个；en 有而 zh 无：0 个；zh 多出 1 个（guides/12-vikingbot-metrics-validation.md）。翻译覆盖度≈100%，甚至 zh 超配。【硬事实】
- **编号漂移**：en/guides/ 出现两个 "11-"（11-grafana-prometheus.md、11-oauth.md）；en/concepts/ 出现两个 "15-"（15-acl.md、15-vikingbot.md）。vikingbot 同时出现在 concepts/15 与 guides/17。【硬事实·小瑕疵】
- **一致性硬门禁**：check-api-reference.mjs 在 CI 校验 API 文档与 server/routers 的一致性（A3）。
- **changelog**：docs/en/about/02-changelog.md 自述"automatically generated from GitHub Releases"，有 Unreleased 节且把 breaking change 写得很具体（Watch API 迁移、session policy 兼容性，:5–20）。
- **版本口径**：README.md:101 / README_CN.md:101 / README_JA.md:101 均写 "OpenViking 0.3.22 has been evaluated..."；而 changelog 最新条目到 v0.4.1（02-changelog.md:148 `compare/v0.3.24...v0.4.1`）。【解释】三语 README 的评测口径统一（都标注 0.3.22、标注评测模型 Doubao 2.0 Pro 与 embedding 版本号），不算虚假，但 README 头条版本落后于 changelog 至少两个 minor 版本，属轻微陈旧。
- 日期体系：changelog v0.3.22=2026-05-29、v0.3.24=2026-06-05（:150,186），CONTRIBUTING 维护者表窗口 2026-06-24~08-24——内部自洽。【未定】该年份与外部真实时间的关系无法从仓库内判断。

### B3. 根 README 抽查

【硬事实】README.md:101–113：声明 OpenViking 0.3.22 在 LoCoMo 与 tau2-bench 评测，给出 alt-text 数字（OpenClaw 24.20%→82.08% 等）与提升区间（token -34.3~91.0%、延迟 -58.45~66.10%、tau2 +6.87pp/+11.87pp），标注了评测所用模型版本，链接 blog 报告与 `./benchmark` 复现脚本。
- 抽查 1（复现脚本存在性）：benchmark/ 有 locomo/（含 openclaw/、claudecode/、hermes/、mem0/、supermemory/ 各 agent 的 import_to_ov.py、judge.py、run_full_eval.sh，benchmark/locomo/README.md 有目录树）、tau2/、longmemeval/、skillsbench/、cuvs/、RAG/ 等——复现脚本确实存在。但 README 引用的具体数字（82.08 等）在 benchmark/ 内 grep 不到，只存在于博客与 README alt-text；benchmark/ 无根 README 汇总入口。【解释】"可复现"成立（脚本+流程在），"数字对得上"无法在仓库内闭环验证。
- 抽查 2（quickstart 命令）：README:117–122 `pip install openviking` → `openviking-server init / doctor / 启动`。核对：`openviking-server` 是 pyproject [project.scripts] 入口（pyproject.toml "openviking-server = openviking_cli.server_bootstrap:main"）；init/doctor 子命令在 openviking_cli/server_bootstrap.py:13,84–88 显式实现。`ov status/add-resource/task status/ls/tree/find/grep` 与 crates/ov_cli/src/main.rs 中的子命令字符串（:2453 "add-resource"|"add-skill"|"find"|"search"|"grep"...、:3095 task status）对得上。quickstart 与源码一致。【硬事实】
- 抽查 3（安装方式口径）：README 提供 pip 与 Docker 两条主路径，SDK 分流到 sdk/python、sdk/go、sdk/typescript 各自 README——sdk 目录确实存在三个子包。【硬事实】

### B4. 给 agent 的自描述：SKILL.md 与 examples/

【硬事实】agent-plugins/skills/openviking-memory/SKILL.md（92 行）质量显著高于平均：
- frontmatter 的 description 写成触发条件式的（"Use at the start of any substantive task... Do not use for casual chat"——正反两向触发条件）。
- 正文明确工具清单（core vs optional），明确 optional 工具"是否存在取决于 server 版本与 hosting mode"，并给出降级路径："Never call a tool that is not registered... If no OpenViking tools are registered at all, continue without memory"。
- 有 URI 兼容性细节：`viking://~` 别名在旧 server 上会报 INVALID_URI，给出替代方案并写明 "Never guess a user ID"。
- 有优先级序：系统/开发者指令 > 当前用户请求 > 当前环境证据 > memory，"prior success never authorizes a destructive action now"。
- persist 节明确了不该存的内容（secrets、transient state、scrollback）。
- 第二个 skill ov-memory-troubleshoot/SKILL.md 45 行。配套 references/optional-tools.md 存在。

【硬事实】examples/ 可运行性抽查：
- examples/quick_start.py 头部 docstring 给出前置命令（openviking-server init、启动 server）再运行脚本（:1–10）；脚本用 SyncHTTPClient，任务轮询处理 failed/cancelled 分支并打印错误。
- examples/basic-usage/ 有 README.md + README_CN.md，列前置条件（Python 3.10+、pip install openviking-sdk、运行中的 server）、模式选择表（HTTP+SDK vs MCP）、到 docs 的相对链接。
- examples/ 根有 ov.conf.example、ovcli.conf.example、workspace-config.example.json 配置样例；但 examples/ 根目录无 README.md 索引（30+ 个示例目录靠各自 README）。

【解释】"给 agent 的说明书"是全仓库最强的自描述资产：SKILL.md 按 agent 行为契约写作（触发条件、降级、禁止项、优先级），明显是认真设计过的。examples 的前置步骤完整度高，未见缺关键步骤的样例。

### B5. 设计文档文化（docs/design/）

【硬事实】docs/design/ 在 `v0.4.19` 有 **21 个 md** 设计/计划文档 + `assets/` 下 5 个图文件（`.png`/`.svg`），共 26 个文件；`v0.5.0` 全部删除。命名可见两种体裁：`*-design.md` 与 `*-plan.md`/`*-rfc.md`（如 l0-l1-okf-sidecars-rfc.md、parser-two-layer-refactor-plan.md）。
- **状态标记不统一**：l0-l1-okf-sidecars-rfc.md:3 有 `Status: Draft`；memory-link-design.md:4 有 `> 状态: Draft`（引用块格式）；local-embedding-llama-cpp-design.md:4 `Status: 已批准进入实现`（中文值）；ov-compile-design.md:5 表格内 `状态 | 历史设计，现行方案见下方说明`（自我宣布过时）。其余约半数（git-version-control-design.md、metric-design.md、resource-ingestion-routing.md、agent-evolution-global-switch-design.md、workspace-config-and-peer-source-rfc.md 等）无状态行。状态字段格式、语言、位置、有无——四种做法并存。
- **与实现同步的迹象**：文档间存在活引用（RFC 引用 `docs/zh/concepts/03-context-layers.md`，该文件存在）；ov-compile-design.md 被标注"历史设计，现行方案见下方说明"并在文内更新，说明有回写机制；usage_reporter 与 ov-compile 在 openviking/ 源码中均有对应实现模块（openviking/usage_reporter/、openviking/storage/content_write.py 等）。cuVS 设计有配套 benchmark 计划（openviking-cuvs-benchmark-plan.md）与 tests/vectordb/test_cuvs_*。【解释】设计文档是活的、与实现有对应关系，但缺统一的 lifecycle 元数据（Status/Date/ADR 编号），无法机器判断哪份是现行设计。

---

## 总评（证据加权）

**开发纪律：中等偏上，但有一个结构性缺口。**
- 强项：发布工程（A5）达到生产级自洽；CONTRIBUTING 有量化审查门槛、设计边界门槛、维护者路由、AI 参与（Human Involvement）制度（A2）；API 文档与代码的一致性有 CI 硬门禁（A3）；测试跳过/marker 有纪律（A4）；三语文档 1:1 镜像（B2）。
- 缺口：**PR 门禁不跑主包单测、不跑主包 ruff/mypy、Rust/C++ 原生层零测试零 lint**（A1）；`_test_full.yml` 名为 Full Test 实为 Build 且无人调用；mypy 宽松配置与 core 实际 100% 类型标注脱节（A6）；无 DCO/CLA（A2）；无 AGENTS.md/CLAUDE.md（B1）；编号跳号 08–11 原因不明。
- 对"上面的 coding agent"而言：这个仓库的 CI 信任模型是"作者自觉 + 维护者 review + AI 审查代理"，而不是机器门禁。当贡献主力是 AI agent 时，这个模型的风险被放大——CONTRIBUTING 对 AI 贡献提了责任要求（:243）却没有配最有效的机器护栏。

**自描述：对使用者/agent 优秀，对仓库内的 agent 缺失。**
- 对使用者：quickstart 与源码逐条对得上（B3）、评测口径标注模型版本、changelog 自动生成且 breaking change 具体化、docs en/zh 完全镜像。
- 对 agent：SKILL.md 是教科书级的 agent 行为契约（B4），MCP/plugin/examples 路径完整可跑。
- 缺失：仓库自身没有 AGENTS.md/CLAUDE.md/.cursorrules；design docs 无统一状态标记；tests/README 落后于实际目录；README 版本口径滞后 changelog 两个 minor。
