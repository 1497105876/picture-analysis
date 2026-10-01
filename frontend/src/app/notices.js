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

// 队列状态：有没有 AI 可用、是不是暂停了、为什么暂停。
// 图库页靠它判断「要不要告诉用户：你的图不会自动识别」。
export const queue = reactive({
  paused: 0,
  reason: "",
  pending: 0,
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

/**
 * 拉取通知。两处（顶栏下拉 / 运维页）共用同一个 limit，
 * 否则顶栏显示 30、运维页显示 200，同一个数字两个值会让人不知道信哪个。
 */
export async function loadNotices(limit = 200) {
  const data = await safe(() => api.notices(limit), null);
  notices.items = Array.isArray(data?.items) ? data.items : [];
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

/** 刷新队列状态（由 App 的轮询统一调用，页面不再各拉各的） */
export async function refreshQueue() {
  const data = await safe(() => api.jobs(), null, { silent: true });
  if (!data) return queue;
  const counts = data.counts || {};
  const pausedRow = (data.items || []).find((j) => j.state === "paused");
  queue.paused = counts.paused || 0;
  queue.pending = (counts.pending || 0) + (counts.running || 0);
  queue.reason = pausedRow?.error || pausedRow?.pause || "";
  return queue;
}
