# OpenViking 扩展接缝与分层边界取证

## v0.5.0 复核登记（2026-10-19）

- **基线**：`v0.5.0` = `20f9c1136`。原锚点基于 `0f77ab56`。
- **接缝数量全部变化**：adapter 白名单 5 → **6**（+`opengauss`，`factory.py:16-23`）；ingest source 6 → **8**（+`mimo`、+`workbuddy`）；parser 仍 10 个；embedder provider 仍 13；VLM provider 仍 7；auth 插件仍 5。
- **分层纪律恶化**：反向 import `openviking_cli` 的文件 282 → **319**（storage 66 / server 42 / session 38 / parse 37 / models 24 / service 20 / utils 16 / retrieve 10 / core 6）。本报告 §3 的定量结论需按新数字读。
- **仍有效**：`CollectionAdapter` 点分类路径动态加载暗门（`factory.py:31-42`，错误消息仍只列白名单 6 项）；auth registry 无 entry-points。


范围：parse/ingest 扩展接缝、embedding/VLM provider 接缝、service/core/storage/retrieve 分层方向。
纪律：只读源码 + 本报告；所有锚点为 `文件:行号`（相对仓库根）。

## 1. parse / ingest 扩展接缝

### 1.1 两级接缝结构
- 顶层是 **AccessorRegistry（来源接缝）**：按来源路由到 accessor，输出 `LocalResource`。基类 `DataAccessor` + `LocalResource` 定义在 `openviking/parse/accessors/base.py:24`（SourceType 常量 LOCAL/GIT/HTTP/FEISHU，`base.py:17-34`）。
- 第二级是 **ParserRegistry（文件类型接缝）**：按扩展名选 parser。基类 `BaseParser` 为 ABC，三个抽象成员 `parse`/`parse_content`/`supported_extensions`，`openviking/parse/parsers/base_parser.py:11,17,49`。
- 分发依据：**扩展名**（`ParserRegistry.get_parser_for_file` 用 `path.suffix.lower()` 查 `_extension_map`，`openviking/parse/registry.py:88-101`），不按 MIME；未知扩展回退 TextParser（`registry.py:141`）。
- 两者之间还有 **ParserRouter**：按配置 `ov.conf.parser_api`（enable + 扩展名白名单）把部分文件路由给外部 UnderstandingAPI（`openviking/parse/parser_router.py:47-85,108-156`）。

### 1.2 注册方式与硬编码程度
- ParserRegistry 在 `__init__` 里**硬编码注册** 10 个内置 parser（text/markdown/pdf/html/anydoc/zip/directory/image/audio/video，`openviking/parse/registry.py:51-69`；2026-09-13 修正：此前写 11，实数 10 个 `_register` 调用——:71 的 `def _register` 是定义不是调用）。注册方法 `_register` 是私有方法（`registry.py:71`），无公开 `register_parser` API，也无 entry-point 机制（全仓 `importlib.metadata` 仅用于版本号，`openviking/__init__.py:13`）。
- 配置只能给**内置 parser 传参**（`parser_configs` 字典，key 固定为 text/markdown/pdf/html/anydoc/image，`registry.py:168-175`），不能注入新 parser 类。
- AccessorRegistry 相对开放：有公开 `register()/unregister()` 且按 priority 排序（`openviking/parse/accessors/registry.py:95-113`），默认 5 个 accessor 硬编码注册（git/web-feed/http/feishu/local，`registry.py:53-93`）。但默认实例是模块级单例惰性创建（`registry.py:195-209`），第三方只能在**同一进程内**编程式调用 `get_accessor_registry().register(...)`，无配置文件注入新 accessor 类的路径。
- ingest 日志源（Claude Code/Codex 等 harness）接缝最干净：`@register_source("name")` 装饰器 + `LogSource` ABC（`openviking/ingest/registry.py:22-33`；ABC 层级说明见 `openviking/ingest/sources/base.py:2-4`），模块 docstring 明言"新增 harness 只需一个装饰器"（`registry.py:4-6`）。但同样是运行时编程式注册，非 entry-point。
- 结论【解释】：新增文件类型 = 在 `registry.py` 硬编码表里加一行 + 新写一个 `BaseParser` 子类（改内核文件）；新增**来源** = 进程内 register 一个 `DataAccessor` 子类；新增 harness = 一个 `@register_source` 子类。**第三方不 fork 无法通过配置或 packaging entry-point 加 parser/accessor**【硬事实】。

### 1.3 ingest API 接受的来源类型
- accessor 层支持：本地文件/目录（LocalAccessor）、Git 仓库、HTTP(S) URL、sitemap/RSS/Atom 整站（WebFeedAccessor）、飞书文档；zip 是 parser 而非 accessor（`ZipParser`，`openviking/parse/registry.py:64`）【硬事实，见 1.2 注册表】。
- 外部 Understanding API 的 host 固定拼 `/api/v3` 路径（`openviking/parse/understanding_api.py:67-69`），即火山方舟 Ark 风格端点【解释】。

## 2. embedding 与 VLM provider 接缝

