// 全局设置单例：schema + values + profiles，以及从设置派生出来的外观。
// 页面不要再各自请求 /api/settings——统一从这里读。
import { computed, reactive } from "vue";

import { api } from "./api.js";
import { notify } from "./toast.js";

export const settings = reactive({
  groups: [],
  values: {},
  profiles: [],
  dangerGroups: [],
  loaded: false,
  loading: false,
  saving: false,
});

// 脏值：key → value。保存时只提交这里面的东西，避免一条微调污染整个审计流。
const dirty = reactive({});

export const dirtyCount = computed(() => Object.keys(dirty).length);
export const isDirty = computed(() => dirtyCount.value > 0);

export function rawValue(key) {
  const v = key in dirty ? dirty[key] : settings.values[key];
  return v;
}

/** 标脏（不落库）。传入的值应与后端 coerce 后的形态一致。 */
export function stage(key, value) {
  const before = settings.values[key];
  if (JSON.stringify(before) === JSON.stringify(value)) {
    delete dirty[key];
  } else {
    dirty[key] = value;
  }
}

export function stageMany(patch) {
  for (const [k, v] of Object.entries(patch)) stage(k, v);
}

export function revertDirty() {
  for (const k of Object.keys(dirty)) delete dirty[k];
}

/** 把 dirty 里的东西提交到后端，成功后合并回 values 并清空脏表。 */
export async function saveSettings() {
  if (!isDirty.value) return 0;
  const payload = { ...dirty };
  settings.saving = true;
  try {
    const applied = await api.putSettings(payload);
    for (const [k, v] of Object.entries(applied || payload)) {
      settings.values[k] = v;
      delete dirty[k];
    }
    notify(`已保存 ${Object.keys(payload).length} 项配置`, "ok");
    await loadSettings({ quiet: true });
    return Object.keys(payload).length;
  } catch (e) {
    notify(e.message, "error");
    return 0;
  } finally {
    settings.saving = false;
  }
}

/** 立即写入单项（用于「改了就想生效」的外观类配置，不进脏表） */
export async function setSetting(key, value) {
  const applied = await api.putSettings({ [key]: value });
  const v = applied?.[key] ?? value;
  settings.values[key] = v;
  delete dirty[key];
  return v;
}

export async function loadSettings({ quiet = false } = {}) {
  settings.loading = true;
  try {
    const data = await api.settings();
    settings.groups = data.groups || [];
    settings.values = data.values || {};
    settings.profiles = data.profiles || [];
    settings.dangerGroups = data.danger_groups || [];
    settings.loaded = true;
    applyAppearance();
    return data;
  } catch (e) {
    if (!quiet) notify(e.message, "error");
    throw e;
  } finally {
    settings.loading = false;
  }
}

// ---------------------------------------------------------------------------
// 外观：模式 × 强调色 × 密度。取值来自后端 schema 里的 theme / accent / card_density / thumb_size
// ---------------------------------------------------------------------------

export const ACCENTS = [
  { name: "azure", label: "天青", color: "#2563eb" },
  { name: "indigo", label: "靛蓝", color: "#4f46e5" },
  { name: "teal", label: "青碧", color: "#0d8a7a" },
  { name: "violet", label: "紫罗兰", color: "#7c3aed" },
  { name: "amber", label: "琥珀", color: "#b45309" },
  { name: "graphite", label: "石墨", color: "#475569" },
];

export const appearance = reactive({
  mode: "light",
  accent: "azure",
  accentCustom: "",
  density: "comfortable",
  cardSize: 208,
});

const systemDark =
  typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

function resolveAccent(hex) {
  if (!hex) return { name: "azure", custom: "" };
  const hit = ACCENTS.find((a) => a.color.toLowerCase() === String(hex).trim().toLowerCase());
  return hit ? { name: hit.name, custom: "" } : { name: "custom", custom: String(hex).trim() };
}

/** 自定义色需要自己算 hover / contrast */
function applyCustomAccent(hex) {
  const root = document.documentElement;
  const raw = String(hex).replace("#", "");
  const full = raw.length === 3 ? raw.split("").map((c) => c + c).join("") : raw;
  const r = parseInt(full.slice(0, 2), 16) || 0;
  const g = parseInt(full.slice(2, 4), 16) || 0;
  const b = parseInt(full.slice(4, 6), 16) || 0;
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  const shade = (amount) => {
    const f = (v) => Math.max(0, Math.min(255, Math.round(v + amount * 255)));
    return `#${[f(r / 255), f(g / 255), f(b / 255)]
      .map((v) => v.toString(16).padStart(2, "0"))
      .join("")}`;
  };
  if (!/^#[0-9a-fA-F]{6}$/.test(String(hex))) {
    root.style.removeProperty("--accent");
    root.style.removeProperty("--accent-hover");
    root.style.removeProperty("--accent-contrast");
    return;
  }
  root.style.setProperty("--accent", `#${full}`);
  const darkMode = root.dataset.theme === "dark";
  root.style.setProperty("--accent-hover", shade(darkMode ? 0.1 : -0.12));
  root.style.setProperty("--accent-contrast", lum > 0.62 ? "#16181d" : "#ffffff");
}

