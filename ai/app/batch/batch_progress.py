"""장시간 CLI 배치의 진행률과 종료 보고서를 공통 형식으로 기록한다.

각 단계 CLI와 E2E 오케스트레이터가 같은 진행 상태 모델을 사용하므로,
실행 중 stdout과 종료 후 JSON 보고서의 의미를 일관되게 유지한다.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path


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
        report_dir: Path | None = None,
        run_id: str | None = None,
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
        self._block_cooldown_seconds = max(
            0.0, float(os.environ.get("NAVER_BLOCK_COOLDOWN_SECONDS", "1800"))
        )
        self.report_dir = report_dir
        requested_run_id = run_id or os.environ.get("BATCH_RUN_ID") or datetime.now(UTC).strftime(
            "%Y%m%d-%H%M%S-%f"
        )
        self.run_id = re.sub(r"[^A-Za-z0-9_-]", "_", requested_run_id)
        self.started_at = datetime.now(UTC)
        self.success = self.failed = self.skipped = 0
        self.preexisting_skipped = 0
        self.retries = self.blocked_count = self.http_429 = 0
        self.provider_requests = self.kakao_requests = self.naver_requests = 0
        self.provider_latency_seconds = self.prefetch_wait_seconds = 0.0
        self.prefetch_hits = self.prefetch_waits = 0
        self.qwen_calls = self.qwen_choose_calls = self.qwen_validate_calls = 0
        self.qwen_total_latency_seconds = 0.0
        self.candidate_count_before_dedup = self.candidate_count_after_dedup = 0
        self.duplicate_candidates_removed = 0
        self.reason_counts: dict[str, int] = {}
        self.browser_starts = self.browser_restarts = self.page_recreates = 0
        self.last_success_restaurant_id: str | int | None = None
        self.last_failure_restaurant_id: str | int | None = None
        self._current_restaurant_id: str | int | None = None
        self._finished = False

    def current(self, restaurant_id: str | int, name: str) -> None:
        self._current_restaurant_id = restaurant_id
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

    def record(self, outcome: str, restaurant_id: str | int, **increments: int) -> None:
        if outcome == "success":
            self.success += 1
            self.last_success_restaurant_id = restaurant_id
        elif outcome == "failed":
            self.failed += 1
            self.last_failure_restaurant_id = restaurant_id
        elif outcome == "skipped":
            self.skipped += 1
        else:
            raise ValueError(f"invalid outcome: {outcome}")
        self.complete(**increments)

    def retry(self, restaurant_id: str | int, delay_seconds: float, error: Exception) -> None:
        self.retries += 1
        self._emit(
            f"[{self.stage}][RETRY] id={restaurant_id} retry_total={self.retries} "
            f"backoff={delay_seconds:.1f}s reason={error}"
        )

    def skip_preexisting(self, count: int) -> None:
        self.preexisting_skipped += count

    def record_reason(self, reason: str, count: int = 1) -> None:
        if count < 0:
            raise ValueError("reason count must be non-negative")
        if reason:
            self.reason_counts[reason] = self.reason_counts.get(reason, 0) + count

    def record_provider(
        self, *, kakao_requests: int, naver_requests: int, latency_seconds: float,
        prefetch_wait_seconds: float = 0.0, prefetch_hit: bool = False,
    ) -> None:
        self.kakao_requests += kakao_requests
        self.naver_requests += naver_requests
        self.provider_requests += kakao_requests + naver_requests
        self.provider_latency_seconds += latency_seconds
        self.prefetch_wait_seconds += prefetch_wait_seconds
        self.prefetch_hits += int(prefetch_hit)
        self.prefetch_waits += int(not prefetch_hit)

    def record_browser_lifecycle(
        self, *, browser_starts: int = 0, browser_restarts: int = 0, page_recreates: int = 0,
    ) -> None:
        self.browser_starts += browser_starts
        self.browser_restarts += browser_restarts
        self.page_recreates += page_recreates

    def record_qwen_call(self, operation: str, latency_seconds: float) -> None:
        self.qwen_calls += 1
        if operation == "choose":
            self.qwen_choose_calls += 1
        elif operation == "validate":
            self.qwen_validate_calls += 1
        else:
            raise ValueError(f"unknown Qwen operation: {operation}")
        self.qwen_total_latency_seconds += max(0.0, latency_seconds)

    def record_qwen_candidates(self, before: int, after: int, duplicates_removed: int) -> None:
        self.candidate_count_before_dedup += before
        self.candidate_count_after_dedup += after
        self.duplicate_candidates_removed += duplicates_removed

    def block(self, restaurant_id: str | int, error: Exception) -> None:
        self.blocked_count += 1
        self.http_429 += int("429" in str(error))
        self.error(restaurant_id, str(error))
        self.record("failed", restaurant_id)

    def finish(self, status: str = "COMPLETED", reason: str | None = None) -> Path | None:
        if self._finished:
            return None
        self._finished = True
        elapsed = max(0.0, self._clock() - self._started)
        finished_at = datetime.now(UTC)
        resume_after = (
            (finished_at + timedelta(seconds=self._block_cooldown_seconds)).isoformat()
            if status == "BLOCKED" else None
        )
        report = {
            "run_id": self.run_id,
            "stage": self.stage,
            "started_at": self.started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": status,
            "target_count": self.total,
            "processed": self.processed,
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped + self.preexisting_skipped,
            "preexisting_skipped": self.preexisting_skipped,
            "retry": self.retries,
            "blocked": self.blocked_count,
            "http_429": self.http_429,
            "provider_requests": self.provider_requests,
            "kakao_requests": self.kakao_requests,
            "naver_requests": self.naver_requests,
            "provider_avg_latency_seconds": round(
                self.provider_latency_seconds / self.provider_requests, 3
            ) if self.provider_requests else None,
            "prefetch_hits": self.prefetch_hits,
            "prefetch_waits": self.prefetch_waits,
            "prefetch_wait_seconds": round(self.prefetch_wait_seconds, 3),
            "qwen_calls": self.qwen_calls,
            "qwen_choose_calls": self.qwen_choose_calls,
            "qwen_validate_calls": self.qwen_validate_calls,
            "qwen_total_latency_seconds": round(self.qwen_total_latency_seconds, 3),
            "qwen_avg_latency_seconds": round(
                self.qwen_total_latency_seconds / self.qwen_calls, 3
            ) if self.qwen_calls else None,
            "candidate_count_before_dedup": self.candidate_count_before_dedup,
            "candidate_count_after_dedup": self.candidate_count_after_dedup,
            "duplicate_candidates_removed": self.duplicate_candidates_removed,
            "reason_counts": dict(self.reason_counts),
            "browser_starts": self.browser_starts,
            "browser_restarts": self.browser_restarts,
            "page_recreates": self.page_recreates,
            "elapsed_seconds": round(elapsed, 3),
            "avg_seconds_per_item": round(elapsed / self.processed, 3) if self.processed else None,
            "eta_seconds": round(elapsed / self.processed * max(0, self.total - self.processed), 3)
            if self.processed else None,
            "interruption_reason": reason,
            "resume_not_before": resume_after,
            "last_success_restaurant_id": self.last_success_restaurant_id,
            "last_failure_restaurant_id": self.last_failure_restaurant_id,
            "metrics": dict(self.counts),
        }
        if self.report_dir is None:
            return None
        self.report_dir.mkdir(parents=True, exist_ok=True)
        stage_key = self.stage.lower().replace(" ", "_")
        path = self.report_dir / f"{self.run_id}-{stage_key}.json"
        with path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        self._emit(f"[{self.stage}] runtime report: {path}")
        return path

    @staticmethod
    def enforce_cooldown(report_dir: Path, stage: str) -> None:
        if not report_dir.exists():
            return
        now = datetime.now(UTC)
        for path in report_dir.glob("*.json"):
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
                if report.get("stage") not in {"Entity Resolution", "Place ID", "Detail"}:
                    continue
                resume_after = report.get("resume_not_before")
                if resume_after and datetime.fromisoformat(resume_after) > now:
                    raise RuntimeError(
                        f"{stage} cooldown until {resume_after}; previous BLOCKED report: {path}"
                    )
            except (OSError, ValueError, KeyError):
                continue

    def summary(self) -> None:
        elapsed = max(0.0, self._clock() - self._started)
        average = elapsed / self.processed if self.processed else 0.0
        eta = average * max(0, self.total - self.processed)
        metrics = " | ".join(
            f"{label}: {self.counts[key]}" for key, label in self.metric_labels.items()
        )
        self._emit(
            f"[{self.stage}] {self.processed}/{self.total} "
            f"({self.processed / self.total:.1%}) | success: {self.success} | "
            f"failed: {self.failed} | skip: {self.skipped + self.preexisting_skipped} | "
            f"retry: {self.retries} | "
            f"blocked: {self.blocked_count} | HTTP 429: {self.http_429} | {metrics} | "
            f"provider: {self.provider_requests} "
            f"(K:{self.kakao_requests}/N:{self.naver_requests}) | "
            f"qwen: {self.qwen_calls} "
            f"(choose:{self.qwen_choose_calls}/validate:{self.qwen_validate_calls}) | "
            f"elapsed: {_duration(elapsed)} | avg: {average:.1f}s/item | ETA: {_duration(eta)}"
        )

    def error(self, restaurant_id: str | int, message: str) -> None:
        self._emit(f"[{self.stage}][ERROR] id={restaurant_id} {message}")
