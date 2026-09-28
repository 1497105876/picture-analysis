// API 客户端：统一错误（中文 message）+ 轻量 toast
import { reactive } from "vue";

export const toast = reactive({ items: [] });

export function notify(message, level = "info") {
  const id = Date.now() + Math.random();
  toast.items.push({ id, message, level });
  setTimeout(() => {
    const i = toast.items.findIndex((t) => t.id === id);
    if (i >= 0) toast.items.splice(i, 1);
  }, 4000);
}

async function request(method, url, { body, params, raw } = {}) {
  let target = url;
  if (params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === "") continue;
      qs.set(k, String(v));
    }
    const text = qs.toString();
    if (text) target += (target.includes("?") ? "&" : "?") + text;
  }
  const init = { method, headers: {} };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(target, init);
  if (raw) return res;
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const message = data?.error?.message || `请求失败（${res.status}）`;
    const err = new Error(message);
    err.code = data?.error?.code || "";
    err.status = res.status;
    throw err;
  }
  return data;
}

export const api = {
  get: (url, params) => request("GET", url, { params }),
  post: (url, body) => request("POST", url, { body }),
  put: (url, body) => request("PUT", url, { body }),
  patch: (url, body) => request("PATCH", url, { body }),
  del: (url, params) => request("DELETE", url, { params }),
  upload: async (file) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/upload", { method: "POST", body: form });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error(data?.error?.message || "上传失败");
    return data;
  },
};

export function thumbUrl(id) {
  return `/api/thumbs/${id}`;
}
