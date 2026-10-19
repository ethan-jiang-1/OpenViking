# 答案：它像 Agentic RAG，但根子是"目录感知的结构化检索"——官方根基论文确有三篇且全部带对比实验；最独特卖点是 token 效率（SOTA 准确率只用其 5.1%–51.9% 的 token）

## 一句话判断

**OpenViking 的检索不是业界常见的"Agent 自由循环调检索工具"式 Agentic RAG，而是"单次 LLM 查询规划 + 确定性目录递归算法"的组合**（⚠️ **v0.5.0 起后半句已不成立**：递归算法被删除，现为"单次 LLM 规划 + 单遍确定性全局召回"。本文结论方向不变，但论证少了一条腿——务必连读文末「反转记录」）：LLM 只在最前面做一次意图分析（拆成 0-5 条带类型的 TypedQuery，temperature=0），之后全部是确定性的层级检索（目录级 L0/L1 向量找入口 → rerank → 目录内递归探索 + 分数传播 + 收敛判停）。"怪异感"的来源是：**它把 RAG 建立在文件系统/目录结构之上（目录是一等公民、向量只是入口），而不是建立在文档片段平铺之上**。而且"它背后确实有 paper、paper 里确实有对比"——README Research 区引的三篇论文（VikingMem / Directory-Aware / VikingRAG）**经网络核验全部真实存在**（arXiv 摘要页 + 全文均抓取成功），其中 VikingRAG 的核心实验就是 token 效率对比（达到 SOTA 准确率只用其 11.6%–51.9% 的 token，加经验边复用与自适应升级后降到 5.1%–32.5%），Directory-Aware 论文则直接包含"在 OpenViking 内做端到端评测"的章节（HotpotQA 上目录式检索 91.00% vs 平面 Naive RAG 62.50%）。

> **一句话给用户**：你猜对了，OpenViking 是"agentic 味的 RAG"，但它归的是 **agentic RAG 家族里的"结构感知/目录感知"分支**（学术综述叫 Agentic RAG，RAG 综述归类为 Modular RAG 加层级）；官方三篇论文都带对比实验，但**全部是火山/字节团队自报，无第三方独立复现**。

## 一、它到底做了什么（本地证据，基线 `0f77ab56`）

### 1.1 检索链路四环节（⚠️ **这是 v0.4.x 的旧管线，不是 v0.5.0 现状**）

> **重要更正**：本节原先标“官方口径”并锚 `docs/en/concepts/07-retrieval.md`。但 `v0.5.0` 的那份官方文档 `:82` 写的是**相反**的话：`retrieval does not navigate directories recursively`。下面这张图和表格描述的是 `v0.4.x`（基线 `0f77ab56`）的管线；**`v0.5.0` 已删除 Directory Recursion、分数传播与收敛停**，现在是单次全局向量检索 + 可选 rerank。保留本图是为了解释论文里 TrieHI 的动机，**不要当成当前实现**。逐条反转见本文件 `## 反转记录`。


```
Query → Intent Analysis → Hierarchical Retrieval → Rerank → Results
              ↓                    ↓                  ↓
         TypedQuery          [已删除] 递归       [已删除] 分数传播
```

| 环节 | 机制 | 锚点 |
|---|---|---|
| **意图分析** | LLM（可单独配 query_planner，缺省回退 VLM）把"压缩摘要+最近 5 条+当前消息"分析成 0-5 条 TypedQuery（context_type=skill/resource/memory、intent、priority 1-5），`asyncio.gather` 并发执行后聚合 | `intent_analyzer.py:38-46,55-136`；prompt `retrieval.intent_analysis` |
| **层级检索** | ~~THINKING：全局向量搜 L0/L1 目录记录（`level=[0,1]`）→ rerank 入口 → 递归搜索（优先队列、分数传播 `final=alpha*score+(1-alpha)*parent_score`、`MAX_PARALLEL_CHILD_SEARCHES=4`、topk 连续 3 轮不变且已满则收敛停）；QUICK：纯扁平一次检索~~ **v0.5.0 已改写为单遍**：一次全局召回 → 去重 → （THINKING 且配了 reranker 时）rerank → 阈值过滤；`THINKING`/`QUICK` 仅表示"要不要 rerank"，**无递归、无分数传播** | 旧 `hierarchical_retriever.py:56-59,220-580`；今 `:92-256`（`:110-113` 模式语义、`:122-123` 默认判定） |
| **Rerank** | ~~THINKING 下对目录入口与递归子节点两处打分~~ **v0.5.0**：单次对召回候选打分；失败回退向量分 | 旧 `:248-257`；今 `:309-324` |
| **上下文装配**（较新） | 单请求装配：token 预算、L1 先加载/L2 按需、跨轮去重 | `retrieve/context_assembler/*` |

