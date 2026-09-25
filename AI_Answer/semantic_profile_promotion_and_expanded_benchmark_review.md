# ZeroPay Lunch AI — Legacy Restaurant Promotion & Expanded Benchmark

## 1. Executive Summary

대상 9562, 9568, 9569, 9570, 9571, 9574를 순차적으로 실제 Detail persistence했다. 6건 모두 MENU·BUSINESS_HOURS·REVIEW Lifecycle이 `SUCCESS`로 생성됐고, freshness 재실행은 모두 `preexisting_skipped=1`, browser start 0으로 확인됐다.

그러나 Qwen/Claim Gate 결과 승인 Claim을 가진 신규 Restaurant는 3건(9570, 9571, 9574)뿐이다. 기존 4건과 합쳐도 총 7건이므로 최소 10건 조건을 충족하지 못했다. 규칙에 따라 Expanded Benchmark와 신규 Claim Vector 생성은 실행하지 않았다.

최종 판단: **INSUFFICIENT_SAMPLE / NO-GO**

## 2. Persistence 대상과 결과

| ID | Detail 저장 | Lifecycle | Freshness 재실행 | Claim 결과 |
|---:|---|---|---|---|
| 9562 | SUCCESS | 3 sections SUCCESS | skipped, browser 0 | AUTO 0 |
| 9568 | SUCCESS | 3 sections SUCCESS | skipped, browser 0 | AUTO 0 |
| 9569 | SUCCESS | 3 sections SUCCESS | skipped, browser 0 | AUTO 0 |
| 9570 | SUCCESS | 3 sections SUCCESS | skipped, browser 0 | AUTO 2 |
| 9571 | SUCCESS | 3 sections SUCCESS | skipped, browser 0 | AUTO 2 |
| 9574 | SUCCESS | 3 sections SUCCESS | skipped, browser 0 | AUTO 2 |

각 대상별 pre/post snapshot:

* `AI_Answer/detail_persistence_snapshot_9562_before.json`
* `AI_Answer/detail_persistence_snapshot_9562_after.json`
* 동일 패턴으로 9568, 9569, 9570, 9571, 9574

Persistence와 Lifecycle 집계는 [semantic_profile_promotion_persistence_evaluation.json](semantic_profile_promotion_persistence_evaluation.json), [semantic_profile_promotion_lifecycle_evaluation.json](semantic_profile_promotion_lifecycle_evaluation.json)에 보존했다.

## 3. DB 변경 범위

허용된 6개 Restaurant의 Detail row와 Section Lifecycle만 정상 갱신됐다. Numeric Place ID, ownership, Verification, Venue, 대상 외 Restaurant는 변경하지 않았다. `9564`는 실행 대상에서 제외했다.

각 실제 write report:

`ai/build/reports/naver-place-pipeline/e2e/semantic-benchmark-write-{9562,9568,9569,9570,9571,9574}-detail.json`

Freshness report:

`ai/build/reports/naver-place-pipeline/e2e/semantic-benchmark-fresh-{9562,9568,9569,9570,9571,9574}-detail.json`

## 4. Qwen Profile 및 Claim Gate

총 Qwen 호출은 6회, 각 대상 1회, retry 0회였다.

* 9562: 사전 호출 결과 AUTO 0; Lifecycle 부재로 실패한 결과를 재호출하지 않음
* 9568: AUTO 0
* 9569: AUTO 0
* 9570: AUTO 2, REVIEW 1, REJECTED 2; 전체 profile validation은 menu evidence type 문제로 strict false
* 9571: AUTO 2, REVIEW 2, REJECTED 1
* 9574: AUTO 2, REVIEW 1, REJECTED 2

REVIEW_REQUIRED와 REJECTED Claim은 승인하거나 Embedding에 사용하지 않았다. 상세 분류는 [semantic_profile_promotion_claim_evaluation.json](semantic_profile_promotion_claim_evaluation.json)과 각 `AI_Answer/semantic_profile_benchmark_*` 산출물에 보존했다.

## 5. 표본 수와 Benchmark 중단

기존 승인 Restaurant 4건 + 신규 승인 Claim 보유 대상 3건 = 총 7건이다. 7~9건이면 Benchmark를 실행하지 않는다는 사전 규칙에 따라 다음 작업은 수행하지 않았다.

* 신규 Claim Point 생성
* `zeropay_semantic_claim_pilot_v7` Collection 생성
* Expanded Benchmark 재실행
* 일본 음식 category 재평가
* TASTE_QUANTITATIVE 후보 비교
* Spring Contract Test

기존 4건의 이전 Benchmark 결과는 변경하지 않았다.

## 6. 일본 음식과 TASTE Quantitative

이번 실행에서는 신규 Claim Point가 0개이므로 두 미해결 문제를 재평가하지 못했다.

* `스시 ↔ 초밥` exact/synonym과 `일식 → 초밥·우동·후토마끼` category 분리: 미검증
* similarity only vs mention count/log1p/ratio: 미검증

기존 Benchmark에서 확인된 실패 원인은 유지된다. 표본을 채우기 위해 REVIEW_REQUIRED/REJECTED를 승격하거나 Qwen을 재시도하지 않았다.

## 7. 테스트 및 안전

* AI Harness: 180 passed, 1 warning
* Detail persistence: 6건 실제 실행, 모두 성공
* Freshness: 6건 모두 외부 navigation 없이 skip
* Provider/Qwen Entity Resolution: 미실행
* Place ID 탐색/교체: 미실행
* Qwen Profile 호출: 6회, retry 없음
* Qdrant 신규 Collection/Claim Vector: 미실행
* MySQL 원본 변경: 허용된 6건 Detail/Lifecycle 외 없음
* `git diff --check`: PASS
* Git add/commit/push: 없음

## 8. 다음 단계 조건

추가 Profile 대상은 Lifecycle SUCCESS와 Evidence Quality Gate를 모두 충족해야 한다. 총 승인 가능한 Restaurant가 10건 이상 확보된 뒤에만 Ground Truth를 다시 고정하고 Expanded Benchmark를 실행한다. 그때도 일본 음식 exact/synonym/category와 TASTE_QUANTITATIVE를 별도 지표로 평가한 후 Runtime 연결을 판단한다.
