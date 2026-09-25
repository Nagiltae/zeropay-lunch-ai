# ZeroPay Lunch AI — Embedding + Qdrant Semantic Retrieval Shadow Pilot

## 1. Executive Summary

승인된 Semantic Claim만으로 9617·9731·9567·9580 네 개 Restaurant Document를 만들고, 동일한 Ollama embedding 모델로 문서와 query를 임베딩해 Qdrant pilot Collection에서 Top-3 검색을 수행했다.

Vector 저장과 검색 자체는 성공했지만 의미 검색 품질은 아직 운영 승인 수준이 아니다. 특히 `스시/일식` query가 9731의 승인된 일반 TASTE claim으로 상위 노출되고, `피자/파스타` query가 9567로 잘못 상위 노출됐다. 검색 동작 성공과 의미적 적합성을 분리해 평가했다.

## 2. Embedding 모델과 Collection

* 모델: `qwen3-embedding:0.6b`
* Ollama 모델 설치: 확인
* 문서/query 동일 모델: PASS
* Vector dimension: 1024
* Distance: Cosine
* Collection: `zeropay_semantic_profile_pilot_v1`
* 기존 Collection 조회: 없음
* Point 수: 4
* Qdrant 운영 Collection 수정/삭제: 없음

Indexing manifest: [semantic_embedding_qdrant_indexing_manifest.json](semantic_embedding_qdrant_indexing_manifest.json)

## 3. Semantic Document 계약

각 문서는 승인 claim만으로 구성했다.

| Restaurant | 사용 Claim Type |
|---:|---|
| 9617 | FOOD_TYPE, DINING_CONTEXT, TASTE |
| 9731 | TASTE 1개 |
| 9567 | FOOD_TYPE 1개 |
| 9580 | TASTE, VENUE_CHARACTERISTIC, MENU_CHARACTERISTIC |

`embeddingText`에는 claim type과 승인된 claim text만 포함했다. 정확한 가격·영업시간·거리·좌표·ZeroPay eligibility·Numeric Place ID·DB ID·REVIEW_REQUIRED·REJECTED Claim은 포함하지 않았다.

Payload에는 추적을 위해 restaurantId, venueId, profileVersion, inputHash, catalogHash, claimTypes, claims, evidenceIds, embeddingText, embeddingModel, embeddingVersion을 보존했다. 긴 원문 Review 전문은 복제하지 않았다.

실제 document text:

* 9617: `FOOD_TYPE: 음식 종류로 김밥과 떡볶이가 메뉴에서 확인된다. DINING_CONTEXT: 혼밥과 빠른 식사를 원하는 이용 맥락이 고객 keyword와 대표 리뷰에서 확인된다. TASTE: 고객 언급에서 음식이 맛있고 가성비가 좋다는 평가가 반복된다.`
* 9731: `TASTE: Delicious, Fresh Ingredients, Savory`
* 9567: `FOOD_TYPE: The restaurant serves Korean set meals including galbi-jjim, octopus stir-fry, and various seafood dishes.`
* 9580: `TASTE: Customers frequently mention that the food is delicious. VENUE_CHARACTERISTIC: Customers appreciate the friendly service provided by the staff. MENU_CHARACTERISTIC: The menu includes a variety of pizza sizes and set meals.`

## 4. Query Pilot

8개 query, Top-K 3으로 수행했다. 결과 원본: [semantic_embedding_qdrant_query_evaluation.json](semantic_embedding_qdrant_query_evaluation.json)

| Query | Top-1 | 평가 |
|---|---:|---|
| 혼밥하기 좋은 음식점 | 9617 | 적절. DINING_CONTEXT 승인 claim 근거 |
| 빠르게 먹기 좋은 음식점 | 9617 | 적절. 빠른 식사 claim 근거 |
| 가성비 좋은 음식점 | 9731 | 부적절 가능성. 9731 embedding에 가성비 claim이 없음 |
| 맛있다는 평가가 많은 음식점 | 9731 | 부분 적절. TASTE claim은 있으나 원문 표현이 영어 일반 의미로 축약됨 |
| 한식 또는 한정식이 먹고 싶다 | 9567 | 적절. 한정식/한식 메뉴 근거 |
| 피자나 파스타가 먹고 싶다 | 9567 | 부적절. 9580이 상위가 아니며 음식 종류 claim은 REJECTED로 제외됨 |
| 스시나 일식이 먹고 싶다 | 9731 | 부적절. 9731의 스시 음식종류 claim은 REJECTED였고 embedding에 없어야 함 |
| 떡볶이와 김밥을 먹고 싶다 | 9617 | 적절. 메뉴 claim과 직접 일치 |

