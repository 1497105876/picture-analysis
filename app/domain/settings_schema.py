"""配置 schema（唯一事实源）：前端设置页按此自动渲染，新增配置零 UI 代码。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

GROUP_LABELS: dict[str, str] = {
    "G1": "服务档案与绑定",
    "G2": "识别行为",
    "G3": "并发与限速",
    "G4": "目录策略",
    "G5": "OCR",
    "G6": "检索",
    "G7": "运维",
    "G8": "外观与排序",
    "G10": "危险操作",
    "G11": "通知",
    "G12": "检索增强",
    "G13": "资源预算",
    "G14": "AI 风格",
    "G15": "隐私",
    "G16": "Profile 与审计",
    "G17": "图库自定义",
    "G18": "规则与分类",
}


@dataclass(frozen=True)
class SettingItem:
    group: str
    key: str
    label: str
    type: str  # int | float | bool | select | text | tags | csv
    default: Any
    help: str = ""
    minimum: float | None = None
    maximum: float | None = None
    options: tuple[str, ...] = ()
    effective: str = "on-save"
    advanced: bool = False
    show_if: dict[str, Any] = field(default_factory=dict)


def _s(
    group: str,
    key: str,
    label: str,
    stype: str,
    default: Any,
    help: str = "",
    minimum: float | None = None,
    maximum: float | None = None,
    options: tuple[str, ...] = (),
    effective: str = "on-save",
    advanced: bool = False,
) -> SettingItem:
    return SettingItem(
        group, key, label, stype, default, help, minimum, maximum, options, effective, advanced
    )


SETTINGS: tuple[SettingItem, ...] = (
    # G1 服务档案与绑定
    _s(
        "G1",
        "profile_vision",
        "识图用途档案",
        "select",
        "default",
        "空或不存在时回退到 default 档案",
        options=("@follow",),
        effective="immediate",
    ),
    _s(
        "G1",
        "profile_embed",
        "嵌入用途档案",
        "select",
        "@follow",
        "跟随识图档案",
        options=("@follow",),
        effective="immediate",
    ),
    _s(
        "G1",
        "profile_chat",
        "对话用途档案",
        "select",
        "@follow",
        "跟随识图档案",
        options=("@follow",),
        effective="immediate",
    ),
    _s(
        "G1",
        "profile_enhance",
        "查询增强档案",
        "select",
        "@follow",
        "跟随对话档案",
        options=("@follow",),
        effective="immediate",
    ),
    _s("G1", "probe_on_start", "启动时连接探测", "bool", True, effective="immediate"),
    _s("G1", "probe_interval_min", "周期探测间隔（分钟）", "int", 30, minimum=1, maximum=1440),
    _s("G1", "embed_dim", "向量维度（0=按模型返回）", "int", 0, minimum=0, maximum=4096),
    _s("G1", "vision_model", "识图模型名", "text", ""),
    _s("G1", "embed_model", "嵌入模型名", "text", ""),
    _s("G1", "chat_model", "对话模型名", "text", ""),
    # G2 识别行为
    _s(
        "G2", "vision_prompt_override", "识图 prompt 模板（空=内置默认）", "text", "", advanced=True
    ),
    _s("G2", "field_description", "输出 description", "bool", True),
    _s("G2", "field_tags", "输出 ai_tags", "bool", True),
    _s("G2", "field_elements", "输出 elements", "bool", True),
    _s("G2", "field_has_text", "输出 has_text 判定", "bool", True),
    # G3 并发与限速
    _s(
        "G3",
        "rate_limit_per_minute",
        "识图限速（次/分钟）",
        "int",
        20,
        "默认 20，即 3 秒一次",
        minimum=1,
        maximum=60,
        effective="immediate",
    ),
    _s(
        "G3",
        "min_interval_seconds",
        "相邻请求最小间隔（秒）",
        "float",
        3.0,
        minimum=0.0,
        maximum=60.0,
        effective="immediate",
    ),
    _s("G3", "vision_concurrency", "识图并发", "int", 2, minimum=1, maximum=16),
    _s("G3", "max_retries", "失败重试上限", "int", 3, minimum=0, maximum=10),
    _s("G3", "daily_token_limit", "每日 token 上限（0=不限）", "int", 0, minimum=0),
    _s("G3", "overnight_rate", "过夜限速（次/分钟，0=关）", "int", 0, minimum=0, maximum=60),
    _s("G3", "overnight_start", "过夜时段开始", "text", "23:00"),
    _s("G3", "overnight_end", "过夜时段结束", "text", "07:00"),
    # G4 目录策略
    _s(
        "G4",
        "default_extensions",
        "扩展名白名单（逗号分隔）",
        "csv",
        ".jpg,.jpeg,.png,.gif,.webp,.bmp,.tif,.tiff",
    ),
    _s("G4", "exclude_globs", "排除 glob（逗号分隔）", "csv", ""),
    _s("G4", "scan_on_start", "启动时增量扫描", "bool", False),
    _s("G4", "watcher_enabled", "截图自动导入（30 秒轮询）", "bool", False, effective="immediate"),
    # G5 OCR
    _s(
        "G5",
        "ocr_default_policy",
        "OCR 默认策略",
        "select",
        "auto",
        "auto=识图判定含文字才 OCR；on=强制；off=关闭",
        options=("auto", "on", "off"),
    ),
    _s("G5", "ocr_min_chars", "OCR 判定最小字数", "int", 3, minimum=1, maximum=100),
    _s("G5", "ocr_empty_policy", "OCR 空结果策略", "select", "keep", options=("keep", "skip")),
    # G6 检索
    _s(
        "G6",
        "search_mode",
        "检索模式",
        "select",
        "hybrid",
        options=("hybrid", "keyword", "vector"),
        effective="immediate",
    ),
    _s("G6", "rrf_k", "RRF k", "int", 60, minimum=1, maximum=200),
    _s("G6", "similarity_threshold", "相似度阈值", "float", 0.0, minimum=0.0, maximum=1.0),
    _s("G6", "query_enhance", "LLM 查询增强", "bool", False, effective="immediate"),
    # G7 运维
    _s(
        "G7",
        "log_level",
        "日志级别",
        "select",
        "INFO",
        options=("DEBUG", "INFO", "WARNING", "ERROR"),
        effective="immediate",
    ),
    _s("G7", "log_backup_count", "日志保留份数", "int", 5, minimum=1, maximum=50),
    _s("G7", "backup_auto", "启动时自动备份数据库", "bool", False),
    _s("G7", "backup_retain", "自动备份保留份数", "int", 7, minimum=1, maximum=100),
    # G8 外观与排序
    _s("G8", "theme", "主题", "select", "system", options=("light", "dark", "system")),
    _s("G8", "accent", "强调色", "text", "#2563eb"),
    _s("G8", "thumb_size", "缩略图尺寸", "int", 220, minimum=120, maximum=480),
    _s(
        "G8",
        "card_density",
        "卡片密度",
        "select",
        "comfortable",
        options=("compact", "comfortable"),
    ),
    _s(
        "G8",
        "default_sort",
        "默认排序",
        "select",
        "mtime",
        options=("mtime", "taken", "rating", "created", "filename"),
    ),
    _s("G8", "language", "语言", "select", "zh", options=("zh", "en")),
    _s(
        "G8",
        "startup_page",
        "启动页",
        "select",
        "gallery",
        options=("gallery", "search", "dashboard"),
    ),
    # G11 通知
    _s("G11", "notify_job_paused", "队列暂停通知", "bool", True),
    _s("G11", "notify_budget", "每日上限通知", "bool", True),
    _s("G11", "notify_watch", "截图导入通知", "bool", False),
    _s("G11", "notify_channel", "通知渠道", "select", "inapp", options=("inapp",)),
    _s("G11", "dnd_start", "免打扰开始", "text", "23:00"),
    _s("G11", "dnd_end", "免打扰结束", "text", "08:00"),
    # G12 检索增强
    _s("G12", "synonyms_enabled", "同义词组展开", "bool", True, effective="immediate"),
    _s("G12", "term_weight_enabled", "术语加权", "bool", True, effective="immediate"),
    _s("G12", "search_history_enabled", "记录搜索历史", "bool", True, effective="immediate"),
    # G13 资源预算
    _s("G13", "thread_cap", "后台线程上限", "int", 4, minimum=1, maximum=32),
    _s("G13", "memory_profile", "内存策略", "select", "normal", options=("low", "normal", "high")),
    _s(
        "G13",
        "process_priority",
        "进程优先级",
        "select",
        "normal",
        options=("below", "normal", "above"),
    ),
    # G14 AI 风格
    _s("G14", "style_language", "描述语言", "select", "中文", options=("中文", "English")),
    _s(
        "G14",
        "style_granularity",
        "风格粒度",
        "select",
        "简洁",
        options=("简洁", "详细"),
        effective="immediate",
    ),
    _s("G14", "style_confidence", "输出置信度", "bool", False),
    _s("G14", "style_ab", "Prompt A/B", "select", "A", options=("A", "B")),
    _s("G14", "sensitive_words", "敏感词（命中永不外发）", "tags", ""),
    # G15 隐私
    _s("G15", "privacy_mode", "隐私模式（前端遮罩）", "bool", False, effective="immediate"),
    _s("G15", "export_strip_exif", "导出剥离 EXIF", "bool", True),
    _s("G15", "sensitive_guard", "敏感守门（命中不送云端）", "bool", True),
    # G16
    _s("G16", "audit_enabled", "记录配置变更审计", "bool", True, effective="immediate"),
    # G17
    _s(
        "G17",
        "sidebar_modules",
        "侧栏模块（顺序，逗号分隔）",
        "csv",
        "gallery,search,dashboard,entities,rules,albums,chat,hidden,trash,jobs,proposals",
    ),
    _s("G17", "default_view", "默认视图", "select", "grid", options=("grid", "list")),
    # G18
    _s("G18", "rules_enabled", "启用规则引擎", "bool", True, effective="immediate"),
)

_BY_KEY: dict[str, SettingItem] = {item.key: item for item in SETTINGS}


def defaults() -> dict[str, Any]:
    return {item.key: item.default for item in SETTINGS}


def find(key: str) -> SettingItem | None:
    return _BY_KEY.get(key)


def coerce(key: str, value: Any) -> Any:
    item = _BY_KEY.get(key)
    if item is None:
        return value
    try:
        if item.type == "int":
            number = int(value)
            if item.minimum is not None:
                number = max(int(item.minimum), number)
            if item.maximum is not None:
                number = min(int(item.maximum), number)
            return number
        if item.type == "float":
            number_f = float(value)
            if item.minimum is not None:
                number_f = max(item.minimum, number_f)
            if item.maximum is not None:
                number_f = min(item.maximum, number_f)
            return number_f
        if item.type == "bool":
            if isinstance(value, str):
                return value.lower() in ("1", "true", "yes", "on")
            return bool(value)
        if item.type == "select":
            text = str(value)
            if item.options and text not in item.options and not text.startswith("@"):
                return item.default
            return text
        if item.type == "csv":
            return [part.strip() for part in str(value).split(",") if part.strip()]
        if item.type == "tags":
            return str(value)
        return str(value)
    except (TypeError, ValueError):
        return item.default


def schema_payload() -> dict[str, Any]:
    groups = [
        {
            "id": gid,
            "label": label,
            "items": [
                {
                    "key": item.key,
                    "label": item.label,
                    "type": item.type,
                    "default": item.default,
                    "help": item.help,
                    "min": item.minimum,
                    "max": item.maximum,
                    "options": list(item.options),
                    "effective": item.effective,
                    "advanced": item.advanced,
                }
                for item in SETTINGS
                if item.group == gid
            ],
        }
        for gid, label in GROUP_LABELS.items()
    ]
    return {"groups": groups}
