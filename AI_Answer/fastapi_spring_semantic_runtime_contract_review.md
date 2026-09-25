# FastAPI AI Runtime + Spring Contract 검증

작성일: 2026-09-25. 공개 서비스 활성화 없이 내부 계약과 local 통합을 검증했다.

## 1. 결과 및 기존 구조

기존 `ai/app/main.py` FastAPI 프로젝트에 `/internal/v1/intent-analysis`와
`/internal/v1/semantic-retrieval`을 추가했다. 기존 `/health`의 `service=ai` 응답도 보존했다.
새 Python 프로젝트나 HTTP library를 만들지 않았다. Spring Boot 4.1.1/Java 21의
기존 AI properties/interface/fallback과 추천 코드를 먼저 확인했다.

Spring의 기존 `FallbackAwareIntentAnalyzer`는 `AiIntentAnalysisClient` Bean이
있으면 자동으로 사용한다. 이번 Client는 별도의 명시적 `SemanticAiClient`로
만들어 기존 Chat/Recommendation 실행을 바꾸지 않았다. 공개 API 배포도 하지 않았다.

실제 Java HTTP Client → local FastAPI → query embedding → 기존 Qdrant v12
경로가 성공했다. 운영 추천과 실제 사용자 MySQL을 포함한 E2E는 이번 검증이 아니다.

## 2. Python 변경

- `ai/app/hybrid_policy.py`: 기존 benchmark의 router/food taxonomy/lexical scoring/
  aggregation을 그대로 추출. DB/산출물 읽기 없음.
- `ai/app/semantic_retrieval_hybrid_v2.py`: 추출한 동일 함수를 import.
  과거 benchmark JSON/Collection을 다시 생성하지 않았다.
- `ai/app/semantic_runtime.py`: 요청·응답 모델, deterministic intent service,
  read-only candidate-scoped retrieval service.
- `ai/app/main.py`: 얇은 API 계층과 공통 JSON 오류 처리.
- 기존 embedding HTTP helper에 timeout keyword argument를 추가. 기존 기본 60s는
  그대로 두고 runtime에서만 3s를 지정한다.

Aggregation은 기존 default top 3를 유지하고 runtime의 bounded topK를 인자로 받는다.
Score 식, source priority, capped mentionCount(999)는 변경하지 않았다.

## 3. Intent Analysis 계약

POST `/internal/v1/intent-analysis`, Request `{query}`.

Response: `intent`, `foodTerms`, `diningContexts`, `tasteTraits`, nullable
`maxBudget`, `quantitativeTaste`, `primaryIntent`, `claimTypes`.

실제 테스트 `혼밥 12000원 안에서 떡볶이 먹고 싶어`는 떡볶이/SOLO_DINING/12000을 반환한다.
원화 숫자·콤마·소수 만원 표기를 처리한다. 식당 가격·영업·거리·제로페이는 판단하지 않는다.
LLM 호출 없음. 복합 Query는 음식/맥락 정보를 모두 노출하되 retrieval은 기존
primary FOOD 우선 Router를 유지한다. caller의 임의 intent는 받지 않는다.

## 4. Retrieval 계약과 Candidate Scope

POST `/internal/v1/semantic-retrieval`:

```json
{"query":"떡볶이 먹고 싶어","candidateRestaurantIds":[9617],"topK":10}
```

ID는 양의 strict integer, 최대 1000개. query는 공백만 허용하지 않고 최대 2000자.
topK는 1..100. 빈 ID 목록은 embedding/Qdrant 호출 없이 빈 결과를 반환한다.

Qdrant query의 `filter.must`에 restaurantId.any와 claimType.any가 함께 들어간다.
전체 Qdrant Top-K 후 client-side ID 필터를 하는 구조가 아니다. 외부 응답이 scope를
위반하면 503으로 차단한다. 최대 200개 Claim을 읽고 공유 aggregation으로 topK를 반환한다.
현재 40-point pilot에는 충분하나 대규모 recall 완전성은 검증하지 않았다.

