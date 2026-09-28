# 集成与持续交付（无部署）

> 本项目**没有部署环节**：交付物是可直接运行的 Release zip。CI 的职责 = 保证 main 恒绿 = 随时可打包发布。

| 项 | 值 |
|---|---|
| 仓库 | GitHub 公开仓库 `picture-analysis`（`github.com/<owner>/picture-analysis`） |
| 分支 | `main`（恒绿）+ 短生命周期 `feat/*`、`fix/*` |
| CI | GitHub Actions：push / PR 触发 |
| 产物 | `picture-analysis-<version>.zip`（含后端、前端构建产物、文档、启动脚本） |
| 运行 | 解压 → `python server.py` → 浏览器 `http://127.0.0.1:8321` |

---

## 1. 集成策略

### 1.1 流程

```
feat/* 分支
  │  本地 pre-push（可选）：ruff + mypy + pytest
  ▼
Push → Pull Request → CI 全绿 + 自审 diff → Squash 合并 → main
  │
  ├─ main 每次合并：CI 全绿 + 生成最新构建产物（artifact，保留 30 天）
  └─ 打 tag vX.Y.Z：CI 追加打包 Release zip 并挂到 GitHub Release
```

### 1.2 集成规则

1. **小步集成**：一个 PR 只做一件事；PR 描述写清"动机 + 影响的 AC"
2. **契约变更必须同 PR**：改 `srs.md` AC 或 `design.md` 契约与代码**同一个 PR**，否则 CI 的文档一致性检查拒绝
3. **main 恒绿**：红了立即修或 revert，不允许"带着红灯开发"
4. **特性开关而非长分支**：预埋功能用配置开关（G 组），避免分支腐化

---

## 2. CI 流水线（`.github/workflows/ci.yml`）

```
                 ┌────────────┐
   push / PR ───►│  backend   │  ruff check → ruff format --check → mypy → pytest(cov)
                 └─────┬──────┘
                       │
                 ┌─────▼──────┐
                 │  frontend  │  仅当存在 frontend/package.json 时：npm ci + build
                 └─────┬──────┘   （当前阶段无前端，任务自动跳过）
                       │
                 ┌─────▼──────┐
                 │  package   │  组装 Release 目录 → 上传 artifact
                 └────────────┘   （tag：追加创建 GitHub Release）
```

| Job | 命令 | 失败即 |
|---|---|---|
| backend-lint | `ruff check .` / `ruff format --check .` | 拒绝合并（风格与常见 bug） |
| backend-type | `mypy app server.py` | 拒绝合并（类型即文档） |
| backend-arch | `python scripts/check_arch.py` | 拒绝合并（依赖方向 + 直读契约完整性） |
| backend-test | `pytest --cov=app --cov-fail-under=80` | 拒绝合并（AC 兜底） |
| frontend-build | `npm ci && npm run build`（条件执行） | 拒绝合并 |
| package | 打包 + `actions/upload-artifact` | 拒绝合并（交付物必须可产出） |

**质量门禁即策略**：覆盖率 <80%、任何 lint/type 告警、缺测试的 AC——都在合并前拦截，而不是发布前。

### 2.1 密钥与供应链

- `.env` 永不入库（`.gitignore` 第一等公民）；CI **不需要任何密钥**（测试全用 FakeAI）
- 依赖：`pyproject.toml` 声明版本范围；发布构建用 `requirements.lock`（`pip freeze` 生成）保证可重现
- 第三方 Actions 固定到主版本 tag；`permissions: contents: read` 最小权限

---

## 3. 本地开发工作流

```bash
# 首次
python -m venv .venv && .venv\Scripts\pip install -e ".[dev]"

# 日常
python server.py                 # 起服务（127.0.0.1:8321）
pytest                            # 跑测试（与 CI 同款）
ruff check . && ruff format .    # lint + 格式
mypy app server.py               # 类型

# 一键本地 CI（与流水线同序）
python scripts/ci.py             # lint → type → test →（有前端则 build）→ package
```

---

## 4. 版本与变更管理

- **SemVer**：`MAJOR.MINOR.PATCH`
  - MAJOR：直读契约/REST 破坏性变更
  - MINOR：新增功能（新 F 域落地）
  - PATCH：修复与文案
- **CHANGELOG**（Keep a Changelog 格式，仓库根目录）：`Added / Changed / Fixed / Removed` 四段，每条关联 AC 或 issue
- **需求变更**：提交信息带 `req:` 前缀，且必须同步 `srs.md` AC——CI 检查最近提交是否触及 `app/` 而文档未动（软检查，人工把关）

---

## 5. 发布流程（Release Checklist）

1. [ ] main CI 全绿（lint/type/test/coverage/frontend/package）
2. [ ] `srs.md` AC 矩阵无未覆盖项（`testing.md` 第 7 章闸门）
3. [ ] 冒烟清单 8 项人工过一遍（`testing.md` 第 5 章）
4. [ ] CHANGELOG 写好本版本段落
5. [ ] `git tag vX.Y.Z && git push --tags`
6. [ ] CI 自动产出 `picture-analysis-vX.Y.Z.zip` 挂到 GitHub Release
7. [ ] 下载 zip 在干净机器验收：解压 → `python server.py` → 冒烟通过

**交付物内容**：

```
picture-analysis-vX.Y.Z/
├── server.py
├── app/                  # 后端源码
├── frontend/dist/        # 前端构建产物（由 app 静态托管）
├── docs/                 # 需求/设计/契约文档（含直读契约）
├── requirements.lock
├── .env.example          # 密钥模板（真实 .env 由用户创建）
└── README.md
```

---

## 6. 环境矩阵

| 项 | 支持 |
|---|---|
| OS | Windows 10/11（主目标）；CI runner：ubuntu-latest（通用逻辑）+ windows-latest（路径/编码兼容） |
| Python | 3.12（CI 固定） |
| 浏览器 | Chrome / Edge 最新两版 |
| Node | 20 LTS（仅前端构建需要） |
