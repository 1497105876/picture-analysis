# 详细设计说明（DDD）

> 回答"数据怎么存、接口长什么样、状态怎么流转、关键算法怎么算"。
> 需求依据 `srs.md`，分层约束见 `architecture.md`。本文档是 **SQLite 直读契约**与 **REST 契约**的权威来源，任何破坏性变更必须升版本并同步文档。

---

## 1. 数据库总体设计

- 单文件 SQLite（WAL 模式），路径 `data/library.db`
- 所有表使用外键（`PRAGMA foreign_keys=ON`），时间统一 `TEXT`（ISO-8601 UTC）
- 迁移：`PRAGMA user_version` + `app/storage/migrations/NNN_*.sql`，**只前进不回滚**，启动时自动应用
- 命名：表 `snake_case` 复数，布尔 `INTEGER 0/1`，JSON 字段 `*_json TEXT`

### 1.1 表清单

| 分组 | 表 | 用途 |
|---|---|---|
| 目录 | `directories` | 手动登记的根目录（**唯一被允许读取的路径来源**） |
| 图片 | `images` | 可见图片主表（隐藏图片物理移出，见 1.4） |
| 图片 | `hidden_images` | 隐藏区图片（同结构，**不在任何文档化对象中**） |
| 图片 | `trash` | 删除源文件的回收站记录 |
| 分析 | `analyses` | AI 识图产出（append-only 历史） |
| 分析 | `ai_tags` | AI 标签（与人工标签分开） |
| 分析 | `image_elements` | AI 元素清单 |
| 分析 | `ocr_results` | **OCR 独立表**：仅识图判定含文字才写入 |
| 分析 | `token_usage` | 成本记账（每次请求 tokens/模型/用途） |
| 人工 | `tags` / `image_tags` | 人工标签主表 / 关联（多值） |
| 人工 | `categories` | 分类字典（内置 6 类 + 自建） |
| 人工 | `custom_fields` / `custom_field_values` | 自定义字段与取值 |
| 资料库 | `entities` / `entity_aliases` | 实体卡与别名 |
| 资料库 | `entity_images` / `reference_images` | 手动关联图 / 标准参考图 |
| 检索 | `image_fts` | FTS5 虚拟表（中文预分词） |
| 检索 | `image_vectors` | 向量（BLOB float32） |
| 检索 | `synonyms` / `term_weights` | 同义词组 / 术语加权 |
| 检索 | `search_history` | 搜索历史（可开关可清空） |
| 规则 | `rules` | 分类规则（IF→THEN，优先级 + 开关） |
| 相册 | `smart_albums` | 智能相册（命名查询快照） |
| 任务 | `jobs` / `job_events` | 识图/扫描/嵌入队列与事件流 |
| 提案 | `proposals` | 对话产生的实体/标签提案（待人工批准） |
| 设置 | `settings` / `audit_log` | 配置 KV（JSON）/ 变更审计 |

### 1.2 核心 DDL（节选）

