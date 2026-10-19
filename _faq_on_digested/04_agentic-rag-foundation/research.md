# 网络调研原始材料 (raw research notes)

> 主题：OpenViking 的 "directory-aware / agentic RAG" 检索设计的学术基础与已发表对比证据。
> 调研对象：OpenViking（github.com/volcengine/OpenViking，docs.openviking.ai）——把知识库当文件系统（`viking://` URI、目录/资源/记忆/技能），检索管线 = QUICK（平面向量搜索）/ THINKING（目录级 L0/L1 向量检索 + 重排 + 递归下钻 + 分数传播 + 收敛停止）+ LLM IntentAnalyzer（多 TypedQuery 并发）+ 混合稠密/稀疏检索 + 两阶段 BM25 grep。
> 方法：只报告从可抓取的一手来源（arXiv 摘要页/全文 HTML、官方 blog、官方 docs、本地源码）验证过的声明，每条附 URL。抓不到的来源明确标注 "unverified"。
> 原始抓取材料（全文 HTML→txt 转换）保留在 `./_raw/`（vikingmem.html/.txt、directory_aware.html/.txt、vikingrag.html/.txt、crag.html/.txt）。

---

## Section 1: 三篇论文 —— 摘要、核心机制、对比数据

三篇 arXiv ID 全部验证存在，标题/作者与 README Research 段完全一致（本地 `README.md` 第 272–293 行，[README](https://github.com/volcengine/OpenViking)）。docs About 页（[about/01-about-us](https://docs.openviking.ai/en/about/01-about-us)）列的学术合作者中：Sun Yahui（中国人民大学）= VikingRAG 作者之一；Gao Yunjun（浙江大学）= VikingMem 作者之一，与论文署名交叉印证。

### 1.1 VikingMem: A Memory Base Management System for Stateful LLM-based Applications
- **位置**：[arXiv:2605.29640](https://arxiv.org/abs/2605.29640)（v3，2026-05-28 提交 / 2026-06-12 修订）；arXiv 页 Comments 注明 **"Accepted by VLDB26"**（README 说 VLDB 2026 9 月宣讲）。全文：<https://arxiv.org/html/2605.29640v3>
- **摘要（已验证，逐字要点）**：提出 "Memory Base" 数据管理范式，三条原则：从原始信息流**选择性提取高价值记忆**；记忆的**内在状态性与演化**（渐进总结、纠正、时间加权、近期优先）；**可泛化的抽象范式**（教育、推荐、agent memory）。VikingMem 实现于 VikingDB 向量引擎之上，用 event/entity 抽象：event-centric 提取 + entity 由 event 动态更新；用 topic-wise timeline 的时间压缩 + time-weighted recall 渐进产出高层摘要记忆。"VikingMem outperformes baselines by up to 30% in memory retrieval effectiveness while maintaining the low latency essential for interactive applications"（**最高 +30% 记忆检索有效性**）。
- **核心机制（全文验证，[HTML v3](https://arxiv.org/html/2605.29640v3)）**：① 智能分段引擎（两阶段 LLM 策略降噪+语义分段，IMSM）；② schema 驱动的单遍（one-pass）提取（一次 LLM 调用提取多种记忆类型，~节省 (k−1)× 的 token）；③ EUA 实体更新算法（SEARCH/REPLACE patch + 编辑距离，免额外 LLM 调用）；④ TIME_COMPRESS 操作符（topic 时间线 + TTL 惰性合并，旧事件合成摘要后剪枝）；⑤ 检索 = 主路径混合检索（稠密+稀疏 + 时间衰减 + 业务权重，`Sfinal=(1−wtime−wbusi)·Sorigin+wtime·Stime+wbusi·Sbusi`）+ 辅助 keyword graph 路径 + 基于 ColBERT 风格 late-interaction 的多向量重排（量化+token-merge 压缩）。
- **对比（重点）**：
  - **Baselines（8 个）**：Mem0、Mem0-graph、Zep、RAG（8 条消息/块）、Mirix、Full-Context（全部历史直接注入）、OpenClaw（Markdown-first 记忆）、Claude Native Memory。
  - **Benchmarks**：LOCOMO（10 段对话、平均 1000+ 消息/对话）和 LongMemEval_s（500 段长对话、平均约 115,000 token，为 LOCOMO 的 346×）。
  - **Metrics**：LLM-as-a-Judge 分（%）、token 级 F1、p50/p95 检索延迟（秒）。
  - **数字（全文 §5，[HTML v3](https://arxiv.org/html/2605.29640v3)）**：
    - LOCOMO Overall：VikingMem **88.83%（GPT-4o-mini 裁判）/ 90.12%（GPT-4.1-mini）**；第二名的 Mirix **85.38%**（"by up to 30%" 即由此类差距而来）。单项（GPT-4.1-mini 列）：Single-Hop 93.46 / Multi-Hop 85.89 / Open Domain 79.79 / Temporal 88.16。
    - LongMemEval Overall：VikingMem **66.36%（GPT-4o-mini）/ 75.80%（GPT-4o）**，均为第一。
    - 延迟：VikingMem p50 ≈ **0.20–0.25s**；LOCOMO p50 0.20s / p95 0.39s；LongMemEval p95 **0.89s**。对照：Mirix p50 **10.90s**、p95 **25.76s**（且在 24 小时时限内跑不完 LongMemEval）。
    - 存储/保留（LongMemEval，vs Naive RAG）：Naive RAG 需存 100% 原始 token；VikingMem 只保留提取后事件+实体快照，**仅 16.82%**（约 6:1，降 83.18%），且 LLM-Judge 75.80 vs Naive RAG 63.81。
    - One-pass 提取（LOCOMO）：成本 $0.35 → $0.11（3.2× 降）；EUA 再把耗时 12.32s → 7.42s、$0.11 → $0.07。
    - F1（LOCOMO，token 级）：VikingMem **54.98%** > Full-Context 53.03%。
    - 生产声明（论文自述，非独立第三方验证）：相对 naive RAG/raw-log 存储成本最高降 83.2%、P95 检索延迟降 900ms；单租户日增 >10 亿 token。
  - **注意（可信度边界）**：表中带 † 的 baseline 分数来自已发表结果而非本论文复测；24 小时时限导致部分 baseline 结果缺失；基准使用 GPT-4.1-mini/GPT-4o-mini/GPT-4o 系列裁判；时间加权在评测中被关闭（数据以事实性问题为主）。

### 1.2 Directory-Aware Query and Maintenance in Vector Databases
- **位置**：[arXiv:2606.16903](https://arxiv.org/abs/2606.16903)（v1，2026-06-15）。**arXiv 页没有 venue 注释**；"Accepted by ICDE" 仅见于 OpenViking README（本地验证，[README](https://github.com/volcengine/OpenViking)），arXiv 侧 **unverified**。全文：<https://arxiv.org/html/2606.16903v1>
- **摘要（已验证，逐字要点）**：向量库通常把元数据当扁平标量属性，无法表达目录层级（代码仓库/企业文档/agent 记忆常用）。形式化两个核心算子：**DSQ（Directory-Semantic Query，层级作用域检索）** 与 **DSM（Directory-Semantic Maintenance，结构更新）**；评估三种实现：**PE-Online**（查询时路径展开）、**PE-Offline**（摄入时路径展开）、**TrieHI**（基于 Trie 的层级索引）。结论：展开式设计有根本缺陷——PE-Online 递归查询延迟高、两种展开式在结构变更时有不可扩展的写放大；TrieHI 用原生前缀树保存目录拓扑，树遍历做递归检索、拓扑节点操作降低维护成本。在 ByteDance Viking 向量引擎内 benchmark，发布 **WIKI-Dir 和 ARXIV-Dir** 两个大规模数据集；**TrieHI 已集成进 OpenViking**。
- **核心机制（全文验证，[HTML v1](https://arxiv.org/html/2606.16903v1)）**：PE-Online（只存直接路径键、查询时展开后代）/ PE-Offline（摄入时物化祖先成员关系）/ TrieHI（目录=前缀树节点 + 节点内闭包 entry-ID 集合，Roaring bitmap 表示；MOVE=子树重挂 + 祖先聚合更新，MERGE=冲突局部合并、无冲突子树按节点单元转移）。目录语义层独立于 ANN 执行器（PG 图索引 / IVF 分区索引均可挂载）。
- **对比（重点）**：
  - **RQ1–RQ3 在自建数据集上对三种设计互相比较**（这是"目录感知 vs 目录感知"的实现级对比，不是 vs 平面 RAG）；**RQ4 是 OpenViking 端到端 vs 真实检索/记忆 baseline**。
  - **WIKI-Dir**（[数据集仓库链接，论文脚注](https://github.com/KurtPatrickHere/dir-vector-dataset)）：Wikipedia 分类层级，**363,467 个目录、平均深度 11.95**，**1.94M 向量条目**、456 条带目录约束的测试查询，bge-m3 1024 维编码；另生成 1,000 次 MOVE + 1,000 次 MERGE。**ARXIV-Dir**：2.76M 篇 arXiv 摘要，双命名空间（168 个学科目录深 2.19、432 个时间目录深 1.92），mxb-ai-embed-large-v1，1,000 条查询，暴力搜索构造 ground truth。
  - **Metrics**：nDCG@k / Recall@k、端到端查询延迟、directory-only 延迟（把目录谓词解析成候选 entry-ID 集合的耗时，µs）、MOVE/MERGE 墙钟延迟、索引构建时间与体积。
  - **数字（§V，[HTML v1](https://arxiv.org/html/2606.16903v1)）**：
    - **递归 DSQ directory-only 延迟（Table IV，µs）**：WIKI-Dir：PE-Online 平均 **365,000.80 µs（≈365 ms）** vs PE-Offline **235.23** vs TrieHI **273.10**；ARXIV-Dir：PE-Online 1,089.20 vs PE-Offline 0.12 vs TrieHI 0.43。→ "query-time path expansion is the main scalability bottleneck for recursive DSQ"。
    - 非递归 DSQ（Table IV）：WIKI-Dir PE-Online 29.07 vs PE-Offline 1,037.07 vs TrieHI 945.17；ARXIV-Dir 4.35 / 163.91 / 112.49（TrieHI 的代价是集合差运算，但对端到端向量检索占比小）。
    - 索引构建（Table V，WIKI-Dir + PG 图索引）：基线向量索引 1491.27s；三种目录感知变体 1502.21–1515.25s，**增幅 <1.7%**；体积 7,925 MB → 最多 8,326 MB（TrieHI 存储开销最大，换取可复用目录作用域与 tree-local 维护）。
    - **OpenViking 端到端 · LOCOMO 用户记忆 QA（Table VI，LLM-as-judge = doubao-seed-2-0-pro-260215）**：
      - OpenClaw 原生记忆 24.20% / 95.14s / 392,559,404 token → **+OpenViking 82.08%** / 38.8s / 37,423,456
      - Hermes 原生记忆 33.38% / 82.4s / 79,228,398 → **+OpenViking 82.86%** / 27.9s / 52,026,755
      - Claude Code auto-memory 57.21% / 49.1s / 353,306,422 → **+OpenViking 80.32%** / 20.4s / 129,968,899
      - （原生记忆 → OpenViking：准确率 +24.0 ~ +49.5 个百分点；平均查询时间大幅下降；总输入 token 降约 4.3×/1.5×/2.7×）
    - **OpenViking 端到端 · HotpotQA 多跳 KB QA（Table VII）**：
      - Naive RAG（平面单次检索）**62.50%**，1,290 token/QA，0.11s/QA
      - HippoRAG 2 **61.00%**，726 token/QA，**20s/QA**
      - LightRAG **89.00%**，28,443 token/QA，**75s/QA**
      - OpenViking (top-5) **72.75%**，3,154 token/QA，0.22s/QA
      - OpenViking (top-20) **91.00%**，12,533 token/QA，**0.23s/QA**
      - → 目录作用域先于向量排序（DSQ 语义），top-k 增大主要加同作用域内证据而非全库噪声；比图式 RAG 快两个数量级、token 更少、准确率更高。评测配置见 [OpenViking benchmark 仓库](https://github.com/volcengine/OpenViking/tree/main/benchmark)。
  - **注意（可信度边界）**：WIKI-Dir/ARXIV-Dir 是论文自建并发布的数据集；OpenViking 端到端部分由同一团队实现与评测（潜在利益关联）；LOCOMO 数字的裁判模型与 VikingMem 论文不同（doubao-seed-2-0-pro-260215 vs GPT-4o-mini 系列），两篇论文的 LOCOMO 结果**不可直接横向比较**。

### 1.3 VikingRAG: Accurate and Token-efficient Retrieval-augmented Generation over Structured Documents
- **位置**：[arXiv:2609.11390](https://arxiv.org/abs/2609.11390)（v1，2026-09-10，submitted；arXiv 页无 venue 注释）。全文：<https://arxiv.org/html/2609.11390v1>
- **摘要（已验证，逐字要点）**：现有方法利用文档结构但 token 成本高。VikingRAG = 目录感知的语义数据管理系统，紧耦合语义与结构访问，支持 **structural-context-efficient、evidence-gap-driven 多轮检索**；把 agentic 多轮检索轨迹物化为 **experience edges（经验边）** 复用；再引入 **adaptive escalation（自适应升级）**——一轮经验增强检索证据足够就直接作答，否则才启用 agentic 多轮。"Experiments on real datasets show that the base system VikingRAG matches high accuracy of state-of-the-art methods while consuming only **11.6%–51.9% of their tokens**. With retrieval-trace reuse and adaptive escalation, token costs drop to **5.1%–32.5%** while maintaining competitive accuracy and practical document-storage performance."
- **核心机制（全文验证，[HTML v1](https://arxiv.org/html/2609.11390v1)）**：① prompt 解耦、保层级语义存储模型（按需暴露相关目录段，而非 DeepRead 式把整棵目录树塞进 prompt）；② 证据缺口驱动的多轮 agentic 检索（LLM 依据已收集证据决定下一步读哪个目录段；round budget B=15 兜底）；③ experience edges：把历史多轮检索轨迹存成 query-conditioned 边，仅在当前查询与边历史上下文相似（阈值 γ=0.8）时激活，避免盲目边遍历；④ 自适应升级：one-round 非 agentic 检索过 evidence-sufficiency check 就直接作答，否则升级多轮。
- **对比（重点）**：
  - **Baselines（8 个，全部实现官方代码）**：MoDora（结构感知树 + 迭代 LLM 引导搜索）、BookRAG（结构树 + 实体知识图谱）、DeepRead（ReAct 风格 locate-then-read 结构感知 RAG）、KohakuRAG（低层文本单元→高层节段的嵌入传播）、LightRAG（图+向量混合）、HippoRAG-2（embedding 查询匹配 + LLM 三元组过滤 + Personalized PageRank）、SQL-AgenticRAG（LLM SQL agent 检索关系库）、NaiveRAG（Lewis et al. 2020 原始向量 RAG）。
  - **Datasets（6 个真实结构化文档集，Table 2）**：VersionQA（软件文档，34 文档/100 QA/0.45M token）、SyllabusQA（课程大纲，63/4358/0.24M）、QASPER（论文，281/945/1.51M）、HotpotQA（Wikipedia 页，991/100/2.13M）、LegalBench-cuad（合同，462/1000/5.37M）、FinanceBench（财报 PDF，84/150/**8.78M**）。
  - **Metrics**：端到端 RAG 准确率（LLM-as-judge + 专家复核，语义一致性判定）、延迟、**LLM token 消耗**；另报摄入时间/token 与文档存储表现。
  - **数字（§6，[HTML v1](https://arxiv.org/html/2609.11390v1)）**：
    - 头条：VikingRAG 达到 SOTA 准确率且只用其 **11.6%–51.9%** 的 token；+experience edges +adaptive escalation（VikingRAG-E+）降到 **5.1%–32.5%**（"matches the RAG accuracy of state-of-the-art methods while using only 11.6%–51.9% of their tokens … drop to 5.1%–32.5%"）。
    - **Table 3：相对最高/次高准确率 baseline 的 token 占比（gold/silver）**：
      | 数据集 | RAG | RAG-E | RAG-E+ |
      |---|---|---|---|
      | VersionQA | 36.9% / 12.9% | 31.0% / 10.8% | 23.1% / 8.0% |
      | SyllabusQA | 40.3% / 51.9% | 31.2% / 40.2% | 25.2% / 32.5% |
      | QASPER | 48.7% / 34.4% | 39.3% / 27.8% | 31.4% / 22.1% |
      | HotpotQA | 28.1% / 11.6% | 24.8% / 10.2% | 12.3% / 5.1% |
      | LegalBench | 49.8% / 40.1% | 38.6% / 31.1% | 30.7% / 24.8% |
      | FinanceBench | 14.4% / 18.4% | 9.7% / 12.4% | 7.9% / 10.0% |
    - 组件增益：RAG-E 平均只用 RAG 的 **67.3%–88.1%** token、**72.3%–91.5%** 延迟；RAG-E+ 平均只用 RAG-E 的 **49.8%–81.1%** token、**73.1%–89.8%** 延迟，准确率持平。
    - 准确率/延迟关系：DeepRead 常是最准 baseline，但把候选文档完整目录放进 prompt；VikingRAG(-E+) 只访问相关目录段，"substantially faster than DeepRead"（图 3）。
    - 可扩展性：其他系统随文档数增加准确率下降、token/延迟上升（图 6，HotpotQA 991 文档），VikingRAG(-E+) 基本稳定。
    - 摄入限制：24h 预算内 LightRAG、HippoRAG-2 在 FinanceBench 无法完成摄入，BookRAG 仅在 VersionQA/SyllabusQA 完成 → 图式/重方法的大语料可扩展性差。
    - Experience edges：每数据集 12,764–38,540 条；构造耗时仅 1.5–3.7s/历史查询；测试问句与历史问句相似率 26.48%–60%。
    - 默认参数：K=10、chunk 上限 L=1000、round budget B=15、γ=0.8、M=1,000 条历史问句；骨干 LLM = DeepSeek-V4-Pro Preview（火山引擎 API）；换 GPT-5.5 / Seed-2.0 / GLM-4.7 结论一致（图 7）。
    - 证据充分性检查（Table 7）：自家 checker 的 false-NoEscalation（误判"不必升级"）率 3%–14.4%（各数据集），naive prompt 为 8%–29.7%；作者承认 >5% 的误判存在但不等比转成端到端准确率损失。
  - **注意（可信度边界）**：VikingRAG 论文为 "submitted"（arXiv 无评审信息），全部结果由作者团队自报；无第三方复现；插入（摄入）阶段 token 消耗高于 DeepRead/MoDora（为每个向量化对象生成 preview），作者论证这是可接受的一次性成本。

---

## Section 2: 文献定位 —— 这个设计家族叫什么、和谁比

### 2.1 设计家族命名
- 官方自己给的名字（已验证）：blog 称 OpenViking 为 **"The Database Paradigm for Context Engineering" / "context database for AI agents"**（[blog.openviking.ai/post/openviking-context-database](https://blog.openviking.ai/post/openviking-context-database/)）；docs 称检索为 **"intent analysis + hierarchical retrieval + rerank"** 的两/三阶段管线（[docs/concepts/07-retrieval](https://docs.openviking.ai/en/concepts/07-retrieval)）。
- 学术界最接近的家族名：**Agentic RAG**。综述 *Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG*（Singh, Ehtesham, Kumar, Khoei, Vasilakos，[arXiv:2501.09136](https://arxiv.org/abs/2501.09136)，v4 2026-04-01）给出 taxonomy（agent 基数、控制结构、自主性、知识表示），指出 agentic 模式 = reflection / planning / tool use / multi-agent collaboration，正好覆盖 OpenViking 的 IntentAnalyzer（planning/query 分解）+ 多轮检索（reflection/evidence-gap 驱动）+ 目录工具调用（tool use）。该综述是分析性 survey，**不含数值对比实验**（就摘要页而言）。
- RAG 主流综述 *Retrieval-Augmented Generation for Large Language Models: A Survey*（Gao et al.，[arXiv:2312.10997](https://arxiv.org/abs/2312.10997)）把 RAG 分 **Naive / Advanced / Modular** 三范式——OpenViking 管线（查询改写/多查询、hybrid 检索、rerank、模块化意图分析）属于 Modular RAG 的典型结构，再叠加目录层级与 agentic 多轮。

### 2.2 同族关键工作（全部 arXiv 摘要页已验证）
- **Self-RAG**（Asai et al.，[arXiv:2310.11511](https://arxiv.org/abs/2310.11511)）：按需自适应检索 + reflection tokens 自我批判；声称显著超过 ChatGPT 与 retrieval-augmented Llama2-chat（open-domain QA、推理、事实验证；长文生成的事实性与引用准确性）。→ OpenViking IntentAnalyzer/证据充分性检查的"按需检索+自我评估"思想同源。
- **CRAG / Corrective RAG**（Yan, Gu, Zhu, Ling，[arXiv:2401.15884](https://arxiv.org/abs/2401.15884) v3）：轻量检索评估器给检索质量打分 → Correct/Ambiguous/Incorrect 三动作（不相关时转 web search）+ decompose-then-recompose 过滤噪声；plug-and-play 耦合标准 RAG 与 Self-RAG。**带数值（全文 [HTML v3](https://arxiv.org/html/2401.15884v3) 验证）**：以 SelfRAG-LLaMA2-7b 为底座时，CRAG 相对标准 RAG 提升 **+7.0% PopQA、+14.9% FactScore（Biography）、+36.6% PubHealth、+15.4% Arc-Challenge**；以 LLaMA2-hf-7b 为底座时 **+4.4% PopQA、+2.8% FactScore、+10.3% Arc-Challenge**；Self-CRAG 相对 Self-RAG 提升 **+20.0% PopQA、+36.9% FactScore、+4.0% Arc-Challenge**（LLaMA2-hf-7b 底座）/ **+6.9% PopQA、+5.0% FactScore、+2.4% PubHealth**（SelfRAG-LLaMA2-7b 底座）。→ "检索会错，需要纠错/升级动作" 与 VikingRAG 的 adaptive escalation 同构。
- **RAPTOR**（Sarthi, Abdullah, Tuli, Khanna, Goldie, Manning，[arXiv:2401.18059](https://arxiv.org/abs/2401.18059)）：递归聚类+摘要构建摘要树、推理时从树检索（多层抽象）；"by coupling RAPTOR retrieval with the use of GPT-4, we can improve the best performance on the QuALITY benchmark by **20% in absolute accuracy**"。→ OpenViking L0/L1 摘要层级 + 目录递归下钻的"摘要阶梯"思想的直接先例（VikingRAG 里 KohakuRAG 也属于这类 embedding 传播式层级 RAG）。
- **图式层级 RAG**（作为 baseline 出现在两篇论文中，经全文验证）：LightRAG（Guo et al. 2025）、HippoRAG-2（Gutiérrez et al. 2025）——OpenViking 对比显示目录式在延迟/token 上远优于图式。
- **结构感知 RAG**（作为 VikingRAG baseline，经全文验证）：DeepRead（Li et al. 2026，ReAct 式 locate-then-read）、MoDora（Xu et al. 2026，树+LLM 引导搜索）、BookRAG（Wang et al. 2026，结构树+实体 KG）、KohakuRAG（Yeh et al. 2026，embedding 向上传播）。
- **查询规划/分解**：VikingRAG 与 docs 均把 IntentAnalyzer 的多 TypedQuery 生成归入 query planning；Agentic RAG 综述的 planning 模式即此（[arXiv:2501.09136](https://arxiv.org/abs/2501.09136)）。"least-to-most" 式分解的具体论文未单独抓取，不引用其数字（**unverified**）。

### 2.3 带数字的 "层级/agentic vs 平面单次 RAG" 对比（任务要求的关键证据）
1. **Directory-Aware 论文 Table VII（一手，最直接）**：HotpotQA 上目录式 OpenViking top-20 = **91.00%** vs 平面 Naive RAG = **62.50%**（+28.5 个百分点），且 OpenViking 0.23s/QA vs LightRAG 89.00% 但 75s/QA、HippoRAG-2 20s/QA（[arXiv:2606.16903](https://arxiv.org/abs/2606.16903) 全文 Table VII）。
2. **CRAG 论文（一手）**：加纠错/升级机制后相对标准 RAG 在 4 个数据集 +2.8~+36.6 个百分点（[arXiv:2401.15884](https://arxiv.org/abs/2401.15884) 全文 §5）。
3. **RAPTOR 论文（一手）**：递归摘要树检索在 QuALITY 上 +20% 绝对准确率（配 GPT-4）（[arXiv:2401.18059](https://arxiv.org/abs/2401.18059) 摘要）。
4. **VikingMem 论文（一手）**：长对话记忆检索最高 +30% 有效性、存储省 83.18%、P95 亚秒（[arXiv:2605.29640](https://arxiv.org/abs/2605.29640) 摘要/全文）。
5. **Agentic RAG 综述**：给命名与 taxonomy，无数值对比（[arXiv:2501.09136](https://arxiv.org/abs/2501.09136)）。

---

## Section 3: Bottom line —— 证据是否支持 "directory-aware / agentic RAG" 有优势

**结论：有、且集中在三根轴上；但全部证据来自论文作者团队自报，缺独立第三方复现。**

1. **准确率（对平面单次 RAG：是，强证据）**
   - 目录/层级检索 vs 平面 chunk RAG：HotpotQA 91.00% vs 62.50%（[2606.16903](https://arxiv.org/abs/2606.16903) Table VII）；结构/agentic 升级机制 vs 标准 RAG：CRAG +2.8~+36.6 个百分点（[2401.15884](https://arxiv.org/abs/2401.15884)）；递归摘要树 QuALITY +20% 绝对准确率（[2401.18059](https://arxiv.org/abs/2401.18059)）；长对话记忆 vs Full-Context/原生记忆：LOCOMO 88.83–90.12% vs 最强 baseline 85.38%（[2605.29640](https://arxiv.org/abs/2605.29640)）。目录感知在 LOCOMO 上把 OpenClaw/Hermes/Claude Code 原生记忆从 24–57% 提到 80–83%（[2606.16903](https://arxiv.org/abs/2606.16903) Table VI）。
2. **Token 效率（是，证据最独特）**
   - VikingRAG 的核心卖点：达到 SOTA 准确率只用 11.6%–51.9% 的 token，加经验边+自适应升级后 5.1%–32.5%（[2609.11390](https://arxiv.org/abs/2609.11390)）；目录式按需暴露段 vs DeepRead 全目录进 prompt。VikingMem one-pass 提取 3.2× 成本下降（[2605.29640](https://arxiv.org/abs/2605.29640)）。这是该设计相对"全量证据 RAG/长上下文"最可量化的优势。
3. **延迟（是，但要看比较对象）**
   - 目录作用域解析：TrieHI 235–273 µs vs PE-Online 展开 365 ms（[2606.16903](https://arxiv.org/abs/2606.16903) Table IV）；端到端 HotpotQA 0.23s vs 图式 RAG 20–75s；VikingMem p50 ~0.2s / p95 <1s。代价：非递归查询 TrieHI 慢于 PE-Online（约 1ms vs 29µs，目录语义的实现权衡）；VikingRAG 相对 NaiveRAG 多轮检索延迟更高（论文只对比"高准确率基线"，如 DeepRead）。
4. **可扩展性（部分证据）**
   - TrieHI 把结构维护从"子树级路径键重写"降到"子树重挂+祖先聚合更新"（[2606.16903](https://arxiv.org/abs/2606.16903) §V-C）；VikingRAG 在文档数增加时检索表现稳定，而基线普遍退化（[2609.11390](https://arxiv.org/abs/2609.11390) 图 6）；图式方法（LightRAG/HippoRAG-2/BookRAG）在 8.78M-token 语料上 24h 内无法完成摄入。但 WIKI-Dir/ARXIV-Dir 是论文自建数据集，第三方未见。
5. **证据缺口 / 需要注意**
   - 三篇论文全部为 ByteDance/Volcano 团队（及合作高校）自报，存在利益关联；VikingRAG 为 submitted 未评审；Directory-Aware 的 "ICDE accepted" 只在 README 出现，arXiv 页无注释（unverified）；VikingMem 部分 baseline 数字引自别处发表结果；两篇论文的 LOCOMO 数字裁判模型不同不可直接互比；没有任何公开的第三方复现或对 OpenViking 实际部署效果的独立评测。**"agentic RAG 有优势" 的结论目前主要建立在团队自己的基准上。**

---

## Sources（全部 URL，标注 verified / unverified）

### 三篇核心论文（全部 verified，摘要页 + 全文 HTML）
- https://arxiv.org/abs/2605.29640 — VikingMem 摘要页（Comments: "Accepted by VLDB26"）[verified]
- https://arxiv.org/html/2605.29640v3 — VikingMem 全文（§5 实验、Table 1/2/4/6、生产声明）[verified]
- https://arxiv.org/abs/2606.16903 — Directory-Aware 摘要页（无 venue 注释）[verified]
- https://arxiv.org/html/2606.16903v1 — Directory-Aware 全文（Table IV/V/VI/VII、WIKI-Dir/ARXIV-Dir、OpenViking 端到端）[verified]
- https://arxiv.org/abs/2609.11390 — VikingRAG 摘要页（submitted）[verified]
- https://arxiv.org/html/2609.11390v1 — VikingRAG 全文（§6 实验、Table 2/3/4/5/6/7、图 3–7）[verified]

### OpenViking 一手来源（全部 verified）
- https://github.com/volcengine/OpenViking — README "Research" 段（本地 `README.md` 第 272–293 行验证：三篇论文的引用与描述一致）[verified]
- https://blog.openviking.ai/post/openviking-context-database/ — "OpenViking: The Database Paradigm for Context Engineering"（设计思路：filesystem-as-context、L0 摘要、staged reading、token discipline）[verified]
- https://docs.openviking.ai/en/concepts/07-retrieval — 检索机制文档（IntentAnalyzer、HierarchicalRetriever 伪代码、score_propagation_alpha=1.0、MAX_CONVERGENCE_ROUNDS=3、GLOBAL_SEARCH_TOPK=10、THINKING/QUICK 模式）[**已失效** —— 2026-10-19 对 `v0.5.0` 复核：`MAX_CONVERGENCE_ROUNDS`、`score_propagation_alpha`、`GLOBAL_SEARCH_TOPK` 三个符号在全仓 grep **零命中**，已随 v0.5.0 的「两级递归 → 单遍全局召回」改造删除。官方文档那一页描述的是**旧机制**；`IntentAnalyzer`（`openviking/retrieve/intent_analyzer.py`）仍在，但 `HierarchicalRetriever` 的伪代码已不符。保留此条仅为记录当年确实对过源码，**当前不可作为检索机制的引用依据**，请改用 `_digested/core/03-retrieval-global-recall.md`]
- https://docs.openviking.ai/en/about/01-about-us — Team & Org（学术合作者 = 论文作者交叉印证；"context database" 定位）[verified]
- https://github.com/volcengine/OpenViking/tree/main/benchmark — 论文引用的 benchmark 配置仓库（未逐文件抓取）[unverified 内容细节]

### 文献定位（全部 verified，摘要/全文按标注）
- https://arxiv.org/abs/2501.09136 — Agentic RAG 综述（Singh et al.，v4 2026）[verified 摘要页]
- https://arxiv.org/abs/2312.10997 — RAG 综述（Gao et al.，Naive/Advanced/Modular RAG）[verified 摘要页]
- https://arxiv.org/abs/2310.11511 — Self-RAG（Asai et al. 2023）[verified 摘要页]
- https://arxiv.org/abs/2401.15884 — CRAG（Yan et al. 2024）[verified 摘要页]
- https://arxiv.org/html/2401.15884v3 — CRAG 全文（§5 数值：+7.0% PopQA 等）[verified]
- https://arxiv.org/abs/2401.18059 — RAPTOR（Sarthi et al. 2024，QuALITY +20%）[verified 摘要页]
- https://github.com/KurtPatrickHere/dir-vector-dataset — WIKI-Dir/ARXIV-Dir 数据集仓库（论文脚注给出；未抓取，内容以论文描述为准）[unverified]
- DeepRead / MoDora / BookRAG / KohakuRAG / LightRAG / HippoRAG-2 / SQL-AgenticRAG 等 baseline 论文——仅在 VikingRAG/Directory-Aware 全文中作为引用出现并验证其存在性描述，未逐一抓取原文 [unverified 单篇原文]
- "least-to-most" 等查询分解原始论文——未抓取 [unverified]
