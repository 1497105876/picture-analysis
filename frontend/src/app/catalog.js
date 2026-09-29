// 分类字典与自定义字段：多个页面都要用（图库筛选、抽屉表单、分类页），统一缓存到这里。
import { reactive } from "vue";

import { api, safe } from "./api.js";

export const catalog = reactive({
  categories: [],
  customFields: [],
  loaded: false,
});

export async function loadCatalog({ force = false } = {}) {
  if (catalog.loaded && !force) return catalog;
  const [cats, fields] = await Promise.all([
    safe(() => api.categories(), []),
    safe(() => api.customFields(), []),
  ]);
  catalog.categories = cats || [];
  catalog.customFields = fields || [];
  catalog.loaded = true;
  return catalog;
}

export function categoryOptions() {
  return catalog.categories.map((c) => ({
    value: c.name,
    label: c.emoji ? `${c.emoji} ${c.name}` : c.name,
  }));
}

export function categoryColor(name) {
  const hit = catalog.categories.find((c) => c.name === name);
  return hit?.color || "";
}

/** 单本变更后在本地字典里同步，避免整页重新拉取 */
export function upsertCategory(row) {
  const i = catalog.categories.findIndex((c) => c.name === row.name);
  if (i >= 0) catalog.categories[i] = { ...catalog.categories[i], ...row };
  else catalog.categories.push(row);
}

export function dropCategory(name) {
  const i = catalog.categories.findIndex((c) => c.name === name);
  if (i >= 0) catalog.categories.splice(i, 1);
}
