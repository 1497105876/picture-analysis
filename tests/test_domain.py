"""纯领域单元测试：限速、融合、规则求值、状态机、配置收敛、媒体工具、目录扫描。"""

from __future__ import annotations

from pathlib import Path

from app.domain import settings_schema as schema
from app.domain.errors import (
    AppError,
    ConfirmWordMismatch,
    HiddenNotBypassable,
    NotFoundError,
    ValidationAppError,
)
from app.domain.fusion import expand_query, rrf_merge, weighted_terms
from app.domain.rate_limit import RateConfig, SlidingWindowLimiter
from app.domain.rules_eval import Rule, RuleContext, first_match, match_condition
from app.domain.states import can_transition_analysis, can_transition_job
from app.files.media import file_md5, is_under, perceptual_hash, strip_exif
from app.files.scanner import ScanOptions, estimate, iter_files

# ---------- 限速 ----------


def test_limiter_interval_and_window() -> None:
    clock = {"t": 0.0}
    limiter = SlidingWindowLimiter(RateConfig(per_minute=2, min_interval=0.0), lambda: clock["t"])

    assert limiter.try_acquire().allowed is True
    second = limiter.try_acquire()  # 窗口 2 次内
    assert second.allowed is True
    third = limiter.try_acquire()  # 超出每分钟上限
    assert third.allowed is False and third.wait > 0

    clock["t"] = 61.0  # 窗口滑出
    assert limiter.try_acquire().allowed is True

    # 最小间隔约束
    limiter.reconfigure(RateConfig(per_minute=20, min_interval=3.0))
    denied = limiter.try_acquire()
    assert denied.allowed is False
    assert 0 < denied.wait <= 3.0
    assert limiter.pending_wait() > 0
    clock["t"] += 3.0
    assert limiter.try_acquire().allowed is True


# ---------- 融合 ----------


def test_rrf_merge_and_weights() -> None:
    merged = rrf_merge([[1, 2, 3], [3, 4, 5]], k=60)
    ids = [i for i, _ in merged]
    assert set(ids) == {1, 2, 3, 4, 5}
    # 两个列表都出现的 3 应排最前
    assert ids[0] == 3

    assert expand_query("海边", {"水域": ["海边", "海岸"]}) == ["海边", "海岸"]
    assert expand_query("海边", {}) == ["海边"]
    expanded = expand_query("落日 夕阳", {"组1": ["落日", "夕阳"], "组2": ["夕阳", "晚霞"]})
    assert "夕阳" in expanded  # 单趟展开（不做递归链）

    weighted = weighted_terms(["a", "b"], {"b": 3.0})
    assert weighted == ["a", "b", "b"]  # 高权词追加一次提升 FTS 权重
    assert weighted_terms(["a"], {}) == ["a"]


# ---------- 规则求值 ----------


def _ctx(**overrides) -> RuleContext:
    base = {
        "path": "C:/lib/beach.jpg",
        "filename": "beach.jpg",
        "dir_path": "C:/lib",
        "ocr_text": "发票 123",
        "category": None,
    }
    base.update(overrides)
    return RuleContext(**base)  # type: ignore[arg-type]


def test_match_condition_ops() -> None:
    assert match_condition({"target": "filename", "op": "contains", "value": "beach"}, _ctx())
    assert not match_condition({"target": "filename", "op": "contains", "value": "cat"}, _ctx())
    assert match_condition({"target": "filename", "op": "endswith", "value": ".jpg"}, _ctx())
    assert match_condition({"target": "filename", "op": "equals", "value": "beach.jpg"}, _ctx())
    assert match_condition({"target": "dir_prefix", "op": "startswith", "value": "C:"}, _ctx())
    assert match_condition({"target": "ocr_text", "op": "regex", "value": r"\d{3}"}, _ctx())
    assert match_condition({"target": "ocr_text", "op": "regex", "value": "["}, _ctx()) is False
    # 非法目标/操作/空值 → 不命中
    assert not match_condition({"target": "evil", "op": "contains", "value": "x"}, _ctx())
    assert not match_condition({"target": "filename", "op": "evil", "value": "x"}, _ctx())
    assert not match_condition({"target": "filename", "op": "contains", "value": ""}, _ctx())
    assert match_condition(
        {"target": "category", "op": "equals", "value": "风景"}, _ctx(category="风景")
    )


def test_first_match_priority_and_disabled() -> None:
    rules = [
        Rule(
            id=2,
            name="b",
            priority=1,
            enabled=True,
            condition={"target": "filename", "op": "contains", "value": "beach"},
            action={"set_category": "低"},
        ),
        Rule(
            id=1,
            name="a",
            priority=0,
            enabled=False,
            condition={"target": "filename", "op": "contains", "value": "beach"},
            action={"set_category": "禁用"},
        ),
        Rule(
            id=3,
            name="c",
            priority=5,
            enabled=True,
            condition={"target": "filename", "op": "contains", "value": "beach"},
            action={"set_category": "高"},
        ),
    ]
    hit = first_match(rules, _ctx())
    assert hit is not None and hit.name == "b"  # 同命中取 priority 最小的启用规则
    assert first_match([r for r in rules if r.enabled and r.priority == 99], _ctx()) is None