Response는 `restaurantId`, `retrievalScore`, `semanticSimilarity`, `matchedClaims`.
Claim은 ID/type/evidenceIds, EXACT/SYNONYM/CATEGORY/TRAIT/SEMANTIC 관계와
match flags/mentionCount를 보존한다. 300 단위 우선순위 점수를 cosine으로 노출하지 않는다.
대표 winning Claim 한 개를 반환하며 새로운 LLM 설명을 생성하지 않는다.

## 5. Qdrant/Embedding 설정과 실제 Scope 검증

`QDRANT_SEMANTIC_COLLECTION`은 필수 환경 설정이다. `.env.example`에 v12 pilot 예시를
추가했지만 compose 서비스 재배포/자동 활성화는 하지 않았다.
qwen3-embedding:0.6b, 1024 차원, 기존 Cosine collection을 사용한다.
runtime은 query embedding만 실행하고 collection 생성/upsert/delete 함수는 호출하지 않는다.

실제 Python 통합 테스트는 `[9617]`, `[9731]`, 그리고 스시 Query에 `[9617]`만 전달하는
상황을 확인했다. scope 밖 Restaurant가 반환되지 않았다. scope는 semantic 적합성과
별개이므로 마지막 경우의 결과를 스시 음식점으로 승인했다는 의미는 아니다.

v12 Point/Vector/Payload 전체 40건 hash:
`c992b83f3f6df0327a29cd4dd7af298cf730e20d72672882dddf1cce84da5648`
실행 전후 동일. 컬렉션 삭제/생성/Point 수정 없음.

## 6. Spring Client 및 연결 위치

- `SemanticAiClient`: intent/retrieval DTO 및 interface.
- `FastApiSemanticClient`: JDK HTTP Client + 기존 Jackson dependency.
  별도 Bean 등록 없음. 기존 `AiIntegrationProperties` 사용.
- `SemanticCandidateEnricher`: Spring에서 이미 필터링한 ID 목록에 semantic signal만
  부착. 순서를 바꾸거나 미색인 Restaurant를 버리지 않는다. 빈 scope는 HTTP 생략.

실제 Hard Filter 소유자는 기존 RestaurantJpaRepository/RestaurantRecommendationService다.
repository가 active/recommendation_ready/ELIGIBLE/ZeroPay/legal dong/운영 schedule/
closed period를 적용하고, service가 budget/disliked category/recent meal/confirmed ACTIVE
Venue를 적용한다. **현재 거리 필터는 없다.** Detail 영업시간 테이블과 추천 schedule도
동일한 모델이라고 가정하지 않았다.

추천 service의 기존 필터를 통과한 `[4]`만 mock semantic client에 전달되는 회귀 테스트를
추가했다. 이는 실제 service 로직을 사용하되 repository/context는 mock이다.
향후 production 연결 시에는 모든 Hard Filter와 recent-Venue 제외 뒤, 최종 dedup/limit 전의
전체 후보 ID를 넘겨야 한다. 현재 추천 결과 3건만으로 retrieval 후보를 만드는 production
연결은 구현하지 않았다.

## 7. Final Ranking/Fallback

Spring deterministic 순서를 유지하면서 nullable semanticSignal을 붙인다.
높은 AI 점수가 탈락 Restaurant를 다시 넣거나 순위를 강제할 수 없다.
실제 추천 점수 가중치 조합은 이번에 도입하지 않았다.

기존 intent fallback은 그대로 존재한다. 신규 retrieval adapter는 설정상 fallback 허용 시
AI timeout/503/잘못된 응답에도 원래 Spring 후보 목록·순서를 반환한다.
fallback 비활성화 시 오류를 전파한다. 정상 빈 AI 결과도 Spring 후보를 삭제하지 않는다.

## 8. Timeout/Error 및 발견한 결함

Spring connect=2s/response=8s 기본 설정 재사용, retry 없음.
FastAPI dependency socket timeout은 각 3s. 매우 느린 chunk 응답에 대한 process 전체
wall-clock deadline까지 보장하는 구조는 아니다.

400 INVALID_REQUEST, 503 SEMANTIC_RETRIEVAL_UNAVAILABLE, 500 INTERNAL_ERROR를
JSON `{code,message}`로 반환하고 stack trace/내부 dependency 문자열을 숨긴다.
Schema coercion으로 bool/string ID가 허용되지 않도록 strict integer를 사용한다.

