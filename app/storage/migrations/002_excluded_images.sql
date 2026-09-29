-- 002 删除索引后的路径排除：只删索引（mode=index）时登记，增量扫描直接跳过，
-- 避免源文件仍在盘上导致下次扫描被当成新图重新入库。
-- 注销目录时随索引一并清除（重新登记 = 全量重来）。

CREATE TABLE excluded_images (
  dir_id     INTEGER NOT NULL,
  path       TEXT NOT NULL,
  deleted_at TEXT NOT NULL,
  PRIMARY KEY(dir_id, path)
);
