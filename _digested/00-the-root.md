# 00 · 根本：OpenViking 是一个关于"上下文如何组织"的判断

> 这是 `_digested/` 的第一篇，也是其余所有篇目的锚。基线 `v0.5.0`（2026-10-19 同步；建档基线为 `0f77ab56`）；品类判断的官方陈述来自设计博客（blog.openviking.ai/post/openviking-context-database/，2026-03-10 发布 / 05-14 更新）与 `docs/en/concepts/01-architecture.md`。

## 先给结论

OpenViking 的根本不是"一个带 RAG 的存储"，而是一个**品类主张**：上下文工程应该被当成**数据库问题**来解——把 context 当受管数据：可摄入、可组织、可索引、可摘要、可推荐、可记忆、可更新、有生命周期。围绕这个主张，项目做了一个**核心组织判断**（四种组织形式的组合而非单选），把它落成**三个第一性机制**（viking:// 统一寻址、L0/L1/L2 渐进加载、session→memory 生命周期），并划了一条**克制的产品边界**（官方公式里它只认领"完整信息组织"）。

## 判断链：从诊断到主张

**诊断**：prompt、RAG、web search、tools/MCP、skills、memory 六种上下文 primitive 是同一问题的六个侧面，共同瓶颈是**信息组织**——如果人类还要反复把背景信息粘贴进模型，自动化收益就被信息编排吃掉。

**主张**：数据库范式。原话（博客）："treats context as data for agents: something that can be ingested, organized, indexed, summarized, recommended, remembered, and continuously updated."

**边界一句话**（【外部·未复核】博客 product boundary，非仓库内文本）：

> Vector search answers **what is semantically close**. File systems answer **where something lives**. A context database answers **how an agent should use the material**.

> ⚠️ **来源说明**：这三句在 `docs/`、`README.md` 与源码里**零命中**（`grep -rn -i "where something lives"` 等均为 0）。它们只可能出自设计博客（`blog.openviking.ai`），而该站在本机不可达，**无法离线核对原文与措辞**。因此这里标【外部·未复核】而不是"官方原话"——如果把博客当成一手来源，请自己在有网环境打开确认，或改引 `docs/en/concepts/01-architecture.md` 里可核对的表述。

读任何一篇机制文档前先记住这句：OpenViking 自我定位的第三句——"agent 应该怎么用这些材料"——是它的差异化承诺。

## 核心组织判断：四种形式，一个组合

博客给出了组织形式的四选一分析，OpenViking 的答案是**组合**而非单选：

| 组织形式 | 承担的角色 | 在源码里的落点 |
|---|---|---|
| **向量** | 语义匹配的**主入口**（不对用户要求预建模） | 向量索引是 find/search 的第一跳（[`core/03`](core/03-retrieval-global-recall.md)） |
| **文件系统** | agent 可导航的**结构**（层级、遍历、agent 已懂的接口） | `viking://` + `ls/tree/read` 操作面（[`core/01`](core/01-viking-uri-and-vfs.md)） |
| **表（标量/schema）** | 治理与过滤（owner/type/ACL/时间/来源） | URI 路径段决定内容类型 + `storage/acl.py`（[`core/01`](core/01-viking-uri-and-vfs.md)） |
| **图** | 关系解释——**刻意弱化**，避免建模成本 | link 机制存在但浅（`memory_updater.py:104` `write_stored_links`），无图建模入口 |

**为什么这个组合成立**：agent 的阅读模式是"先判断相关、再导航结构、最后按需取全文"——向量回答第一跳，文件系统承载第二跳，L0/L1/L2 让第三跳可控。四形态各管一段，组合即产品。

## 三个第一性机制（判断的落地）

1. **`viking://` 统一寻址 + 目录即数据记录**——一切上下文（文档/记忆/技能）都是文件系统里的节点，目录本身带 L0/L1 摘要和向量。机制见 [`core/01`](core/01-viking-uri-and-vfs.md)。
2. **L0/L1/L2 渐进加载**——token 纪律的物理化：每层是独立的向量记录，检索天然分层，"先摘要后全文"是加载契约。机制见 [`core/02`](core/02-context-layers.md)。
3. **session→memory 生命周期**——经验从对话流变成可检索资产的管道；决策主体是 LLM（identity 才可合并），代码只守边界。机制见 [`core/04`](core/04-session-to-memory.md)。

## 三类上下文：生命周期不对称

官方原话（`docs/en/concepts/02-context-types.md:3`）："resources provide reference material, memories retain information from interactions, and skills describe how to carry out tasks"——**注意：这里只按"角色"三分，没有说它们映射人类认知**。~~旧文本曾在此引"人类认知模式的简化映射"作为官方自述，该句子在 `docs/` 与源码中零命中，已撤回~~。下面是【解释】，不是官方说法：

