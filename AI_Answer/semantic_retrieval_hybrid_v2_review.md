# ZeroPay Lunch AI — Ground Truth v2 + Hybrid Semantic Retrieval

## 1. 결론

10개 Restaurant의 승인 Claim/Evidence를 기준으로 Ground Truth v2를 검색 전에 고정하고, FOOD_MENTION을 보강한 v12 Shadow Collection에서 A/B/C 비교를 수행했다.

Hybrid C 결과는 Precision@1 `0.9545`, Hit@3 `1.0000`, Evidence Trace `100%`, 모든 leakage `0`이었다. 기존 v8 결과를 재평가한 A는 `0.5455/0.7273`, Router만 적용한 B는 `0.6818/0.8636`이었다.

사전 기준은 충족했지만, 표본은 10건·Query는 22개이고 TASTE_QUANTITATIVE의 denominator가 없어 ratio를 계산하지 못했다. 따라서 최종 판단은 `CONDITIONAL_GO`다. FastAPI/Spring Runtime 연결은 아직 실행하지 않는다.

## 2. Ground Truth v2

기존 v1은 초기 4개 Restaurant 중심의 단일 정답을 사용해 신규 Evidence가 있는 9571·9568·9590 등을 오답으로 계산할 수 있었다. v2는 검색 전에 10개 Restaurant의 `AUTO_APPROVED` Claim과 valid FOOD_MENTION을 읽어 multi-label 정답을 고정했다.

Ground Truth에는 Query, intent, expectedRestaurantIds, expectedClaimTypes, expectedTerms, Evidence ID, 근거 사유를 보존했다. 검색 결과를 본 뒤 정답을 변경하지 않았다.

* [Ground Truth v2](semantic_retrieval_ground_truth_v2.json)

예를 들어 피자 Query는 실제 메뉴 Evidence가 있는 9571과 Review FOOD_MENTION이 있는 9580을 모두 정답 후보로 포함했다. 한식 Query는 공식 메뉴 Evidence가 확인되는 9567·9568을 포함했다.

## 3. FOOD_MENTION 보강

v8 Manifest에는 FOOD_MENTION Point가 `0`개였다. 원인은 기존 확장 실행기가 승인된 Profile Claim만 적재하고, 반복 Review Keyword에서 생성해야 하는 FOOD_MENTION을 재생성하지 않았기 때문이다.

v12에서는 다음 조건으로 16개 FOOD_MENTION Point를 생성했다.

* Review Section `SUCCESS`
* keyword Evidence
* mentionCount >= 3
* `sourceKind=review_keyword_only`
* 공식 메뉴로 표현하지 않음
* Evidence ID와 mentionCount payload 보존

9731의 초밥·우동·후토마끼, 9580의 피자 Evidence가 포함됐다. [hybrid indexing manifest](semantic_retrieval_hybrid_indexing_manifest.json)

## 4. Router 및 Hybrid 구조

Router v2는 디저트·피자·메뉴 요청·`먹고 싶다`를 FOOD로 우선 분류하며, FOOD Query의 검색 Type을 `FOOD_TYPE`, `FOOD_MENTION`, `MENU_CHARACTERISTIC`으로 제한한다. DINING_CONTEXT/TASTE/VENUE를 무제한 fallback으로 포함하지 않는다.

Hybrid 점수는 다음 신호를 별도로 보존한다.

* exact food term
* synonym (`스시`→`초밥`)
* category (`일식`→`초밥·우동·후토마끼`)
* trait match
* source strength (`FOOD_TYPE`/`MENU_CHARACTERISTIC`가 FOOD_MENTION보다 강함)
* semantic score
* mentionCount

정렬 우선순위는 exact > synonym > category > vector-only이며, exact FOOD_MENTION은 관련 없는 FOOD_TYPE보다 우선할 수 있다. Restaurant 결과는 Query 관련 Claim만으로 max aggregation한다.

## 5. A/B/C 비교

| 방식 | Precision@1 | Hit@3 |
|---|---:|---:|
| A: 기존 v8 결과 | 0.5455 | 0.7273 |
| B: 새 Collection + 기존 Router | 0.6818 | 0.8636 |
| C: 새 Router + Hybrid | 0.9545 | 1.0000 |

Hybrid의 Intent별 Precision@1은 FOOD `0.9231`, DINING_CONTEXT `1.0`, TASTE `1.0`, TASTE_QUANTITATIVE `1.0`, VENUE_CHARACTERISTIC `1.0`이었다.

* [Hybrid results](semantic_retrieval_hybrid_results.json)
* [Hybrid metrics](semantic_retrieval_hybrid_metrics.json)
* [Router evaluation](semantic_retrieval_router_evaluation.json)

## 6. 필수 Query 검증

일본 음식:

* 스시: 9731 초밥 FOOD_MENTION이 synonym으로 Top-1
* 초밥: 9731 초밥 FOOD_MENTION이 exact로 Top-1
* 일식: 9731이 category match로 Top-1
* 우동: 9731 우동 FOOD_MENTION이 exact로 Top-1

디저트:

* `디저트 먹고 싶다`: 9590 Top-1
* `카페에서 디저트 먹고 싶다`: 9590 Top-1
* 두 Query 모두 FOOD Router로 처리됐고 all-types fallback이 아니었다.

## 7. TASTE_QUANTITATIVE

정량 Query는 관련 TASTE Claim만 남긴 뒤 다음을 실제 비교했다.

* similarity-only
* raw mentionCount
* `log1p(mentionCount)`
* denominator가 없어 ratio는 `NOT_COMPUTED_NO_DENOMINATOR`

맛있다는 평가 Query에서는 raw/log1p 모두 mention metadata가 있는 후보를 우선했다. 가성비 Query에서도 9571·9617만 비교 대상으로 남겼다. 다만 전체 리뷰 수 denominator를 임의 생성하지 않았고, 운영 weight는 확정하지 않았다.

* [TASTE_QUANTITATIVE evaluation](semantic_retrieval_taste_quantitative_v2_evaluation.json)

## 8. 안전성

* REVIEW_REQUIRED leakage: 0
* REJECTED leakage: 0
* deterministic field leakage: 0
* Evidence Trace: 100%
* 기존 v1 Ground Truth와 v8 Collection은 덮어쓰지 않았다.
* 최종 Shadow Collection은 `zeropay_semantic_claim_pilot_v12`이며, 실행 중 생성된 v9/v10/v11도 보존했다. 기존 v8 Collection은 수정/삭제하지 않았다.
* MySQL, Detail, Place ID, Venue, Profile persistence는 실행하지 않았다.
* Provider/Qwen Entity Resolution 및 FastAPI/Spring Runtime은 실행하지 않았다.

## 9. 테스트

* Hybrid targeted tests: `3 passed`
* Semantic/Profile/Retrieval targeted 포함: `16 passed`
* AI Harness: `184 passed, 1 warning`
* `git diff --check`: 통과

## 10. 다음 단계

현재 결과는 오프라인 Shadow 기준으로는 Runtime 후보가 될 수 있으나, 10개 표본과 22개 정답 Query에 한정된다. 따라서 `CONDITIONAL_GO`로 유지한다.

다음 단계에서 필요한 것은 더 큰 Profile Batch가 아니라, 추가 표본에 대한 동일 Ground Truth 작성, 실제 denominator가 있는 정량 평가, 그리고 FastAPI → Spring Contract Test다. 이번 단계에서는 Runtime API를 구현하지 않았다.
