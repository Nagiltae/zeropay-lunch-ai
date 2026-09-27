# 프로젝트 학습 6 — 테스트와 검증 계층

## 테스트 계층

| 계층 | 위치/명령 | 보장하려는 것 | 보장하지 않는 것 |
|---|---|---|---|
| AI unit/API | `ai/tests/test_semantic_runtime.py`, graph tests, `./scripts/check-ai.sh` | schema, routing, scope filter, typed error, aggregation, graph 분기 | 운영 Qdrant의 모든 point 품질 |
| Spring unit | `backend/src/test/java/com/zeropaylunch/backend/` 및 `./scripts/check-backend.sh` | repository/service 정책, ordering, scope validation, Venue dedup/max3 | 배포 환경 네트워크의 지속 가용성 |
| Frontend unit | `frontend/src/**/*.test.ts(x)`, `./scripts/check-frontend.sh` | 이벤트 parsing, UI 상태/컴포넌트 | 실제 database/API 연결 |
| Compose integration | `./scripts/check-integration.sh` 등 | Docker service, MySQL/Flyway 경계 | production traffic/availability |
| Browser E2E | `frontend/e2e/mvp-recommendation.pw.ts`, `./scripts/check-mvp-e2e.sh` | browser 로그인→Spring SSE→추천 UI, semantic ON/OFF/failure 시나리오 | 전체 모집단에서의 검색 relevance |

테스트 명령은 문서화 목적의 이번 분석에서 재실행하지 않았다. 아래 E2E 수치는 저장소에 있는 이전 결과 artifact를 인용한 것이다.

## 대표 테스트 5개

1. `ai/tests/test_recommendation_graph.py::test_retryable_failure_then_success_retries_once_with_same_input` — transient 실패 후 1회 재시도, 같은 query/scope, 성공 route를 검증한다.
2. `ai/tests/test_semantic_runtime.py::test_scope_is_in_qdrant_request_and_response_preserves_evidence` — Qdrant request-level ID/type filter, retrieval fields, evidence round-trip을 확인한다.
3. `backend/src/test/java/com/zeropaylunch/backend/restaurant/application/RestaurantRecommendationServiceTests.java::hybridSemanticRelevanceCanOutrankDeterministicPreferenceScore` — 현재 semantic hybrid signal이 deterministic preference score를 앞설 수 있음을 보여준다.
4. 같은 파일의 `runtimeRetrievalReceivesEveryHardFilteredCandidateBeforeVenueDedupAndMaxThree` — semantic retrieval이 dedup/max3보다 먼저 모든 hard-filtered candidate를 받는 순서를 보장한다.
5. `frontend/e2e/mvp-recommendation.pw.ts::isolated semantic MVP recommendations render through authenticated SSE` — 로그인된 browser에서 4 query를 전송하고 SSE 추천을 화면에 렌더링하는 격리 E2E다.

같이 볼 가치가 있는 회귀 테스트: `test_unknown_intent_skips_retrieval`, `test_empty_result_falls_back_without_retry`, `test_retry_exhaustion_falls_back_and_never_exceeds_max`, `test_non_retryable_failure_falls_back_without_retry`, `FastApiSemanticClientTests::rejectsOutOfScopeResponse`, `RestaurantRecommendationServiceTests::confirmedVenueIsReturnedOnceWhileUnassociatedRestaurantRemainsCompatible`, `ai/tests/test_semantic_profile_source_scope.py::test_customer_raw_claim_or_missing_scoped_text_cannot_be_embedded`.

## 기록된 Browser E2E 결과

`AI_Answer/langgraph_recommendation_v1_compose_e2e.json`은 isolated DB/browser 테스트에서 떡볶이·피자·혼밥·단체 query를 확인했다. 모두 최대 3개, candidate leakage 0, hard-filter violation 0; AI 경로 8 semantic requests, 12 Qdrant queries/embedding calls 기록이다. Test database에는 fixture/user/conversation/message/recommendation writes가 있었지만 disposable E2E DB였고 `devMysqlWrites=0`; Qdrant point count 40→40, writes 0이다. `AI_Answer/langgraph_recommendation_v1_fallback_e2e.json`은 AI 장애 시 semantic/embedding/Qdrant 요청 없이 deterministic 결과를 표시한 별도 E2E 기록이다. 두 수치는 이번 문서 작업에서 다시 실행하지 않았다.

## 테스트를 읽는 방법

- Unit test: 한 정책 함수/서비스 계약을 분리 검증한다.
- Graph test: node sequence, retry budget, immutable scope를 fake dependency로 검증한다.
- Semantic service test: vector/Qdrant protocol과 candidate filter를 stub HTTP dependency로 확인한다.
- Browser E2E: 진짜 UI와 Spring/SSE 경계를 검증하지만, semantic provider correctness는 테스트 환경의 실제/fixture Qdrant 상태에 한정된다.
- Fallback E2E: AI가 unavailable인 상황에서도 deterministic UX가 계속되는 경로를 보여준다.

한 테스트가 통과했다고 “전체 서비스 운영 안정성”이나 “모든 Claim이 진실”이 입증되는 것은 아니다. 서로 다른 계층의 증거를 결합하고, 데이터 크기와 환경을 함께 말해야 한다.

### 내가 이해했는지 확인

- Qdrant filter는 어느 테스트가 검증하는가?
- Graph unit test와 Browser E2E가 각각 놓치는 것은 무엇인가?
- E2E DB에 fixture write가 있었는데도 shared dev DB write가 0일 수 있는 이유는?
- 결과 artifact의 40 point count를 현재 실시간 상태라고 말해도 되는가?
