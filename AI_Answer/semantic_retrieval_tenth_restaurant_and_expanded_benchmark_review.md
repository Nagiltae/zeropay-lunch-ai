# ZeroPay Lunch AI — Claim-Level Eligibility 및 10번째 Restaurant Benchmark

## 1. 결론

Claim-level 기준을 적용해 9590에서 신규 승인 Claim 2개를 확보했고, 승인 가능 Restaurant 표본은 9건에서 10건으로 증가했다. 이에 따라 제한된 Expanded Benchmark를 실행했다.

그러나 22개 Query 기준 결과는 Precision@1 `0.1818`, Hit@3 `0.6818`로 사전 기준인 `0.80/0.90`에 미달했다. 일본 음식 Query와 TASTE_QUANTITATIVE에서 핵심 오류가 남아 있어 최종 Runtime 판단은 `NO-GO`다. FastAPI/Spring 연결과 Spring Contract Test는 실행하지 않았다.

## 2. Claim-level Benchmark Eligibility

이번에 코드로 고정한 규칙은 다음과 같다.

* `AUTO_APPROVED` Claim만 후보가 된다.
* Evidence ID가 실제 Catalog에 존재하고, 모든 해당 Evidence Section이 `SUCCESS`여야 한다.
* identity/Place ID ownership conflict, lifecycle 부재, provenance 손상이 있으면 해당 Restaurant의 Claim을 모두 차단한다.
* 다른 Claim의 국소 validation 오류는 해당 AUTO Claim을 자동 승인하지 않지만, 직접적인 관련이 없는 정상 AUTO Claim까지 폐기하지 않는다.
* `REVIEW_REQUIRED`, `REJECTED`, deterministic 필드는 사용하지 않는다.

9568은 strict 상태는 true지만 다른 Claim의 identity evidence 오류가 있어 전체 validation은 false였다. 정상 `AUTO_APPROVED` 3개만 사용했다. 9569는 strict false이나 lifecycle과 해당 Evidence가 유효한 AUTO Claim 5개를 Claim-level로 사용했다. 9570은 전체 validation 오류와 무관한 AUTO Claim 2개만 사용했다. 이들은 Profile 전체 READY와 Claim-level 사용 가능을 혼동하지 않는다.

상세 manifest: [semantic_retrieval_tenth_eligibility_manifest.json](semantic_retrieval_tenth_eligibility_manifest.json)

## 3. 신규 후보 및 Detail Promotion

읽기 전용 집계에서 충돌 없는 후보 9865, 9590, 9659를 최대 3건으로 선정했다. 세 대상 모두 ACTIVE/ELIGIBLE/NAVER MATCHED이며 기존 표본과 충돌 대상에서 제외했다.

| ID | Dry-run | Persistence | 결과 |
|---:|---|---|---|
| 9590 | SUCCESS | SUCCESS | MENU/HOURS/REVIEW 모두 SUCCESS, AUTO Claim 2개 확보 |
| 9659 | SUCCESS | 미실행 | 9590으로 10건 달성 후 중단 |
| 9865 | SUCCESS | 미실행 | 9590으로 10건 달성 후 중단 |

9590은 저장 전후 Snapshot을 보존했다.

* [before snapshot](detail_promotion_snapshot_9590_before.json)
* [after snapshot](detail_promotion_snapshot_9590_after.json)
* [persistence evaluation](semantic_retrieval_tenth_persistence_evaluation.json)

9590의 freshness 재실행은 `preexisting_skipped=1`, browser start `0`, navigation `0`이었다. Place ID ownership과 Venue는 변경하지 않았다.

후보 결과: [semantic_retrieval_tenth_candidate_evaluation.json](semantic_retrieval_tenth_candidate_evaluation.json)

## 4. Profile 및 Claim 결과

최종 표본은 다음 10건이다.

`9617, 9731, 9567, 9580, 9568, 9569, 9570, 9571, 9574, 9590`

총 Claim Point는 24개이며, `qwen3-embedding:0.6b`, 1024 dimension, Cosine을 사용했다. 9590 Profile Qwen 호출은 1회, retry 0회였다. 9590 결과는 `AUTO_APPROVED=2`, `REVIEW_REQUIRED=2`, `REJECTED=1`이며 후자의 Claim은 Vector에 넣지 않았다.

## 5. Expanded Benchmark

기존 Query를 유지하고 9590의 카페/디저트 Coverage를 평가하는 2개 Query를 추가해 총 22개로 고정했다. 검색 후 Ground Truth를 변경하지 않았다.