실제 Java HTTP 테스트 첫 실행에서 기본 HTTP/2 upgrade(h2c)를 Uvicorn이 거절해 400이
발생했다. 해당 Client에 HTTP/1.1을 명시한 후 동일 테스트가 통과했다.

## 9. TASTE_QUANTITATIVE 및 기존 데이터 한계

runtime/offline은 관련 trait이 없는 후보 제외 + capped count 정책을 공유한다.
거대한 raw count가 음식 exact/source priority를 압도하지 않는다. ratio 없음.

다만 v12 mentionCount는 인용 keyword 중 최댓값으로 만들어졌기 때문에 query-specific
keyword count라는 보장은 없다. 기존 traitMatch는 FOOD exact에서도 true가 될 수 있고,
공유 policy가 traitMatch를 비정량 score 우선순위로 사용하지 않는 부분도 그대로다.
이번에는 benchmark보다 더 검증됐다고 주장하거나 weight를 수정하지 않았다.
API Evidence trace 통과가 Claim의 의미 정확성 전체 재승인을 뜻하지 않는다.

## 10. 검증 결과

| 검증 | 실제 결과 |
|---|---|
| Python API/shared-policy targeted | 22 passed |
| Python real v12 scope + point hash | 1 passed (opt-in) |
| Java Mock HTTP contract | 8 passed |
| Java real HTTP → FastAPI → Qdrant | 1 passed (opt-in, 초기 h2c 실패 수정 후) |
| AI Harness | 203 passed, 1 skipped, 1 warning |
| Backend Harness build | PASS: 61 tests 중 60 passed, live test 1 skipped |
| 기존 추천 filter/fallback/Venue regression | Backend Harness에서 PASS |
| git diff --check | PASS |

기본 Harness의 live skip은 별도 opt-in 실행 PASS와 구분한다. Backend 기본 DB는 H2 memory다.
실제 MySQL Integration을 실행했다고 보고하지 않는다. `scripts/check-integration.sh`는
개발 DB/서비스 쓰기를 포함하므로 이번 무쓰기 작업에서는 실행하지 않았다. 대신 실제 HTTP
계약 통합 테스트를 수행했다. React/사용자 인증/실제 user recommendation E2E는 미실행.

## 11. 산출물과 재현

- [HTTP 실제 결과 및 v12 hash](fastapi_spring_semantic_runtime_live_results.json)
- [계약/설정/재현 문서](../docs/semantic-runtime-contract.md)
- Python: `ai/tests/test_semantic_runtime.py`, `test_semantic_runtime_live.py`
- Java: `FastApiSemanticClientTests`, `FastApiSemanticLiveContractTests`
- Backend HTML/XML: `backend/build/reports/tests/test/`, `backend/build/test-results/test/`
  (최종 Harness 기준으로 live test는 skipped; 별도 실행 결과는 이 보고서에 구분 기록)

local Uvicorn은 127.0.0.1:18091에서 일시 실행 후 종료했다. 기존 compose는 교체하지 않았다.
실환경 query embedding 총 6회(Python scope 3 + Java live 2 + 결과 보존 HTTP 1).
Profile Qwen/Provider/Detail/새 Embedding Batch는 0회.

## 12. 미구현/다음 단계 및 안전 확인

현재 완료 범위는 내부 HTTP 계약과 후보 제한/실패 처리다. 실제 Recommendation runtime
wiring, semantic ranking 가중치, LLM explanation, React, public API activation, 배포는 미구현이다.
다음 단계에서 후보 생성/선택 분리, AI intent의 기존 AnalyzedIntent 변환, Spring Hard Filter
후 retrieval, 최종 점수 반영 정책을 검증해야 한다. 서비스 보안/내부 인증은 배포 전에 결정한다.

신규 Restaurant/Detail 수집, MySQL write, Profile 영속화, Place ID/Venue 변경 없음.
v12와 과거 benchmark artifact 보존. 기존 dirty working tree 보존.
Git add/commit/push 및 destructive Git 명령 없음. 새 HTTP library/Schema/Migration/React 변경 없음.
