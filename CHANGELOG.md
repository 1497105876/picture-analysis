# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 SemVer。

## [Unreleased]

### Added

- 需求基线：`docs/需求与功能清单.md`（F1-F15、G1-G18、效果要求、里程碑）
- 工程文档集：SRS、架构、详细设计（含 SQLite 直读契约）、质量属性与工程规范、测试计划、集成与持续交付
- ADR-001~005（SQLite 唯一存储 / 不做 MCP / FastAPI+Vue3 / OCR 按需触发 / 限速 20 次每分）
- 工程骨架：FastAPI 应用装配、健康端点、pytest + ruff + mypy 门禁、本地 CI 脚本、打包脚本
- GitHub Actions CI（backend lint/type/test + 条件 frontend build + package）
- 存储层：SQLite 迁移与仓储（images/hidden 分表、FTS5、向量、任务、审计、提案、回收站）
- 领域层：状态机、限速（可注入时钟）、RRF 融合、规则求值、媒体工具、错误码
- AI 层：OpenAI 兼容客户端（vision/embed/chat，MockTransport 可测）、提示词与 JSON 解析
- 服务层：两阶段登记/增量扫描、识图队列（限速/日预算/无密钥暂停、退避重试、OCR 按需）、
  混合检索、人工修正（AI 位永不覆盖）、隐藏区、删除/回收站、统计与运维、schema 驱动设置
- API 层：85 个 REST 端点（目录/图片/检索/知识/对话/运维/设置），统一错误信封 + SPA 回退
- 前端：Vue3 + Vite SPA（图库/检索/仪表盘/实体/规则/相册/对话/隐藏区/回收站/任务/提案/设置），
  schema 驱动设置页、两阶段导入向导、隐藏区可见性说明条、明暗主题

### Changed（第二版前端重写）

- 前端彻底重写：拆 `styles/`（tokens / base / components 三件套）、`app/`（api、settings、
  notices、toast、format、useList、catalog 单例）、`components/`（18 个）三层，页面只写业务
- 主题体系改为令牌驱动：亮/暗 × 6 套强调色（天青/靛蓝/青碧/紫罗兰/琥珀/石墨）× 密度，
  软色由 `color-mix` 派生；选择结果写回后端 `theme` / `accent` / `card_density` / `thumb_size`
- 列表统一走 `ImageGrid`：网格/列表双视图 + 多选 + cursor 无限滚动 + 骨架 + 空态
- 抽屉统一走 `ImageDrawer`：补齐改名、移动到目录、自定义字段填写、识别历史时间线、← → 翻图
- 危险操作统一走 `ConfirmDialog`，移除全部 `window.confirm` / `window.prompt`
- 设置页改为「只提交脏值」，避免一次微调把 92 项配置全写进审计
- 新增页面：运维 `/ops`（健康/通知中心/日志查看器/存储/SQLite 直读契约/清空索引）、
  分类 `/categories`（分类字典 + 自定义字段 + 同义词组 + 术语权重）
- 测试：60 用例全绿，`pytest --cov-fail-under=80` 实测覆盖率 **88%**；
  ruff / ruff format / mypy strict（54 文件）/ 架构门禁全部通过
- 设计口径固化：`docs/design.md` 第 9 节（排序校验位置、暂停口径、日界、批量端点等）
