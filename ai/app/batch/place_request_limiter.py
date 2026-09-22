"""Playwright PCMap 요청 사이의 보수적인 간격과 제한적 재시도를 관리한다."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class TransientRetryPolicy:
    """차단 신호가 아닌 일시적 전송 오류에만 제한적으로 적용되는 재시도 정책."""

    max_retries: int
    base_delay_seconds: float

    @classmethod
    def from_env(cls) -> TransientRetryPolicy:
        return cls(
            max_retries=min(2, max(0, int(os.environ.get("BATCH_TRANSIENT_MAX_RETRIES", "0")))),
            base_delay_seconds=max(
                0.0, float(os.environ.get("BATCH_TRANSIENT_RETRY_BACKOFF_SECONDS", "10"))
            ),
        )

    def delay(self, attempt: int) -> float:
        return self.base_delay_seconds * (2**attempt)

    @staticmethod
    def is_retryable(error: Exception) -> bool:
        return isinstance(error, ConnectionError) or type(error).__name__ == "TimeoutError"


class NavigationRateLimiter:
    def __init__(
        self,
        navigation_delay: float = 2.5,
        restaurant_delay: float = 5.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.navigation_delay = max(0.0, navigation_delay)
        self.restaurant_delay = max(0.0, restaurant_delay)
        self._clock = clock
        self._sleep = sleeper
        self._last_navigation: float | None = None

    def before_navigation(self) -> None:
        now = self._clock()
        if self._last_navigation is not None:
            remaining = self.navigation_delay - (now - self._last_navigation)
            if remaining > 0:
                self._sleep(remaining)
        self._last_navigation = self._clock()

    def after_restaurant(self) -> None:
        if self.restaurant_delay > 0:
            self._sleep(self.restaurant_delay)
