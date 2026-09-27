# 프로젝트 직접 분석 학습 계획

문서만 읽지 말고 매일 지정 파일을 열어 함수 호출을 따라간다. 먼저 한 번 훑고, 두 번째에는 코드를 보지 않고 자신의 말로 그린다.

## 권장 7일 일정

### DAY 1 — 문제와 전체 request flow

읽기: `project_review_01_architecture.md`; `frontend/src/App.tsx`, `hooks/useChatStream.ts`, `api/chat.ts`, Spring `ChatController.java`, `ChatStreamService.java`.

연습: “사용자가 혼밥 요청을 전송한 뒤 추천 카드가 뜨기까지”를 10개 단계로 적는다. 이때 SSE가 token generation이 아니라 event stream이라는 점을 설명한다.

### DAY 2 — Spring hard filter / 순위

읽기: `RecommendationContextService.java`, `RestaurantRecommendationService.java`, `RestaurantJpaRepository.java`, `VerifiedNaverServingCandidateService.java`, `VerifiedHoursPolicy.java`, `ServingReadinessPolicy.java`, Spring tests.

연습: 서비스 area/open/ZeroPay/budget/recent/venue 조건을 코드가 실제 검사하는 위치와 함께 구분한다. semantic 신호가 있는/없는 두 순위를 설명한다.

### DAY 3 — FastAPI contract와 retrieval

읽기: `ai/app/main.py`, `semantic_runtime.py`, `hybrid_policy.py`; `ai/tests/test_semantic_runtime.py`.

연습: 요청 JSON에서 Qdrant request까지 어떤 값이 보존되고 어느 곳에서 validation되는지 적는다. intent가 현재 LLM인지 규칙 기반인지 확인한다.

### DAY 4 — Embedding과 Qdrant

읽기: `semantic_embedding_qdrant_pilot.py::embed`, runtime retrieve, Compose env sample, saved E2E JSON.

연습: query vector와 indexed document vector 역할을 그린다. collection point 40은 저장된 격리 E2E 관측이며 live 확인이 아님을 구별한다. Indexer `main()`은 실행하지 않는다.

### DAY 5 — Data pipeline과 provenance

읽기: `project_review_04_data_pipeline.md`, `semantic_profile_shadow.py`, `semantic_profile_generator_v2.py`, `semantic_profile_quality_gate.py`, `semantic_profile_source_scope.py`, source-scope review artifact.

연습: raw source→Evidence→Claim→quote/atomic verifier→scope/searchText 흐름을 설명하고, legacy v12가 guard 적용 전인 이유를 설명한다. 어떠한 profile 재생성도 하지 않는다.

### DAY 6 — LangGraph와 failure behavior

읽기: `recommendation_state.py`, `recommendation_graph.py`, `ai/tests/test_recommendation_graph.py`, Spring fallback client/enricher.

연습: graph를 손으로 그리고 retry/fallback node에서 state가 어떻게 달라지는지 표로 쓴다. if/else 대안과 graph의 실제 이득/비용을 각각 하나씩 든다.

### DAY 7 — 테스트와 회고 / 면접

읽기: `project_review_06_testing.md`, `project_review_07_retrospective.md`, `project_review_08_interview.md`, `scripts/check-ai.sh`, `scripts/check-backend.sh`, `scripts/check-mvp-e2e.sh` (읽기만).

연습: 5개 대표 테스트를 각각 “보장하는 것/보장하지 않는 것”으로 말한다. 면접 질문 30개 중 10개를 1분 안에 답하고, 모든 성과 수치에 artifact/cohort 범위를 붙인다.

## 내가 직접 답해볼 질문 20개

아래에는 모범답안을 붙이지 않는다. 먼저 자기 말로 적은 뒤 각 질문에 연결된 실제 코드와 대조한다.

1. 왜 candidateRestaurantIds는 Spring에서 만든 다음 FastAPI에 전달하는가?
2. ZeroPay 여부를 embedding similarity로 판단하면 어떤 문제가 생기는가?
3. hard-filter 탈락 Restaurant가 semantic result로 돌아오지 못하는 지점은 어디인가?
4. Spring intent endpoint와 graph intent node가 각각 하는 일은 무엇이며 중복은 어디인가?
5. empty result와 dependency failure는 왜 다른 상태인가?
6. 503/timeout은 retry할 수 있는데 429는 retry하지 않는 이유는 무엇인가?
7. graph의 max retry가 1일 때 외부 요청 총 횟수는 몇 번인가?
8. retry 중 query와 candidate scope가 달라지면 무엇이 깨지는가?
9. Qdrant의 cosine score와 FastAPI retrievalScore는 어떻게 다른가?
10. Qdrant가 top K를 돌려줬는데 최종 추천이 다를 수 있는 이유는 무엇인가?
11. Spring이 semantic score를 받지 못한 hard-filter candidate를 왜 유지하는가?
12. Venue dedup을 후보 filtering 전에 하면 어떤 경우를 잘못 처리할 수 있는가?
13. Evidence ID가 유효해도 Claim이 틀릴 수 있는 사례는 무엇인가?
14. exact supportQuote가 검증하는 것과 검증하지 못하는 것은 무엇인가?
15. Atomicizer와 Assertion Verifier의 역할 차이는 무엇인가?
16. CUSTOMER_REPORTED raw claimText와 safe searchText의 차이를 설명해보라.
17. Source Scope Guard가 legacy Qdrant v12 points를 자동으로 보호하지 않는 이유는?
18. LangGraph State는 무엇이며 durable user memory와 어떻게 다른가?
19. 이 프로젝트의 Browser E2E가 production-scale 품질을 증명하지 않는 이유는 무엇인가?
20. 처음부터 다시 만든다면 어떤 복잡성은 줄이고 어떤 safety boundary는 유지할 것인가?

## 전체 자가 점검

- [ ] 브라우저→SSE→최종추천까지 정확한 endpoint와 함수로 말할 수 있다.
- [ ] Spring hard filter와 FastAPI retrieval의 소유권을 분리해 설명할 수 있다.
- [ ] 실제 filter와 단지 요청에 존재하는 preference field를 구별한다.
- [ ] Embedding은 runtime에서 query에 대해 호출되며 문서 indexing은 별도임을 설명한다.
- [ ] Qdrant query-level candidate filter와 후처리 검증을 모두 설명한다.
- [ ] 현 코드의 ranking order가 stored docs 일부 설명과 다른 점을 알고 code를 우선한다.
- [ ] Graph의 State, node, conditional edge, `compile`, `ainvoke`를 이 프로젝트 예로 설명한다.
- [ ] retryable/non-retryable/empty/UNKNOWN 경로를 구분한다.
- [ ] fallback enabled/disabled 결과 차이를 설명한다.
- [ ] Data Pipeline이 frozen experimental이라는 점과 40 legacy points의 한계를 말한다.
- [ ] 11 fixture 결과와 40 legacy points 결과를 전체 profile 품질로 과장하지 않는다.
- [ ] E2E의 isolated DB writes와 dev DB writes 0의 차이를 설명한다.
- [ ] 무엇이 production에 배포·운영 검증됐는지 확인되지 않으면 그렇게 말하지 않는다.

## 공부하는 요령

각 주제에서 처음에는 호출 순서를 찾고, 다음에 data shape와 실패 path를 추적한다. 모르는 점은 “코드에서 확인되지 않음”이라고 표시한다. README 문장을 외우기보다 실제 호출부와 test assertion을 나란히 읽는다. 마지막에는 이 문서들을 닫고 sequence diagram을 직접 다시 그려 본다.
