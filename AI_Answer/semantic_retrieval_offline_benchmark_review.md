# ZeroPay Lunch AI — Semantic Retrieval Offline Benchmark

## 1. 결론

실제 확보된 승인 Profile/Evidence가 4개뿐이어서 20개 Restaurant Benchmark는 구성할 수 없었다. 추가 Detail/Profile 생성 없이 동일 4개 Restaurant에 대해 Ground Truth 20개 Query를 사전 고정하고 세 가지 검색 방식을 비교했다.

결과는 Claim Router/Claim Vector가 기존 Restaurant Vector보다 개선됐다.

| 방식 | Precision@1 | Hit@3 |
|---|---:|---:|
| Baseline A: Restaurant Vector | 0.40 | 0.95 |
| Claim B: Claim Vector + Router + max | 0.90 | 1.00 |
| Candidate C: Claim B + 최소 synonym/category 보정 | 0.90 | 1.00 |

Evidence trace는 100%, REVIEW_REQUIRED/REJECTED/deterministic field leakage는 모두 0이었다. 그러나 표본이 4개이고 `일식`과 정량적 `맛있다는 평가가 많은 곳`에서 실패가 남아 **Runtime 연결은 CONDITIONAL_GO**로 판단한다. FastAPI/Spring은 변경하지 않았다.

## 2. Benchmark 대상과 제한

실제 산출물로 안전하게 재사용 가능한 대상은 다음 4건뿐이었다.

* 9617
* 9731
* 9567
* 9580

모두 기존 승인 Claim/Evidence Catalog와 Numeric/Detail 데이터 산출물을 재사용했다. 새 Detail 수집, 신규 Profile Qwen 생성, Provider/Qwen Entity Resolution은 실행하지 않았다. 범주가 충분하지 않아 중식·카페 등은 억지로 추가하지 않았다.

## 3. Ground Truth

20개 Query의 expectedRestaurantIds와 Evidence ID를 검색 실행 전에 [semantic_retrieval_benchmark_dataset.json](semantic_retrieval_benchmark_dataset.json)에 고정했다. 검색 결과를 보고 expected 값을 변경하지 않았다.

포함 범주:

* FOOD: 스시, 초밥, 일식, 우동, 피자, 떡볶이, 김밥, 한식, 한정식, 갈비찜
* DINING_CONTEXT: 혼밥, 빠른 식사
* TASTE: 맛, 신선도, 가성비
* 정량 의도: 맛 평가가 많은 곳, 가성비 언급이 있는 곳
* VENUE_CHARACTERISTIC: 친절한 서비스

## 4. 음식 Taxonomy와 FOOD_MENTION

최소 taxonomy만 적용했다.

* 스시 ↔ 초밥: synonym
* 일식 → 초밥·우동·후토마끼: category
* 한정식 → 한식·정식: category
* 피자·파스타·우동 등은 실제 Evidence가 있는 경우만 사용

FOOD_MENTION은 Review SUCCESS keyword, mention count 3 이상, `sourceKind=review_keyword_only` 조건을 유지했다. 공식 메뉴로 변환하지 않았고, point payload에 `mentionTerm`, `mentionCount`, `evidenceIds`를 보존했다. mention count는 embedding text에 넣지 않았다.

## 5. 방법별 결과

### Baseline A

기존 `zeropay_semantic_profile_pilot_v1` Restaurant Vector를 그대로 검색했다. Precision@1은 0.40으로, 일반 TASTE가 음식 종류 Query를 오염시키는 문제가 재현됐다.

### Claim B

`zeropay_semantic_claim_pilot_v6`에서 Claim Type Router와 Restaurant max Claim score를 사용했다. Precision@1 0.90, Hit@3 1.00이었다.

### Candidate C

Claim B에 exact/synonym/category 용어 신호를 추가한 설명 가능한 보정 방식이다. 전체 수치는 Claim B와 같았으며, 4개 표본에서는 추가 개선이 측정되지 않았다. 복잡한 ML ranking이나 운영 weight는 확정하지 않았다.

세부 결과와 score는 [semantic_retrieval_benchmark_results.json](semantic_retrieval_benchmark_results.json), 지표는 [semantic_retrieval_benchmark_metrics.json](semantic_retrieval_benchmark_metrics.json)에 보존했다.

## 6. 실패 사례

