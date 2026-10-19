# 答案：火山是"默认指向"而非"唯一路径"——模型层全宽门、可全离线；BM25 有，但只活在 VikingDB 系后端上

## 一句话判断

**OpenViking 是一套完整的 RAG 栈（dense/sparse/hybrid embedding + ~~两级向量检索~~ 单遍全局召回 + rerank + 意图规划 + BM25 grep），但它不是火山锁死的产品**：模型层全部配置驱动——embedding 13 个 provider、rerank 5 个、VLM 7 个，任意 OpenAI 兼容端点（含自建 llama.cpp/MLX/vLLM）都能接，甚至内置一个**完全离线的本地 GGUF embedding**（bge-small-zh，`llama-cpp-python` 进程内跑）；向量库默认是**本地 C++ 引擎**而非云。真正"火山独占"的只有两块：**sparse/hybrid embedding**（只有 volcengine/vikingdb 两个 provider 产出稀疏向量）和 **BM25 grep**（只有 VikingDB 系后端写了 `content` 全文字段）。所以"完全靠火山"不成立——准确说法是：**火山是全功能路径，非火山路径功能上有明确的天花板**（无稀疏信号、无 BM25、媒体理解走 Ark 风格 API）。

## 一、RAG 组件全景：它"有"哪些技术

| 组件 | 角色 | 配置项 / 锚点 |
|---|---|---|
| **Embedding**（dense / sparse / hybrid 三模式） | 把 L0/L1/L2 内容向量化；图片是多模态 embedding（summary+data-uri） | `ov.conf` → `embedding.{dense,sparse,hybrid}`；`embedding_config.py:168-182` |
| **向量检索模型（v0.5.0 已改写）** | 单遍全局召回 + 可选 rerank；`find` 固定 QUICK，`search` 配了 rerank 才走 THINKING——**两者差别只剩"要不要 rerank"，没有目录递归** | `_digested/core/03-retrieval-global-recall.md`；`hierarchical_retriever.py:110-113,122-123` |
| **Rerank** | search 的精排；不配则 search 退化为纯向量相似度 | `rerank_config.py:13,79`；`docs/en/guides/01-configuration.md:956` |
| **IntentAnalyzer** | search 带 session 上下文时，LLM 把用户查询规划成多路 TypedQuery 并发执行 | `openviking/retrieve/intent_analyzer.py:38-46` |
| **VLM** | L0/L1 目录摘要生成（语义加工） | `vlm` 配置块；`models/vlm/registry.py:10-18` |
| **BM25 grep** | 关键词/正则内容检索；VikingDB 系后端走 BM25 召回 + 本地精确匹配两段式 | `grep` 配置块；`viking_fs/_grep.py:264-403` |
| **混合检索** | dense + sparse 加权（`sparse_weight`） | `storage.vectordb.sparse_weight`（`docs/en/guides/01-configuration.md:1434`） |

## 二、模型层：宽门——13 / 5 / 7 个 provider，可自配甚至全离线

> （此前标题写 "4 个" rerank provider，正文已修正为 **5**，含 `jev`；标题未跟上。）

**【硬事实】embedding 的 provider 是封闭枚举但宽到 13 个**（`embedding_config.py:168-182` `_VALID_PROVIDERS`）：`openai / azure / volcengine / vikingdb / jina / ollama / gemini / voyage / dashscope / minimax / cohere / litellm / local`。其中 `openai` + 自定义 `api_base` 或 `litellm` 桥接 = **任意 OpenAI 兼容端点**（OpenRouter、自建 llama.cpp/MLX/vLLM、任何网关）；`ollama` 直连本地；`local` 是进程内 GGUF。

**【硬事实】开箱默认不是火山**：整个 `embedding` 配置块缺省时，`apply_default_local_dense` 自动填 `{provider: "local", model: "bge-small-zh-v1.5-f16"}`（`embedding_config.py:688-700`）——本地 GGUF，512 维，`llama-cpp-python` 加载，模型文件自动从 HuggingFace 下载（`models/embedder/local_embedders.py:21-46`），`pip install "openviking[local-embed]"` 即可。**只有显式写了一个 dense 块却没写 provider 时**，默认值才是 `volcengine`（`embedding_config.py:69-78`）。这个"配置缺省→本地、写了没指明→火山"的双默认是理解产品取向的关键。

