-- 001 初始结构（图片分析与搜索系统）
-- 说明：图片子表（ai_tags/analyses/ocr/vectors/fts）不设对 images 的外键，
-- 由仓储层显式级联——隐藏区迁移（images <-> hidden_images）需要行可移动。

CREATE TABLE directories (
  id            INTEGER PRIMARY KEY,
  path          TEXT NOT NULL UNIQUE,
  recursive     INTEGER NOT NULL DEFAULT 1,
  enabled       INTEGER NOT NULL DEFAULT 1,
  offline       INTEGER NOT NULL DEFAULT 0,
  privacy       INTEGER NOT NULL DEFAULT 0,
  frozen        INTEGER NOT NULL DEFAULT 0,
  watcher       INTEGER NOT NULL DEFAULT 0,
  ocr_policy    TEXT    NOT NULL DEFAULT 'auto',
  profile_json  TEXT    NOT NULL DEFAULT '{}',
  source        TEXT    NOT NULL DEFAULT 'manual',
  last_scanned_at TEXT,
  created_at    TEXT NOT NULL
);

CREATE TABLE images (
  id            INTEGER PRIMARY KEY,
  dir_id        INTEGER NOT NULL,
  path          TEXT NOT NULL,
  filename      TEXT NOT NULL,
  ext           TEXT NOT NULL,
  md5           TEXT NOT NULL,
  dhash         TEXT NOT NULL DEFAULT '',
  width         INTEGER,
  height        INTEGER,
  bytes         INTEGER,
  mtime         REAL NOT NULL,
  exif_taken_at TEXT,
  dominant_color TEXT,
  analysis_state TEXT NOT NULL DEFAULT 'unanalyzed',
  category_ai   TEXT,
  category_manual TEXT,
  description_ai TEXT,
  description_manual TEXT,
  has_text      INTEGER NOT NULL DEFAULT 0,
  correction_count INTEGER NOT NULL DEFAULT 0,
  last_feedback TEXT,
  notes         TEXT,
  rating        INTEGER NOT NULL DEFAULT 0,
  favorite      INTEGER NOT NULL DEFAULT 0,
  missing       INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  UNIQUE(dir_id, path)
);
CREATE INDEX idx_images_dir    ON images(dir_id);
CREATE INDEX idx_images_md5    ON images(md5);
CREATE INDEX idx_images_dhash  ON images(dhash);
CREATE INDEX idx_images_state  ON images(analysis_state);
CREATE INDEX idx_images_mtime  ON images(mtime);
CREATE INDEX idx_images_taken  ON images(exif_taken_at);
CREATE INDEX idx_images_rating ON images(rating);
CREATE INDEX idx_images_cat    ON images(category_manual, category_ai);