```sql
CREATE TABLE directories (
  id          INTEGER PRIMARY KEY,
  path        TEXT NOT NULL UNIQUE,      -- 规范化绝对路径
  recursive   INTEGER NOT NULL DEFAULT 1,
  enabled     INTEGER NOT NULL DEFAULT 1,
  offline     INTEGER NOT NULL DEFAULT 0, -- 盘符不可达
  privacy     INTEGER NOT NULL DEFAULT 0, -- 永不外发云端
  frozen      INTEGER NOT NULL DEFAULT 0, -- 冻结：不扫描不识图
  ocr_policy  TEXT    NOT NULL DEFAULT 'auto', -- auto | on | off
  profile_json TEXT   NOT NULL DEFAULT '{}',   -- 目录级模型/档位覆盖
  last_scanned_at TEXT,
  created_at  TEXT NOT NULL
);

CREATE TABLE images (
  id            INTEGER PRIMARY KEY,
  dir_id        INTEGER NOT NULL REFERENCES directories(id),
  path          TEXT NOT NULL,
  filename      TEXT NOT NULL,
  ext           TEXT NOT NULL,
  md5           TEXT NOT NULL,             -- 内容身份（移动改名认回）
  dhash         TEXT NOT NULL,             -- 相似聚类用
  width INTEGER, height INTEGER, bytes INTEGER,
  mtime         REAL   NOT NULL,
  exif_taken_at TEXT,                      -- EXIF 拍摄时间
  dominant_color TEXT,
  analysis_state TEXT NOT NULL DEFAULT 'unanalyzed',
                 -- unanalyzed|queued|running|done|failed|skipped
  category_ai TEXT, category_manual TEXT,  -- 取值时 COALESCE(manual, ai)
  description_ai TEXT, description_manual TEXT,
  has_text     INTEGER NOT NULL DEFAULT 0, -- 识图"含文字"判定（OCR 触发依据）
  correction_count INTEGER NOT NULL DEFAULT 0,
  last_feedback TEXT,                      -- 最近一次打回的纠正说明
  notes TEXT, rating INTEGER NOT NULL DEFAULT 0,
  favorite INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(dir_id, path)
);
CREATE INDEX idx_images_md5   ON images(md5);
CREATE INDEX idx_images_state ON images(analysis_state);
CREATE INDEX images_category  ON images(category_manual, category_ai);

CREATE TABLE ocr_results (          -- OCR 独立表
  image_id   INTEGER PRIMARY KEY,    -- 每图最多一条最新结果
  text       TEXT NOT NULL DEFAULT '',
  model      TEXT NOT NULL,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE ai_tags (              -- AI 标签，与人工分开
  image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  tag      TEXT NOT NULL, rank INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(image_id, tag)
);
CREATE TABLE image_tags (           -- 人工标签
  image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  tag_id   INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY(image_id, tag_id)
);

CREATE VIRTUAL TABLE image_fts USING fts5(
  image_id UNINDEXED,               -- 定位键
  filename, description, tags, elements, notes,
  tokenize = 'unicode61 remove_diacritics 2'
);
-- 中文友好由写入侧保证：description/tags/elements 经 jieba 分词后以空格写入

CREATE TABLE image_vectors (
  image_id INTEGER PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
  model    TEXT NOT NULL,
  dim      INTEGER NOT NULL,
  vector   BLOB NOT NULL             -- float32 小端，numpy 直读
);

CREATE TABLE proposals (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL CHECK(type IN ('entity','tag')),
  payload_json TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'chat',
  status TEXT NOT NULL DEFAULT 'pending'
         CHECK(status IN ('pending','approved','rejected')),
  created_at TEXT NOT NULL, decided_at TEXT
);
```

### 1.3 FTS 与向量的写入时机

| 事件 | FTS | 向量 |
|---|---|---|
| 入库 | 立即（文件名） | 不写 |
| 识图完成 | 重建该行（描述/AI标签/元素） | 写入 |
| 人工修正 | 立即重建（AC：FTS 即时更新） | 队列异步重算 |
| 标签/备注/评分变更 | 立即 | 备注变更→队列重算 |
| 隐藏/恢复 | 删除/恢复该行 | 保留（不参与检索） |

### 1.4 隐藏区的物理分表

- 隐藏 = `images` 行**整体迁移**到 `hidden_images`（同 DDL，id 不变；子表 `ai_tags` 等按 `image_id` 照常级联，但因主表行不存在，任何以 `images` 为起点的查询天然不可见）
- 恢复 = 迁回。迁移在同一事务内完成
- 识图/OCR/备份照常：worker 经 `image_repo` 路由到当前所在表
- **边界声明（威胁模型）**：直读契约 = 本文档化的表与视图；`hidden_images` 不出现在任何文档化对象中。本机持有文件者理论上可枚举 `sqlite_master`，物理强隔离需加密，超出本项目范围——契约层**无任何参数可绕过**

### 1.5 关键索引与预期性能

| 查询 | 索引 | 目标 |
|---|---|---|
| 关键词检索 | FTS5 内置倒排 | <100ms @10 万 |
| 向量检索 | 全表扫描 + numpy 批量余弦（10 万×768 ≈ 300MB 内存上限可控，分块计算） | <300ms |
| 深分页 | `ORDER BY id` cursor（游标键 = 排序值+id） | 无重复遗漏 |
| 目录浏览 | `idx_images_dir` + mtime 排序 | 首屏 <300ms |
| 增量扫描 | `md5`、`(dir_id,path)` 唯一索引 | 扫描 ≥300 文件/秒 |

---

## 2. SQLite 直读契约（对外接口）

### 2.1 连接规范

