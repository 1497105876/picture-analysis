// 纯展示用的格式化函数。全部对 null/undefined 安全，界面上永远显示占位而不是 undefined。

export const EMPTY = "—";

const UNITS = ["B", "KB", "MB", "GB", "TB"];

export function bytes(n) {
  if (n === null || n === undefined || n === "") return EMPTY;
  let value = Number(n);
  if (!Number.isFinite(value)) return EMPTY;
  if (value === 0) return "0 B";
  let unit = 0;
  while (Math.abs(value) >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${UNITS[unit]}`;
}

export function megabytes(n) {
  if (n === null || n === undefined) return EMPTY;
  return `${(Number(n) / 1048576).toFixed(1)} MB`;
}

const pad = (n) => String(n).padStart(2, "0");

/**
 * 时间显示。后端存的是 UTC（如 2026-09-30T15:07:19+00:00），
 * 直接截字符串会显示成比真实时间早 8 小时，所以带时区的要先转本地。
 * 不带时区的字符串（少数历史数据）按本地时间原样显示，不再二次偏移。
 */
export function datetime(s) {
  if (!s) return EMPTY;
  const text = String(s).trim();
  const d = new Date(text);
  if (Number.isNaN(d.getTime())) return text.slice(0, 16).replace("T", " ");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

export function date(s) {
  if (!s) return EMPTY;
  return String(s).slice(0, 10);
}

/** 秒级时间戳与 ISO 混用都要不崩 */
export function datetimeAny(s) {
  if (!s) return EMPTY;
  if (typeof s === "number" || /^\d+$/.test(String(s))) {
    const ms = Number(s) > 1e11 ? Number(s) : Number(s) * 1000;
    return datetime(new Date(ms).toISOString());
  }
  // 纯数字以外的无时区串（如 "2026-09-30 15:07:19"）按本地时间理解
  return datetime(String(s).includes("T") || /[Z+]/.test(String(s)) ? s : String(s).replace(" ", "T"));
}

export function ago(s) {
  if (!s) return EMPTY;
  const ms = Date.now() - new Date(String(s).trim()).getTime();
  if (!Number.isFinite(ms)) return EMPTY;
  const min = Math.round(ms / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hour = Math.round(min / 60);
  if (hour < 24) return `${hour} 小时前`;
  const day = Math.round(hour / 24);
  if (day < 30) return `${day} 天前`;
  return date(s);
}

export function duration(seconds) {
  const s = Number(seconds) || 0;
  if (s < 60) return `${Math.round(s)} 秒`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} 分 ${Math.round(s % 60)} 秒`;
  const h = Math.floor(m / 60);
  return `${h} 小时 ${m % 60} 分`;
}

export function num(n) {
  if (n === null || n === undefined || n === "") return EMPTY;
  const v = Number(n);
  return Number.isFinite(v) ? v.toLocaleString("zh-CN") : String(n);
}

export function percent(part, whole) {
  const w = Number(whole) || 0;
  if (!w) return "0%";
  return `${((Number(part) / w) * 100).toFixed(1)}%`;
}

// ---------------------------------------------------------------- 业务语义

export const ANALYSIS_STATE = {
  unanalyzed: { text: "未识别", tone: "" },
  queued: { text: "排队中", tone: "accent" },
  pending: { text: "待处理", tone: "accent" },
  running: { text: "识别中", tone: "accent" },
  done: { text: "已识别", tone: "ok" },
  failed: { text: "失败", tone: "danger" },
  skipped: { text: "跳过", tone: "warn" },
};

export function stateMeta(state) {
  return ANALYSIS_STATE[state] ?? { text: state || "未知", tone: "" };
}

export const JOB_STATE = {
  pending: "accent",
  running: "accent",
  paused: "warn",
  succeeded: "ok",
  failed: "danger",
  dead: "danger",
};

export const NOTICE_KIND = {
  correction: "人工修正",
  "scan-skip": "扫描跳过",
  watch: "截图导入",
  scan: "扫描",
  budget: "预算",
  setting: "配置",
  system: "系统",
  // 任务相关（这些是后端实际写入的值，不翻译就会在界面上露出英文）
  no_key: "缺少密钥",
  paused: "队列暂停",
  "job-paused": "任务暂停",
  "job-dead": "任务耗尽重试",
  "job-failed": "任务失败",
  rate: "限速等待",
  skip: "跳过",
  import: "导入",
  trash: "回收站",
  embed: "嵌入向量",
  analyze: "AI 识别",
  directory: "目录",
};

export function noticeKind(kind) {
  return NOTICE_KIND[kind] || kind || "系统";
}

export const PROFILE_USAGE = [
  { value: "vision", label: "识图" },
  { value: "embed", label: "嵌入" },
  { value: "chat", label: "对话" },
  { value: "enhance", label: "查询增强" },
];

export const RULE_TARGETS = [
  { value: "dir_prefix", label: "目录前缀" },
  { value: "dir_suffix", label: "路径包含" },
  { value: "filename", label: "文件名" },
  { value: "ocr_text", label: "OCR 文本" },
  { value: "category", label: "分类" },
];

export const RULE_OPS = [
  { value: "contains", label: "包含" },
  { value: "equals", label: "等于" },
  { value: "startswith", label: "开头是" },
  { value: "endswith", label: "结尾是" },
  { value: "regex", label: "正则" },
];

export const FIELD_TYPES = [
  { value: "text", label: "文本" },
  { value: "number", label: "数字" },
  { value: "date", label: "日期" },
  { value: "select", label: "枚举" },
];

export const SORT_OPTIONS = [
  { value: "mtime", label: "修改时间" },
  { value: "taken", label: "拍摄时间" },
  { value: "created", label: "入库时间" },
  { value: "filename", label: "文件名" },
  { value: "rating", label: "评分" },
  { value: "id", label: "编号" },
];

/** 列表 item → 展示用分类（人工位优先，这是全产品的一致口径） */
export function categoryOf(row) {
  return row?.category_manual || row?.category_ai || "";
}

export function descriptionOf(row) {
  return row?.description_manual || row?.description_ai || "";
}

export function starsOf(n) {
  return "★".repeat(Math.max(0, Math.min(5, Number(n) || 0)));
}

export function maskKey(s) {
  if (!s) return "未设置";
  if (s.length <= 10) return "••••";
  return `${s.slice(0, 6)}••••${s.slice(-4)}`;
}

export function pretty(v) {
  if (v === null || v === undefined || v === "") return EMPTY;
  if (typeof v === "object") {
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  return String(v);
}