### 2.1 embedding
- 抽象在 `openviking/models/embedder/base.py`：`EmbedderBase`/`DenseEmbedderBase`/`SparseEmbedderBase`/`HybridEmbedderBase`/`CompositeHybridEmbedder`/`FailoverEmbedder`（导出清单 `openviking/models/embedder/__init__.py:15-27`）。
- 配置字段：`OpenVikingConfig.embedding: EmbeddingConfig`（`openviking_cli/utils/config/open_viking_config.py:181`）；`EmbeddingModelConfig.provider` 默认 `"volcengine"`，可选值（`_VALID_PROVIDERS`，`embedding_config.py:168-182`）openai/azure/volcengine/vikingdb/jina/ollama/gemini/voyage/dashscope/minimax/cohere/litellm/local **共 13 个**（2026-09-13 修正：此前列 12 个漏 azure），docstring 明示 OpenAI 兼容端点走 `litellm` 或 `openai + api_base + extra_headers`。支持 `api_base`/`api_version`/`extra_headers`/`extra_body`（`embedding_config.py:27-29,65-74`）。
- 工厂：`EmbeddingConfig.get_embedder()` → `_create_embedder()` 内部硬编码 `factory_registry` 字典（provider,type)→class，`openviking_cli/utils/config/embedding_config.py:1011,1046-1063`。service 侧入口：`openviking/service/core.py:155` `self._embedder = config.embedding.get_embedder()`。
- 判断【解释】：**开放度较高**——任意 OpenAI 兼容端点可配（openai provider + 自定义 api_base，或 litellm 桥接），13 个 provider 全部配置驱动，非仅 volcengine。但 provider 集合本身是封闭枚举，新增 provider 类需改 `factory_registry`。

### 2.2 VLM（语义摘要）
- 抽象 `VLMBase(ABC)`（`openviking/models/vlm/base.py:64`）；provider 元数据注册表 `VALID_PROVIDERS = (volcengine, openai, azure, kimi, glm, litellm, openai-codex)`（`openviking/models/vlm/registry.py:10-18`）。
- 配置：`OpenVikingConfig.vlm: VLMConfig`（`open_viking_config.py:185`）；`VLMConfig` 支持 `provider`/`providers`(多 provider dict)/`default_provider`/`api_base`/`extra_headers`/多凭据 failover（`openviking_cli/utils/config/vlm_config.py:141-155,44-59`）。`query_planner` 可另配独立 VLM，缺省回落 `vlm`（`open_viking_config.py:187-191`）。
- 判断【解释】：**开放**——litellm provider 可桥任意 OpenAI 兼容端点，openai/azure provider 支持自定义 api_base；volcengine 只是默认路径之一而非唯一选项。与 embedding 同构：配置可换端点，provider 代码集合封闭。

## 3. 分层依赖方向抽查

### 3.1 service 层 import 抽查（3 个文件）
- `openviking/service/core.py`：import core/privacy/resource/server/service 自身/session/storage/queuefs（`core.py:13-40`）。
- `openviking/service/session_service.py`：import core/server/service/session/storage/utils + `openviking_cli`（`session_service.py:14-45`）。
- `openviking/service/debug_service.py`：import server/storage/openviking_cli（`debug_service.py:10-23`）。
- 【硬事实】service → server 反向依赖存在：`core.py:17-21`（account_settings、identity）、`session_service.py:15-18`（agent_evolution_config、config、identity、user_config）、`debug_service.py:10`。同时 server → service 也有 8 个文件（`grep "from openviking.service" openviking/server` 计数）。service 与 server **双向耦合**。
- 【硬事实】service → core/storage 方向正常存在（如 `core.py:13,36-40`）。

### 3.2 反向越层证据（core/storage/retrieve → service / server）
- `openviking/storage/queuefs/semantic_dag.py:14-15`：import `openviking.server.identity` 与 `openviking.service.task_work_index`。**（v0.5.0：该文件已删除，等价位置见 `queuefs/semantic_executor.py`——3 处 `openviking.service` import；本行按旧基线留档）**
- `openviking/storage/queuefs/session_commit_processor.py:14-16,23`：server.identity + service.task_tracker/task_work_index/SessionService。
- `openviking/storage/queuefs/add_resource_processor.py:13-15`：server.identity + service.task_tracker/task_work_index。
- `openviking/storage/queuefs/external_task_processor.py:11-13`：service.external_task_service/task_tracker_concurrency/task_work_index。
- `openviking/storage/queuefs/named_queue.py:13`：service.task_work_index。
- `openviking/storage/viking_vector_index_backend.py:19`、`openviking/storage/collection_schemas.py:21`：server.identity。
- `openviking/core/` 对 service/server 仅有一类依赖：**3 处 import `server.identity`**（`core/retrieval_targets.py:14`、`core/namespace.py:10`、`core/directories.py:21`，均为 `RequestContext`/`Role` 类型）——2026-09-13 修正：此前写"未发现 import service/server【grep 无命中】"系 grep 模式不全所致，"core 零反向"结论作废；core 无 service 业务逻辑依赖仍成立。其依赖 openviking_cli（见 3.3）。

### 3.3 openviking_cli 反向 import（client/compat 之外）
- 【硬事实】`openviking` 内部 import `openviking_cli` 的文件数（grep -l 计数）：storage 56、parse 35、session 34、models 23、service 17、retrieve 8、core 6、resource 5——**282 个文件**全仓。典型例子：
  - `openviking/core/context.py:12-13`（`openviking_cli.session.user_id`、`openviking_cli.utils.uri.VikingURI`）
  - `openviking/core/namespace.py:11-12`、`core/uri_validation.py:14-15`、`core/directories.py:30`
  - `openviking/retrieve/context_assembler/gather.py:26-27`（`openviking_cli.retrieve.ContextType`）、`expansion.py:17-18`
  - `openviking/service/session_service.py:39-45`（exceptions、logger、memory_config）
- 【解释】分层结论：**不存在单向分层**。openviking_cli 处事实上的"共享内核/上层"，被 core/storage/retrieve/service 普遍反向依赖；service 与 server 互相 import；storage 的 queuefs 子包直接依赖 service。相对干净的只有 `core`→`service/server` 方向（无反向）。