Similarity score만으로 성공을 판단하지 않았다. Query와 승인 claim의 의미가 일치하는지 별도로 평가했다.

## 5. 발견된 한계

1. Restaurant 단일 Vector에 서로 다른 Claim Type을 합치면 일반 TASTE 표현이 음식 종류 query까지 끌어올릴 수 있다.
2. 승인된 FOOD_TYPE이 적은 문서는 특정 음식 query recall이 낮다.
3. 9580에서 피자 관련 후보가 있음에도 FOOD_TYPE claim이 REJECTED라 검색 text에 들어가지 않았고, 현재 pilot 결과는 이를 보수적으로 반영했다.
4. 한국어 query와 영어로 생성된 claim text가 섞여 의미 일관성이 낮아질 수 있다.
5. 4건 표본으로 전체 검색 품질이나 recall을 추정할 수 없다.

## 6. Restaurant Vector와 Claim Vector

이번 구현은 Restaurant당 하나의 Vector다. Point dedup과 payload 추적은 단순하지만 Claim 의미가 섞여 일반적인 평가 claim이 검색을 지배할 수 있었다.

후속 검토에서는 Claim 단위 Vector가 음식 종류·맛·이용 맥락 query에 더 적합할 가능성이 높다. 다만 Claim 단위 도입 시 Restaurant dedup, type별 score aggregation, deterministic hard filter 결합이 필요하다. 이번 단계에서는 두 번째 Collection이나 대규모 구현을 하지 않았다.

## 7. Runtime Architecture 준비 상태

현재 Qdrant shadow 검색은 독립 CLI로만 구현됐다. Spring 추천 경로, React, FastAPI Intent Analysis와 연결하지 않았다. 따라서 목표 흐름 중 다음만 검증됐다.

```text
approved Profile → same-model embedding → Qdrant Top-K → Evidence payload trace
```

아직 검증되지 않은 부분:

* FastAPI query intent와 query embedding 계약
* Spring의 ZeroPay/거리/영업시간/예산/최근 식사 hard filter 결합
* Qdrant 후보가 없는 경우 fallback
* Claim Vector aggregation
* 운영 Collection versioning/rollback

Qdrant는 의미 후보 검색만 담당하고 최종 추천 결정은 Spring deterministic filter/ranking이 담당해야 한다.

## 8. 테스트

추가 테스트:

* 승인 Claim만 document text에 포함
* REVIEW_REQUIRED/REJECTED 및 deterministic field 제외
* payload Evidence trace 보존
* 동일 embedding model 계약

결과:

* Embedding/Qdrant targeted tests: 2 passed
* Semantic Profile targeted 포함 AI Harness: PASS, 175 passed, 1 warning
* 실제 Qdrant: pilot Collection 생성, 4 point upsert, 8 query 수행
* Provider/Qwen Entity Resolution: 미실행
* Profile/Detail/MySQL 저장: Profile 저장 없음; 기존 Detail 외에는 변경 없음

## 9. 다음 단계

현재 결과로는 Qdrant를 실제 FastAPI/Spring 추천 경로에 연결하지 않는다. 먼저 승인 claim의 한국어 표현 정규화와 FOOD_TYPE coverage를 보강하고, Claim 단위 오프라인 비교 평가를 별도 수행해야 한다. 그 후에만 더 큰 shadow collection과 deterministic hard filter 결합을 검토한다.

Git add/commit/push 없음. 기존 Collection 삭제/recreate 및 기존 DB 변경 없음.