# ---------- 状态机 ----------


def test_state_transitions() -> None:
    assert can_transition_job("pending", "running")
    assert can_transition_job("running", "succeeded")
    assert can_transition_job("running", "failed")
    assert can_transition_job("failed", "dead")
    assert not can_transition_job("running", "dead")  # 先 failed 再 dead
    assert not can_transition_job("succeeded", "running")
    assert can_transition_analysis("queued", "running")
    assert can_transition_analysis("running", "done")
    assert not can_transition_analysis("unanalyzed", "done")
    assert not can_transition_analysis("skipped", "done")


# ---------- 配置收敛 ----------


def test_coerce_clamps_and_falls_back() -> None:
    assert schema.coerce("rate_limit_per_minute", 999) == 60
    assert schema.coerce("rate_limit_per_minute", -5) == 1
    assert schema.coerce("min_interval_seconds", "2.5") == 2.5
    assert schema.coerce("theme", "neon") == "system"
    assert schema.coerce("style_confidence", "on") is True
    assert schema.coerce("style_confidence", "false") is False
    assert schema.coerce("exclude_globs", "a, b , ,c") == ["a", "b", "c"]
    assert schema.coerce("不存在的键", "任意") == "任意"
    assert schema.coerce("rate_limit_per_minute", object()) == 20  # 解析失败 → 默认

    assert schema.find("theme") is not None
    assert schema.find("nope") is None
    defaults = schema.defaults()
    assert defaults["search_mode"] == "hybrid"
    payload = schema.schema_payload()
    assert {g["id"] for g in payload["groups"]} == set(schema.GROUP_LABELS)


# ---------- 错误码 ----------


def test_error_codes_and_status() -> None:
    assert ValidationAppError("x").code == "VALIDATION_ERROR"
    assert ValidationAppError("x").status == 422
    assert NotFoundError("x").status == 404
    assert ConfirmWordMismatch("x").code == "CONFIRM_WORD_MISMATCH"
    assert HiddenNotBypassable("x").status == 400
    assert AppError("x").status == 500
    err = ValidationAppError("细节", field="name")
    assert err.detail["field"] == "name"


# ---------- 媒体工具 ----------


def test_media_helpers(tmp_path: Path) -> None:
    from PIL import Image

    image_path = tmp_path / "a.jpg"
    Image.new("RGB", (40, 30), (10, 200, 30)).save(image_path, format="JPEG")

    digest = file_md5(image_path)
    assert len(digest) == 32
    assert file_md5(image_path) == digest  # 稳定

    image = Image.open(image_path)
    ph1 = perceptual_hash(image)
    ph2 = perceptual_hash(image)
    assert ph1 == ph2 and len(ph1) == 16  # 64bit → 16 hex

    # EXIF 剥离
    with_exif = tmp_path / "b.jpg"
    Image.new("RGB", (10, 10), (1, 1, 1)).save(with_exif, format="JPEG")
    dest = tmp_path / "c.jpg"
    strip_exif(with_exif, dest)
    assert dest.is_file() and dest.stat().st_size > 0

    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    inside = root / "sub" / "x.jpg"
    inside.write_bytes(b"1")
    assert is_under(inside, root)
    assert not is_under(tmp_path / "outside.jpg", root)
    assert not is_under(root / ".." / "evil.jpg", root)


# ---------- 扫描器 ----------


def test_scanner_excludes_and_estimate(tmp_path: Path) -> None:
    (tmp_path / "keep.jpg").write_bytes(b"a")
    (tmp_path / "skip.png").write_bytes(b"b")
    nested = tmp_path / "node_modules"
    nested.mkdir()
    (nested / "deep.jpg").write_bytes(b"c")

    options = ScanOptions(
        extensions=(".jpg",),
        exclude_globs=("node_modules/*",),
        recursive=True,
    )
    found = sorted(p.name for p in iter_files(tmp_path, options))
    assert found == ["keep.jpg"]

    stats = estimate(tmp_path, options)
    assert stats["count"] == 1

    flat = ScanOptions(extensions=(".jpg", ".png"), exclude_globs=(), recursive=False)
    assert len(list(iter_files(tmp_path, flat))) == 2


def test_scanner_excludes_deleted_index_paths(tmp_path: Path) -> None:
    """exclude_paths：删除索引登记的路径在扫描与预估中都被跳过。"""
    keep = tmp_path / "keep.jpg"
    keep.write_bytes(b"a")
    dropped = tmp_path / "dropped.jpg"
    dropped.write_bytes(b"b")

    options = ScanOptions(
        extensions=frozenset({".jpg"}),
        exclude_globs=(),
        exclude_paths=frozenset({str(dropped)}),
    )
    assert [p.name for p in iter_files(tmp_path, options)] == ["keep.jpg"]
    assert estimate(tmp_path, options) == {"count": 1, "bytes": 1}


def test_scanner_non_recursive(tmp_path: Path) -> None:
    (tmp_path / "top.jpg").write_bytes(b"a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "inner.jpg").write_bytes(b"b")
    options = ScanOptions(extensions=(".jpg",), exclude_globs=(), recursive=False)
    names = [p.name for p in iter_files(tmp_path, options)]
    assert names == ["top.jpg"]