### 1.2 "agentic 味"只有一个地方：单次查询规划，不是循环

`retrieval.intent_analysis` prompt（`openviking/prompts/templates/retrieval/intent_analysis.yaml`）暴露真实形态：

- 系统提示自称 "context query planner, responsible for **analyzing task context gaps** and generating queries"——**LLM 的角色是 planner，不是 retriever 控制器**；
- 固定三步：识别任务类型（operational/informational/conversational）→ 检查会话覆盖度（fully/partially/not covered）→ 生成查询（≤5 条、多类型组合）；**JSON 一次性输出、temperature=0.0**；
- 唯一的"自适应"成分是检索**之前**的"已覆盖则跳过"决策；
- 工程上甚至为这步**微调了专用小模型**（`ollama/guoxuter/ov_intent_analysis_sft:v7_q8`，prompt `ov_intent_analysis_sft_v7.yaml`）——把 agentic 最贵的一步做成轻量模块。

### 1.3 "怪异"的真正来源：目录是一等公民，向量只是入口

- L0/L1 是**目录级语义 sidecar**（`.abstract.md` ≤256 字符 / `.overview.md` ≤4000 字符，`docs/en/concepts/03-context-layers.md`），VLM 生成、语义化摘要；向量库第一跳检索的是**目录记录**而非文档片段；
- 检索入口按 context_type 映射根目录（memory→`{user_root}/memories`、resource→`viking://resources`、skill→`{user_root}/skills` + `viking://agent/skills`），支持 `scope_dsl` 过滤器 + `target_uri`——**检索范围本身是结构化的**（v0.5.0：映射逻辑迁到 `openviking/core/retrieval_targets.py:56-83`，skill 还多了 agent 级根）；
- `_digested/README.md:41` 的总结：**"它不是 RAG 库……目录结构是一等公民、向量只是入口"**。

## 二、官方根基：三篇论文全部真实存在（网络核验，`research.md` 为原始材料）

