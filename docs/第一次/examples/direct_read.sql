-- SQLite 直读查询示例（随库提供给本机 Agent）
-- 连接方式：必须只读打开
--   sqlite3.connect("file:/path/to/library.db?mode=ro", uri=True)
-- 契约：只允许查询 docs/design.md 第 2.2 节列出的对象；
--       隐藏图片不在其中，且无任何参数可绕过。

-- 1. 基本列表：分类/描述已 COALESCE 人工优先，category_source 标明来源
SELECT id, path, category, category_source, description, rating, favorite
FROM v_images
ORDER BY mtime DESC
LIMIT 50;

-- 2. 上个月拍摄、分类为“风景”的可见图片
SELECT id, path, description, exif_taken_at
FROM v_images
WHERE category = '风景'
  AND date(exif_taken_at) >= date('now', '-1 month')
ORDER BY exif_taken_at DESC;

-- 3. 关键词检索（FTS5；中文写入侧已做 jieba 预分词）
SELECT v.id, v.path, v.description
FROM image_fts f
JOIN v_images v ON v.id = f.image_id
WHERE image_fts MATCH '傍晚 海岸'
ORDER BY rank
LIMIT 20;

-- 4. 查某张图的识别内容（AI 标签 / 元素 / OCR 文字）
SELECT category, description, ai_tags, elements, ocr_text, has_text
FROM v_analysis
WHERE image_id = ?;

-- 5. 标签合并视图：人工与 AI 一并返回，按 source 区分
SELECT tag, source FROM v_tags WHERE image_id = ?;

-- 6. 资料库实体（仅启用中的）
SELECT id, name, category, description FROM v_entities;

-- 7. 目录清单（不含隐私/冻结等内部策略细节之外的敏感信息）
SELECT id, path, recursive, offline, privacy FROM v_directories;

-- 8. 统计示例：与仪表盘同口径（隐藏图片天然不在 v_images 中）
SELECT category, COUNT(*) AS cnt FROM v_images GROUP BY category ORDER BY cnt DESC;