```python
con = sqlite3.connect("file:.../library.db?mode=ro", uri=True)  # 必须只读打开
```

- 只读打开：**物理上无法写入**，天然满足只读铁律
- 管理操作（扫描/识图）**不在数据库中暴露任何可执行入口**（无任务表写权限）

### 2.2 文档化对象（契约清单）

```sql
-- 图片主视图（已内置：隐藏过滤 + 人工优先 COALESCE）
CREATE VIEW v_images AS
SELECT i.id, i.path, i.filename, i.md5,
       i.width, i.height, i.mtime, i.exif_taken_at,
       COALESCE(i.category_manual, i.category_ai)   AS category,
       CASE WHEN i.category_manual IS NOT NULL THEN 'manual'
            WHEN i.category_ai     IS NOT NULL THEN 'ai' END AS category_source,
       COALESCE(i.description_manual, i.description_ai) AS description,
       i.rating, i.favorite, i.notes,
       i.analysis_state, i.correction_count, i.created_at, i.updated_at
FROM images i;

-- 识别内容视图（AI 原始产出，含 OCR 文字）
CREATE VIEW v_analysis AS
SELECT a.image_id, a.category, a.description,
       (SELECT group_concat(tag) FROM ai_tags t WHERE t.image_id=a.image_id) AS ai_tags,
       (SELECT group_concat(element) FROM image_elements e WHERE e.image_id=a.image_id) AS elements,
       (SELECT text FROM ocr_results o WHERE o.image_id=a.image_id) AS ocr_text,
       a.has_text, a.created_at
FROM analyses a;

-- 标签（人工与 AI 合并视图）
CREATE VIEW v_tags AS
SELECT image_id, tag, 'manual' AS source FROM image_tags jt
  JOIN tags t ON t.id = jt.tag_id
UNION ALL
SELECT image_id, tag, 'ai' FROM ai_tags;

-- 分类字典 / 资料库 / 目录
CREATE VIEW v_categories AS SELECT * FROM categories WHERE active = 1;
CREATE VIEW v_entities   AS SELECT * FROM entities  WHERE active = 1;
CREATE VIEW v_directories AS SELECT id, path, recursive, offline, privacy FROM directories;
```

### 2.3 直读规则（逐条对应 FR-F12）

| 规则 | 保证方式 |
|---|---|
| 只读 | 连接 `mode=ro`；无任何"管理"表可写 |
| 隐藏区不可见 | 隐藏行物理在 `hidden_images`，文档化对象只覆盖 `images`；**无 include_hidden 之类参数** |
| 人工优先 | 视图内 `COALESCE(manual, ai)`，并给出 `category_source` 标注 |
| 字段语义稳定 | 本清单即契约；破坏性变更 = 升 `SCHEMA_VERSION` 并同步 `design.md` |
| 提案批准前库零变化 | `proposals.status='pending'`；实体/标签在批准前**不出现**在 `entities`/`tags` |

### 2.4 查询示例（随库提供 `docs/examples/`）

```sql
-- 上个月拍摄、分类为“风景”的可见图片
SELECT id, path, description FROM v_images
WHERE category = '风景'
  AND date(exif_taken_at) >= date('now','-1 month')
ORDER BY exif_taken_at DESC LIMIT 50;

-- 按关键词找图（直读方自行查 FTS，注意中文需 jieba 预分词或用 LIKE）
SELECT v.id, v.path FROM image_fts f JOIN v_images v ON v.id = f.image_id
WHERE image_fts MATCH '傍晚 海岸';
```

---

## 3. REST API 设计

- 前缀 `/api`，JSON；仅监听 `127.0.0.1`
- 认证：本机单用户，**不做登录**（安全边界 = 只监听回环地址）
- 统一错误结构：

```json
{ "error": { "code": "RATE_LIMITED", "message": "识图已达每分钟 20 次上限，已暂停 12 秒", "detail": {} } }
```