| 论文 | arXiv 状态 | 与代码的对应 |
|---|---|---|
| **VikingMem: A Memory Base Management System for Stateful LLM-based Applications**（[arXiv:2605.29640](https://arxiv.org/abs/2605.29640)，VLDB 2026，arXiv 页注明 "Accepted by VLDB26"） | ✅ 摘要页+全文已验证 | session→memory 管道（事件提取/实体更新/时间压缩），OpenViking 开源子集 |
| **Directory-Aware Query and Maintenance in Vector Databases**（[arXiv:2606.16903](https://arxiv.org/abs/2606.16903)，README 称 ICDE 接收；**arXiv 页无 venue 注释 → "ICDE accepted" 未在 arXiv 侧证实**） | ✅ 摘要页+全文已验证 | TrieHI 的 DSQ 语义 → `scope_dsl`/`target_directories`/L0/L1 目录检索；**代码里无字面 TrieHI 数据结构**，集成的是"目录范围先于向量排序"的语义（论文 IV-C 节即 "Deployment in OpenViking"） |
| **VikingRAG: Accurate and Token-efficient Retrieval-augmented Generation over Structured Documents**（[arXiv:2609.11390](https://arxiv.org/abs/2609.11390)，submitted 未评审） | ✅ 摘要页+全文已验证 | "evidence gap"语言 = intent_analysis prompt 的 "context gaps"；L1→按需 L2 分级加载；QUICK/THINKING 两档 = "按需升级"的朴素形态；**"经验边复用"在代码里只有部分对应**（trajectory 记忆的 `retrieval_anchor` 索引，`openviking/session/train/*`），检索主路径无字面 experience edges |

## 三、论文里的对比实验（你要的"paper 有比较"）

### 3.1 VikingRAG —— token 效率对比（最独特卖点，arXiv:2609.11390 §6）

- **基线 8 个**（全部跑官方代码）：NaiveRAG（Lewis 2020 平面 chunk RAG）、SQL-AgenticRAG、LightRAG、HippoRAG-2（图式）、MoDora、BookRAG、DeepRead（ReAct 式结构感知）、KohakuRAG（层级嵌入传播）。
- **数据集 6 个**：VersionQA / SyllabusQA / QASPER / HotpotQA / LegalBench-cuad / FinanceBench（最大 8.78M token）。
- **头条数字**：VikingRAG 达到 SOTA 准确率，只用其 **11.6%–51.9% 的 token**；加经验边复用 + 自适应升级（VikingRAG-E+）后降到 **5.1%–32.5%**（Table 3，gold/silver = 准确率第 1/第 2 的 baseline）：
  - VersionQA 36.9%/12.9% → E+ 23.1%/8.0%；SyllabusQA 40.3%/51.9% → 25.2%/32.5%；QASPER 48.7%/34.4% → 31.4%/22.1%；HotpotQA 28.1%/11.6% → **12.3%/5.1%**；LegalBench 49.8%/40.1% → 30.7%/24.8%；FinanceBench 14.4%/18.4% → 7.9%/10.0%。
- 组件增益：经验边（E）平均只用 RAG 的 67.3%–88.1% token、72.3%–91.5% 延迟；自适应升级（E+）再只用 E 的 49.8%–81.1% token、73.1%–89.8% 延迟，准确率持平。
- 准确率关系：DeepRead 常是最准 baseline，但把候选文档**完整目录塞进 prompt**；VikingRAG 只访问相关目录段，"substantially faster than DeepRead"。图式方法（LightRAG/HippoRAG-2）在 FinanceBench 上 24h 内无法完成摄入；VikingRAG 在文档数增加时表现稳定而基线普遍退化（图 6）。
- 默认参数 K=10、chunk 上限 L=1000、round budget **B=15**、相似阈值 γ=0.8；骨干 LLM = DeepSeek-V4-Pro Preview，换 GPT-5.5/Seed-2.0/GLM-4.7 结论一致。
- 【外部事实】开源仓库：github.com/rucdatascience/VikingRAG。

### 3.2 Directory-Aware —— TrieHI vs 展开式 + OpenViking 端到端（arXiv:2606.16903 §V）

- **形式化**：DSQ（目录语义查询：递归子树限定/非递归/分支排除）与 DSM（目录语义维护：子树 MOVE/MERGE）；三种实现 **PE-Online**（查询时路径展开）/ **PE-Offline**（摄入时展开）/ **TrieHI**（原生前缀树）。结论：展开式有根本缺陷——递归查询延迟高 + 结构变更写放大。
- **实现级对比**（自建 WIKI-Dir：363,467 目录、平均深 11.95、1.94M 条目；ARXIV-Dir：2.76M 摘要）：递归 DSQ 的 directory-only 解析延迟 WIKI-Dir 上 **PE-Online ≈365ms vs PE-Offline 235µs vs TrieHI 273µs**（ARXIV-Dir：1089µs vs 0.12µs vs 0.43µs）；索引构建开销 **<1.7%**（TrieHI 存储最大但换取可复用作用域 + tree-local 维护）。
- **OpenViking 端到端（Table VI，LLM-as-judge = doubao-seed-2-0-pro-260215）**——LOCOMO 用户记忆 QA：
  - OpenClaw 原生记忆 24.20%/95.14s/392,559,404 token → **+OpenViking 82.08%**/38.8s/37,423,456
  - Hermes 原生 33.38%/82.4s → **+OpenViking 82.86%**/27.9s
  - Claude Code auto-memory 57.21%/49.1s → **+OpenViking 80.32%**/20.4s
- **OpenViking 端到端（Table VII，HotpotQA 多跳）——目录式 vs 平面/图式，最直接的"层级 RAG 有优势"证据**：

| 方法 | 准确率 | Tokens/QA | 延迟 s/QA |
|---|---|---|---|
| Naive RAG（平面单次） | 62.50% | 1,290 | 0.11 |
| HippoRAG 2（图式） | 61.00% | 726 | 20 |
| LightRAG（图式） | 89.00% | 28,443 | 75 |
| **OpenViking top-5** | 72.75% | 3,154 | 0.22 |
| **OpenViking top-20** | **91.00%** | 12,533 | **0.23** |

→ 目录作用域先于向量排序（DSQ 语义）：top-k 增大主要加**同作用域**证据而非全库噪声；比图式 RAG 快两个数量级、token 更少、准确率更高。

### 3.3 VikingMem —— 记忆检索对比（arXiv:2605.29640 §5）

- 8 个 baseline（Mem0/Mem0-graph/Zep/RAG/Mirix/Full-Context/OpenClaw/Claude Native）；LOCOMO Overall **88.83%（GPT-4o-mini 裁判）/ 90.12%（GPT-4.1-mini）** vs 最强 baseline Mirix 85.38%（"up to 30%" 出处）；LongMemEval 66.36%/75.80% 第一。
- 延迟 p50 ≈0.20–0.25s / p95 <1s vs Mirix p50 10.90s/p95 25.76s；存储仅为 Naive RAG 的 **16.82%**；one-pass 提取成本 $0.35→$0.11（3.2×）。

## 四、文献定位：它属于哪条研究线

- **家族名 = Agentic RAG**：综述 *Agentic RAG: A Survey*（Singh et al.，[arXiv:2501.09136](https://arxiv.org/abs/2501.09136)）的 taxonomy 里，reflection / planning / tool use / multi-agent 四个模式正好覆盖 OpenViking 的意图规划（planning）、证据缺口驱动多轮（reflection）、目录工具调用（tool use）——但该综述是分析性的，**无数值对比**。
- **RAG 三范式 = Modular RAG**：Gao et al. 综述（[arXiv:2312.10997](https://arxiv.org/abs/2312.10997)）把 RAG 分 Naive/Advanced/Modular；OpenViking = Modular RAG 的典型结构（查询改写、多查询、hybrid 检索、rerank）+ 目录层级 + agentic 多轮。
- **同族关键工作（arXiv 摘要/全文已验证）**：Self-RAG（[2310.11511](https://arxiv.org/abs/2310.11511)，按需检索+反思）、CRAG（[2401.15884](https://arxiv.org/abs/2401.15884)，检索纠错升级，**带数字**：相对标准 RAG **+2.8~+36.6 个百分点**，与 VikingRAG 的 adaptive escalation 同构）、RAPTOR（[2401.18059](https://arxiv.org/abs/2401.18059)，递归摘要树，QuALITY **+20% 绝对准确率**，是 L0/L1 摘要阶梯的直接先例）。
- **"怪异"的定位结论**：业界 agentic RAG 的默认形态是"agent 循环调检索工具"（如 LlamaIndex/LangGraph 的 Self-RAG/CRAG agent）；OpenViking 换成了**确定性为主的结构算法 + 单次规划**——agentic 家族里的"数据库派"（把检索智能前移到索引与结构里，而不是放到推理循环里），这正是它与众不同的地方，也是它把自己叫 "context database" 而非 "RAG library" 的原因（[官方设计博客](https://blog.openviking.ai/post/openviking-context-database/)）。

## 五、结论：证据支持什么、缺口在哪

1. 【网络核验】**三篇论文真实存在**，标题/作者与 README 完全一致；Directory-Aware 论文里就有 "Deployment in OpenViking" 章节与 OpenViking 端到端评测，VikingRAG 论文的对比就是"结构感知/agentic 多轮 vs 平面/图式 RAG"。
2. 【网络核验】**优势证据成立，集中在三根轴**：准确率（HotpotQA 91.00% vs 平面 62.50%，+28.5 个百分点；LOCOMO 原生记忆 24–57% → 80–83%）、**token 效率（最独特卖点：SOTA 准确率只用其 5.1%–51.9% token）**、延迟（TrieHI 目录解析 273µs vs 展开 365ms；端到端 0.23s vs 图式 20–75s）；可扩展性有部分证据（图式方法在 8.78M-token 语料上 24h 摄不进去）。
3. 【网络核验】**证据缺口**：三篇论文全部为火山/字节团队（+合作高校）自报，利益关联；VikingRAG submitted 未评审；"ICDE accepted" 只在 README、arXiv 页无注释；两篇论文的 LOCOMO 数字裁判模型不同（doubao-seed vs GPT-4o-mini 系）**不可直接互比**；**无任何第三方独立复现**。判断"agentic/目录式 RAG 有优势"目前主要建立在团队自己的基准上——但注意：CRAG（+2.8~+36.6pp）、RAPTOR（+20%）是**第三方独立论文**给出的同方向证据，方向一致性是加分项。
4. 【本地佐证】`benchmark/RAG/`（LoCoMo/SyllabusQA/Qasper/FinanceBench，度量 recall/F1/准确率/**token 用量**/延迟）与论文评测轴一致，说明这套评价口径是团队自己的日常基准。

## 状态标注

- 【硬事实】IntentAnalyzer 单次规划（temperature=0）、L0/L1 目录 sidecar、context_type→根目录映射、scope_dsl——锚点 `openviking/retrieve/*`、`docs/en/concepts/{01,03,07}*.md`，基线 `0f77ab56`
- ~~【硬事实】检索链路四环节、THINKING 递归机制~~——**已随 v0.5.0 撤回**：`v0.5.0` 删除了目录递归/分数传播/收敛停，现在的链路是"单次全局召回 + 可选 rerank"，THINKING 只表示"要不要 rerank"（`hierarchical_retriever.py:122-123`）。详见本文件 `## 反转记录` 与 `docs/en/concepts/07-retrieval.md:82`。
- 【硬事实】README Research 区三篇论文官方表述（`README{,_CN,_JA}.md`，commit `c31e261b` #4924）；`benchmark/RAG/` 数据集与度量轴
- 【外部事实·已验证】三篇论文的 arXiv 位置、摘要、实验数字（VikingRAG Table 3、Directory-Aware Table IV/VI/VII、VikingMem §5）、CRAG/RAPTOR/Self-RAG 定位——全部来自抓取到的 arXiv 原文与官方页面，见 [research.md](research.md) 与 `_raw/` 原始全文
- 【外部事实·未证实】"Directory-Aware 被 ICDE 接收"（arXiv 页无注释）；VikingRAG 的评审状态（submitted）
- ~~【解释】"单次规划 + 确定性递归"的 agentic 变体定位~~（**“递归”这一半已失效**，“单次规划”仍成立）；"数据库派 agentic RAG"的归纳；"怪异感"来源
- 【未定】论文声称的 "experience edges / 检索轨迹复用" 与代码里 trajectory/`retrieval_anchor` 子系统的精确对应程度；两篇论文 LOCOMO 数字因裁判模型不同无法合并解读

---

## 反转记录（2026-10-19，v0.5.0 复核）

**本文的核心论点（"像 Agentic 但其实是单次 LLM 规划 + 确定性目录递归"）在 v0.5.0 变成了"单次 LLM 规划 + 单遍全局召回"**：

- **"确定性"仍成立，而且更强了**：递归算法被删掉之后，检索变成一次向量召回 + 可选 rerank，确定性只增不减。
- **"目录递归"这一半没了**：`hierarchical_retriever.py` 从 672 行降到 381 行，`THINKING`/`QUICK` 退化为"要不要 rerank"的开关。本文与 Agentic RAG 的对照结论（"不是自由循环、而是单次规划"）**方向不变，但用于论证的第二个特征退出了**。
- **L0/L1 的角色变了**：仍是目录级语义 sidecar（VLM 生成、参与 embedding 白名单），但**不再是第一跳检索对象**——它们是召回结果里的 level 维度，不是检索的入口。
- **意图分析（1.2 节）完全有效**：`IntentAnalyzer` 仍在主路径（`_semantic.py:430,481`、`context_assembler/expansion.py:53`），prompt 与 temperature=0 的结论无需修改。

机制现状见 [`_digested/core/03-retrieval-global-recall.md`](../../_digested/core/03-retrieval-global-recall.md)。
