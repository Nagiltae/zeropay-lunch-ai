"""Report-only Kakao/NAVER provider fusion with Qwen Entity Resolution."""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

from app.place_provider import (
    KakaoPlaceSearchProvider,
    NaverPlaceSearchProvider,
    PlaceSearchCandidate,
    ProviderSearchResult,
    candidate_json,
)
from app.provider_input import load_local_env, load_provider_manifest
from app.qwen_candidate_matcher import (
    OllamaClient,
    QwenCandidateMatcher,
    configured_qwen_model,
)
from app.verification_quality_gate import (
    VerificationDecision,
    VerificationResult,
    can_reuse_rejection,
    map_semantic_result,
    recommendation_eligibility,
    source_fingerprint,
    technical_unknown,
)

FIELDS = (
    "restaurant_id", "external_merchant_id", "komsco_name", "komsco_address",
    "source_fingerprint", "decision", "recommendation_eligibility", "verification_reason",
    "provider_calls_skipped", "qwen_calls_skipped", "kakao_candidate_count",
    "naver_candidate_count", "candidates_json", "kakao_error", "naver_error",
    "qwen_model", "qwen_ranking", "qwen_decision", "qwen_business_type",
    "qwen_location_scope", "qwen_reason", "error",
)


def _query_variants(reference) -> tuple[str, ...]:
    return tuple(dict.fromkeys((reference.komsco_name, f"논현동 {reference.komsco_name}")))


def _merge(results: tuple[ProviderSearchResult, ...]) -> tuple[PlaceSearchCandidate, ...]:
    seen: set[tuple[str, str]] = set()
    merged: list[PlaceSearchCandidate] = []
    for result in results:
        for candidate in result.candidates:
            key = (
                candidate.provider,
                candidate.external_place_id or candidate.detail_url or candidate.name,
            )
            if key not in seen:
                seen.add(key)
                merged.append(candidate)
    return tuple(merged)


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


def _cache_rows(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as stream:
        rows = csv.DictReader(stream)
        return {
            row["external_merchant_id"]: row
            for row in rows
            if row.get("external_merchant_id")
        }


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
        "error": "",
    }


def evaluate_reference(reference, kakao, naver, matcher, cached=None) -> dict[str, str]:
    fingerprint = source_fingerprint(_source(reference))
    row = _base(reference, fingerprint)
    if cached and can_reuse_rejection(
        VerificationResult(
            decision=VerificationDecision.REJECT,
            reason=cached.get("verification_reason", ""),
        ) if cached.get("decision") == "REJECT" else None,
        cached.get("source_fingerprint"), fingerprint,
    ):
        row.update({key: value for key, value in cached.items() if key in FIELDS})
        row["restaurant_id"] = str(reference.restaurant_id)
        row["source_fingerprint"] = fingerprint
        row["provider_calls_skipped"] = "true"
        row["qwen_calls_skipped"] = "true"
        return row

    kakao_results = tuple(kakao.search(query, longitude=reference.komsco_longitude,
                                       latitude=reference.komsco_latitude)
                          for query in _query_variants(reference))
    naver_results = tuple(naver.search(query) for query in _query_variants(reference))
    candidates = _merge(kakao_results + naver_results)
    row.update({
        "kakao_candidate_count": str(sum(len(result.candidates) for result in kakao_results)),
        "naver_candidate_count": str(sum(len(result.candidates) for result in naver_results)),
        "candidates_json": candidate_json(candidates),
        "kakao_error": ";".join(sorted({r.error for r in kakao_results if r.error})),
        "naver_error": ";".join(sorted({r.error for r in naver_results if r.error})),
    })
    if not candidates:
        errors = tuple(
            error
            for result in kakao_results + naver_results
            for error in [result.error]
            if error
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
        for index in ranking.candidate_indices:
            decision = matcher.validate(reference, candidates[index])
            decisions.append(decision)
            if decision.final_decision == "ACCEPT":
                break
        accepted = next(
            (decision for decision in decisions if decision.final_decision == "ACCEPT"),
            None,
        )
        selected = accepted or decisions[-1]
        all_rejected = decisions and all(
            item.final_decision == "REJECT" for item in decisions
        )
        result = map_semantic_result(
            final_decision=("ACCEPT" if accepted else "REJECT" if all_rejected else "UNCERTAIN"),
            business_type=selected.business_type,
            location_scope=selected.location_scope,
            reason=selected.reason,
            model=configured_qwen_model(),
        )
        row.update({
            "qwen_decision": selected.final_decision,
            "qwen_business_type": selected.business_type,
            "qwen_location_scope": selected.location_scope,
            "qwen_reason": selected.reason,
        })
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
    parser = argparse.ArgumentParser(
        description="Official provider fusion and Qwen Entity Resolution"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cache", type=Path,
        help="previous fusion report; only unchanged REJECT rows are reused",
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    load_local_env(root)
    references = list(load_provider_manifest(args.manifest))
    if args.limit is not None:
        references = references[:args.limit]
    cache = _cache_rows(args.cache)
    kakao = KakaoPlaceSearchProvider()
    naver = NaverPlaceSearchProvider()
    matcher = QwenCandidateMatcher(OllamaClient())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for reference in references:
            row = evaluate_reference(
                reference,
                kakao,
                naver,
                matcher,
                cache.get(reference.external_merchant_id or ""),
            )
            writer.writerow(row)
            stream.flush()
    print(f"processed={len(references)} elapsed_seconds={time.monotonic() - started:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