CREATE TABLE hidden_images (
  id            INTEGER PRIMARY KEY,
  dir_id        INTEGER NOT NULL,
  path          TEXT NOT NULL,
  filename      TEXT NOT NULL,
  ext           TEXT NOT NULL,
  md5           TEXT NOT NULL,
  dhash         TEXT NOT NULL DEFAULT '',
  width         INTEGER,
  height        INTEGER,
  bytes         INTEGER,
  mtime         REAL NOT NULL,
  exif_taken_at TEXT,
  dominant_color TEXT,
  analysis_state TEXT NOT NULL DEFAULT 'unanalyzed',
  category_ai   TEXT,
  category_manual TEXT,
  description_ai TEXT,
  description_manual TEXT,
  has_text      INTEGER NOT NULL DEFAULT 0,
  correction_count INTEGER NOT NULL DEFAULT 0,
  last_feedback TEXT,
  notes         TEXT,
  rating        INTEGER NOT NULL DEFAULT 0,
  favorite      INTEGER NOT NULL DEFAULT 0,
  missing       INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX idx_hidden_md5 ON hidden_images(md5);

CREATE TABLE trash (
  id            INTEGER PRIMARY KEY,
  image_id      INTEGER,
  original_path TEXT NOT NULL,
  trash_path    TEXT NOT NULL,
  deleted_at    TEXT NOT NULL
);

CREATE TABLE analyses (
  id            INTEGER PRIMARY KEY,
  image_id      INTEGER NOT NULL,
  category      TEXT,
  description   TEXT,
  has_text      INTEGER NOT NULL DEFAULT 0,
  model         TEXT NOT NULL DEFAULT '',
  tokens_in     INTEGER NOT NULL DEFAULT 0,
  tokens_out    INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL
);
CREATE INDEX idx_analyses_image ON analyses(image_id);

CREATE TABLE ai_tags (
  image_id INTEGER NOT NULL,
  tag      TEXT NOT NULL,
  rank     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(image_id, tag)
);
CREATE INDEX idx_ai_tags_tag ON ai_tags(tag);

CREATE TABLE image_elements (
  image_id INTEGER NOT NULL,
  element  TEXT NOT NULL,
  rank     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(image_id, element)
);

CREATE TABLE ocr_results (
  image_id   INTEGER PRIMARY KEY,
  text       TEXT NOT NULL DEFAULT '',
  model      TEXT NOT NULL DEFAULT '',
  tokens_out INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE token_usage (
  id         INTEGER PRIMARY KEY,
  image_id   INTEGER,
  purpose    TEXT NOT NULL,
  model      TEXT NOT NULL,
  tokens_in  INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_token_usage_day ON token_usage(created_at);

CREATE TABLE tags (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);
CREATE TABLE image_tags (
  image_id INTEGER NOT NULL,
  tag_id   INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY(image_id, tag_id)
);

CREATE TABLE categories (
  id      INTEGER PRIMARY KEY,
  name    TEXT NOT NULL UNIQUE,
  color   TEXT NOT NULL DEFAULT '#64748b',
  emoji   TEXT NOT NULL DEFAULT '',
  builtin INTEGER NOT NULL DEFAULT 0,
  active  INTEGER NOT NULL DEFAULT 1,
  sort    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE custom_fields (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL UNIQUE,
  type         TEXT NOT NULL CHECK(type IN ('text','number','date','select')),
  options_json TEXT NOT NULL DEFAULT '[]',
  sort         INTEGER NOT NULL DEFAULT 0,
  active       INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE custom_field_values (
  field_id   INTEGER NOT NULL REFERENCES custom_fields(id) ON DELETE CASCADE,
  image_id   INTEGER NOT NULL,
  value_text TEXT,
  value_num  REAL,
  value_date TEXT,
  PRIMARY KEY(field_id, image_id)
);

CREATE TABLE entities (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  category    TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  active      INTEGER NOT NULL DEFAULT 1,
  vector      BLOB,
  vector_dim  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL
);
CREATE TABLE entity_aliases (
  entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  alias     TEXT NOT NULL,
  PRIMARY KEY(entity_id, alias)
);
CREATE TABLE entity_images (
  entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  image_id  INTEGER NOT NULL,
  PRIMARY KEY(entity_id, image_id)
);
CREATE TABLE reference_images (
  id        INTEGER PRIMARY KEY,
  entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  path      TEXT NOT NULL,
  sort      INTEGER NOT NULL DEFAULT 0
);

CREATE VIRTUAL TABLE image_fts USING fts5(
  image_id UNINDEXED,
  filename,
  description,
  tags,
  elements,
  notes,
  tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE image_vectors (
  image_id INTEGER PRIMARY KEY,
  model    TEXT NOT NULL,
  dim      INTEGER NOT NULL,
  vector   BLOB NOT NULL
);

CREATE TABLE synonyms (
  id         INTEGER PRIMARY KEY,
  group_name TEXT NOT NULL,
  term       TEXT NOT NULL
);
CREATE TABLE term_weights (
  term   TEXT PRIMARY KEY,
  weight REAL NOT NULL DEFAULT 1.0
);

CREATE TABLE search_history (
  id         INTEGER PRIMARY KEY,
  query      TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE rules (
  id             INTEGER PRIMARY KEY,
  name           TEXT NOT NULL,
  priority       INTEGER NOT NULL DEFAULT 0,
  enabled        INTEGER NOT NULL DEFAULT 1,
  condition_json TEXT NOT NULL,
  action_json    TEXT NOT NULL,
  created_at     TEXT NOT NULL
);

CREATE TABLE smart_albums (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL UNIQUE,
  query_json TEXT NOT NULL,
  sort_json  TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE jobs (
  id           INTEGER PRIMARY KEY,
  type         TEXT NOT NULL CHECK(type IN ('scan','analyze','embed')),
  image_id     INTEGER,
  dir_id       INTEGER,
  state        TEXT NOT NULL DEFAULT 'pending'
               CHECK(state IN ('pending','running','succeeded','failed','dead','paused')),
  attempts     INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  priority     INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL DEFAULT '{}',
  error        TEXT,
  retry_at     REAL,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);
CREATE INDEX idx_jobs_state ON jobs(state, priority DESC, id);

CREATE TABLE job_events (
  id         INTEGER PRIMARY KEY,
  job_id     INTEGER NOT NULL,
  level      TEXT NOT NULL DEFAULT 'info',
  message    TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE proposals (
  id           INTEGER PRIMARY KEY,
  type         TEXT NOT NULL CHECK(type IN ('entity','tag')),
  payload_json TEXT NOT NULL,
  source       TEXT NOT NULL DEFAULT 'chat',
  status       TEXT NOT NULL DEFAULT 'pending'
               CHECK(status IN ('pending','approved','rejected')),
  image_id     INTEGER,
  created_at   TEXT NOT NULL,
  decided_at   TEXT
);

CREATE TABLE settings (
  key        TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE audit_log (
  id          INTEGER PRIMARY KEY,
  scope       TEXT NOT NULL DEFAULT 'settings',
  key         TEXT NOT NULL,
  before_json TEXT,
  after_json  TEXT,
  action      TEXT NOT NULL,
  created_at  TEXT NOT NULL
);

CREATE TABLE notices (
  id         INTEGER PRIMARY KEY,
  kind       TEXT NOT NULL,
  level      TEXT NOT NULL DEFAULT 'info',
  message    TEXT NOT NULL,
  read       INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

-- 直读契约视图（隐藏区过滤 + 人工优先 COALESCE）
CREATE VIEW v_images AS
SELECT i.id, i.path, i.filename, i.md5,
       i.width, i.height, i.mtime, i.exif_taken_at,
       COALESCE(i.category_manual, i.category_ai) AS category,
       CASE WHEN i.category_manual IS NOT NULL THEN 'manual'
            WHEN i.category_ai     IS NOT NULL THEN 'ai'
            ELSE NULL END AS category_source,
       COALESCE(i.description_manual, i.description_ai) AS description,
       i.rating, i.favorite, i.notes,
       i.analysis_state, i.correction_count, i.created_at, i.updated_at
FROM images i;

CREATE VIEW v_analysis AS
SELECT a.image_id, a.category, a.description, a.has_text,
       (SELECT group_concat(tag, ',') FROM ai_tags t WHERE t.image_id = a.image_id) AS ai_tags,
       (SELECT group_concat(element, ',') FROM image_elements e WHERE e.image_id = a.image_id) AS elements,
       (SELECT text FROM ocr_results o WHERE o.image_id = a.image_id) AS ocr_text,
       a.created_at
FROM analyses a;

CREATE VIEW v_tags AS
SELECT jt.image_id, t.name AS tag, 'manual' AS source
FROM image_tags jt JOIN tags t ON t.id = jt.tag_id
UNION ALL
SELECT image_id, tag, 'ai' FROM ai_tags;

CREATE VIEW v_categories AS
SELECT id, name, color, emoji, builtin, sort FROM categories WHERE active = 1;

CREATE VIEW v_entities AS
SELECT id, name, category, description, created_at FROM entities WHERE active = 1;

CREATE VIEW v_directories AS
SELECT id, path, recursive, offline, privacy, frozen FROM directories;