export function applyAppearance() {
  if (!settings.loaded) return;
  const root = document.documentElement;
  const v = settings.values;
  const mode = String(v.theme || "system");
  const accentInfo = resolveAccent(v.accent || ACCENTS[0].color);
  const density = String(v.card_density || "comfortable");
  const size = Number(v.thumb_size) || 208;

  const dark =
    mode === "dark" || (mode === "system" && Boolean(systemDark?.matches));

  if (accentInfo.name === "custom") {
    root.style.removeProperty("--accent");
    root.style.removeProperty("--accent-hover");
    root.style.removeProperty("--accent-contrast");
  }
  root.dataset.theme = dark ? "dark" : "light";
  root.dataset.accent = accentInfo.name;
  if (accentInfo.name === "custom") applyCustomAccent(accentInfo.custom);
  root.dataset.density = density;
  root.style.setProperty("--card-min", `${Math.max(120, Math.min(480, size))}px`);

  appearance.mode = mode;
  appearance.accent = accentInfo.name;
  appearance.accentCustom = accentInfo.custom;
  appearance.density = density;
  appearance.cardSize = size;
}

systemDark?.addEventListener("change", () => {
  if (String(settings.values.theme || "system") === "system") applyAppearance();
});

// ---------------------------------------------------------------------------
// 侧栏模块注册表：顺序以设置里的 sidebar_modules 为准，
// 注册表里存在但配置中没有的模块追加到末尾，保证新页面一定能被发现。
// ---------------------------------------------------------------------------

export const MODULES = [
  { key: "gallery", to: "/gallery", label: "图库", icon: "image", group: "浏览" },
  { key: "search", to: "/search", label: "检索", icon: "search", group: "浏览" },
  { key: "albums", to: "/albums", label: "相册", icon: "album", group: "浏览" },
  { key: "chat", to: "/chat", label: "对话", icon: "chat", group: "浏览" },
  { key: "dashboard", to: "/dashboard", label: "仪表盘", icon: "chart", group: "浏览" },
  { key: "entities", to: "/entities", label: "实体", icon: "user", group: "整理" },
  { key: "categories", to: "/categories", label: "分类", icon: "tag", group: "整理" },
  { key: "rules", to: "/rules", label: "规则", icon: "rule", group: "整理" },
  { key: "proposals", to: "/proposals", label: "提案", icon: "inbox", group: "整理" },
  { key: "jobs", to: "/jobs", label: "任务", icon: "task", group: "运维" },
  { key: "ops", to: "/ops", label: "运维", icon: "gear", group: "运维" },
  { key: "hidden", to: "/hidden", label: "隐藏区", icon: "eye-off", group: "运维" },
  { key: "trash", to: "/trash", label: "回收站", icon: "trash", group: "运维" },
];

const DEFAULT_MODULES = [
  "gallery",
  "search",
  "dashboard",
  "entities",
  "rules",
  "albums",
  "chat",
  "hidden",
  "trash",
  "jobs",
  "proposals",
];

export const sidebarModules = computed(() => {
  let keys = rawValue("sidebar_modules");
  if (typeof keys === "string") keys = keys.split(",");
  if (!Array.isArray(keys) || !keys.length) keys = DEFAULT_MODULES;
  const cleaned = keys.map((k) => String(k).trim()).filter(Boolean);
  const picked = cleaned.map((k) => MODULES.find((m) => m.key === k)).filter(Boolean);
  const missing = MODULES.filter((m) => !cleaned.includes(m.key));
  return [...picked, ...missing.map((m) => ({ ...m, fresh: true }))];
});

/** 字典开的分组顺序，用于侧栏分组显示 */
export const MODULE_GROUPS = ["浏览", "整理", "运维"];

export const privacyMode = computed(() => Boolean(rawValue("privacy_mode")));

export const defaultView = computed(() => String(rawValue("default_view") || "grid"));

export const defaultSort = computed(() => String(rawValue("default_sort") || "mtime"));
