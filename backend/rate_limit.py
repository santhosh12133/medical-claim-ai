"""Small in-process sliding-window rate limiter (per API process).

Good enough to blunt password guessing on a single instance; put a shared
limiter (e.g. Redis or the ingress) in front for multi-instance deployments.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._events[key]
        while events and now - events[0] > self.window_seconds:
            events.popleft()
        return events

    def is_limited(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self.max_attempts

    def hit(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def retry_after(self, key: str) -> int:
        with self._lock:
            events = self._prune(key, time.monotonic())
            if not events:
                return 0
            return max(1, int(self.window_seconds - (time.monotonic() - events[0])))
