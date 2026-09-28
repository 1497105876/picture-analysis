# 测试计划与测试策略

> 目标：**`srs.md` 第 5 章的每一条 AC 都有自动化用例兜底**，"CI 绿 = 可发布"。
> 本文档定义测什么、怎么测、在哪测、测到什么程度算过。

| 项 | 值 |
|---|---|
| 测试框架 | pytest 8 + httpx（TestClient）+ coverage |
| 执行入口 | `pytest`（本地与 CI 同款，见 `delivery.md`） |
| 覆盖率门槛 | 全局 ≥ 80%；`app/domain/` ≥ 90%；CI 不达标即红 |
| 外部依赖 | **测试零网络**：FakeAI 注入，不碰真实 VLM |

---

## 1. 测试分层策略

```
        ┌────────────────────────────┐
        │ E2E（浏览器 Playwright，少量）│  ← 冒烟：入库→识图→搜索→纠错
        ├────────────────────────────┤
        │ 系统/API 测试（TestClient）  │  ← REST 契约、错误码、软失败
        ├────────────────────────────┤
        │ 集成测试（真 SQLite + tmp 文件）│  ← 仓储/FTS/向量/迁移/直读视图
        ├────────────────────────────┤
        │ 单元测试（纯函数，domain 为主） │  ← RRF/规则/限速/状态机/COALESCE
        └────────────────────────────┘
```

| 层 | 目录 | 速度目标 | 数量原则 |
|---|---|---|---|
| 单元 | `tests/unit/` | < 5s 全量 | 覆盖全部分支与边界；领域逻辑 100% 场景化 |
| 集成 | `tests/integration/` | < 30s | 每张表的读写路径、迁移、FTS/向量一致性 |
| API/系统 | `tests/api/` | < 30s | 每个端点的成功 + 主要失败路径 + 错误码 |
| E2E | `tests/e2e/` | < 2min，可 `-m e2e` 跳过 | 每里程碑 1 条主链路 |
| 性能 | `tests/perf/` | 手动/夜间 `-m perf` | 合成 10 万库基准（见第 6 章） |

**约定**：文件 `test_<主题>.py`；用例名中文 docstring 描述"给定-当-则"；标记 `@pytest.mark.slow|e2e|perf`。

---

## 2. 测试夹具（Testability 落地）

| 夹具 | 作用 | 对应 QA |
|---|---|---|
| `FakeAI` | 实现 `VisionClient/EmbedClient/ChatClient` 协议：可编排固定响应、延迟、异常、记录调用次数 | QA-6.1、软失败、限速计数 |
| `fake_clock` | 可推进的 `Clock`：限速/每日上限用例**不真等 3 秒** | QA-6.3 |
| `tmp_library` | `tmp_path` 上建完整 SQLite + 迁移，函数级隔离 | QA-6.2 |
| `image_factory` | Pillow 生成带文字/纯图/损坏图/1×1 等边界图 | OCR 触发、坏文件 |
| `seed_10k` | 生成 10 万行合成库（仅 perf 标记） | QA-3 |
| `client` | FastAPI `TestClient`（app 注入 FakeAI + fake_clock） | API 层 |

**红线**：单测与 API 测试中出现真实网络调用 = 测试失败（CI 断网可跑）。

---

## 3. 关键专项测试（风险最高的六件事）

### 3.1 软失败（QA-2.4 / AC-F2）

| 用例 | 断言 |
|---|---|
| 识图服务 500/超时/连接拒绝 | 任务退避重试 ≤ 上限；入库与关键词搜索照常可用；UI 得到中文原因 |
| 嵌入服务挂 | 混合搜索自动降级纯关键词，仍有结果，响应含降级提示 |
| 对话服务挂 | 返回引导语，非错误页 |
| 模拟开关（设置页） | 全链降级零外发请求（FakeAI 调用计数 = 0） |

### 3.2 限速 20 次/分钟（AC-F2 / QA-3）

| 用例 | 断言 |
|---|---|
| fake_clock 连续放行 20 次 | 第 21 次被拒，等待时间 = 60s − 窗口最早请求 |
| 相邻请求间隔 | **任意两次放行间隔 ≥ 3 秒**（虚拟时钟断言） |
| 修改配置为 5/分钟 | 保存后立即生效（`effective: immediate`） |
| 跨线程并发取任务 | 计数器无竞态（多线程压 100 次请求，放行数 = 预期） |

### 3.3 OCR 按需触发（AC-F2 / QA-1）

| 用例 | 断言 |
|---|---|
| FakeAI 判定 `has_text=false` | **OCR 调用次数 = 0**，`ocr_results` 无行 |
| 判定 `has_text=true`，policy=auto | 恰好 1 次 OCR 调用，结果落独立表 |
| policy=off | 0 次调用但 `has_text=1`（规则可用） |
| OCR 请求也计入限速与预算 | 调用总数受 20/分钟与每日上限约束 |

### 3.4 隐藏区无绕过（AC-F15/F12 / QA-4.3）

| 用例 | 断言 |
|---|---|
| 隐藏一张图 | 前端列表/搜索/相册响应零包含 |
| 直读文档化对象（`v_images` 等） | 查询结果零隐藏行 |
| 任何 `include_hidden`/`show_hidden` 参数 | 400 `HIDDEN_NOT_BYPASSABLE` 或被忽略（契约无此参数） |
| 恢复 | 立即回到全部通路，识别数据不变 |

### 3.5 SQLite 直读契约（AC-F12 / QA-4.3）