**rerank **5** 个 provider**（`rerank_config.py:13` 的 description、`:96-106` 的校验列表）：`vikingdb / cohere / openai / litellm / jev`——**原文写"4 个"，漏了 `jev`**（Jev/TypeSafe，实现在 `openviking/models/rerank/jev_rerank.py`，还有专属的 `mode in ("noul","choice")` 校验 `:90-93`）。`openai` + `api_base` 可以指向 DashScope（`qwen3-rerank`）或任何 OpenAI 兼容 rerank 服务（含本地冷启动场景，超时可调，配置项见 `docs/en/guides/01-configuration.md:2216`）。不配 rerank 时 search 用纯向量相似度。

**【硬事实】VLM 7 个 provider**（`models/vlm/registry.py:10-18`）：`volcengine / openai / azure / kimi / glm / litellm / openai-codex`——同样是"volcengine 只是其一"。

**【解释】模型层接缝的开放度是全仓最健康的**（`_digested/harness/01-Architecture/1.3_data_seams.md` 的结论）：**端点开放（任意 OpenAI 兼容 base_url 可配）、provider 代码集合封闭**（新增 provider 类需改内核工厂表）。对使用者是宽门，对 contributor 是窄门。

## 三、向量库层：5+1 条路，默认本地 C++ 引擎

**`storage.vectordb.backend` 注册表 6 项**（`vectordb_adapters/factory.py:16-24` `_ADAPTER_REGISTRY`）：`local`（内置 C++ abi3 引擎，文件型）、`cuvs`（NVIDIA GPU 密集检索）、`http`（远程服务）、`volcengine`（火山云 VikingDB）、`vikingdb`（私有化部署）、`opengauss`（openGauss/pgvector 系）。

（**原文此处有三处错**：① 写"注册表 5 项、另有 openGauss"——openGauss **就在同一个 dict 里**，是第 6 项，不是"另有"；② 锚 `factory.py:15-21` 少一行（实为 `:16-24`）；③ openGauss 的文档锚 `docs/en/guides/01-configuration.md:1498` 指向 `directory_marker_mode`，与该主题无关——openGauss 真正的文档表述在 `docs/en/api/06-retrieval.md:421`（"openGauss accepts the forwarded parameters but does not apply time decay"）。）

**默认 `local`**：默认值定义在 `openviking_cli/utils/config/vectordb_config.py:403-411`（`backend: str = Field(default="local")`），`open_viking_config.py:815-816` 再用 `or "local"` 兜底（原文引 `open_viking_config.py:778`，那是 `initialize_openviking_config` 内部，不是默认值定义处）。`_digested/architecture/01-three-languages.md` 记其为"开箱即用的向量索引"。

**四个自由度的排列组合**：embedding provider × rerank provider × vectordb 后端 × grep 引擎互相独立配置——比如"本地 bge embedding + 本地向量库 + 无 rerank"是完全离线的最小可用形态；"OpenAI 兼容 embedding + 本地向量库 + 本地 rerank 服务"是自建形态；"volcengine multimodal embedding + vikingdb rerank + 火山云 VikingDB + BM25 grep"是火山全家桶形态。

## 四、真正"锁"在火山的部分（非火山路径的天花板）

**【硬事实】sparse/hybrid embedding 只有 volcengine/vikingdb**：工厂注册表里稀疏/混合 provider 条目仅 `("volcengine","sparse"/"hybrid")` 与 `("vikingdb","sparse"/"hybrid")`（`embedding_config.py:829/839/867/879`）；文档明示 "OpenAI-compatible, Ollama, and built-in local providers are dense-only"（`docs/en/guides/01-configuration.md:656-658`）。**配了 dense-only embedder 不会自动补 BM25 或稀疏向量**（`:662-664`）——想用混合检索必须上火山系稀疏模型（如 `doubao-embedding-vision-251215` / `doubao-embedding-hybrid`）并把 `sparse_weight > 0`。

