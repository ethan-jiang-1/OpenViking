# 02 L0/L1/L2 三层加载

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。取证原料 [core-evidence §2](../_notes/core-evidence.md)。

## 先给结论

L0（一句话摘要）/ L1（概览）/ L2（全文）不是文档修辞，而是一套**物理机制**：每个上下文对象在向量库里按 level 存三条记录，目录以 `.abstract.md` / `.overview.md` sidecar 文件承载 L0/L1，sidecar 是 **OKF 格式（YAML frontmatter + body）**，metadata 有写保护。设计稿（`docs/design/l0-l1-okf-sidecars-rfc.md`，仍标 Draft）与实现**高度同步**——RFC 的存储格式与读路径已落地，但 freshness 父冒泡属于 Future Work、只是部分实现。
>
> **v0.5.0 的两处口径修正**：① `docs/design/` 目录已从 upstream 删除，该 RFC 只剩**搬迁前旧分支里的副本**（`backup/ethan-before-v050`；搬迁到 v0.5.0 之后工作树里也没有了）；② "L0/L1 分层是两级检索的物理前提"这句**作废**——两级递归没了，level 现在是索引过滤条件（见下）。

## 层定义与物理形态

- 层枚举：`openviking/core/context.py:34-39` `ContextLevel`：`ABSTRACT=0`（L0）、`OVERVIEW=1`（L1）、`DETAIL=2`（L2）
- sidecar 文件名常量：`openviking/storage/abstract_overview.py:29` `ABSTRACT_OVERVIEW_FILENAMES = {".abstract.md", ".overview.md"}`
- 向量记录按 level 存储（L0/L1/L2 各一条）。**v0.5.0 起 level 是索引侧过滤条件**：`retrieve()` 把 `level` 下推给 `search_in_tenant(level=...)`（`hierarchical_retriever.py:183-204`），最终变成 `viking_vector_index_backend.py:2988-2989` 的 `In("level", level)`。**分层先于检索存在**——但它现在是**过滤维度**，不再是递归骨架（旧的 `:301-307`/`:542` 两条锚点在递归代码里，已随递归删除）。

## 谁生成 L0/L1：三条路径

1. **异步语义生成（主路径）**：`storage/queuefs/semantic_processor.py:1096`——bottom-up：先并发生成目录内文件摘要 → 收集子目录 `.abstract.md` → 生成本目录两文件（`abstract_overview.py:533` `write_abstract_overview()`，由 `semantic_processor.py:1836` 调用）
2. **同步直接写入**：`VikingFS.write_context`（`_semantic.py:566-577`）——显式传 abstract/overview 时分别写 sidecar，内容经 `render_abstract_overview()` 渲染成 OKF 格式
3. **预设目录播种**：`core/directories.py:381-423`（见 [01](01-viking-uri-and-vfs.md)）

## 读取时按层裁剪

- L0/L1 结果的展示 URI 拼上 sidecar 后缀：`hierarchical_retriever.py:56` `LEVEL_URI_SUFFIX = {0: ".abstract.md", 1: ".overview.md"}`（`_append_level_suffix()` :369-381）
- L0/L1 预览剥 frontmatter 只留可见正文：`abstract_overview.py:389-397` `body_for_preview()`（retriever 在 `:345` 调用它）
- 目录 overview 直接读 `{dir}/.overview.md`，缺失时返回占位 `[Directory overview is not ready]`（`_semantic.py:194`）

## OKF 格式与写保护

- 解析/渲染：`abstract_overview.py:182-227` `parse_abstract_overview()`（兼容无 frontmatter 旧内容；frontmatter 必须含 directory 字段 `:219-220`）、`:230-255` `render_abstract_overview()`（YAML frontmatter + body）
- metadata 规范化四组字段：directory/source/generated_by/freshness（`:97-179`；字段序常量 `_METADATA_ORDER :31`）——与 RFC "Metadata Fields" 一一对应
- **写保护**：公开写只能改 body，改 metadata 抛 `AbstractOverviewMetadataError`（`prepare_abstract_overview_write()` :348-386，相等性守卫 `:374-375`）——语义摘要归系统管，用户只管内容
- metadata **默认不进** embedding，但**有一个白名单例外**：`EMBEDDING_METADATA_FIELDS = ("directory",)`（`:30`）——`body_for_embedding()` / `embedding_text_for_body()`（`:456-474` / `:477-480`）会把 `directory` 拼回 frontmatter 送进 embedding。**这条例外在 v0.4.19 就存在**，旧文写成"metadata 一律不进"是**基线就错**

## 设计稿 vs 已实现（对照 RFC）

| RFC 内容 | 状态 | 证据 |
|---|---|---|
| OKF sidecar 格式（frontmatter + body） | ✅ 已实现 | `abstract_overview.py:182-386` |
| metadata 对 embedding 默认排除 | ✅ 已实现（**`directory` 例外**） | `:30`、`:456-474` |
| 不做 `read_metadata()` API；directory 进 embedding | ✅ 与代码一致 | RFC Decisions :251-255 |
| frontmatter 原样进 git diff | ⚠️ 未见验证 | — |
| Freshness-Aware Parent Bubbling | 🟡 部分实现（RFC Future Work） | `abstract_overview.py:671` `plan_abstract_overview_refresh()`；调用点 `semantic_processor.py:374`、`content_write.py:636`、`fs_service.py:616`、`abstract_overview.py:840`；"仅在子摘要变化时冒泡"的完整语义【未定】 |

## 易误解点

1. **L0/L1 不是"缓存"**：它们是独立的数据记录 + 独立的向量，删了 L2 不影响 L0/L1 被检索命中。
2. **frontmatter 不是用户的**：metadata 写保护意味着"改摘要内容可以、改摘要的元数据不行"——生成链路（SemanticProcessor）与用户写入走同一格式但不同权限面。
3. **RFC 标 Draft 不等于没实现**：格式与读路径已落地，Draft 状态主要卡在 freshness 冒泡的调度语义上。引用设计稿时按这篇的表格区分，不要整体当"规格"或整体当"现状"。**但这份 RFC 已不在 upstream 树里**（`docs/design/` 于 v0.5.0 前被删），引用前先确认你手上的是本地副本。
4. **`directory` 会进 embedding**：这是"metadata 不进 embedding"的**唯一例外**，而且它是有道理的——目录路径本身是强语义信号，摘要文本脱离目录会失去上下文。

## 状态标注

- 硬事实：以上锚点见 core-evidence §2
- 未定：freshness 父冒泡的完整决策语义；RFC "git diff" 决策项
- 反转记录（2026-10-19，v0.5.0）："level 过滤是两级检索物理前提"作废（level 改为索引下推）；补 `directory` embedding 白名单例外（**此错基线就有**）；RFC 锚点降级为本地副本