| 用例 | 断言 |
|---|---|
| `mode=ro` 连接 | 任何 INSERT/UPDATE 报 `readonly` 错误 |
| `COALESCE` | 人工修正后 `v_images.category/description` 取人工值，`category_source='manual'` |
| 契约清单 | `design.md` 列出的视图/表全部存在（迁移后 introspect） |
| 提案未批准 | `entities`/`tags` 中查不到提案内容；批准后出现 |

### 3.6 安全（QA-4）

| 用例 | 断言 |
|---|---|
| 密钥脱敏 | 故意把密钥值写进上下文，抓取日志/审计/导出 → **零命中** |
| 绑定地址 | 服务 `127.0.0.1`；非回环连接失败 |
| 路径穿越 | `../../`、绝对路径逃逸、符号链接逃逸 → 拒绝且零读取 |
| 危险操作确认词 | 差一个字符 → 400，源文件完好 |
| 隐私目录 | 断言 FakeAI 收到的请求体中**不含**隐私目录图片数据 |

---

## 4. AC ↔ 用例追踪矩阵（摘要）

> 全量矩阵以 `tests/` 内用例 docstring 中的 `AC-Fx` 标签为准；CI 输出覆盖率时同步输出 AC 覆盖清单。

| AC | 代表用例 | 层 |
|---|---|---|
| F1 未登记目录零扫描 | `test_scan_ignores_unregistered_dir` | 集成 |
| F1 拔盘复活 | `test_offline_dir_revive` | 集成 |
| F1 MD5 认回身份 | `test_md5_identity_after_move` | 集成 |
| F1 导入向导预估 | `test_import_wizard_estimate_then_phase` | API |
| F2 限速 20/分、间隔≥3s | `test_rate_limit_window` / `test_min_interval` | 单元 |
| F2 OCR 按需 | `test_ocr_triggered_only_when_has_text` | 集成 |
| F2 每日上限触顶 | `test_daily_budget_pauses_queue` | 单元+API |
| F2 软失败全链 | `test_vision_down_ingest_and_search_ok` | API |
| F3 中文/语义/RRF | `test_fts_chinese` / `test_hybrid_rrf_order` | 集成+单元 |
| F3 cursor 深分页 | `test_cursor_pagination_no_dup_no_skip` | 集成 |
| F4 相册回放=原查询 | `test_smart_album_replay_matches` | 集成 |
| F5 schema 渲染 | `test_settings_schema_returns_groups` | API |
| F5 密钥明文可读 | `test_secret_read_back_plaintext` | API |
| F6 人工不被覆盖 | `test_manual_never_overwritten` | 集成 |
| F6 打回带纠正说明 | `test_redo_carries_feedback` | API |
| F7 三路注入 | `test_reference_injection_three_routes` | 单元+API |
| F8 删除双模式/回收站 | `test_delete_index_only` / `test_delete_source_to_trash` | API |
| F9 拖拽/翻页 | E2E `test_dnd_import` / `test_lightbox_nav` | E2E |
| F10 watcher ≤35s | `test_watcher_ingest_under_35s` | 集成（标记 slow） |
| F11 提案零变化 | `test_proposal_no_db_change_until_approve` | API |
| F12 直读只读/过滤 | `test_readonly_conn` / `test_views_exclude_hidden` | 集成 |
| F13 首命中即停/试跑 | `test_rules_first_match_wins` / `test_rule_dry_run` | 单元 |
| F14 级联合并 | `test_category_merge_cascades` | 集成 |
| F15 全通路不可见 | `test_hidden_invisible_everywhere` | API+集成 |
| 横切 性能指标 | `tests/perf/test_benchmarks.py` | perf |
| 横切 密钥不落日志 | `test_secret_never_logged` | 集成 |

---

## 5. 回归与冒烟清单

**每次发布前手工冒烟（5 分钟）**：

1. `python server.py` 启动，浏览器打开无控制台报错
2. 登记一个测试目录 → 扫描入库 → 缩略图出现
3. 无 Key 状态：识图队列显示暂停与中文原因，**入库/搜索照常**
4. 配一个假 Key + 限速 1/min：观察 ≥3 秒间隔
5. 搜中文词 → 混合结果；搜"报错码"命中 OCR 截图
6. 隐藏一张图 → 搜索/直读视图均不可见 → 恢复
7. 危险操作确认词错误 → 拒绝
8. 设置页密钥明文可见；`data/logs` 中 grep 密钥零命中

**CI 自动回归** = 第 4 章矩阵全量 + 覆盖率门槛。

---

## 6. 性能测试方案

| 基准 | 方法 | 通过线 |
|---|---|---|
| 关键词搜索 | `seed_10k` 合成 10 万库，执行 100 次查询取 P95 | < 100ms |
| 向量搜索 | 同上 | < 300ms |
| 深分页 | cursor 翻到第 1000 页 | 无重复遗漏，P95 < 100ms |
| 扫描吞吐 | 10 万个 1×1 PNG | ≥ 300 文件/秒 |
| 仪表盘 | 冷/热各 50 次 | P95 < 500ms |

- 标记 `-m perf`，不进默认 CI（夜间/手动触发），结果记录进 `docs/perf/` 基线文件，**劣化 > 20% 即人工介入**
- 硬件基线写在基线文件头（避免跨机器误报）

---

## 7. 测试通过标准（发布闸门）

1. `pytest` 全绿（含集成与 API；E2E 可选跑）
2. 覆盖率：全局 ≥ 80%，`domain` ≥ 90%
3. ruff / mypy 零告警
4. AC 追踪矩阵无"未覆盖"行
5. 冒烟清单 8 项人工过一遍
6. `srs.md` / `design.md` / 代码三方一致（文档一致性 AC）
