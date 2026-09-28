# 直读查询示例

给本机 Agent 的现成 SQL 片段：[direct_read.sql](direct_read.sql)

- 连接必须只读：`sqlite3.connect("file:.../library.db?mode=ro", uri=True)`
- 只查 `docs/design.md` 第 2.2 节列出的对象；隐藏图片天然不可见，无参数可绕过
- 字段语义以 `design.md` 第 2 章契约为准，破坏性变更会升 `SCHEMA_VERSION` 并同步文档
