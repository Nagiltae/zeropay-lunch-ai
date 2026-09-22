"""Kakao/NAVER 후보를 합치고 Qwen Entity Resolution 결과를 기록하는 CLI.

기본 경로는 report-only이며, 동일 source fingerprint의 REJECT만 provider와
Qwen을 다시 호출하지 않는다. 의미 판단은 Qwen에 맡기고 코드는 안전장치만 둔다.
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from app.batch.batch_progress import BatchProgress
from app.entity_resolution.qwen_candidate_matcher import (
    OllamaClient,
    QwenCandidateMatcher,
    configured_qwen_model,
)
from app.entity_resolution.verification_quality_gate import (
    VerificationDecision,
    VerificationResult,
    can_reuse_rejection,
    map_semantic_result,
    recommendation_eligibility,
    source_fingerprint,
    technical_unknown,
    unknown_reason_kind,
)
from app.providers.place_provider import (
    KakaoPlaceSearchProvider,
    NaverPlaceSearchProvider,
    PlaceSearchCandidate,
    ProviderSearchResult,
    candidate_json,
)
from app.providers.provider_input import load_local_env, load_provider_manifest

FIELDS = (
    "restaurant_id",
    "external_merchant_id",
    "komsco_name",
    "komsco_address",
    "source_fingerprint",
    "decision",
    "recommendation_eligibility",
    "verification_reason",
    "provider_calls_skipped",
    "qwen_calls_skipped",
    "kakao_candidate_count",
    "naver_candidate_count",
    "candidates_json",
    "kakao_error",
    "naver_error",
    "qwen_model",
    "qwen_ranking",
    "qwen_decision",
    "qwen_business_type",
    "qwen_location_scope",
    "qwen_reason",
    "kakao_selected_index",
    "kakao_external_id",
    "naver_selected_index",
    "naver_external_id",
    "error",
)


def _query_variants(reference) -> tuple[str, ...]:
    return tuple(dict.fromkeys((reference.komsco_name, f"논현동 {reference.komsco_name}")))


def _provider_concurrency() -> int:
    return min(2, max(1, int(os.environ.get("PROVIDER_CONCURRENCY", "1"))))


def _prefetch_size() -> int:
    return min(4, max(0, int(os.environ.get("PROVIDER_PREFETCH_SIZE", "2"))))


def _search_provider_variants(
    provider, reference, *, include_coordinates: bool
) -> tuple[ProviderSearchResult, ...]:
    results = []
    for query in _query_variants(reference):
        if include_coordinates:
            result = provider.search(
                query,
                longitude=reference.komsco_longitude,
                latitude=reference.komsco_latitude,
            )
        else:
            result = provider.search(query)
        results.append(result)
        error_key = (
            "kakao_error" if getattr(provider, "provider", "KAKAO") == "KAKAO" else "naver_error"
        )
        blocked = _blocked_provider_error({error_key: result.error})
        if blocked:
            raise RuntimeError(f"BLOCKED: {blocked}")
    return tuple(results)


@dataclass(frozen=True)
class ProviderBatchResult:
    kakao: tuple[ProviderSearchResult, ...]
    naver: tuple[ProviderSearchResult, ...]
    provider_latency_seconds: float
    prefetch_wait_seconds: float
    prefetch_hit: bool


class ProviderPrefetch:
    """Bounded one-flow-per-provider producer for the single Qwen consumer."""

    def __init__(self, kakao, naver, *, queue_size: int | None = None):
        self.queue_size = _prefetch_size() if queue_size is None else max(0, queue_size)
        workers = _provider_concurrency()
        self.kakao_pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="kakao")
        self.naver_pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="naver")
        self.kakao = kakao
        self.naver = naver
        self._closed = False

    def submit(self, reference) -> tuple[Future, Future, float]:
        submitted_at = time.monotonic()
        return (
            self.kakao_pool.submit(
                _search_provider_variants,
                self.kakao,
                reference,
                include_coordinates=True,
            ),
            self.naver_pool.submit(
                _search_provider_variants,
                self.naver,
                reference,
                include_coordinates=False,
            ),
            submitted_at,
        )

    def result(self, pending: tuple[Future, Future, float]) -> ProviderBatchResult:
        kakao_future, naver_future, submitted_at = pending
        ready = kakao_future.done() and naver_future.done()
        wait_started = time.monotonic()
        kakao = kakao_future.result()
        naver = naver_future.result()
        now = time.monotonic()
        return ProviderBatchResult(
            kakao=kakao,
            naver=naver,
            provider_latency_seconds=max(0.0, now - submitted_at),
            prefetch_wait_seconds=max(0.0, now - wait_started),
            prefetch_hit=ready,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.kakao_pool.shutdown(wait=True, cancel_futures=True)
        self.naver_pool.shutdown(wait=True, cancel_futures=True)
        for provider in (self.kakao, self.naver):
            close = getattr(provider, "close", None)
            if close:
                close()


def _blocked_provider_error(row: dict[str, str]) -> str | None:
    for field in ("kakao_error", "naver_error"):
        value = row.get(field, "")
        if any(token in value.upper() for token in ("HTTP_403", "HTTP_429", "CAPTCHA", "BLOCKED")):
            return f"{field}: {value}"
    return None


def _dedup_text(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def _candidate_key(candidate: PlaceSearchCandidate) -> tuple[object, ...]:
    # 동일 provider 외부 ID 또는 완전히 같은 evidence만 제거해 provenance와 순서를 보존한다.
    provider = _dedup_text(candidate.provider)
    external_id = _dedup_text(candidate.external_place_id)
    if external_id:
        return provider, "external_id", external_id
    detail_url = _dedup_text(candidate.detail_url)
    if detail_url:
        return provider, "detail_url", detail_url
    return (
        provider,
        "record",
        _dedup_text(candidate.name),
        _dedup_text(candidate.address),
        _dedup_text(candidate.road_address),
        _dedup_text(candidate.category),
        candidate.longitude,
        candidate.latitude,
    )


def _merge_with_stats(
    results: tuple[ProviderSearchResult, ...],
) -> tuple[tuple[PlaceSearchCandidate, ...], int, int]:
    seen: set[tuple[object, ...]] = set()
    merged: list[PlaceSearchCandidate] = []
    for result in results:
        for candidate in result.candidates:
            key = _candidate_key(candidate)
            if key not in seen:
                seen.add(key)
                merged.append(candidate)
    before = sum(len(result.candidates) for result in results)
    return tuple(merged), before, before - len(merged)


def _merge(results: tuple[ProviderSearchResult, ...]) -> tuple[PlaceSearchCandidate, ...]:
    return _merge_with_stats(results)[0]


def _source(reference) -> dict[str, object]:
    return {
        "external_merchant_id": reference.external_merchant_id,
        "name": reference.komsco_name,
        "address": reference.komsco_address,
        "latitude": reference.komsco_latitude,
        "longitude": reference.komsco_longitude,
        "legal_dong_code": "11680108",
        "provider_institution_code": "I0000002",
        "industry_code": "561",
        "business_status_name": "계속사업자",
    }


def _cached_rejection(reference, cache: dict[str, dict[str, str]]) -> dict[str, str] | None:
    cached = cache.get(reference.external_merchant_id or "")
    if not cached or cached.get("decision") != "REJECT":
        return None
    fingerprint = source_fingerprint(_source(reference))
    result = VerificationResult(
        decision=VerificationDecision.REJECT, reason=cached.get("verification_reason", "")
    )
    return (
        cached
        if can_reuse_rejection(result, cached.get("source_fingerprint"), fingerprint)
        else None
    )


def _cache_rows(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as stream:
        rows = csv.DictReader(stream)
        return {row["external_merchant_id"]: row for row in rows if row.get("external_merchant_id")}


def _db_reject_cache(root: Path) -> dict[str, dict[str, str]]:
    query = """
    SELECT r.external_merchant_id, v.source_fingerprint, v.verification_reason, v.model_name
    FROM restaurant_naver_verifications v
    JOIN restaurants r ON r.id = v.restaurant_id
    WHERE v.provider = 'NAVER' AND v.verification_status = 'REJECTED'
    """
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "mysql",
        "sh",
        "-c",
        f'MYSQL_PWD="zeropay_local" mysql --default-character-set=utf8mb4 '
        f'--batch --raw -u zeropay zeropay_lunch -e "{query}"',
    ]
    process = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"MySQL reject cache query failed: {process.stderr}")
    lines = process.stdout.strip().splitlines()
    if len(lines) <= 1:
        return {}
    headers = lines[0].split("\t")
    cache = {}
    for line in lines[1:]:
        values = line.split("\t")
        row = dict(zip(headers, values, strict=True))
        merchant_id = row.get("external_merchant_id")
        if merchant_id:
            cache[merchant_id] = {
                "external_merchant_id": merchant_id,
                "source_fingerprint": row.get("source_fingerprint", ""),
                "verification_reason": row.get("verification_reason", ""),
                "qwen_model": row.get("model_name", ""),
                "decision": "REJECT",
            }
    return cache


def _base(reference, fingerprint: str) -> dict[str, str]:
    return {
        "restaurant_id": str(reference.restaurant_id),
        "external_merchant_id": reference.external_merchant_id or "",
        "komsco_name": reference.komsco_name,
        "komsco_address": reference.komsco_address,
        "source_fingerprint": fingerprint,
        "decision": "UNKNOWN",
        "recommendation_eligibility": "UNKNOWN",
        "verification_reason": "",
        "provider_calls_skipped": "false",
        "qwen_calls_skipped": "false",
        "kakao_candidate_count": "0",
        "naver_candidate_count": "0",
        "candidates_json": "[]",
        "kakao_error": "",
        "naver_error": "",
        "qwen_model": configured_qwen_model(),
        "qwen_ranking": "",
        "qwen_decision": "",
        "qwen_business_type": "",
        "qwen_location_scope": "",
        "qwen_reason": "",
        "kakao_selected_index": "",
        "kakao_external_id": "",
        "naver_selected_index": "",
        "naver_external_id": "",
        "error": "",
    }


def evaluate_reference(
    reference,
    kakao,
    naver,
    matcher,
    cached=None,
    provider_results: ProviderBatchResult | None = None,
    on_candidates=None,
) -> dict[str, str]:
    fingerprint = source_fingerprint(_source(reference))
    row = _base(reference, fingerprint)
    if cached and can_reuse_rejection(
        VerificationResult(
            decision=VerificationDecision.REJECT,
            reason=cached.get("verification_reason", ""),
        )
        if cached.get("decision") == "REJECT"
        else None,
        cached.get("source_fingerprint"),
        fingerprint,
    ):
        row.update({key: value for key, value in cached.items() if key in FIELDS})
        row["restaurant_id"] = str(reference.restaurant_id)
        row["source_fingerprint"] = fingerprint
        row["recommendation_eligibility"] = "INELIGIBLE"
        row["provider_calls_skipped"] = "true"
        row["qwen_calls_skipped"] = "true"
        return row

    if provider_results is None:
        kakao_results = _search_provider_variants(kakao, reference, include_coordinates=True)
        naver_results = _search_provider_variants(naver, reference, include_coordinates=False)
    else:
        kakao_results = provider_results.kakao
        naver_results = provider_results.naver
    blocked = _blocked_provider_error(
        {
            "kakao_error": ";".join(result.error for result in kakao_results if result.error),
            "naver_error": ";".join(result.error for result in naver_results if result.error),
        }
    )
    if blocked:
        raise RuntimeError(f"BLOCKED: {blocked}")
    candidates, candidate_count_before, duplicate_candidates_removed = _merge_with_stats(
        kakao_results + naver_results
    )
    if on_candidates:
        on_candidates(
            candidate_count_before,
            len(candidates),
            duplicate_candidates_removed,
        )
    row.update(
        {
            "kakao_candidate_count": str(sum(len(result.candidates) for result in kakao_results)),
            "naver_candidate_count": str(sum(len(result.candidates) for result in naver_results)),
            "candidates_json": candidate_json(candidates),
            "kakao_error": ";".join(sorted({r.error for r in kakao_results if r.error})),
            "naver_error": ";".join(sorted({r.error for r in naver_results if r.error})),
        }
    )
    if not candidates:
        errors = tuple(
            error for result in kakao_results + naver_results for error in [result.error] if error
        )
        result = technical_unknown(errors[0] if errors else "NO_CANDIDATE", configured_qwen_model())
        row["error"] = result.reason if errors else ""
        row["verification_reason"] = result.reason
        row["recommendation_eligibility"] = recommendation_eligibility(result)
        row["decision"] = result.decision.value
        return row

    try:
        ranking = matcher.choose(reference, candidates)
        row["qwen_ranking"] = ",".join(str(index) for index in ranking.candidate_indices)
        decisions = []
        accepted_indices = {}
        for index in ranking.candidate_indices:
            candidate = candidates[index]
            if candidate.provider in accepted_indices:
                continue

            decision = matcher.validate(reference, candidate)
            decisions.append(decision)
            if decision.final_decision == "ACCEPT":
                accepted_indices[candidate.provider] = index

            if "KAKAO" in accepted_indices and "NAVER" in accepted_indices:
                break

        accepted = next(
            (decision for decision in decisions if decision.final_decision == "ACCEPT"),
            None,
        )
        selected = accepted or decisions[-1]

        kakao_selected_index = ""
        kakao_external_id = ""
        naver_selected_index = ""
        naver_external_id = ""

        if "KAKAO" in accepted_indices:
            idx = accepted_indices["KAKAO"]
            kakao_selected_index = str(idx)
            kakao_external_id = candidates[idx].external_place_id or ""

        if "NAVER" in accepted_indices:
            idx = accepted_indices["NAVER"]
            naver_selected_index = str(idx)
            naver_external_id = candidates[idx].external_place_id or ""
        elif "NAVER_LOCAL" in accepted_indices:
            idx = accepted_indices["NAVER_LOCAL"]
            naver_selected_index = str(idx)
            naver_external_id = candidates[idx].external_place_id or ""

        all_rejected = decisions and all(item.final_decision == "REJECT" for item in decisions)
        result = map_semantic_result(
            final_decision=("ACCEPT" if accepted else "REJECT" if all_rejected else "UNCERTAIN"),
            business_type=selected.business_type,
            location_scope=selected.location_scope,
            reason=selected.reason,
            model=configured_qwen_model(),
        )
        row.update(
            {
                "qwen_decision": selected.final_decision,
                "qwen_business_type": selected.business_type,
                "qwen_location_scope": selected.location_scope,
                "qwen_reason": selected.reason,
                "kakao_selected_index": kakao_selected_index,
                "kakao_external_id": kakao_external_id,
                "naver_selected_index": naver_selected_index,
                "naver_external_id": naver_external_id,
            }
        )
    except (ValueError, RuntimeError) as error:
        result = technical_unknown("STRUCTURED_OUTPUT_ERROR", configured_qwen_model())
        row["error"] = type(error).__name__
        row["verification_reason"] = result.reason
        row["recommendation_eligibility"] = recommendation_eligibility(result)
        row["decision"] = result.decision.value
        return row
    row["decision"] = result.decision.value
    row["verification_reason"] = result.reason
    row["recommendation_eligibility"] = recommendation_eligibility(result)
    return row


def main() -> int:
    # 이 단계는 후보 수집과 의미 판단만 담당하며 canonical/detail DB 상태를 직접 만들지 않는다.
    parser = argparse.ArgumentParser(
        description="Official provider fusion and Qwen Entity Resolution"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cache",
        type=Path,
        help="previous fusion report; only unchanged REJECT rows are reused",
    )
    parser.add_argument(
        "--db-reject-cache",
        action="store_true",
        help="reuse unchanged REJECT decisions from MySQL without provider or Qwen calls",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--preexisting-skipped",
        type=int,
        default=0,
        help="verified DB rows excluded before manifest creation; reporting only",
    )
    args = parser.parse_args()
    if args.preexisting_skipped < 0:
        parser.error("--preexisting-skipped must be non-negative")
    root = Path(__file__).resolve().parents[2]
    load_local_env(root)
    references = list(load_provider_manifest(args.manifest))
    if args.limit is not None:
        references = references[: args.limit]
    cache = _cache_rows(args.cache)
    if args.db_reject_cache:
        cache.update(_db_reject_cache(root))
    report_dir = root / "ai/build/reports/naver-place-pipeline/e2e"
    BatchProgress.enforce_cooldown(report_dir, "Entity Resolution")
    kakao = KakaoPlaceSearchProvider()
    naver = NaverPlaceSearchProvider()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    progress = BatchProgress(
        "Entity Resolution",
        len(references),
        {
            "cache_skip": "cache skip",
            "qwen": "Qwen 호출 음식점",
            "accept": "ACCEPT",
            "reject": "REJECT",
            "unknown": "UNKNOWN",
        },
        report_dir=report_dir,
    )
    progress.skip_preexisting(args.preexisting_skipped)
    qwen_client = OllamaClient()
    matcher = QwenCandidateMatcher(
        qwen_client,
        on_call=lambda operation, latency: progress.record_qwen_call(operation, latency),
    )
    status = "COMPLETED"
    reason = None
    current_id = None
    prefetch = ProviderPrefetch(kakao, naver)
    pending = deque()
    next_reference = 0

    def fill_prefetch_queue() -> None:
        nonlocal next_reference
        capacity = prefetch.queue_size + 1
        while next_reference < len(references) and len(pending) < capacity:
            reference = references[next_reference]
            pending.append(
                (
                    reference,
                    None if _cached_rejection(reference, cache) else prefetch.submit(reference),
                )
            )
            next_reference += 1

    try:
        with args.output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            fill_prefetch_queue()
            for _ in references:
                reference, provider_future = pending.popleft()
                current_id = reference.restaurant_id
                if reference.processing_reason:
                    progress.record_reason(reference.processing_reason)
                progress.current(reference.restaurant_id, reference.komsco_name)
                try:
                    provider_results = (
                        prefetch.result(provider_future) if provider_future is not None else None
                    )
                    if provider_results is not None:
                        progress.record_provider(
                            kakao_requests=len(provider_results.kakao),
                            naver_requests=len(provider_results.naver),
                            latency_seconds=provider_results.provider_latency_seconds,
                            prefetch_wait_seconds=provider_results.prefetch_wait_seconds,
                            prefetch_hit=provider_results.prefetch_hit,
                        )
                    fill_prefetch_queue()
                    row = evaluate_reference(
                        reference,
                        kakao,
                        naver,
                        matcher,
                        cache.get(reference.external_merchant_id or ""),
                        provider_results=provider_results,
                        on_candidates=progress.record_qwen_candidates,
                    )
                except Exception as error:
                    if "BLOCKED:" in str(error):
                        progress.block(reference.restaurant_id, error)
                    else:
                        progress.error(reference.restaurant_id, str(error))
                    raise
                blocked_error = _blocked_provider_error(row)
                if blocked_error:
                    progress.block(reference.restaurant_id, RuntimeError(blocked_error))
                    raise RuntimeError(f"BLOCKED: {blocked_error}")
                writer.writerow(row)
                stream.flush()
                if row.get("error") or row.get("kakao_error") or row.get("naver_error"):
                    errors = "; ".join(
                        filter(
                            None,
                            (
                                row.get("error"),
                                row.get("kakao_error"),
                                row.get("naver_error"),
                            ),
                        )
                    )
                    progress.error(reference.restaurant_id, errors)
                cache_skipped = row["qwen_calls_skipped"] == "true"
                if cache_skipped:
                    progress.record_reason("REJECT_CACHE_REUSED")
                if row["decision"] == "UNKNOWN":
                    unknown_reason = row.get("verification_reason", "UNKNOWN")
                    progress.record_reason(f"UNKNOWN_{unknown_reason_kind(unknown_reason)}")
                    progress.record_reason(f"UNKNOWN_REASON_{unknown_reason}")
                has_candidates = (
                    int(row["kakao_candidate_count"]) + int(row["naver_candidate_count"]) > 0
                )
                outcome = (
                    "skipped" if cache_skipped else "failed" if row.get("error") else "success"
                )
                progress.record(
                    outcome,
                    reference.restaurant_id,
                    cache_skip=int(cache_skipped),
                    qwen=int(not cache_skipped and has_candidates),
                    accept=int(row["decision"] == "ACCEPT"),
                    reject=int(row["decision"] == "REJECT"),
                    unknown=int(row["decision"] == "UNKNOWN"),
                )
    except BaseException as error:
        status = (
            "INTERRUPTED"
            if isinstance(error, KeyboardInterrupt)
            else "BLOCKED"
            if isinstance(error, Exception) and "BLOCKED:" in str(error)
            else "FAILED"
        )
        reason = str(error) or type(error).__name__
        if current_id is not None:
            progress.last_failure_restaurant_id = current_id
        raise
    finally:
        prefetch.close()
        close_qwen = getattr(qwen_client, "close", None)
        if close_qwen:
            close_qwen()
        if progress.failed and status == "COMPLETED":
            status = "PARTIAL"
        progress.finish(status, reason)
    print(
        f"processed={len(references)} elapsed_seconds={time.monotonic() - started:.2f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
