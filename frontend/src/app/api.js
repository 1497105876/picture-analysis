// API 客户端。
// 约定：① 所有请求走相对路径 /api/...（dev 由 vite 代理，prod 由 FastAPI 同源托管）
//      ② 错误一律规范化为 Error(message) + err.code / err.status，message 取自后端人话
//      ③ 除 GET 外，是否提示由调用方决定；这里只负责抛错
import { notify } from "./toast.js";

function buildUrl(url, params) {
  if (!params) return url;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) {
      if (v.length) qs.set(k, v.join(","));
    } else {
      qs.set(k, String(v));
    }
  }
  const text = qs.toString();
  return text ? `${url}${url.includes("?") ? "&" : "?"}${text}` : url;
}

class ApiError extends Error {
  constructor(message, status, code, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function request(method, url, { body, params } = {}) {
  const init = { method, headers: {} };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(buildUrl(url, params), init);
  } catch {
    throw new ApiError("连不上后端服务，先把它跑起来（python server.py）", 0, "NETWORK");
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    throw new ApiError(
      data?.error?.message || `请求失败（HTTP ${res.status}）`,
      res.status,
      data?.error?.code || `HTTP_${res.status}`,
      data?.error?.detail,
    );
  }
  return data;
}

/**
 * 带兜底的请求：失败时 toast 并返回 null，不向上抛。
 * 用于「没有数据就算了」的场景（ biomarkers、轮询、可选信息块）。
 */
export async function safe(fn, fallback = null, opts = {}) {
  try {
    return await fn();
  } catch (e) {
    if (opts.silent !== true) notify(e.message, "error");
    return fallback;
  }
}

export const http = {
  get: (url, params) => request("GET", url, { params }),
  post: (url, body, params) => request("POST", url, { body: body ?? {}, params }),
  put: (url, body) => request("PUT", url, { body: body ?? {} }),
  patch: (url, body) => request("PATCH", url, { body: body ?? {} }),
  del: (url, params) => request("DELETE", url, { params }),
  upload: async (file, onBatch) => {
    const form = new FormData();
    form.append("file", file);
    let res;
    try {
      res = await fetch("/api/upload", { method: "POST", body: form });
    } catch {
      throw new ApiError("连不上后端服务", 0, "NETWORK");
    }
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new ApiError(data?.error?.message || "上传失败", res.status, data?.error?.code);
    }
    onBatch?.(data);
    return data;
  },
};

// ---------------------------------------------------------------------------
// 端点清单：与后端 6 个路由模块一一对应
// ---------------------------------------------------------------------------