### 3.1 端点清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 存活与版本 |
| GET/POST | `/api/directories` | 列出 / 登记目录（POST 先返回预估再 `?confirm=1` 执行） |
| DELETE | `/api/directories/{id}` | 注销目录（默认不删源文件） |
| POST | `/api/scan/{dir_id}` | 触发增量扫描 |
| GET | `/api/images` | 图片列表：`q`、`cursor`、`limit`、多维筛选、排序 |
| GET | `/api/images/{id}` | 详情（含 AI 原始产出、OCR、纠错史） |
| PATCH | `/api/images/{id}` | 人工修正（分类/描述/标签/评分/收藏/备注/自定义字段） |
| POST | `/api/images/{id}/hide` \| `/unhide` | 隐藏 / 恢复（支持批量 `ids`） |
| POST | `/api/images/{id}/redo` | 打回重识别（带 `feedback`） |
| DELETE | `/api/images/{id}` | 删除（`?mode=index` 默认 / `?mode=source` 走回收站） |
| GET | `/api/search` | 混合检索（关键词+语义 RRF，`mode` 默认 `hybrid`） |
| GET | `/api/similar/{id}` | 以图搜图 |
| GET | `/api/stats/dashboard` | 仪表盘聚合 |
| GET/POST/PATCH | `/api/entities`… | 资料库实体 CRUD + 参考图 |
| GET/POST/PATCH | `/api/rules`… | 规则 CRUD + `POST /api/rules/try` 试跑 |
| GET/POST/PATCH | `/api/albums`… | 智能相册 CRUD 与回放 |
| GET/POST | `/api/categories` | 分类字典（内置 6 类不可删改） |
| GET/POST | `/api/proposals` · `POST /api/proposals/{id}/approve`\|`/reject` | 提案队列与批准 |
| GET/POST | `/api/chat` | 对话问答（SSE 流式可选，超字数 400 截断） |
| GET/POST | `/api/jobs` · `POST /api/jobs/{id}/cancel` | 队列任务查询/停止（实时进度） |
| GET/PUT | `/api/settings` | schema 驱动配置（`GET` 返回分组+控件 schema 与当前值） |
| POST | `/api/settings/test` | 连接探测 |
| GET | `/api/logs` | 运维日志查询 |

### 3.2 分页（cursor）

```
GET /api/images?sort=mtime&order=desc&limit=100&cursor=eyJpZCI6MTIzfQ==
```

- `cursor` = base64(JSON `{sort_value, id}`)；服务端 `WHERE (sort_value, id) < (?, ?)` 复合条件
- 响应 `{ "items": [...], "next_cursor": "...", "has_more": true }`；**禁止 OFFSET 深分页**

### 3.3 错误码表（节选）

| code | HTTP | 场景 |
|---|---|---|
| `DIR_NOT_FOUND` | 404 | 目录不存在/不可达 |
| `DIR_ALREADY_REGISTERED` | 409 | 重复登记（含父子重叠） |
| `RATE_LIMITED` | 429 | 触发 20 次/分钟限速 |
| `DAILY_BUDGET_EXCEEDED` | 429 | 每日 token 上限触顶 |
| `AI_SERVICE_UNAVAILABLE` | 503 | 识图/嵌入/对话服务不可用（**软失败：仅该功能降级**） |
| `CONFIRM_WORD_MISMATCH` | 400 | 危险操作确认词不匹配 |
| `HIDDEN_NOT_BYPASSABLE` | 400 | 任何试图查询隐藏区的参数 |
| `VALIDATION_ERROR` | 422 | pydantic 校验失败（中文人话 message） |

---

## 4. 识图队列与状态机

### 4.1 任务状态机

```
            ┌──────── cancel ────────┐
            ▼                        │
 pending → running → succeeded       │
    │         │                      │
    │         └→ failed ─(重试<上限)─┘→ pending
    │                    └(超上限)→ dead（待人工处理）
    └→ paused（限速 / 每日上限 / 无密钥 / 服务不可达）
              └─条件恢复→ pending
```

- `jobs` 表持久化；**进程重启后 `running` 复位为 `pending`（断点续跑）**
- 图片侧 `images.analysis_state` 与任务联动：`unanalyzed → queued → running → done|failed|skipped`
- 优先级：`priority_score = 档案权重(目录策略) + 新图加成`，同分 FIFO

### 4.2 软失败契约（可靠性核心）

| 失败点 | 行为 | 用户可见 |
|---|---|---|
| 识图请求超时/5xx | 任务退避重试（上限可配），不阻塞队列 | 进度条 + 中文失败原因 |
| 服务整体不可达 | 队列 `paused`，指数退避探测恢复 | 设置页横幅"识图服务不可用" |
| 嵌入失败 | 语义检索自动降级为关键词 | 搜索页小字提示 |
| 对话失败 | 返回引导语 | 对话页引导卡片 |
| 解析失败（AI 返回非法 JSON） | 按字段降级入库可得部分 | 记录日志，不报错给用户 |

