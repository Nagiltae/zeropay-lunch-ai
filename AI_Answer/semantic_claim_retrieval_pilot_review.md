# ZeroPay Lunch AI — Claim-level Semantic Retrieval Quality Pilot

## 1. Executive Summary

승인된 Claim만으로 Claim Point 21개를 만들고, 한국어 deterministic normalization과 Query Claim-Type Router를 적용해 별도 Qdrant Shadow Collection에서 8개 질의를 재검증했다.

기존 Restaurant 단위 Vector보다 음식 종류 검색의 원인 추적성과 오염 방지는 개선됐다. `가성비`는 실제 가성비 근거가 있는 9617이 1위가 되었고, `피자/파스타`는 9580의 리뷰 음식 언급 근거로 1위가 되었다. `스시/일식`도 9731이 FOOD_MENTION 근거로 1위가 되었다. 다만 스시 결과의 최상위 근거가 `우동`이어서 세부 음식 일치까지 완전히 해결된 것은 아니다.

표본이 4개 Restaurant뿐이고, 음식 종류별 Claim coverage가 불균일하므로 FastAPI/Spring runtime 연결은 아직 NO-GO다.

## 2. 이전 Restaurant Vector 실패 원인

기존 Collection은 Restaurant별로 여러 Claim을 한 Vector에 합쳤다. 그 결과 일반적인 TASTE 표현이 음식 종류 질의에 영향을 주었고, 승인된 음식 종류 Claim이 없는 Restaurant도 상위에 노출됐다. 또한 한국어 Query와 영어 Claim Text가 혼재했다.

이번 Pilot은 Claim Type을 분리하고 Query별 허용 Type을 제한해 이 오염을 줄였다. 기존 Collection `zeropay_semantic_profile_pilot_v1`은 삭제·수정하지 않았다.

## 3. 한국어 normalization 계약

* 원본 Claim은 `originalClaimText`로 보존한다.
* Embedding 전용 문장은 `normalizedClaimText`로 생성한다.
* `normalizationVersion`: `ko-claim-normalization-v1`
* FOOD_TYPE는 승인 Claim의 menu Evidence 이름만 사용한다.
* MENU_CHARACTERISTIC도 Evidence에 실제로 존재하는 메뉴명만 사용한다.
* TASTE/VENUE_CHARACTERISTIC은 승인 Claim의 review keyword Evidence를 한국어 의미 표현으로 정규화한다.
* 정규화에서 가격, 영업시간, ID, Eligibility는 생성하지 않는다.

## 4. FOOD_TYPE / FOOD_MENTION 정책

`FOOD_MENTION`은 공식 메뉴가 아니다. REVIEW SUCCESS keyword에서 음식명이 반복 언급되고 mention count가 3 이상인 경우에만 생성했다. 이번 실제 생성 대상은 9731의 초밥·우동·후토마끼, 9580의 피자 계열 등이다.

각 FOOD_MENTION payload에는 `sourceKind=review_keyword_only`, `mentionTerm`, Evidence ID를 보존했다. FOOD_TYPE와 동일하게 취급하지 않았으며, 단일 리뷰나 메뉴 부재를 공식 메뉴로 변환하지 않았다.

## 5. Query Router 및 Aggregation

* DINING_CONTEXT: 혼밥·빠른 식사·모임 관련 질의
* TASTE: 맛·가성비·신선도·평가 질의
* FOOD_TYPE: 한식·한정식
* FOOD_TYPE + FOOD_MENTION: 스시·일식·초밥·우동
* FOOD_TYPE + MENU_CHARACTERISTIC + FOOD_MENTION: 피자·파스타·떡볶이·김밥

Claim 검색 후 Restaurant별 최대 Claim score를 사용했다. 이는 Semantic Candidate Retrieval 점수이며 Spring의 최종 추천 점수나 결정론적 Hard Filter를 대체하지 않는다.

## 6. Qdrant 계약 및 인덱싱

* Collection: `zeropay_semantic_claim_pilot_v5`
* Model: `qwen3-embedding:0.6b`
* Dimension: 1024
* Distance: Cosine
* Claim Point: 21개
* Restaurant: 9617, 9731, 9567, 9580
* 문서와 Query에 동일 Embedding Model 사용

Payload에는 restaurantId, venueId, claimId, claimType, 원본/정규화 Claim, confidence, evidenceIds, inputHash, catalogHash, model/version, normalizationVersion를 보존했다. 긴 Review 원문은 복제하지 않았다.

## 7. 8 Query 결과