| 类型 | 是什么 | 驱动者 | 生命周期 |
|---|---|---|---|
| **Resource** | 外部知识（文档/代码/论文） | 用户添加 | 静态，用户改 |
| **Memory** | agent 的认知（九类：profile/preferences/entities/events/identity/soul/cases/trajectories/experiences） | **agent 提取记录** | 动态，持续更新 |
| **Skill** | 声明式能力配置（SKILL.md） | 用户或系统 | 静态 |

不对称即语义：**Resource 是世界的知识，Memory 是对特定用户的认知，Skill 是做事的方法**。三者共享同一套 viking:// 机制但写入路径、生命周期、可写边界完全不同（MCP `write` 不能写 skill——skill 有专门的 `add_skill` 工具，[`integration/01`](integration/01-start-here.md) 误解点 3）。

## 出身：VikingDB 血统

不是 blank page——博客明说 it "grows out of VikingDB's experience"：2019-2025 大规模向量检索 → 2021-2024 表/标量/稀疏检索 → 2023-2024 图探索 → 2024-2025 文件系统语义。**OpenViking 是这条演进线的下一站**：把四种已验证的组织形式组合成 agent 可操作的数据接口。这也解释了为什么向量是主入口（VikingDB 的本行）而文件系统语义是最新的加法。

## 官方公式与自我定位（克制的部分）

> Context engineering = 可靠推理约束 + 完整信息组织 + 有效上下文推荐 + 全生命周期记忆 + 可追溯自进化

博客明确 OpenViking 的位置：**主要提供"完整信息组织"，作为"上下文推荐"与"全生命周期记忆"的基础设施**。推理约束（prompt/rules）不是它的领地——这解释了为什么 skill 是"声明式配置文件"而不是执行引擎，也解释了为什么它对宿主 compaction 的接管只发生在少数集成里（[`integration/01`](integration/01-start-here.md) 的 pi/openclaw 行）。

## 诚实的坑（评价任何集成方案前先读这段）

1. **原件保不保留是"分类型"的——别按"一律不保留"理解**。博客边界表原话："Original files — **Not retained by default**; still being refined"，这是官方主张；但代码实态**按内容类型分裂**（2026-09-13 复核修正：此前版本写成"没有原样归档通道"，系误判）：**文档类**（如 PDF）确实入库即转换、源文件不归档（`parse/parsers/pdf.py` 只落 markdown + 提取图片）；**媒体类默认保留原件**——video/audio 的 `parse()` docstring 原话是 "only copy original file and extract basic metadata"（`parse/parsers/media/video.py:60`、`audio.py:66`），实际写入 `await writer.write_bytes(f"{root_dir_name}/{original_filename}", ...)`（`video.py:123`、`audio.py:130`，`writer` 是 `openviking/parse/output.py:192` 的 `write_bytes`）；小图同样存原始字节（`image.py:257`），仅大图显式不存（`image.py:202` 原话 "The original file is intentionally NOT saved"）。

> ⚠️ **这一格的锚点此前全错**（2026-10-19 修正）：原文写 `Save original ... with original filename`（`video.py:98`/`audio.py:104`）——**"Save original" 这个字符串在源码里不存在**；写的是 `write_file_bytes` 且锚到 `storage/viking_fs/_ops.py:1719`——`:1719` 实际是列表循环里的 `modTime`/RFC-3339 解析，与写入无关；`image.py:246`/`:190` 也各偏 11/12 行。**结论（媒体保留原件、大图不存）是对的，但五处引用没有一处可用**——这正是"结论对所以没人查引用"的典型样本。AGFS 本身有原样字节通道，"不保留"是解析器策略而非存储层限制。对合规/审计/精确引用场景：**逐内容类型确认**，不要引用一概而论的口径。
2. **server-first 的部署重量**。没有嵌入式用法，最小试用也要跑起 Python+Rust+C++ 三层（[`integration/01`](integration/01-start-here.md)）。
3. **检索的"聪明"有前提**：v0.5.0 起检索**不再有目录递归**——两种模式都是「一次全局向量召回」，差别只在 THINKING 会对候选做一遍 rerank（[`core/03`](core/03-retrieval-global-recall.md)）。所以"聪明"= 配了 rerank 模型，没配就是一次扁平向量检索。热度加权与父级分数传播已随 v0.5.0 删除。

## 相关篇目（按根本问题导航）

- 上下文怎么被组织？→ [`core/01`](core/01-viking-uri-and-vfs.md)（寻址+结构）、[`core/02`](core/02-context-layers.md)（分层加载）
- 上下文怎么进出？→ [`core/03`](core/03-retrieval-global-recall.md)（取）、[`integration/01`](integration/01-start-here.md)（外部接入面）
- 上下文怎么"活"？→ [`core/04`](core/04-session-to-memory.md)（记忆生命周期）
- 这个判断实现得成不成立？→ [`architecture/01`](architecture/01-three-languages.md)（三语言实现）、[`harness/`](harness/README.md)（评价层）
- 跟别的比呢？→ [`_faq_on_digested/01`](../_faq_on_digested/01_server_first_vs_library_first/question.md)（vs pi-mono）