**【硬事实】媒体理解（音视频解析）走 Ark 风格 API**：UnderstandingAPI 把 `parser_api.host` 强制拼成 `/api/v3` 路径（`openviking/parse/understanding_api.py:71-73`），即火山方舟端点形态（`_digested/_notes/seams-boundaries-evidence.md:23`）；上传 Ark Files、Responses API 轮询、尽力删除（`docs/en/guides/01-configuration.md:875`）。这是媒体类的专属依赖，文本/图片主链路不受影响。

**【解释】产品血统确实是火山的**：upstream 是 `volcengine/OpenViking`（`_digested/README.md`），官方评测用 Doubao 2.0 Pro + Doubao-embedding（`docs/repository/README_CN.md:113`），`init` 向导把火山作为一等选择——**血统 ≠ 锁死**，但可以解释为什么火山路径总是"最顺、最全"的那条。

## 五、有 BM25 吗？——有，但它是"VikingDB 的服务端全文检索"，不是本地索引

**【硬事实】BM25 只存在于两条 VikingDB 系后端上**：

- 写入侧：`CollectionAdapter.USE_CONTENT_FIELD` 默认 `False`（`vectordb_adapters/base.py:121`），只有 `volcengine_adapter.py:31` 和 `vikingdb_private_adapter.py:26` 置 `True`——**只有这两个后端往向量库写 `content` 全文字段**（截断到 1MB，`docs/en/guides/01-configuration.md:1191`），这是 BM25 召回的数据前提。
- 读取侧：`_grep.py:146-188` `_resolve_grep_engine` 的决策树——`engine: "fs"` 强制本地文件搜索；`"auto"`（默认）要求**后端类型 ∈ {volcengine, vikingdb}** 且 collection 有 `content` FullText 配置，还要看 **`switch_to_remote_threshold`（默认 10000）**：搜索范围内 L2 记录数 < 阈值仍走本地 fs，`0` 才始终用 VikingDB BM25。
- BM25 路径本身是**两段式**（`_grep.py:366-403` `_grep_vikingdb_then_fs`）：① VikingDB `search_by_keywords` 召回候选 URI（召回上限 `min(node_limit*5, 100000)`）→ ② 对候选文件在本地做**正则精确匹配**（BM25 只做粗召回，最终命中靠 regex）。所以 grep 的正确性不依赖 BM25，BM25 是数据量大时的加速/预筛。

**【硬事实】本地/自建路径没有 BM25**：`local_collection.py:734-764` 的 `search_by_keywords` 直接 `NotImplementedError`；local/cuvs/http 后端不写 `content` 字段（`USE_CONTENT_FIELD=False`），grep 自动落回 agfs 原生 grep（Rust）或 VikingFS 正则扫描（含加密文件解密匹配，`_grep.py:225-262`）。**仓库里没有任何本地 BM25 索引实现**（Rust 侧 grep full-text 检索无匹配，grep 结果为空）——想要真正的关键词召回，要么上 VikingDB 系后端，要么把"稀疏信号"交给火山系 sparse embedding（注意：那是稀疏向量，不是 BM25，两套机制）。

**【外部事实】BM25 grep 是 v0.4.6（2026-06-29）才加入的能力**（`docs/zh/about/02-changelog.md:77`，节标题 `:70`）——不是开箱就有，是火山系后端增强项。

## 六、结论：你能配到什么程度（四档递进）

1. **纯离线（无任何云依赖）**：本地 GGUF embedding（bge-small-zh）+ local 向量库 + 无 rerank + grep=fs。代价：search 退化为 QUICK（无 rerank 精排、无 BM25、无稀疏信号）。（v0.5.0 起"无 THINKING 递归"不再是代价——递归已不存在。）
2. **自带模型**：任意 OpenAI 兼容 embedding/rerank（自建 llama.cpp/MLX/vLLM 或任意网关）+ local 向量库。恢复 rerank（即 THINKING），仍无 BM25。
3. **火山全家桶（功能最全）**：volcengine multimodal/sparse/hybrid embedding + vikingdb rerank + 云 VikingDB/私有化 + BM25 grep + Ark 媒体理解。
4. **混合任意组合**：例如"火山 embedding + 本地向量库"、"OpenAI embedding + 火山云 VikingDB"——四自由度互不绑定。

