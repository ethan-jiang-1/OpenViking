# 问题：OpenViking 的 RAG 技术栈是完全依赖火山（Volcengine/方舟）吗？可以自己配置吗？有 BM25 吗？

## 背景

翻 `_digested/` 和源码时注意到 OpenViking 的检索链路横跨多个模型层组件：embedding（还有 dense/sparse/hybrid 三种模式）、rerank、VLM（L0/L1 摘要）、向量库后端、grep 关键词检索。README 的评测口径全部用 Doubao 模型（`docs/repository/README_CN.md:113`），changelog 里又有 "VikingDB BM25 grep"（v0.4.6），直觉上像是个火山系全家桶产品。但 `_digested/_notes/seams-boundaries-evidence.md` 又说 embedding 有 13 个 provider、任意 OpenAI 兼容端点可配。

直觉与既有材料冲突，需要搞清楚**"火山依赖"到底锁在哪些层、哪些层是宽门**：

1. OpenViking 的 RAG 组件全景是什么（embedding / rerank / 检索模式 / BM25 各自角色）？
2. 模型层（embedding / rerank / VLM）是不是只能用火山的 Ark/VikingDB？能不能接别的云或本地模型？
3. 向量库后端有几条路，默认是什么？
4. "有 BM25 吗"——是内置实现、还是只有火山后端才有？本地后端能不能用？

## 证据边界

- **源码**：只引用本仓库 `openviking/`、`openviking_cli/` 的配置与实现文件（基线 `0f77ab56`；本次取证所涉关键文件 `_grep.py` / `embedding_config.py` / `rerank_config.py` / `vectordb_adapters/*` / `docs/en/guides/01-configuration.md` 在该基线到 HEAD `57571ca9` 之间无 diff，锚点可视为基线有效）。
- **消化材料**：`_digested/_notes/seams-boundaries-evidence.md`（provider 接缝）、`_digested/core/03-retrieval-global-recall.md`（QUICK/THINKING；该篇 v0.5.0 由 ~~`03-retrieval-two-levels.md`~~ 更名而来）、`_digested/architecture/01-three-languages.md`（向量引擎分层）。
- **不做**：不审计第三方 SDK（vikingdb/cohere/openai 库）内部实现，只以 OpenViking 侧配置面与调用点为据。
