# ADR-003：技术栈 = FastAPI（Python 3.12）+ Vue3/Vite

- 状态：已接受
- 日期：2026-09-28
- 决策者：库主

## 上下文

需求明确"Python + FastAPI 实现"，交付形态为本地 Web（`python server.py` → 浏览器），界面要求表单化/卡片化、schema 驱动渲染、状态可见——交互密度不低。

## 决策

- **后端**：Python 3.12 + FastAPI + uvicorn，仅监听 `127.0.0.1:8321`，同时托管前端构建产物
- **前端**：Vue3 + Vite 独立工程（`frontend/`），构建产物输出到 `app/static/`，**无运行时 Node 依赖**
- **配套**：Pillow（提取/缩略图）、httpx（AI 客户端）、jieba（中文分词）、numpy（向量）

## 后果

- ✅ FastAPI 的 pydantic 校验天然承接"schema 驱动配置"与统一错误结构
- ✅ 类型注解贯穿（mypy strict），OpenAPI 免费得到接口文档
- ✅ Vue3 组件化适合 schema 渲染器与复杂状态展示
- ⚠️ 双语言栈（Python + TS）：契约靠 `design.md` + 生成的 OpenAPI 同步
- ⚠️ 构建链多一步 `npm build`——已纳入 CI 流水线

## 曾考虑的备选

- Flask：校验与文档都要自建，放弃
- FastAPI + Jinja2/HTMX：单栈简单，但交互密度（网格、批量、实时进度）撑不住，放弃
- Electron 桌面壳：需求明确"不做桌面壳"，放弃
