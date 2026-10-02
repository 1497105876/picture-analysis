-- 003 排除表加代理主键。
-- 墓碑要能在界面上被单条定位（恢复 / 移除记录），原来只有 (dir_id, path) 复合主键，
-- 把整条路径塞进 URL 又长又容易出问题。重建表补一个自增 id，历史墓碑一并迁移。

CREATE TABLE excluded_images_new (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  dir_id     INTEGER NOT NULL,
  path       TEXT NOT NULL,
  deleted_at TEXT NOT NULL
);

INSERT INTO excluded_images_new(dir_id, path, deleted_at)
  SELECT dir_id, path, deleted_at FROM excluded_images ORDER BY rowid;

DROP TABLE excluded_images;

ALTER TABLE excluded_images_new RENAME TO excluded_images;

CREATE UNIQUE INDEX IF NOT EXISTS ux_excluded_dir_path ON excluded_images(dir_id, path);
