"""Low-overhead, immediately visible progress for long-running CLI batches."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping


def _duration(seconds: float) -> str:
    rounded = max(0, int(seconds))
    hours, remainder = divmod(rounded, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


class BatchProgress:
    def __init__(
        self,
        stage: str,
        total: int,
        metric_labels: Mapping[str, str],
        *,
        every: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        emit: Callable[[str], None] | None = None,
    ) -> None:
        self.stage = stage
        self.total = total
        configured_every = every if every is not None else int(
            os.environ.get("BATCH_PROGRESS_EVERY", "10")
        )
        self.every = max(1, configured_every)
        self.metric_labels = metric_labels
        self.counts = dict.fromkeys(metric_labels, 0)
        self.processed = 0
        self._clock = clock
        self._started = clock()
        self._emit = emit or (lambda line: print(line, flush=True))

    def current(self, restaurant_id: str | int, name: str) -> None:
        safe_name = " ".join(name.split())[:100]
        self._emit(
            f"[{self.stage}] current {self.processed + 1}/{self.total} "
            f"id={restaurant_id} name={safe_name}"
        )

    def complete(self, **increments: int) -> None:
        self.processed += 1
        for key, amount in increments.items():
            if key not in self.counts:
                raise KeyError(f"unknown progress metric: {key}")
            self.counts[key] += amount
        if self.processed % self.every == 0 or self.processed == self.total:
            self.summary()

    def summary(self) -> None:
        elapsed = max(0.0, self._clock() - self._started)
        average = elapsed / self.processed if self.processed else 0.0
        eta = average * max(0, self.total - self.processed)
        metrics = " | ".join(
            f"{label}: {self.counts[key]}" for key, label in self.metric_labels.items()
        )
        self._emit(
            f"[{self.stage}] {self.processed}/{self.total} "
            f"({self.processed / self.total:.1%}) | {metrics} | "
            f"elapsed: {_duration(elapsed)} | avg: {average:.1f}s/item | ETA: {_duration(eta)}"
        )

    def error(self, restaurant_id: str | int, message: str) -> None:
        self._emit(f"[{self.stage}][ERROR] id={restaurant_id} {message}")
