"""공식 Kakao와 NAVER Local 후보를 비교 보고하는 수동 CLI."""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path

from app.providers.place_provider import (
    KakaoPlaceSearchProvider,
    NaverPlaceSearchProvider,
    PlaceSearchCandidate,
    candidate_json,
)
from app.providers.provider_input import load_local_env, load_provider_manifest

FIELDS = (
    "restaurant_id", "external_merchant_id", "komsco_name", "komsco_address",
    "komsco_lat", "komsco_lon", "kakao_candidate_count", "kakao_candidates_json",
    "naver_candidate_count", "naver_candidates_json", "kakao_no_result",
    "naver_no_result", "kakao_error", "naver_error", "kakao_gold_rank",
    "naver_gold_rank", "reviewer_note",
)


def _query_variants(reference) -> tuple[str, ...]:
    name = reference.komsco_name.strip()
    return tuple(dict.fromkeys((name, f"논현동 {name}")))


def _merge(results) -> tuple[PlaceSearchCandidate, ...]:
    seen: set[tuple[str, str]] = set()
    merged: list[PlaceSearchCandidate] = []
    for result in results:
        for candidate in result.candidates:
            key = (candidate.provider, candidate.external_place_id or candidate.detail_url)
            if key in seen:
                continue
            seen.add(key)
            merged.append(candidate)
    return tuple(merged)


def _result(reference, kakao, naver) -> dict[str, str]:
    kakao_candidates = _merge(kakao)
    naver_candidates = _merge(naver)
    return {
        "restaurant_id": str(reference.restaurant_id),
        "external_merchant_id": reference.external_merchant_id or "",
        "komsco_name": reference.komsco_name,
        "komsco_address": reference.komsco_address,
        "komsco_lat": "" if reference.komsco_latitude is None else str(reference.komsco_latitude),
        "komsco_lon": "" if reference.komsco_longitude is None else str(reference.komsco_longitude),
        "kakao_candidate_count": str(len(kakao_candidates)),
        "kakao_candidates_json": candidate_json(kakao_candidates),
        "naver_candidate_count": str(len(naver_candidates)),
        "naver_candidates_json": candidate_json(naver_candidates),
        "kakao_no_result": str(not kakao_candidates).lower(),
        "naver_no_result": str(not naver_candidates).lower(),
        "kakao_error": ";".join(sorted({r.error for r in kakao if r.error})),
        "naver_error": ";".join(sorted({r.error for r in naver if r.error})),
        "kakao_gold_rank": "", "naver_gold_rank": "", "reviewer_note": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Kakao/NAVER official candidate retrieval")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--smoke", action="store_true", help="first three manifest rows only")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    load_local_env(root)
    references = list(load_provider_manifest(args.manifest))
    if args.smoke:
        references = references[:3]
    elif args.limit is not None:
        references = references[:args.limit]
    kakao = KakaoPlaceSearchProvider()
    naver = NaverPlaceSearchProvider()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    started = time.monotonic()
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for index, reference in enumerate(references, 1):
            kakao_results = []
            naver_results = []
            for query in _query_variants(reference):
                kakao_results.append(kakao.search(query, longitude=reference.komsco_longitude,
                                                  latitude=reference.komsco_latitude))
                naver_results.append(naver.search(query))
            row = _result(reference, kakao_results, naver_results)
            writer.writerow(row)
            stream.flush()
            k = int(row["kakao_candidate_count"]) > 0
            n = int(row["naver_candidate_count"]) > 0
            counts["kakao_success" if k else "kakao_no_result"] += 1
            counts["naver_success" if n else "naver_no_result"] += 1
            counts["both"] += int(k and n)
            counts["kakao_only"] += int(k and not n)
            counts["naver_only"] += int(n and not k)
            counts["neither"] += int(not k and not n)
            print(
                f"[{index}/{len(references)}] restaurant_id={reference.restaurant_id} "
                f"Kakao={row['kakao_candidate_count']} NAVER={row['naver_candidate_count']}",
                flush=True,
            )
    print(json.dumps({
        "processed": len(references),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        **counts,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