* `일식 먹고 싶다`: 9567이 Top-1이 되어 category 처리와 embedding 유사도가 충돌했다. 9731의 초밥·우동·후토마끼 Evidence가 있어도 category Query의 exact/candidate aggregation이 완전히 해결되지 않았다.
* `맛있다는 평가가 많은 곳`: 9580이 1위였지만, 9731의 `음식이 맛있어요` keyword count가 739로 더 크다. 현재 검색은 count를 ranking에 반영하지 않아 정량 의도 실패로 분류한다.

`스시`, `초밥`, `우동`, `피자`, `한식` 등의 개별 Query는 Evidence에 대응하는 Restaurant를 회수했다. 다만 Top-1 Claim의 세부 term이 Query와 정확히 일치하는지와 category 관계는 별도 평가가 필요하다.

## 7. TASTE mentionCount 분석

현재 확보된 Evidence에서 예시 count는 다음과 같다.

* 9731 맛있어요: 739, 신선해요: 500, 맛: 1182
* 9580 맛있어요: 32, 맛: 16
* 9617 맛있어요: 30, 가성비: 12
* 9567 맛있어요: 149, 가성비: 51

Raw count를 그대로 score에 더하지 않았다. `log1p(count)`와 Restaurant별 keyword 상대비중을 운영 weight로 확정하기에는 denominator와 전체 benchmark가 부족하다. 정량 Query에서는 의미 유사도와 count 신호를 별도 필드로 반환한 뒤 Spring 정책과 분리해 비교하는 것이 다음 단계다.

## 8. Metrics와 안전성

정의한 기준:

* Precision@1 >= 0.80
* Hit@3 >= 0.90
* Wrong Claim Type Rate = 0
* Evidence Trace = 100%
* REVIEW_REQUIRED/REJECTED leakage = 0

Claim B/C는 수치상 기준을 충족했다. 그러나 Restaurant 수가 4개로 최소 목표 10보다 작고, 음식 종류·맛 Claim coverage가 편중되어 통계적 일반화는 불가하다. 따라서 결과 상태는 GO가 아닌 CONDITIONAL_GO다.

## 9. Runtime 계약 초안

조건부 검토용으로만 [semantic_retrieval_runtime_contract_draft.json](semantic_retrieval_runtime_contract_draft.json)을 작성했다. 실제 `POST /internal/v1/semantic-retrieval` API는 구현하지 않았다.

FastAPI는 intent, semantic candidates, evidence trace만 반환하고, Spring은 ZeroPay eligibility·영업시간·거리·예산·최근 식사·최종 ranking을 계속 담당해야 한다.

## 10. 테스트와 산출물

* Claim retrieval tests: 3 passed
* AI Harness: 180 passed, 1 warning
* Ground Truth Query: 20개
* External Provider/Qwen Entity Resolution: 미실행
* 신규 Qwen Profile 생성: 미실행
* Detail persistence: 미실행
* MySQL 원본 변경: 없음
* 기존 Qdrant Collection 삭제/수정: 없음
* 신규 Shadow Collection: `zeropay_semantic_claim_pilot_v6`, 21 points

구현 파일:

* `ai/app/semantic_retrieval_offline_benchmark.py`
* `ai/app/semantic_claim_retrieval_pilot.py`
* `ai/tests/test_semantic_claim_retrieval_pilot.py`

## 11. 다음 단계

Runtime 연결 전 다음을 수행해야 한다.

1. 실제 승인 Evidence가 있는 Restaurant를 최소 10개 이상 확보하되 전체 Detail/Profile Batch는 수행하지 않는다.
2. 일식 category와 초밥 exact term을 분리 평가한다.
3. 정량 TASTE Query에 mention count를 반영할지 별도 benchmark로 검증한다.
4. Claim-level 결과를 Spring deterministic filter와 결합하는 contract test를 작성한다.

현재는 의미 후보 검색 Shadow 단계까지이며, 운영 FastAPI/Spring 연결을 완료한 것으로 보고하지 않는다.

## 12. Git 및 데이터 보호

기존 MySQL, Profile, Venue, Place ID, Detail 데이터를 변경하지 않았다. Provider/Qwen Entity Resolution, 전체 Detail/Profile Batch, Embedding 운영 Collection 변경은 실행하지 않았다. Git add/commit/push는 수행하지 않았고 기존 Working Tree 변경을 보존했다.
