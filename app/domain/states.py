"""任务与识图状态机（纯函数校验）。"""

from __future__ import annotations

JOB_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"running", "paused", "failed"},
    "running": {"succeeded", "failed", "paused", "pending"},
    "paused": {"pending", "failed", "dead"},
    "failed": {"pending", "dead", "paused"},
    "succeeded": set(),
    "dead": {"pending"},
}

ANALYSIS_TRANSITIONS: dict[str, set[str]] = {
    "unanalyzed": {"queued"},
    "queued": {"running", "skipped"},
    "running": {"done", "failed", "queued"},
    "done": {"queued", "running"},
    "failed": {"queued", "running", "skipped"},
    "skipped": {"queued"},
}


def can_transition_job(current: str, target: str) -> bool:
    return target in JOB_TRANSITIONS.get(current, set())


def can_transition_analysis(current: str, target: str) -> bool:
    return target in ANALYSIS_TRANSITIONS.get(current, set())