export const api = {
  // ---- system.py ----
  health: () => http.get("/api/health"),
  notices: (limit = 50) => http.get("/api/notices", { limit }),
  clearNotices: () => http.del("/api/notices"),
  logs: (lines = 200) => http.get("/api/logs", { lines }),

  // ---- library.py 目录 ----
  directories: () => http.get("/api/directories"),
  estimateDirectory: (payload) => http.post("/api/directories", payload),
  registerDirectory: (payload) => http.post("/api/directories?confirm=1", payload),
  patchDirectory: (id, payload) => http.patch(`/api/directories/${id}`, payload),
  deleteDirectory: (id) => http.del(`/api/directories/${id}`),
  scanDirectory: (id) => http.post(`/api/scan/${id}`, {}),

  // ---- library.py 图片 ----
  images: (params) => http.get("/api/images", params),
  hidden: (params) => http.get("/api/hidden", params),
  imageDetail: (id) => http.get(`/api/images/${id}`),
  patchImage: (id, payload) => http.patch(`/api/images/${id}`, payload),
  hideImage: (id) => http.post(`/api/images/${id}/hide`, {}),
  unhideImage: (id) => http.post(`/api/images/${id}/unhide`, {}),
  redoImage: (id, feedback) => http.post(`/api/images/${id}/redo`, { feedback }),
  renameImage: (id, name) => http.post(`/api/images/${id}/rename`, { name }),
  moveImage: (id, dirId) => http.post(`/api/images/${id}/move`, { dir_id: dirId }),
  deleteImage: (id, { mode = "index", confirm } = {}) =>
    http.del(`/api/images/${id}`, { mode, confirm: confirm || undefined }),
  batch: (op, ids, payload) => http.post("/api/images/batch", { op, ids, payload }),
  similar: (id, limit = 24) => http.get(`/api/images/${id}/similar`, { limit }),
  exportImages: (ids, format = "json") => http.post("/api/export", { ids, format }),

  // ---- library.py 检索 ----
  search: (params) => http.get("/api/search", params),
  searchHistory: () => http.get("/api/search/history"),
  clearSearchHistory: () => http.del("/api/search/history"),

  // ---- knowledge.py 分类 ----
  categories: () => http.get("/api/categories"),
  addCategory: (payload) => http.post("/api/categories", payload),
  patchCategory: (name, payload) => http.patch(`/api/categories/${encodeURIComponent(name)}`, payload),
  deleteCategory: (name) => http.del(`/api/categories/${encodeURIComponent(name)}`),

  // ---- knowledge.py 实体 ----
  entities: (includeInactive = false) => http.get("/api/entities", { include_inactive: includeInactive ? 1 : 0 }),
  entity: (id) => http.get(`/api/entities/${id}`),
  addEntity: (payload) => http.post("/api/entities", payload),
  patchEntity: (id, payload) => http.patch(`/api/entities/${id}`, payload),
  deleteEntity: (id) => http.del(`/api/entities/${id}`),
  addReference: (id, path) => http.post(`/api/entities/${id}/references`, { path }),
  removeReference: (id, refId) => http.del(`/api/entities/${id}/references/${refId}`),
  linkEntity: (id, imageId) => http.post(`/api/entities/${id}/link`, { image_id: imageId }),
  unlinkEntity: (id, imageId) => http.del(`/api/entities/${id}/link/${imageId}`),

  // ---- knowledge.py 规则 ----
  rules: () => http.get("/api/rules"),
  addRule: (payload) => http.post("/api/rules", payload),
  patchRule: (id, payload) => http.patch(`/api/rules/${id}`, payload),
  deleteRule: (id) => http.del(`/api/rules/${id}`),
  tryRule: (condition, limit = 50) => http.post("/api/rules/try", { condition, limit }),
  recomputeRules: (phase) => http.post("/api/rules/recompute", { phase }),

  // ---- knowledge.py 智能相册 ----
  albums: () => http.get("/api/albums"),
  addAlbum: (payload) => http.post("/api/albums", payload),
  patchAlbum: (id, payload) => http.patch(`/api/albums/${id}`, payload),
  deleteAlbum: (id) => http.del(`/api/albums/${id}`),
  albumImages: (id, params) => http.get(`/api/albums/${id}/images`, params),

  // ---- knowledge.py 提案 ----
  proposals: (status) => http.get("/api/proposals", { status: status || undefined }),
  approveProposal: (id) => http.post(`/api/proposals/${id}/approve`, {}),
  rejectProposal: (id) => http.post(`/api/proposals/${id}/reject`, {}),

  // ---- knowledge.py 自定义字段 / 同义词 / 权重 ----
  customFields: () => http.get("/api/custom-fields"),
  addCustomField: (payload) => http.post("/api/custom-fields", payload),
  deleteCustomField: (id) => http.del(`/api/custom-fields/${id}`),
  synonyms: () => http.get("/api/synonyms"),
  putSynonyms: (group, terms) => http.put("/api/synonyms", { group, terms }),
  termWeights: () => http.get("/api/term-weights"),
  putTermWeight: (term, weight) => http.put("/api/term-weights", { term, weight }),

  // ---- ops.py ----
  jobs: (state) => http.get("/api/jobs", { state: state || undefined }),
  jobEvents: (id) => http.get(`/api/jobs/${id}/events`),
  cancelJob: (id) => http.post(`/api/jobs/${id}/cancel`, {}),
  retryJob: (id) => http.post(`/api/jobs/${id}/retry`, {}),
  clearJobs: () => http.del("/api/jobs"),
  dashboard: () => http.get("/api/stats/dashboard"),
  duplicates: (perceptual, threshold) =>
    http.get("/api/stats/duplicates", { perceptual: perceptual ? 1 : 0, threshold }),
  cleanup: () => http.get("/api/stats/cleanup"),
  systemStats: () => http.get("/api/stats/system"),
  trash: () => http.get("/api/trash"),
  restoreTrash: (id) => http.post(`/api/trash/${id}/restore`, {}),
  clearTrash: () => http.del("/api/trash", { confirm: "清空回收站" }),
  clearIndex: () => http.post("/api/danger/clear-index", { confirm: "清空索引" }),

  // ---- assistant.py ----
  chat: (question) => http.post("/api/chat", { question }),

  // ---- settings.py ----
  settings: () => http.get("/api/settings"),
  putSettings: (values) => http.put("/api/settings", { values }),
  testConnection: (payload) => http.post("/api/settings/test", payload),
  audit: (limit = 100) => http.get("/api/settings/audit", { limit }),
  rollback: (id) => http.post(`/api/settings/audit/${id}/rollback`, {}),
  profiles: () => http.get("/api/settings/profiles"),
  saveProfile: (payload) => http.post("/api/settings/profiles", payload),
  deleteProfile: (name) => http.del(`/api/settings/profiles/${encodeURIComponent(name)}`),
  backup: () => http.post("/api/settings/backup", {}),
};

export function thumbUrl(id) {
  return `/api/thumbs/${id}`;
}

export { ApiError };
