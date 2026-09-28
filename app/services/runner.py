"""任务执行器：识图 / OCR / 嵌入 / 扫描，含限速、预算、暂停恢复与退避重试。"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

from app.ai.prompts import (
    PromptStyle,
    build_entity_context,
    build_ocr_prompt,
    build_vision_prompt,
)
from app.ai.protocol import VisionRequest
from app.domain.errors import AiUnavailable, DirNotFoundError
from app.services import ingest, rules_svc
from app.services.entities_svc import select_injection

if TYPE_CHECKING:
    from app.services.state import AppState

WATCH_INTERVAL = 30.0


def _sensitive_words(state: AppState) -> list[str]:
    raw = str(state.settings.get("sensitive_words", "") or "")
    parts = raw.replace("，", ",").replace("、", ",").split(",")
    return [part.strip() for part in parts if part.strip()]


def _style(state: AppState) -> PromptStyle:
    return PromptStyle(
        language=state.settings.get_str("style_language", "中文"),
        style=state.settings.get_str("style_granularity", "简洁"),
        with_confidence=state.settings.get_bool("style_confidence", False),
        sensitive_words=tuple(_sensitive_words(state)),
    )


class JobRunner:
    """单进程 worker：claim 原子占位，网络调用在数据库锁之外执行。"""

    def __init__(self, state: AppState) -> None:
        self._state = state
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._watch_lock = threading.Lock()
        self._next_watch = 0.0

    # ---------- 生命周期 ----------

    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        count = max(1, min(8, self._state.settings.get_int("vision_concurrency", 2)))
        for index in range(count):
            thread = threading.Thread(target=self._loop, name=f"pa-worker-{index}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=5.0)
        self._threads.clear()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                wait = self.step()
                self._maybe_watch()
            except Exception:  # noqa: BLE001 — worker 兜底，绝不让线程静默退出
                wait = 1.0
            self._stop.wait(max(0.05, min(wait if wait > 0 else 0.2, 1.0)))

    def _maybe_watch(self) -> None:
        state = self._state
        if not state.settings.get_bool("watcher_enabled", False):
            return
        with self._watch_lock:
            now = time.monotonic()
            if now < self._next_watch:
                return
            self._next_watch = now + WATCH_INTERVAL
        try:
            ingest.poll_watchers(state)
        except Exception:  # noqa: BLE001 — 轮询失败不影响识图主链路
            state.notice("watch", "截图轮询失败，稍后自动重试", "warning")

    # ---------- 调度 ----------

    def step(self) -> float:
        """执行一个任务单元。返回建议等待秒数（0 = 还有活可立即继续）。"""
        state = self._state
        self.resume_paused()
        job = state.jobs.next_pending()
        if job is None:
            return 0.0
        job_id = int(job["id"])
        if not state.jobs.claim(job_id):
            return 0.0
        fresh = state.jobs.get(job_id) or job
        try:
            return self._dispatch(fresh)
        except AiUnavailable as exc:
            return self._fail(fresh, exc)
        except DirNotFoundError as exc:
            self._event(fresh, str(exc), "warning")
            self._succeed(fresh, str(exc))
            return 0.0
        except Exception as exc:  # noqa: BLE001 — 单任务失败不阻塞队列
            return self._fail(fresh, exc)

    def _dispatch(self, job: dict[str, Any]) -> float:
        jtype = str(job["type"])
        if jtype == "scan":
            return self._run_scan(job)
        if jtype == "analyze":
            return self._run_analyze(job)
        if jtype == "embed":
            return self._run_embed(job)
        self._fail_with_state(job, ValueError(f"未知任务类型：{jtype}"))
        return 0.0

    # ---------- 扫描 ----------

    def _run_scan(self, job: dict[str, Any]) -> float:
        state = self._state
        dir_id = job.get("dir_id")
        if dir_id is None:
            self._fail_with_state(job, ValueError("scan 任务缺少 dir_id"))
            return 0.0
        result = ingest.scan_directory(state, int(dir_id))
        self._event(job, f"扫描完成：{result}", "info")
        self._succeed(job, "扫描完成")
        return 0.0

    # ---------- 识图 ----------

    def _guard(
        self, job: dict[str, Any], image: dict[str, Any], dir_row: dict[str, Any] | None
    ) -> str | None:
        """外发前守门：返回 None 表示放行，否则返回跳过原因（零外发）。"""
        state = self._state
        if dir_row is None:
            return "目录不存在"
        if dir_row.get("offline"):
            return "目录已离线"
        if dir_row.get("frozen"):
            return "目录已冻结"
        haystack = f"{image.get('path', '')} {image.get('filename', '')}"
        if state.settings.get_bool("sensitive_guard", True):
            for word in _sensitive_words(state):
                if word and word in haystack:
                    return f"敏感词「{word}」命中，未外发"
        if dir_row.get("privacy"):
            return "隐私目录，永不外发云端"
        return None

    def _budget_ok(self) -> tuple[bool, int]:
        state = self._state
        limit = int(state.settings.get("daily_token_limit", 0))
        if limit <= 0:
            return True, 0
        used = state.images.tokens_today(state.deps.today())
        return used < limit, used

    def _run_analyze(self, job: dict[str, Any]) -> float:
        state = self._state
        image_id = int(job["image_id"] or 0)
        image = state.images.get(image_id) or state.images.get_hidden(image_id)
        if image is None:
            self._succeed(job, "图片已不存在")
            return 0.0
        dir_row = state.dirs.get(int(image["dir_id"]))
        if dir_row is None:
            state.images.update_any(image_id, analysis_state="skipped")
            self._event(job, "目录不存在", "warning")
            self._succeed(job, "目录不存在")
            return 0.0
        reason = self._guard(job, image, dir_row)
        if reason is not None:
            state.images.update_any(image_id, analysis_state="skipped")
            self._event(job, reason, "warning")
            self._succeed(job, reason)
            return 0.0

        payload = dict(job.get("payload") or {})
        wait = self._precheck(job, "vision")
        if wait is not None:
            return wait

        resume_ocr = payload.get("resume") == "ocr"
        if not resume_ocr:
            wait = self._acquire(job)
            if wait is not None:
                return wait
            self._analyze_once(job, image, dir_row, payload)
            fresh = self._payload_of(job)
            if fresh.get("need_ocr") is not True:
                self._enqueue_embed(image_id)
                self._succeed(job, "识图完成")
                return 0.0
            fresh["resume"] = "ocr"  # 先落 resume，OCR 限速/失败都不会重跑识图
            state.jobs.update_payload(int(job["id"]), fresh)
            wait = self._acquire(job)
            if wait is not None:
                return wait
            self._ocr_once(job, image, dir_row)
        else:
            wait = self._acquire(job)
            if wait is not None:
                return wait
            self._ocr_once(job, image, dir_row)
        self._enqueue_embed(image_id)
        self._succeed(job, "识图完成")
        return 0.0

    def _payload_of(self, job: dict[str, Any]) -> dict[str, Any]:
        fresh = self._state.jobs.get(int(job["id"]))
        payload = dict((fresh or {}).get("payload") or {})
        job["payload"] = payload
        return payload

    def _precheck(self, job: dict[str, Any], purpose: str) -> float | None:
        """预算与可用性检查；返回 None 放行，否则返回建议等待秒数。"""
        state = self._state
        ok, used = self._budget_ok()
        if not ok:
            limit = int(state.settings.get("daily_token_limit", 0))
            self._pause(
                job,
                "budget",
                0.0,
                f"今日 token 已用 {used}/{limit}，队列暂停，次日自动恢复",
            )
            return 0.0
        if purpose == "vision" and state.get_vision() is None:
            self._pause(job, "no_key", 0.0, "识图服务未配置或缺少 API Key，队列暂停")
            if state.settings.get_bool("notify_job_paused", True):
                state.notice("no_key", "识图队列已暂停：缺少可用的识图档案或 API Key", "warning")
            return 0.0
        if purpose == "ocr" and state.get_vision() is None:
            self._pause(job, "no_key", 0.0, "OCR 需要素材识图档案，队列暂停")
            return 0.0
        return None

    def _acquire(self, job: dict[str, Any]) -> float | None:
        """限速闸门；返回 None 表示已拿到名额。"""
        state = self._state
        decision = state.limiter.try_acquire()
        if decision.allowed:
            return None
        wait = max(0.2, decision.wait)
        self._pause(
            job,
            "rate",
            wait,
            f"识图达限速上限，{wait:.0f} 秒后继续",
            dedupe=True,
        )
        return wait

    def _pause(
        self,
        job: dict[str, Any],
        reason: str,
        wait: float,
        message: str,
        *,
        dedupe: bool = False,
    ) -> None:
        state = self._state
        payload = self._payload_of(job)
        payload["pause"] = reason
        state.jobs.update_payload(int(job["id"]), payload)
        # 恢复统一交给 resume_paused：限速用注入时钟判定，不能与 epoch retry_at 混用
        state.jobs.transition(int(job["id"]), "paused", error=message, retry_at=None)
        self._event(job, message, "warning")
        if not dedupe and state.settings.get_bool("notify_job_paused", True):
            state.notice("paused", message, "warning")

    def resume_paused(self) -> int:
        """条件恢复：限速到期 / 次日预算 / 密钥补齐 → 自动回 pending。"""
        state = self._state
        now = time.time()
        resumed = 0
        for job in state.jobs.rows(state="paused", limit=200):
            reason = str((job.get("payload") or {}).get("pause", ""))
            should = False
            if reason == "rate":
                should = job.get("retry_at") is None or float(job["retry_at"]) <= now
            elif reason == "budget":
                ok, _ = self._budget_ok()
                should = ok
            elif reason == "no_key":
                should = state.get_vision() is not None
            else:
                should = job.get("retry_at") is None or float(job["retry_at"]) <= now
            if should:
                state.jobs.transition(int(job["id"]), "pending", retry_at=None)
                resumed += 1
        return resumed

    def _analyze_once(
        self,
        job: dict[str, Any],
        image: dict[str, Any],
        dir_row: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        state = self._state
        image_id = int(image["id"])
        vision = state.get_vision()
        if vision is None:  # 与 _precheck 双保险
            raise AiUnavailable("识图服务不可用")
        state.images.update_any(image_id, analysis_state="running")
        style = _style(state)
        categories = [str(row["name"]) for row in state.catalog.list_categories()]
        override = state.settings.get_str("vision_prompt_override", "")
        prompt = override if override.strip() else build_vision_prompt(style, categories)
        selected, refs = select_injection(state, image)
        context_parts: list[str] = []
        if selected:
            context_parts.append(build_entity_context(selected, str(image["filename"])))
        feedback = str(payload.get("feedback") or image.get("last_feedback") or "")
        if payload.get("redo") and feedback:
            context_parts.append(f"人工纠正说明（必须遵循）：{feedback}")
        request = VisionRequest(
            image_path=str(image["path"]),
            prompt=prompt,
            model=state.settings.get_str("vision_model", ""),
            reference_paths=refs,
            context_text="\n".join(context_parts),
            allow_remote=not bool(dir_row.get("privacy")),
        )
        output = vision.analyze(request)

        fields: dict[str, Any] = {"analysis_state": "done"}
        if state.settings.get_bool("field_has_text", True):
            fields["has_text"] = int(output.has_text)
        if state.settings.get_bool("field_description", True) and output.description:
            fields["description_ai"] = output.description
        if state.settings.get_bool("field_tags", True):
            state.images.replace_ai_tags(image_id, output.ai_tags[:5])
        if state.settings.get_bool("field_elements", True):
            state.images.replace_elements(image_id, output.elements)
        if output.category:
            fields["category_ai"] = output.category
        state.images.add_analysis(
            image_id,
            category=output.category,
            description=output.description,
            has_text=output.has_text,
            model=output.model,
            tokens_in=output.tokens_in,
            tokens_out=output.tokens_out,
        )
        state.images.add_token_usage(
            image_id, "vision", output.model, output.tokens_in, output.tokens_out
        )
        state.images.update_any(image_id, **fields)
        state.images.sync_fts(image_id)
        rules_svc.apply_phase(state, state.images.get(image_id) or image, "pre")

        # OCR 按需触发
        policy = str(dir_row.get("ocr_policy") or "auto")
        if policy == "off":
            payload["need_ocr"] = False
            state.jobs.update_payload(int(job["id"]), payload)
            return
        want = bool(output.has_text) or policy == "on"
        payload["need_ocr"] = want
        state.jobs.update_payload(int(job["id"]), payload)

    def _ocr_once(
        self, job: dict[str, Any], image: dict[str, Any], dir_row: dict[str, Any]
    ) -> None:
        state = self._state
        image_id = int(image["id"])
        vision = state.get_vision()
        if vision is None:
            raise AiUnavailable("OCR 服务不可用")
        style = _style(state)
        request = VisionRequest(
            image_path=str(image["path"]),
            prompt=build_ocr_prompt(style),
            model=state.settings.get_str("vision_model", ""),
            allow_remote=not bool(dir_row.get("privacy")),
        )
        output = vision.ocr(request)
        text = output.text.strip()
        min_chars = int(state.settings.get("ocr_min_chars", 3))
        policy = str(dir_row.get("ocr_policy") or "auto")
        empty_policy = state.settings.get_str("ocr_empty_policy", "keep")
        if not text or len(text) < min_chars and policy != "on":
            keep = empty_policy == "keep"
        else:
            keep = True
        if keep:
            state.images.set_ocr(image_id, text, output.model, output.tokens_out)
            state.images.add_token_usage(
                image_id, "ocr", output.model, output.tokens_in, output.tokens_out
            )
            if text:
                state.images.update_any(image_id, has_text=1)
                rules_svc.apply_phase(
                    state,
                    state.images.get(image_id) or image,
                    "ocr",
                    ocr_text=text,
                )
                state.images.sync_fts(image_id)
        payload = dict(job.get("payload") or {})
        payload["need_ocr"] = False
        payload.pop("resume", None)
        state.jobs.update_payload(int(job["id"]), payload)

    # ---------- 嵌入 ----------

    def _enqueue_embed(self, image_id: int) -> None:
        state = self._state
        if state.get_embed() is None:
            return
        state.jobs.enqueue("embed", image_id=image_id, payload={})

    def _run_embed(self, job: dict[str, Any]) -> float:
        state = self._state
        image_id = int(job["image_id"] or 0)
        image = state.images.get(image_id) or state.images.get_hidden(image_id)
        if image is None:
            self._succeed(job, "图片已不存在")
            return 0.0
        embed = state.get_embed()
        if embed is None:
            self._event(job, "未配置嵌入服务，语义检索降级为关键词", "warning")
            self._succeed(job, "跳过嵌入")
            return 0.0
        description = str(image.get("description_manual") or image.get("description_ai") or "")
        tags = " ".join(state.images.ai_tags_of(image_id))
        elements = " ".join(state.images.elements_of(image_id))
        notes = str(image.get("notes") or "")
        text = "\n".join(part for part in (description, tags, elements, notes) if part)
        if not text:
            text = str(image.get("filename", ""))
        matrix = embed.embed([text])
        if matrix.size:
            state.images.set_vector(image_id, str(embed.model), matrix[0])
            state.images.add_token_usage(image_id, "embed", str(embed.model), 0, 0)
        self._succeed(job, "嵌入完成")
        return 0.0

    # ---------- 结果与失败 ----------

    def _event(self, job: dict[str, Any], message: str, level: str = "info") -> None:
        self._state.jobs.add_event(int(job["id"]), message, level)

    def _succeed(self, job: dict[str, Any], message: str) -> None:
        state = self._state
        state.jobs.transition(int(job["id"]), "succeeded", error=message)
        self._event(job, message, "info")

    def _fail(self, job: dict[str, Any], exc: Exception) -> float:
        return self._fail_with_state(job, exc)

    def _fail_with_state(self, job: dict[str, Any], exc: Exception) -> float:
        state = self._state
        job_id = int(job["id"])
        attempts = int(job.get("attempts") or 0) + 1
        max_attempts = int(job.get("max_attempts") or 3)
        message = str(exc) or exc.__class__.__name__
        image_id = job.get("image_id")
        state.jobs.transition(job_id, "failed", error=message, bump_attempt=True)
        self._event(job, f"{message}（第 {attempts} 次）", "error")
        if isinstance(exc, AiUnavailable) and attempts < max_attempts:
            backoff = min(5.0 * float(2 ** (attempts - 1)), 300.0)
            state.jobs.transition(job_id, "pending", retry_at=time.time() + backoff)
            return backoff
        state.jobs.transition(job_id, "dead", error=message)
        if image_id:
            state.images.update_any(int(image_id), analysis_state="failed")
        state.notice("job-dead", f"任务失败已达上限：{message}", "error")
        return 0.0

    # ---------- 手动操作 ----------

    def cancel(self, job_id: int) -> dict[str, Any]:
        state = self._state
        job = state.jobs.get(job_id)
        if job is None:
            from app.domain.errors import NotFoundError

            raise NotFoundError(f"任务不存在：{job_id}")
        if job["state"] in ("succeeded", "dead", "failed"):
            return job
        state.jobs.transition(job_id, "failed", error="用户取消")
        self._event(job, "用户取消", "warning")
        return state.jobs.get(job_id) or job

    def retry(self, job_id: int) -> dict[str, Any]:
        state = self._state
        job = state.jobs.get(job_id)
        if job is None:
            from app.domain.errors import NotFoundError

            raise NotFoundError(f"任务不存在：{job_id}")
        payload = dict(job.get("payload") or {})
        payload.pop("pause", None)
        state.jobs.update_payload(job_id, payload)
        state.jobs.transition(job_id, "pending", error=None, retry_at=None)
        return state.jobs.get(job_id) or job
