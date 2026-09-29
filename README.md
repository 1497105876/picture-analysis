# picture-analysis

**规范化图片索引数据库 + 本地 Web 管理界面**——本机 Agent 生态（QClaw / openclaw / workbuddy 等）的图片记忆与检索基建。

> **找图是能力，索引是本体。** Web 界面是管索引、做人工审核的工具；对外的真正接口是那个可以被只读直连的 SQLite 数据库文件。

## 核心特性

- **手动登记目录**：只扫你指定的目录，未登记路径一概不碰（增量扫描 / 离线盘复活 / 目录级策略）
- **AI 识图管线**：OpenAI 兼容协议，产出分类/描述/AI 标签/元素清单；**OCR 按需触发**（识图判定含文字才追加，独立表存储）
- **限速与预算**：默认 **20 次/分钟（≥3 秒一次）** 可调，每日 token 上限触顶自动暂停
- **混合检索**：FTS5 关键词 + 向量语义 RRF 融合默认生效；中文分词、同义词、cursor 深分页
- **人工优先**：纠错/打回/分类永远压过 AI；规则引擎试跑先行
- **参考资料库**：标准人物"连图带文"注入识图 prompt
- **隐藏区**：前端/搜索/相册/直读全通路不可见，无参数可绕过
- **SQLite 只读直连**：Agent 打开文件即用，**不做 MCP Server**

## 快速开始

```bash
# 1. 准备环境（Python 3.12）
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

# 2. 配置密钥（可选，测试不需要）
copy .env.example .env      # 填入你的 OpenAI 兼容 API Key

# 3. 启动
python server.py            # → http://127.0.0.1:8321
```

## 文档导航

| 文档 | 内容 |
|---|---|
| [docs/第二次/01-前端功能分析.md](docs/第二次/01-前端功能分析.md) | **前端重写起点**：现有功能模块盘点、架构现状、缺陷清单、差距清单 |
| [docs/第二次/02-重构方案.md](docs/第二次/02-重构方案.md) | 第二轮前端重构方案：技术决策、设计系统、页面清单、验收标准 |
| [docs/第一次/使用指南.md](docs/第一次/使用指南.md) | 使用指南与产品介绍：安装、上手流程、F1-F15/G1-G18 全景与状态 |
| [docs/第一次/需求与功能清单.md](docs/第一次/需求与功能清单.md) | 需求基线：功能 F1-F15、配置组 G1-G18、效果要求 |
| [docs/第一次/srs.md](docs/第一次/srs.md) | 软件需求规格说明（FR 需求条目 + AC 验收基线） |
| [docs/第一次/architecture.md](docs/第一次/architecture.md) | 架构设计：分层视图、模块职责、技术选型 |
| [docs/第一次/design.md](docs/第一次/design.md) | 详细设计：数据库 DDL、**SQLite 直读契约**、REST API、状态机、限速器 |
| [docs/第一次/quality.md](docs/第一次/quality.md) | 质量属性场景（健壮/可靠/性能/安全…）、设计原则与工程原则落地 |
| [docs/第一次/testing.md](docs/第一次/testing.md) | 测试策略、夹具、专项用例、AC 追踪矩阵、性能基准 |
| [docs/第一次/delivery.md](docs/第一次/delivery.md) | 集成与持续交付（**无部署**）：CI 门禁、发布流程 |
| [docs/第一次/adr/](docs/第一次/adr/) | 关键架构决策记录（ADR-001~005） |

> 文档分轮归档：`docs/第一次` 是需求→设计→实现的第一轮产出，`docs/第二次` 是前端彻底重写的分析与方案。

## 开发

```bash
python scripts/ci.py        # 本地一键 CI：lint → type → test → package（与 GitHub Actions 同序）
pytest                      # 测试（零网络：全部走 FakeAI）
ruff check . && ruff format .
mypy app server.py
```

## 项目状态

M1–M7 全部实现并接入 CI（88 用例 / 覆盖率 88% / ruff+mypy+架构门禁全绿），早期阶段功能完整、部分界面入口待补——**界面上看不到的功能见 [docs/使用指南.md](docs/使用指南.md) 第 9 节差距清单**。

## 许可证

私人项目，未授权不公开使用。