* [Claim indexing manifest](semantic_retrieval_tenth_claim_indexing_manifest.json)
* [Benchmark results](semantic_retrieval_tenth_benchmark_results.json)
* [Benchmark metrics](semantic_retrieval_tenth_benchmark_metrics.json)

| 지표 | 결과 | 기준 |
|---|---:|---:|
| Restaurant 수 | 10 | >=10 |
| Precision@1 | 0.1818 | >=0.80 |
| Hit@3 | 0.6818 | >=0.90 |
| Evidence Trace | 100% | 100% |
| REVIEW_REQUIRED leakage | 0 | 0 |
| REJECTED leakage | 0 | 0 |
| deterministic leakage | 0 | 0 |

Intent별 Precision@1은 FOOD `0.0769`, DINING_CONTEXT `0.3333`, TASTE `0.3333`, TASTE_QUANTITATIVE `0.5`, VENUE_CHARACTERISTIC `0.0`이었다. 표본 확대 후에도 안전성은 유지됐지만 의미 정확도는 기준에 크게 미달했다.

## 6. 일본 음식 평가

`스시↔초밥` synonym, `일식→초밥·우동·후토마끼` category, `exact > synonym > category` 규칙을 평가 대상으로 고정했다.

현재 Vector-only 결과는 다음 네 Query 모두 기대 Top-1을 맞추지 못했다.

* 스시: 9567이 Top-1
* 초밥: 9617이 Top-1
* 일식: 9569가 Top-1
* 우동: 9569가 Top-1

따라서 category 보정이 해결된 것으로 볼 수 없다. [taxonomy evaluation](semantic_retrieval_tenth_taxonomy_evaluation.json)

## 7. TASTE_QUANTITATIVE 평가

이번 실행에서 실제로 측정한 것은 similarity-only다. raw count, `log1p(count)`, denominator가 있는 ratio 재랭킹은 실행하지 않았으며 운영 weight도 확정하지 않았다.

* `맛있는 곳`: 9731 Top-1
* `맛있다는 평가가 많은 곳`: 9580 Top-1, 기대 9731과 불일치
* `가성비 좋은 곳`: 9571 Top-1, 기대 9617과 불일치
* `가성비 언급이 있는 곳`: 9617 Top-1

정량 Query에는 mention count를 별도 signal로 검토할 필요가 있지만, 추가 ranking 정책 검증 없이 Runtime 연결을 진행하지 않는다. [taste evaluation](semantic_retrieval_tenth_taste_quantitative_evaluation.json)

## 8. 변경 사항

* `ai/app/semantic_profile_shadow.py`: lifecycle·Evidence SUCCESS를 확인하는 Claim-level eligibility helper 추가.
* `ai/app/semantic_retrieval_tenth_benchmark.py`: 10개 Restaurant 전용 report-only Shadow Collection/Benchmark 실행기 추가.
* Claim별 Evidence provenance와 기존 profile 전체 상태를 별도 기록.
* 기존 Provider/Qwen Entity Resolution, Detail, Place ID, Venue, Spring/FastAPI runtime은 변경하지 않았다.

## 9. 테스트

* Semantic/Profile/Retrieval targeted tests: `13 passed`
* AI Harness: `181 passed, 1 warning`
* Detail dry-run: 3건 성공
* Detail persistence: 9590 1건 성공
* Freshness 재실행: 9590 browser 0
* Expanded Benchmark: 22 Query 실행
* Spring Contract Test: NO-GO 조건으로 미실행
* `git diff --check`: 통과

## 10. 안전 확인 및 남은 문제

* DB 원본 변경은 9590의 정상 Detail persistence 범위로 제한했다.
* 9590 외 후보는 persistence하지 않았다.
* 기존 Place ID, Verification, Venue, 기존 Qdrant Collection은 변경하지 않았다.
* 새 Shadow Collection `zeropay_semantic_claim_pilot_v7`와 최종 `v8`만 생성했다. 기존 Collection은 삭제·재생성하지 않았다.
* Provider/Qwen Entity Resolution과 전체 Batch는 실행하지 않았다.
* Git add/commit/push는 수행하지 않았다.

핵심 후속 과제는 음식 taxonomy를 Vector similarity와 분리해 exact/synonym/category를 명시적으로 반영하는 것과, TASTE_QUANTITATIVE의 mention count 신호를 별도 오프라인 비교하는 것이다. 이 두 문제를 해결·검증하기 전에는 FastAPI/Spring Runtime 연결을 진행하지 않는다.
