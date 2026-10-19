# 01 viking:// URI 与虚拟文件系统

> **基线**：`v0.5.0`（2026-10-19 同步；建档基线 `0f77ab56`）。取证原料 [core-evidence §1](../_notes/core-evidence.md)。

## 先给结论

viking:// 是一个**带命名空间白名单的虚拟文件系统**：公开 scope 只有 `{resources, user, agent}` 三个（外加 legacy/内部/别名 scope）——这套白名单自 v0.4.19 起**逐字节未变**，v0.5.0 的改动在 `agent` 的语义上，不在清单上，目录树不是"用户创建文件自然长出来的"，而是**预设目录 + ingest 双来源**，且每个目录本身就是一条数据记录（自带 L0/L1 文案）。所有文件操作的实现主体是 `VikingFS`（7 个 mixin 的组合），IO 与加密**打穿到 Rust 层**（详见 [architecture/01](../architecture/01-three-languages.md)）。

## 命名空间：白名单制，不是约定俗成

| 类别 | scope | 锚点 |
|---|---|---|
| 公开（可列出） | `resources` / `user` / `agent` | `openviking_cli/utils/uri.py:58-62` `LISTABLE_SCOPES`；另有子集 `PUBLIC_SCOPES` :63、`VISITABLE_SCOPES` :71 |
| legacy | `session` | `uri.py:64` |
| 内部 | `temp` / `queue` / `upload` | `uri.py:65` `INTERNAL_SCOPES` |
| 别名 | `~`（home，仅请求边界展开、不持久化） | `uri.py:68` `ALIAS_SCOPES` |

- 请求边界校验：`openviking/core/uri_validation.py:35-64` `validate_viking_uri()`；scope 不在白名单抛 `InvalidURIError`
- 内容类型映射：`core/namespace.py:14-17` `_CONTENT_TYPES_BY_SCOPE`——`user` 下 `memories→memory`、`resources→resource`、`skills→skill`，`agent` 下**只剩** `skills→skill`（v0.5.0 移除了 agent→memory/resource 的映射）。**URI 路径段决定内容类型**，这是"目录结构是一等公民"的第一处体现
- 别名与 legacy 的 fail-closed 解析：`namespace.py:222` `resolve_uri()`（fail-closed 块 `:233-248`）；请求边界展开在 `resolve_request_uri()`（`:251`）
- 可见根：`viking://resources`、`viking://agent`（**整个 agent 命名空间**，不再只是 skills 子树）、`viking://user/{user_id}`（`namespace.py:180-185`）。旧常量 `AGENT_SHARED_ROOTS` 已改名为 `AGENT_SKILLS_ROOT`（`:177`）
- 访问控制内建于 URI 层：`namespace.py:317-334` `is_accessible()`——**`agent` 现已进入"永不拒绝"集合** `{"", "resources", "agent", "temp", "queue"}`（`:326`），原来那条 `actor_peer_id` 校验被删掉了；只剩 `user` 校验 owner_user_id（`:328-332`）和 `upload` 一律拒绝（`:325-326`）

## 目录树从哪来：两个来源

1. **预设目录**（`core/directories.py:53-188` `PRESET_DIRECTORIES`）：`user` scope 预置 `memories/`（九个分类子目录）、`resources/`、`privacy/`、`peers/`、`skills/`、`sessions/`；**v0.5.0 新增 `agent` 树**（`:155-188`）：`skills/`、`endpoints/`（A2A/ANP 等通信端点）、`tools/`（MCP server 配置）、`payments/`（AP2 等支付能力）。**每个目录定义自带 abstract（L0）与 overview（L1）文案**（`DirectoryDefinition` :33-40），`DirectoryInitializer`（`:191`）落盘时同步播种 L0/L1 向量（`:381-423`）。模块 docstring（`:6`）原话："all directories are data records"
2. **ingest 生长**（`core/building_tree.py:11` `BuildingTree` + `parse/tree_builder.py:39` `TreeBuilder`）：v5.0 流水线 = Parser 建 temp 目录结构 → TreeBuilder 建 URI 元数据 → ResourceProcessor 提交 → SemanticProcessor 异步生成语义

## "像文件一样操作"的操作面

实现主体 `VikingFS` = 7 个 mixin 组合（`openviking/storage/viking_fs/__init__.py:110-126`）：

| 操作 | 锚点 | 说明 |
|---|---|---|
| `read` / `write` | `_ops.py:139` / `:178` | read 接受 URI 或 32 位 hex 向量记录 id；加密下沉 ragfs 层（`:152-154` 注释） |
| `glob` / `tree` / `ls` | `_ops.py:1184` / `:1747` / `:2165` | 文件式遍历。**v0.5.0 起 `ls`/`tree` 接受 `include_abstract`/`include_overview`/`overview_limit`**——导航本身变成显式的信息获取（见 [vfs/04](../vfs/04-why-agent-sees-fs.md)） |
| `grep` | `_grep.py:30` | 内容 grep（内部 `search_recursive` :772）；**v0.5.0 新增 `before_context`/`after_context`**，但 MCP 工具面没暴露（见 [vfs/03](../vfs/03-operation-semantics.md)） |
| `find` / `search` | `_semantic.py:196` / `:393` | 语义/关键词检索（见 [03](03-retrieval-global-recall.md)）；另有 `find_skills :211` 走包级折叠 |
| `write_context` | `_semantic.py:566` | 写 L0/L1/L2 三件套（见 [02](02-context-layers.md)） |

服务层暴露：`service/fs_service.py:251`（ls）、`service/search_service.py:108/:166`（search/find）。URI→物理路径映射见 **`_access.py:687`** `_uri_to_path()`（已从 `_ops.py` 迁出）。

## 易误解点

1. **"user 下直接写文件"不走**：`viking://user/<reserved>` 无 uid 形式已废弃并报错（`namespace.py:296-314`）——user scope 必须带 user_id。
2. **`~` 别名不持久化**：只在请求边界展开，落盘前已解析为 canonical URI。
3. **目录不是容器对象**：目录本身是数据记录（带 L0/L1 与向量）。v0.4.19 时这条是"目录递归"的前提；v0.5.0 递归删除后它**依然重要**，但原因是另一个：目录记录是**检索结果的合法终点**，agent 可以只拿 L0/L1 就决定要不要继续读（见 [03](03-retrieval-global-recall.md)）。
4. **`agent` 命名空间从"skills 专用"变成"账号级能力面"**：v0.5.0 给它补了 `endpoints`/`tools`/`payments` 三棵子树，并把它划进永不拒绝集合。旧文"`agent/skills` 是唯一的 agent 共享根"**已作废**——现在整个 `viking://agent` 都可见；`skills` 是其中**可写**的子树之一。

## 状态标注

- 硬事实：以上锚点均来自静态读源码（core-evidence §1）
- 未展开：`endpoints/` / `tools/` / `payments/` 三棵新子树**有没有任何代码在写**——v0.5.0 只做到"预置 + 可见 + L0/L1 播种"，写入方可能是商业版
- 反转记录（2026-10-19，v0.5.0）：`agent` scope 语义与预设树重写；`actor_peer_id` 门禁删除；scope 白名单本身未变