| Query | Router | Top-1 | Claim | 판정 |
|---|---|---:|---|---|
| 혼밥하기 좋은 음식점 | DINING_CONTEXT | 9617 | DINING_CONTEXT | PASS |
| 빠르게 먹기 좋은 음식점 | DINING_CONTEXT | 9617 | DINING_CONTEXT | PASS |
| 가성비 좋은 음식점 | TASTE | 9617 | 가성비 고객 평가 | PASS |
| 맛있다는 평가가 많은 음식점 | TASTE | 9580 | 맛있다는 고객 평가 | PARTIAL |
| 한식 또는 한정식이 먹고 싶다 | FOOD_TYPE | 9567 | 한식 정식 메뉴 | PASS |
| 피자나 파스타가 먹고 싶다 | FOOD_TYPE/MENU/MENTION | 9580 | 피자 FOOD_MENTION | PASS |
| 스시나 일식이 먹고 싶다 | FOOD_TYPE/MENTION | 9731 | 우동 FOOD_MENTION | PARTIAL |
| 떡볶이와 김밥을 먹고 싶다 | FOOD_TYPE/MENU/MENTION | 9617 | 김밥·떡볶이 FOOD_TYPE | PASS |

정확한 원본 score와 Top-3, baseline 비교는 [semantic_claim_retrieval_comparison.json](semantic_claim_retrieval_comparison.json)에 보존했다.

## 8. Baseline 비교와 남은 실패

개선된 점:

* 일반 TASTE가 음식 종류 검색을 직접 지배하는 문제를 Router로 제한했다.
* 9731의 음식 종류 정보는 REJECTED FOOD_TYPE를 되살리지 않고 REVIEW 기반 FOOD_MENTION으로 검색했다.
* 가성비 질의가 실제 가성비 Claim이 없는 9731 대신 9617을 우선 반환했다.
* 피자 질의가 한식 Restaurant 9567 대신 9580으로 이동했다.

남은 문제:

* `스시/일식`은 9731이 반환되지만 Top Claim은 우동이다. 스시·일식·우동의 세부 동의어와 의도 분류는 별도 검증이 필요하다.
* `맛있다`는 Claim은 mention count를 ranking에 반영하지 않으므로 9580이 9731보다 높아진 이유를 품질 우위로 해석할 수 없다.
* FOOD_MENTION이 여러 음식명으로 확장되면 unrelated food 후보가 남을 수 있다.
* 9567과 9580의 승인 Claim coverage와 Evidence 품질이 균일하지 않다.
* 4개 Restaurant/8개 Query 결과를 전체 데이터셋 recall·precision으로 일반화할 수 없다.

## 9. FastAPI 연결 판단

현재는 **NO-GO**다. Claim Type routing과 Evidence trace는 설명 가능하게 동작했지만, 스시의 세부 음식 일치와 TASTE ranking 안정성이 충분히 검증되지 않았다. 다음 단계에서 Claim-level offline benchmark를 확장하고, 음식명 synonym/mention threshold 및 score 해석을 먼저 확정해야 한다.

향후 연결 시에도 Qdrant는 의미 후보 검색만 담당하고, Spring이 ZeroPay eligibility·거리·영업시간·예산·최근 식사 Hard Filter와 최종 ranking을 담당해야 한다. FastAPI/Spring/React runtime은 이번 작업에서 변경하지 않았다.

## 10. 테스트 및 산출물

* Claim retrieval targeted tests: 3 passed
* Embedding pilot targeted tests: 2 passed
* AI Harness: 178 passed, 1 warning
* 실제 Claim Qdrant: 21 point upsert, 8 query 수행
* Provider/Qwen Entity Resolution: 미실행
* MySQL/Profile/Detail: 변경 없음
* 운영 Qdrant Collection: 변경 없음

산출물:

* [semantic_claim_retrieval_indexing_manifest.json](semantic_claim_retrieval_indexing_manifest.json)
* [semantic_claim_retrieval_query_routing_evaluation.json](semantic_claim_retrieval_query_routing_evaluation.json)
* [semantic_claim_retrieval_comparison.json](semantic_claim_retrieval_comparison.json)
* 구현: `ai/app/semantic_claim_retrieval_pilot.py`
* 테스트: `ai/tests/test_semantic_claim_retrieval_pilot.py`

## 11. 안전 및 Git

기존 Restaurant Vector Collection은 삭제하거나 수정하지 않았고, 새로운 pilot Collection만 생성했다. MySQL 원본, Profile persistence, Venue, Place ID, Spring 추천 경로는 변경하지 않았다. 전체 Profile/Detail/Provider Batch와 FastAPI runtime 연결은 실행하지 않았다. Git add/commit/push는 수행하지 않았으며 기존 Working Tree 변경을 보존했다.
