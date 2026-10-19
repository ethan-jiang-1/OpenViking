# 答案：OpenWiki 与 OpenViking 不是竞品——一个是"文档保鲜工具"，一个是"上下文数据库"；它们在 Google OKF 这个格式家族里擦肩而过

## 一句话判断

**归属：OpenWiki 由 LangChain 维护；OKF（Open Knowledge Format）规范出自 Google**（GoogleCloudPlatform/knowledge-catalog）。**OpenWiki 与 OpenViking 解决不同层的问题——OpenWiki 让 agent 为代码库写并保鲜文档（git 里的普通 Markdown），OpenViking 让 agent 存取与检索上下文/记忆（server + viking:// + 向量）。两者不冲突、不能互相替代，通过 OKF 有一个真实但松散的接口。OpenViking 无需"支持"它（它不是协议也不是存储），但可以直接把 OpenWiki 产物摄入为资源；且 OpenViking 的 L0/L1 sidecar 本来就自认是 OKF-style 的收窄子集。**

## 一、三个名字，各自是什么

| 名字 | 是什么 | 归属 | 【标注】 |
|---|---|---|---|
| **OKF v0.2**（Open Knowledge Format） | 一个**可移植知识包格式规范**：每页 YAML frontmatter（`type` 必填）+ body；可选 provenance/trust/lifecycle 家族（`generated{by,at}` / `sources` / `verified` / `status` / `stale_after`）；`index.md`/~~`log.md`~~ 保留文档；Markdown 链接表达页面关系 | **Google**（GoogleCloudPlatform/knowledge-catalog） | 【外部事实】[OKF SPEC](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)、[OpenWiki README](https://github.com/langchain-ai/openwiki) |
| **OpenWiki** | 一个 **CLI 工具**：Deep Agents 文档 agent 读代码库（或个人知识源），生成并持续更新 OKF wiki；Grounded Claims 把每条事实绑到 `repo://src/server.ts#L40-L82` 级别的版本化证据，证据变更即知道哪些命题要复核；CI 定时开 docs PR；配 Codex/Claude Code/OpenCode/Cursor 的编码 agent 集成（MCP page-job 生命周期）与可视化 graph | **LangChain** | 【外部事实】同上 |
| **OpenViking 的 OKF-style sidecar** | L0/L1 语义摘要文件的**内部文档格式**：YAML frontmatter（directory / source / generated_by / freshness 四组字段）+ 可见 body | 本仓库 | 【硬事实】`openviking/storage/abstract_overview.py:3,178-231`；~~`docs/design/l0-l1-okf-sidecars-rfc.md:1-12,50-70`~~ **该文件已被 v0.5.0 删除**（`docs/design/` 整目录消失），旧基线锚点仅供溯回，见文末反转记录 |

## 二、"我们支持吗"——分三层回答

**1. 不存在"需要支持"的协议。** OpenWiki 不是存储协议或检索协议——它的产物就是 git 里的普通 Markdown 文件（`openwiki/` 目录），agent 用普通文件读取就能消费。OpenViking 与它没有协议冲突，也没有协议重叠（viking:// 是进程内/服务器寻址，OpenWiki 完全不涉及）。

**2. 格式层：同一家族，但"同源"未证实。** 两边都叫 OKF、都是 "YAML frontmatter + Markdown body"，字段语义也明显呼应（OpenWiki 的 `generated.by` ↔ OpenViking 的 `generated_by.component`；`sources` ↔ `source`；`stale_after` ↔ `freshness`）。**但**：OpenViking 的 RFC（:121）只说自己是 "minimal OKF-style"、比 general OKF wiki pages 收窄，且 RFC 全文没有引用 Google spec（grep 无 knowledge-catalog / GoogleCloudPlatform 链接）。所以诚实的结论是：**两者是同一个格式家族的两个独立实现，显式规范遵循关系【未定】**——要么 OpenViking 独立趋同，要么 RFC 成文时参考过但未落引用。若要正式兼容，需要做一次字段映射（`generated_by→generated`、`source→sources`、`freshness→stale_after`，加 `type` 必填字段），工作量小但**当前没有任何一方宣称兼容**。

**3. 数据层：可以今天就组合使用。** OpenWiki 的 wiki 是普通文件，`ov add-resource ./openwiki/ -w` 即可把整棵 wiki 摄入 OpenViking 成为语义可检索的资源（L0/L1 自动生成，`find "认证流程怎么工作的"` 直接命中 wiki 页）。反过来 OpenWiki 无法替代 OpenViking：它没有 server、没有向量检索、没有记忆生命周期——它的"检索"就是 agent 老老实实读文件。

## 三、逐维对照：它们其实把一条价值链拆成了两半

| 维度 | OpenWiki（LangChain） | OpenViking（volcengine） |
|---|---|---|
| 解决的问题 | **文档保鲜**：代码库的知识文档化且不腐烂 | **上下文供给**：agent 的记忆/资源/技能可存取可检索 |
| 产物形态 | git 里的 plain Markdown（OKF bundle），你拥有 | server 持有的 viking:// 树（AGFS + 向量索引） |
| 知识从哪来 | agent 读代码/连接器（Notion/Gmail/Slack/X/HN）**生成** | ingest 管线 + session→memory **抽取**（LLM 决策合并） |
| agent 怎么消费 | 直接读文件；AGENTS.md/CLAUDE.md 指路 | MCP/API/CLI/SDK + 语义检索（find/search） |
| 新鲜度机制 | **Grounded Claims**：命题绑定版本化证据，证据变更即失效待复核 | freshness 元数据 + 语义刷新重写 sidecar（自底向上冒泡） |
| 检索能力 | 无（graph 可视化是给人看的） | ~~QUICK/THINKING 两级向量检索 + rerank~~ v0.5.0：单遍全局召回 + rerank（THINKING/QUICK 仅表示是否 rerank） |
| 服务器 | 刻意没有（CI job + 本地 CLI） | 刻意必须有（server-first，见 [`_faq/01`](../01_server_first_vs_library_first/answer.md)） |
| 对"原件"的态度 | 证据指针留在 sidecar，原件本来就在 git 里 | **分类型**：文档类默认不保留（入库即转换）；媒体类（视频/音频/小图）默认保留原件，仅大图显式不存（[`00-the-root`](../../_digested/00-the-root.md) 坑 1，2026-09-13 修正口径） |
| 人读还是 agent 读 | 双方都是一等公民（visualizer + agent memory） | agent 一等，人有 Web Studio |

【解释】最有意思的一行是**新鲜度机制**：两边独立地发明了"知识会过期"的答案——OpenWiki 用命题级 claims 绑证据版本，OpenViking 用目录级 freshness 统计（`unsampled_entries`、`pending_child_changes`）。粒度不同（命题 vs 目录），但都承认"摘要会撒谎"这个同一前提。

## 四、谁好？——判据不是"谁更强"，是"你的问题在哪层"

- 要**让代码库文档不腐烂**、团队人机共读、PR 流程审查文档 → OpenWiki（或者：OpenWiki 生成 + git 保管）。
- 要**跨会话/跨 agent 的记忆与上下文检索**（用户偏好、历史决策、技能库语义查找）→ OpenViking。
- **两者组合是合理形态**：OpenWiki 管"代码库说了什么"（git，人审），OpenViking 管"agent 经历过什么、用户是谁"（server，机器检索），再用 `add-resource` 把前者喂给后者。这也正好落在 [`00-the-root`](../../_digested/00-the-root.md) 三类上下文的划分上：OpenWiki 产的是 Resource，OpenViking 独有的能力在 Memory。
- 【解释】如果非要一句竞品判断：OpenWiki 是"知识文档化的 GitOps"，OpenViking 是"上下文的数据库"——数据库不会打败文档工具，正如 PostgreSQL 没有打败 Markdown。

## 事实清单

1. **归属**：OpenWiki = LangChain（`langchain-ai/openwiki`，npm `openwiki`，MIT）；OKF v0.2 规范 = Google（~~`GoogleCloudPlatform/knowledge-catalog/okf/SPEC.md`~~）。
2. **OpenWiki 是什么**：CLI 工具——agent 读代码库/连接器，生成并持续更新 linked Markdown wiki；Grounded Claims 把事实绑到版本化代码证据；CI 定时开 docs PR；有 Codex/Claude Code/OpenCode/Cursor 集成与可视化 graph。无 server、无向量检索。
3. **OKF v0.2 是什么**：文档格式规范——每页 YAML frontmatter（`type` 必填）+ body，可选 `generated{by,at}` / `sources` / `verified` / `status` / `stale_after` 家族；`index.md`/~~`log.md`~~ 保留；Markdown 链接表达页面关系。
4. **OpenViking 侧的 OKF**：L0/L1 sidecar 用 minimal OKF-style Markdown（RFC `docs/design/l0-l1-okf-sidecars-rfc.md:1-12`——**该 RFC 已随 v0.5.0 删除**，此处为旧基线引用），四组字段 directory/source/generated_by/freshness，自述比 general OKF wiki pages 收窄（:121）；RFC 未引用 Google spec，正式兼容关系不存在也未宣称。
5. **组合方式**：`ov add-resource ./openwiki/ -w` 把 OpenWiki 产物摄入为 Resource（静态，非 Memory），即可被 find/search 语义检索。
6. **选型判据**：代码库文档保鲜、人机共读 → OpenWiki；跨会话记忆/上下文检索 → OpenViking；组合使用落在 00-the-root 的 Resource/Memory 划分上。

## 规范领导力快照（2026-09-12 检索，全部【外部事实】）

**OKF 生态响应**（发布约数月内）：

- **血统**：OKF 是 Google 把 Karpathy 的 LLM wiki 模式规范化的产物（第三方报道标题即 "Google Just Turned Karpathy's Wiki Into an Open Format"，[dutchstartup.ai](https://www.dutchstartup.ai/en/tv/google-just-turned-karpathy-s-wiki-into-an-open-format-okf)；中文报道称其为 "AI Agent 知识库的中立标准"，[53ai 2026-06-16](https://www.53ai.com/news/zhishiguanli/2026061641358.html)）。
- **第三方实现已出现**：OKF 校验器 `@jfomhover/okf-validator`（npm）、`pi-okf`（npm）、`@zosmaai/pi-llm-wiki`（npm）、[Polobase/llm-wiki-template](https://github.com/Polobase/llm-wiki-template)（自述带 "OKF conformance linter nothing upstream ships"）、[Albertchamberlain/Awesome-OKF](https://github.com/Albertchamberlain/Awesome-OKF)（plugins/skills/proposals/tools 资源清单）。
- 【解释】规模判断：还只是" validators + 模板 + Awesome 清单"级别的早期生态，谈不上事实标准；但"Karpathy 模式 + Google 背书 + 纯文本文件格式"三者叠加，**进入未来训练语料的路径是通畅的**——格式规范靠"出现在无数仓库的 Markdown 里"进语料，这正是 OKF 的传播形状。

**OpenViking 采用度**：

- **~34.5K stars、GitHub 月榜第 8**（截至 2026-08-31，[七牛云深度解析](https://news.qiniu.com/archives/1788141049000)）；最新 release v0.4.17（2026-08-28）。
- 生态面：Claude Code/Codex/Cursor/OpenClaw/OpenCode 官方集成 + 三语言 SDK + LoCoMo/tau2-bench 公开评测 + 学术侧 VikingMem 论文（arXiv:2605.29640）。
- 【解释】**viking:// 的"进语料"通道与 OKF 不同且正交**：OKF 靠静态文件在仓库里繁殖，viking:// 靠 (a) 产品装机量让集成文档/教程/issue 进语料，(b) **运行时自描述**——MCP 工具描述在运行时教模型，不依赖训练先验（这正是 [`_digested/harness/04-Self-Description/4.2`](../../_digested/harness/04-Self-Description/4.2_docs_for_agents.md) 判断 1「运行时的 agent 自描述是模范级的」）。OKF 需要模型"预先认识"，viking:// 不需要。

**结论（对用户假设的回答）**：

1. **OKF 成为"更好的 knowledge map 标准"的假设成立概率高**：血统、背书、文件格式传播形状三者都占；风险是它目前只管"知识怎么写"，不管"怎么检索"——knowledge map 的导航能力仍要靠文件系统或工具层。
2. **OpenViking 有两种leadership路径，且已有部分在手**：(a) 产品采用度路径——34.5K stars/月榜第 8 的量级足以让 viking:// 语义与 L0/L1/L2 模式进语料，第三方文章已经在把它当通用模式讲解（七牛文即例）；(b) **规范搭车路径——把 L0/L1 sidecar 从 "minimal OKF-style" 升级为 OKF v0.2 兼容**（补 `type`、对齐 `generated/sources/verified` 家族），即可直接吃到 OKF 的训练先验红利：agent 离开 server 也能凭格式先验读懂导出的内容。这条路的成本是一次字段映射 + RFC 更新，是当前最划算的战略动作。
3. 【解释】两条通道不竞争：OKF 拿"格式先验"，viking:// 拿"运行时自描述"——OpenViking 若双通道都占，恰恰是把知识层的开放格式与检索层的私有服务解耦的标准打法（同 GitHub 之于 git：协议开放、实现收租）。

## 状态标注

- 【硬事实】OpenViking 侧全部锚点（RFC/源码，`0f77ab56`）
- 【外部事实】OpenWiki README 行为描述与 OKF spec 链接（2026-09 抓取，未审计源码）
- 【解释】价值链拆分判断、新鲜度机制的类比、组合使用形态、leadership 双通道判断
- 【未定】两格式显式同源性（RFC 无 Google spec 引用）；OKF v0.2 与 RFC 成文的先后关系；knowledge-catalog 仓库 star 数（GitHub 抓取超时，生态规模以可检索到的第三方实现为准）
- 【外部事实】检索日期 2026-09-12；OpenViking 数字（34.5K stars / 月榜第 8 / v0.4.17）转引自七牛云 2026-08-31 核验文，未直接复核 GitHub 页面

---

## 反转记录（2026-10-19，v0.5.0 复核）

- **"两级向量检索"作废**：OpenViking v0.5.0 把检索改为单遍全局召回（`hierarchical_retriever.py:92-256`），但**这不影响本文的对照结论**——OpenWiki/OKF 没有检索能力这一点没变，差距只是从"两级 vs 零"变成"一遍 vs 零"。
- **一个真正的坏消息**：本文的关键一手来源 `docs/design/l0-l1-okf-sidecars-rfc.md`（OKF sidecar 与 OpenViking 存储格式的对照依据）**已被 upstream 在 v0.5.0 删除**——`docs/design/` 整目录消失。搬迁前的分支（`backup/ethan-before-v050`）里还有本地副本，但 upstream 树与当前工作树里都没有了。**这份对照现在只能靠旧分支副本与 `openviking/storage/abstract_overview.py` 的代码互证。**
- 其余结论（OpenWiki 与 OKF 的关系、"我们支持吗"的答案、OKF 是规格而 OpenViking 是实现）不受影响。
