// toast 队列：全站唯一的轻量反馈通道
import { reactive } from "vue";

export const toasts = reactive({ items: [] });

let seed = 0;

/**
 * 推一条提示。
 * @param {string} message 正文（后端 error.message 是人话，可直接透传）
 * @param {"info"|"ok"|"warn"|"error"} level
 * @param {{ timeout?: number }} [opts] timeout=0 表示不自动消失
 */
export function notify(message, level = "info", opts = {}) {
  const id = ++seed;
  const timeout = opts.timeout ?? (level === "error" ? 6000 : 3600);
  toasts.items.push({ id, message: String(message ?? ""), level });
  if (toasts.items.length > 5) toasts.items.shift();
  if (timeout > 0) {
    setTimeout(() => dismiss(id), timeout);
  }
  return id;
}

export function dismiss(id) {
  const i = toasts.items.findIndex((t) => t.id === id);
  if (i >= 0) toasts.items.splice(i, 1);
}

notify.ok = (m, o) => notify(m, "ok", o);
notify.warn = (m, o) => notify(m, "warn", o);
notify.error = (m, o) => notify(m, "error", o);
