"""Kakao/NAVER 후보를 합치고 Qwen Entity Resolution 결과를 기록하는 CLI.

기본 경로는 report-only이며, 동일 source fingerprint의 REJECT만 provider와
Qwen을 다시 호출하지 않는다. 의미 판단은 Qwen에 맡기고 코드는 안전장치만 둔다.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
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
    "search_policy_version",
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

# 검색어 생성/Provider Round 정책을 바꾸면 이 값을 올린다. 기존 NULL 행은
# 자동 대량 재처리하지 않고, 오케스트레이터의 명시적 재검증 옵션으로만 다룬다.
SEARCH_POLICY_VERSION = "provider-search-v2"


def _query_variants(reference) -> tuple[str, ...]:
    return tuple(dict.fromkeys((reference.komsco_name, f"논현동 {reference.komsco_name}")))


def _provider_query_rounds(reference, provider_name: str) -> tuple[tuple[str, ...], ...]:
    name = reference.komsco_name
    local_name = f"논현동 {name}"
    fallback_queries = _fallback_query_variants(name)
    if provider_name == "NAVER_LOCAL":
        return (
            tuple(dict.fromkeys((local_name,))),
            tuple(dict.fromkeys((name, *fallback_queries))),
        )
    return (
        tuple(dict.fromkeys((name,))),
        tuple(dict.fromkeys((local_name, *fallback_queries))),
    )


def _fallback_query_variants(name: str) -> tuple[str, ...]:
    """Return only conservative name fallbacks; the KOMSCO reference is unchanged."""
    text = re.sub(r"\s+", " ", name or "").strip()
    if not text:
        return ()
    queries: list[str] = []
    branch_match = re.search(r"\s+(본점|지점|\d+호점)$", text)
    if branch_match:
        branch_name = text[: branch_match.start()].strip()
        if len(branch_name) >= 2:
            queries.append(branch_name)
            branch_tokens = branch_name.split()
            if len(branch_tokens) >= 2:
                # 지점 표기가 명확한 경우에만 앞쪽 법인/대표자 토큰을 포함하지 않은
                # 마지막 상호 토큰도 보조 후보로 사용한다. 최종 동일성은 Qwen이 판단한다.
                queries.append(branch_tokens[-1])
    if re.match(r"^(?:\(주\)|㈜|주식회사|유한회사)\s*", text):
        stripped = re.sub(r"^(?:\(주\)|㈜|주식회사|유한회사)\s*", "", text)
        tokens = stripped.split()
        if len(tokens) >= 3:
            # 법인 표기가 명시된 경우에만 마지막 상호·지점 토큰을 보조 검색한다.
            queries.append(f"{tokens[-1]} {tokens[-2]}")
    return tuple(dict.fromkeys(queries))


def _provider_concurrency() -> int:
    return min(2, max(1, int(os.environ.get("PROVIDER_CONCURRENCY", "1"))))


def _prefetch_size() -> int:
    return min(4, max(0, int(os.environ.get("PROVIDER_PREFETCH_SIZE", "2"))))


def _search_provider_variants(
    provider, reference, *, include_coordinates: bool, queries: tuple[str, ...] | None = None
) -> tuple[ProviderSearchResult, ...]:
    results = []
    for query in queries or _query_variants(reference):
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
    round_number: int = 1


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

    def submit(
        self, reference, *, round_number: int | None = None
    ) -> tuple[Future, Future, float, int]:
        submitted_at = time.monotonic()
        if round_number is None:
            # 단독 CLI/기존 호출자는 기존 전체 query variant 계약을 유지한다.
            kakao_queries = _query_variants(reference)
            naver_queries = _query_variants(reference)
            stored_round = 1
        else:
            kakao_rounds = _provider_query_rounds(reference, "KAKAO")
            naver_rounds = _provider_query_rounds(reference, "NAVER_LOCAL")
            kakao_queries = (
                kakao_rounds[round_number - 1] if round_number <= len(kakao_rounds) else ()
            )
            naver_queries = (
                naver_rounds[round_number - 1] if round_number <= len(naver_rounds) else ()
            )
            stored_round = round_number
        def timed_search(provider, queries, *, include_coordinates: bool):
            started = time.monotonic()
            print(
                f"[Entity Resolution][PROVIDER_START] provider={provider.provider} "
                f"round={stored_round} requests={len(queries)}",
                flush=True,
            )
            result = _search_provider_variants(
                provider,
                reference,
                include_coordinates=include_coordinates,
                queries=queries,
            )
            print(
                f"[Entity Resolution][PROVIDER_END] provider={provider.provider} "
                f"round={stored_round} requests={len(result)} "
                f"candidates={sum(len(item.candidates) for item in result)} "
                f"errors={sum(bool(item.error) for item in result)} "
                f"elapsed={time.monotonic() - started:.3f}s",
                flush=True,
            )
            return result

        return (
            self.kakao_pool.submit(
                timed_search, self.kakao, kakao_queries, include_coordinates=True
            ),
            self.naver_pool.submit(
                timed_search, self.naver, naver_queries, include_coordinates=False
            ),
            submitted_at,
            stored_round,
        )

    def result(self, pending: tuple[Future, Future, float, int]) -> ProviderBatchResult:
        kakao_future, naver_future, submitted_at, round_number = pending
        ready = kakao_future.done() and naver_future.done()
        wait_started = time.monotonic()
        print(
            f"[Entity Resolution][PREFETCH_WAIT_START] round={round_number} ready={ready}",
            flush=True,
        )
        kakao = kakao_future.result()
        naver = naver_future.result()
        now = time.monotonic()
        print(
            f"[Entity Resolution][PREFETCH_WAIT_END] round={round_number} "
            f"elapsed={now - wait_started:.3f}s",
            flush=True,
        )
        return ProviderBatchResult(
            kakao=kakao,
            naver=naver,
            provider_latency_seconds=max(0.0, now - submitted_at),
            prefetch_wait_seconds=max(0.0, now - wait_started),
            prefetch_hit=ready,
            round_number=round_number,
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


def _should_expand_search(row: dict[str, str]) -> bool:
    # Round 1 후보가 확정되지 않은 경우에만 검색을 넓혀 recall을 보완한다.
    return (
        row.get("qwen_calls_skipped") != "true"
        and row.get("decision") in {"REJECT", "UNKNOWN"}
    )


def _combine_provider_results(
    first: ProviderBatchResult, second: ProviderBatchResult
) -> ProviderBatchResult:
    return ProviderBatchResult(
        kakao=first.kakao + second.kakao,
        naver=first.naver + second.naver,
        provider_latency_seconds=first.provider_latency_seconds + second.provider_latency_seconds,
        prefetch_wait_seconds=first.prefetch_wait_seconds + second.prefetch_wait_seconds,
        prefetch_hit=first.prefetch_hit,
        round_number=second.round_number,
    )


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


def _cached_rejection(
    reference, cache: dict[str, dict[str, str]], policy_version: str = SEARCH_POLICY_VERSION
) -> dict[str, str] | None:
    cached = cache.get(reference.external_merchant_id or "")
    if not cached or cached.get("decision") != "REJECT":
        return None
    fingerprint = source_fingerprint(_source(reference))
    result = VerificationResult(
        decision=VerificationDecision.REJECT, reason=cached.get("verification_reason", "")
    )
    return (
        cached
        if can_reuse_rejection(
            result,
            cached.get("source_fingerprint"),
            fingerprint,
            cached.get("search_policy_version"),
            policy_version,
        )
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
    SELECT r.external_merchant_id, v.source_fingerprint, v.search_policy_version,
           v.verification_reason, v.model_name
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
                "search_policy_version": row.get("search_policy_version", ""),
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
        "search_policy_version": SEARCH_POLICY_VERSION,
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
    on_qwen_candidates=None,
    on_validate_many=None,
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
        cached.get("search_policy_version"),
        SEARCH_POLICY_VERSION,
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
    if on_qwen_candidates:
        on_qwen_candidates(len(candidates))
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
        if len(candidates) == 1 and hasattr(matcher, "validate"):
            # 후보 하나는 순위를 고를 필요가 없으므로 choose를 생략하고 바로 검증한다.
            ranking_indices = (0,)
        else:
            print(
                f"[Entity Resolution][QWEN_CHOOSE_START] candidates={len(candidates)}",
                flush=True,
            )
            qwen_started = time.monotonic()
            ranking = matcher.choose(reference, candidates)
            print(
                f"[Entity Resolution][QWEN_CHOOSE_END] selected={len(ranking.candidate_indices)} "
                f"elapsed={time.monotonic() - qwen_started:.3f}s",
                flush=True,
            )
            ranking_indices = ranking.candidate_indices
        decisions = []
        accepted_indices = {}
        checked_indices: set[int] = set()
        while True:
            row["qwen_ranking"] = ",".join(str(index) for index in ranking_indices)
            ranked_indices = list(ranking_indices)
            ranked_candidates = [candidates[index] for index in ranked_indices]
            if len(ranked_candidates) > 1 and hasattr(matcher, "validate_many"):
                try:
                    print(
                        "[Entity Resolution][QWEN_VALIDATE_MANY_START] "
                        f"candidates={len(ranked_candidates)}",
                        flush=True,
                    )
                    qwen_started = time.monotonic()
                    ranked_decisions = matcher.validate_many(reference, ranked_candidates)
                    print(
                        f"[Entity Resolution][QWEN_VALIDATE_MANY_END] "
                        f"elapsed={time.monotonic() - qwen_started:.3f}s",
                        flush=True,
                    )
                    if on_validate_many:
                        on_validate_many(success=True, fallback=False)
                except ValueError:
                    print(
                        "[Entity Resolution][QWEN_VALIDATE_MANY_FALLBACK] single_validate=true",
                        flush=True,
                    )
                    # 묶음 응답이 계약을 지키지 못하면 기존 단일 검증으로만 복구한다.
                    if on_validate_many:
                        on_validate_many(success=False, fallback=True)
                    ranked_decisions = tuple(
                        matcher.validate(reference, candidate) for candidate in ranked_candidates
                    )
            else:
                print(
                    f"[Entity Resolution][QWEN_VALIDATE_START] candidates={len(ranked_candidates)}",
                    flush=True,
                )
                qwen_started = time.monotonic()
                ranked_decisions = tuple(
                    matcher.validate(reference, candidate) for candidate in ranked_candidates
                )
                print(
                    f"[Entity Resolution][QWEN_VALIDATE_END] "
                    f"elapsed={time.monotonic() - qwen_started:.3f}s",
                    flush=True,
                )
            for index, decision in zip(ranked_indices, ranked_decisions, strict=True):
                checked_indices.add(index)
                candidate = candidates[index]
                if candidate.provider in accepted_indices:
                    continue
                decisions.append(decision)
                if decision.final_decision == "ACCEPT":
                    accepted_indices[candidate.provider] = index

                if "KAKAO" in accepted_indices and (
                    "NAVER" in accepted_indices or "NAVER_LOCAL" in accepted_indices
                ):
                    break

            all_checked_rejected = decisions and all(
                item.final_decision == "REJECT" for item in decisions
            )
            remaining_indices = [
                index for index in range(len(candidates)) if index not in checked_indices
            ]
            if not all_checked_rejected or not remaining_indices:
                break
            # top-N 전체가 REJECT일 때만 미검증 후보를 확장한다. 정상 easy case는 추가 호출이 없다.
            remaining_candidates = [candidates[index] for index in remaining_indices]
            if len(remaining_candidates) == 1:
                ranking_indices = (remaining_indices[0],)
            else:
                remaining_ranking = matcher.choose(reference, remaining_candidates)
                ranking_indices = tuple(
                    remaining_indices[index] for index in remaining_ranking.candidate_indices
                )

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
        if any(token in str(error).upper() for token in ("HTTP_403", "HTTP_429")):
            # Qwen endpoint의 차단 응답도 일반 구조화 오류로 저장하지 않고
            # 기존 BLOCKED cooldown 경로로 보내 조기 재호출을 막는다.
            raise RuntimeError(f"BLOCKED: {error}") from error
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
    root = Path(__file__).resolve().parents[3]
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
        run_id=os.environ.get("BATCH_RUN_ID"),
    )
    progress.skip_preexisting(args.preexisting_skipped)
    qwen_client = OllamaClient()
    matcher = QwenCandidateMatcher(
        qwen_client,
        on_call=lambda operation, latency: progress.record_qwen_call(operation, latency),
        on_retry=progress.record_qwen_retry,
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
                    None
                    if _cached_rejection(reference, cache)
                    else prefetch.submit(reference, round_number=1),
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
                            round_number=provider_results.round_number,
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
                        on_qwen_candidates=progress.record_qwen_candidate_count,
                        on_validate_many=progress.record_validate_many,
                    )
                    if provider_results is not None and _should_expand_search(row):
                        # Round 1의 후보가 확정되지 않은 어려운 경우에만 추가 검색을 실행한다.
                        progress.record_round2_required()
                        round2_future = prefetch.submit(reference, round_number=2)
                        round2_results = prefetch.result(round2_future)
                        progress.record_provider(
                            kakao_requests=len(round2_results.kakao),
                            naver_requests=len(round2_results.naver),
                            latency_seconds=round2_results.provider_latency_seconds,
                            prefetch_wait_seconds=round2_results.prefetch_wait_seconds,
                            prefetch_hit=round2_results.prefetch_hit,
                            round_number=round2_results.round_number,
                        )
                        row = evaluate_reference(
                            reference,
                            kakao,
                            naver,
                            matcher,
                            cache.get(reference.external_merchant_id or ""),
                            provider_results=_combine_provider_results(
                                provider_results, round2_results
                            ),
                            on_candidates=progress.record_qwen_candidates,
                            on_qwen_candidates=progress.record_qwen_candidate_count,
                            on_validate_many=progress.record_validate_many,
                        )
                    elif provider_results is not None and row.get("decision") == "ACCEPT":
                        progress.record_round1_resolved()
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
                print(
                    f"[Entity Resolution][CSV_FLUSH] restaurant_id={reference.restaurant_id} "
                    f"decision={row['decision']}",
                    flush=True,
                )
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