**不变式**：任何 AI 依赖的失败，都不得影响扫描入库、人工管理、关键词搜索三条主链路。

### 4.3 成本记账与每日上限

```
每次请求 → token_usage(purpose, model, tokens_in, tokens_out)
预估 = 历史同模型平均 tokens/张 × 张数（批量前展示）
每日上限：SUM(tokens) WHERE date=今天 ≥ limit → jobs 全部 paused
恢复：日期变更自动 resume + 通知
```

---

## 5. 限速器（默认 20 次/分钟）

### 5.1 规格

| 参数 | 默认值 | 说明 |
|---|---|---|
| `rate_limit_per_minute` | **20** | 滑动窗口（60s）内最多 20 次请求 |
| `min_interval_seconds` | **3** | 相邻请求强制间隔 ≥3 秒（双保险） |
| 可调范围 | 1~60 /分钟 | 设置页 G3 组，保存即生效 |

### 5.2 算法（领域层纯函数，可单测）

```python
# 伪代码：滑动窗口 + 最小间隔，二者同时满足才放行
def allow(now: float, history: deque[float], cfg: RateConfig) -> Decision:
    while history and now - history[0] > 60.0:
        history.popleft()
    if now - history[-1] < cfg.min_interval:      # 3 秒间隔
        return Decision(wait=cfg.min_interval - (now - history[-1]))
    if len(history) >= cfg.per_minute:            # 20 次/分钟
        return Decision(wait=60.0 - (now - history[0]))
    return Decision(allow=True)
```

- 全局限额（所有识图请求共享一个计数器），**跨线程用锁保护**
- 拒绝时任务 `paused` 并记录 `wait` 秒，UI 显示"已达每分钟 20 次上限，N 秒后继续"
- 过夜限速在此之上叠加（更小的 per_minute）

---

## 6. OCR 按需触发流程

```
VLM 请求（prompt 含“has_text 布尔字段”）
   → 返回 has_text = true ？
        ├─ 否 → 跳过 OCR，images.has_text=0，ocr_results 无行（零开销）
        └─ 是 → 检查目录 ocr_policy：
                 auto → 追加 OCR 请求（计入同一限速器与预算）
                 on   → 必定追加
                 off   → 跳过（仍标记 has_text 供规则使用）
   → 写 ocr_results（独立表，覆盖式最新一条）
   → 触发规则引擎第二阶段求值（OCR 文本条件）
```

- 阈值：`ocr_min_chars`（判定置信/长度阈值，G5 组）
- 识图 prompt 的 `has_text` 判定与 OCR 请求**共享同一次识图的记账周期**，OCR 单独记 `purpose='ocr'`

---

## 7. 配置机制（schema 驱动）

```jsonc
// 设置项定义在代码中（一个数据 = 一项配置）
{
  "group": "G3",                    // 配置组（G1~G18）
  "key": "rate_limit_per_minute",
  "label": "识图限速（次/分钟）",
  "type": "int",                    // int|float|bool|select|text|secret|kv-list|...
  "default": 20,
  "min": 1, "max": 60,
  "help": "默认 20 次/分钟，即相邻请求至少间隔 3 秒",
  "effective": "immediate"          // immediate | on-save（3.8-3 要求标注生效时机）
}
```

- `GET /api/settings` 返回 **schema + 当前值 + 脏状态**，前端**零硬编码**渲染表单
- `secret` 类型：值存 `.env`，API 读回明文（**界面可见可复制**），日志/审计/导出自动脱敏
- 变更写 `audit_log`（before/after），支持单项回滚（G16）

---

## 8. 日志与可观测

| 项 | 规范 |
|---|---|
| 级别 | DEBUG/INFO/WARNING/ERROR，G7 可配 |
| 输出 | 控制台 + `data/logs/app.log`（轮转：10MB × 5） |
| 脱敏 | 密钥、`.env` 值、Authorization 头一律 `***`（**安全 AC**） |
| 结构 | `时间 级别 模块 消息 key=value`；任务事件另入 `job_events` 供 UI 进度回放 |
| 关键埋点 | 扫描吞吐、识图延迟/重试数、限速等待时长、检索耗时（分路）、直读无（不介入） |
