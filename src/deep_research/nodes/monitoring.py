"""Slow request monitoring utilities."""

from __future__ import annotations

import threading
import time
from collections import deque

_SLOW_THRESHOLD_SECS: float = 20.0
_SLOW_WINDOW_SECS: float = 300.0  # 5 minutes


class _SlowRequestCounter:
    """Thread-safe sliding window counter for requests exceeding a time threshold."""

    def __init__(self, threshold: float = _SLOW_THRESHOLD_SECS, window: float = _SLOW_WINDOW_SECS) -> None:
        self.threshold = threshold
        self.window = window
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def record(self, elapsed: float) -> int:
        """Record elapsed time. If >= threshold, add to window. Returns current slow count."""
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            if elapsed >= self.threshold:
                self._timestamps.append(now)
            return len(self._timestamps)

    def count(self) -> int:
        """Return how many slow requests occurred within the current window."""
        with self._lock:
            self._evict(time.monotonic())
            return len(self._timestamps)

    def _evict(self, now: float) -> None:
        cutoff = now - self.window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()


_slow_counter = _SlowRequestCounter()
