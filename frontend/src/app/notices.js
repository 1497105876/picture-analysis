// 通知与健康状态单例。
// 门槛没有「已读」接口（表里 read 字段存在但无处更新），所以未读数用本地水位线：
// 记录本地最后一次看到的通知 id，严格大于它的都算未读。
import { computed, reactive } from "vue";

import { api, safe } from "./api.js";

const SEEN_KEY = "pa.notices.seen";

const readSeen = () => Number(window.localStorage.getItem(SEEN_KEY) || 0);
const writeSeen = (n) => window.localStorage.setItem(SEEN_KEY, String(n));

export const notices = reactive({
  items: [],
  seen: readSeen(),
  loaded: false,
});

export const backend = reactive({
  online: false,
  version: "",
  checked: false,
});

export const unreadCount = computed(() =>
  notices.items.reduce((acc, n) => acc + (Number(n.id) > notices.seen ? 1 : 0), 0),
);

export function markAllSeen() {
  const max = notices.items.reduce((acc, n) => Math.max(acc, Number(n.id) || 0), 0);
  if (max > notices.seen) {
    notices.seen = max;
    writeSeen(max);
  }
}

export async function loadNotices(limit = 30) {
  const items = await safe(() => api.notices(limit), []);
  notices.items = items || [];
  notices.loaded = true;
  return notices.items;
}

export async function clearNotices() {
  await api.clearNotices();
  notices.items = [];
  notices.seen = readSeen();
  markAllSeen();
}

/** 后端可达性。轮询失败静默（不出 toast），只反映到顶栏标记上。 */
export async function checkHealth() {
  const data = await safe(() => api.health(), null, { silent: true });
  backend.online = Boolean(data?.status === "ok");
  backend.version = data?.version || "";
  backend.checked = true;
  return backend.online;
}
