"""识图全局限速：滑动窗口 + 最小间隔双重约束（纯逻辑，时钟注入）。"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RateConfig:
    per_minute: int = 20
    min_interval: float = 3.0


@dataclass(frozen=True)
class Decision:
    allowed: bool
    wait: float = 0.0


class SlidingWindowLimiter:
    """默认 20 次/分钟且相邻请求间隔 >=3 秒；跨线程安全。"""

    def __init__(self, config: RateConfig, clock: Callable[[], float]) -> None:
        self._config = config
        self._clock = clock
        self._history: deque[float] = deque()
        self._lock = threading.Lock()

    @property
    def config(self) -> RateConfig:
        return self._config

    def reconfigure(self, config: RateConfig) -> None:
        with self._lock:
            self._config = config

    def try_acquire(self) -> Decision:
        with self._lock:
            now = self._clock()
            window = self._config
            while self._history and now - self._history[0] > 60.0:
                self._history.popleft()
            if self._history:
                since_last = now - self._history[-1]
                if since_last < window.min_interval:
                    return Decision(False, window.min_interval - since_last)
                if len(self._history) >= window.per_minute:
                    return Decision(False, 60.0 - (now - self._history[0]))
            self._history.append(now)
            return Decision(True, 0.0)

    def pending_wait(self) -> float:
        """当前若被拒绝需要等待的秒数（用于 UI 展示，不占用名额）。"""
        with self._lock:
            now = self._clock()
            while self._history and now - self._history[0] > 60.0:
                self._history.popleft()
            if not self._history:
                return 0.0
            if now - self._history[-1] < self._config.min_interval:
                return self._config.min_interval - (now - self._history[-1])
            if len(self._history) >= self._config.per_minute:
                return max(0.0, 60.0 - (now - self._history[0]))
            return 0.0