**一句话选型判据**：如果你的数据量需要关键词召回（BM25）或混合检索（dense+sparse），火山系后端是唯一通道；如果只要语义检索 + 精排，模型层完全不需要火山。

## 状态标注

- 【硬事实】provider 枚举与默认值（`openviking_cli/utils/config/embedding_config.py:167-181`、稀疏/混合注册 `:829-893`）、rerank provider、VLM provider（`models/vlm/registry.py:10-18`）、vectordb 注册表（`vectordb_adapters/factory.py:16-23`，**v0.5.0 起 6 项，+opengauss**）与默认 `local`、grep 引擎决策树与两段式（`viking_fs/_grep.py:146-190`、`:264-403`）、`USE_CONTENT_FIELD`（`base.py:121` / `volcengine_adapter.py:31` / `vikingdb_private_adapter.py:26`，opengauss 显式 `False` `:71`）、本地 `search_by_keywords` NotImplementedError（`vectordb/collection/local_collection.py:734-763`）、UnderstandingAPI `/api/v3`、本地 GGUF embedder（`models/embedder/local_embedders.py`）——**锚点基线 `0f77ab56`；2026-10-19 对 `v0.5.0` 复核，结论全部仍成立**。

  ⚠️ **但"行号已重锚"这句话当时是虚的**（2026-10-19 二次复核发现）：正文里 `base.py:116`、`volcengine_adapter.py:26`、`vikingdb_private_adapter.py:21`、`_grep.py:133-170`、`local_collection.py:704-731`、`understanding_api.py:67-69`、`factory.py:15-21`、`embedding_config.py:675-689` 等**十余处仍是旧基线行号**，且 `rerank 4 个 provider`、`注册表 5 项`、`README_CN.md:103` 三处是**内容层面的错**不是漂移。已逐个改正。
  **教训**：状态标注里写"已复核"必须逐条对着代码签，否则它会变成下一轮复核的**免检通行证**——这一条比任何单个行号错都危险。
- 【外部事实】v0.4.6 引入 "VikingDB BM25 grep"（`docs/zh/about/02-changelog.md:77`，条目原文 "VikingDB BM25 grep 与 Studio 指标"；节标题 `:70` 为 v0.4.6 2026-06-29）
- 【解释】"双默认"（配置缺省→本地 / 写了没指明→火山）的取向判断；四档配置路径的归纳；"BM25 只做粗召回、regex 保证正确性"的角色划分
- 【未定】litellm rerank 客户端（`models/rerank/litellm_rerank.py`）在配置文档表格中未列出、但 `rerank_config.py:13` 已收录——文档与代码口径的细微出入未进一步追查

---

## 反转记录（2026-10-19，v0.5.0 复核）

**本文的核心判断——"火山是默认指向而非唯一路径、模型层全宽门、BM25 只在 VikingDB 系后端"——在 v0.5.0 全部仍然成立**，且逐条复核通过：

| 本文判断 | v0.5.0 复核结果 |
|---|---|
| embedding 13 个 provider，任意 OpenAI 兼容端点可配 | ✅ 未变（`_VALID_PROVIDERS` 仍是 13 项） |
| VLM 7 个 provider | ✅ 未变 |
| rerank 可自建 | ✅ 未变 |
| sparse/hybrid 只有 volcengine + vikingdb | ✅ 未变（`:829-893` 仍只有这两家） |
| `USE_CONTENT_FIELD` 只有两家为 True | ✅ 仍是 volcengine/vikingdb；新增的 opengauss 显式 `False` |
| 本地 `search_by_keywords` 抛 NotImplementedError | ✅ 仍在，且报错文案更明确了（"no longer performs automatic vectorization"） |
| 本地/自建路径无 BM25 | ✅ 未变 |
| 向量库默认 local | ✅ 未变；adapter 白名单 **5 → 6**（+opengauss） |

**唯一作废的一条**："两级向量检索"这个前提没了（v0.5.0 改成单遍全局召回）。这不影响本文关于"火山依赖程度"的任何结论——检索形态与模型/provider 选择是两件独立的事。

**新增的一个正面事实**：`find`/`search` 现在都支持 `--search-type semantic|keywords`，关键词检索不再只挂在 grep 上。
