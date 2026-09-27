# 프로젝트 면접 질문 30개

각 항목은 답변의 핵심만 정리했다. 설명은 “문제 → 선택 → 이유 → 관측된 결과/제약” 순서로 한다.

## Architecture / Spring-FastAPI

1. **왜 React가 FastAPI가 아니라 Spring을 호출하나요?** — 인증·세션·MySQL·공개 API를 Spring이 이미 소유한다. 내부 AI service를 브라우저에서 직접 노출하지 않는다. 코드: `ChatController`, `chat.ts`.
2. **Spring과 FastAPI 경계를 어디에 뒀나요?** — Spring은 hard filter/final order, FastAPI는 semantic retrieval/evidence signal. 코드: `RestaurantRecommendationService`, `semantic_runtime.py`.
3. **FastAPI 장애 때 사용자 요청은 어떻게 되나요?** — 설정된 fallback이면 Spring deterministic route 유지; 비활성화 시 오류가 SSE error로 전달될 수 있다. 코드: `FallbackAwareIntentAnalyzer`, `SemanticCandidateEnricher`, `ChatStreamService`.
4. **candidateRestaurantIds를 왜 Spring에서 만들까요?** — authoritative constraints를 적용한 유일한 후보 scope이기 때문. 코드: `RestaurantRecommendationService.recommend`.
5. **Spring과 Python이 중복으로 하는 일이 있나요?** — Spring intent endpoint 후 graph intent node에서 deterministic analyze가 재수행될 수 있다. 코드: `FastApiIntentAnalysisAdapter`, `recommendation_graph.py`.

## Hard filter / Ranking

6. **Hard filter와 semantic relevance의 차이는?** — eligibility 사실과 열린 자연어 유사도. AI similarity는 ZeroPay/open을 대체하지 않는다. 코드: repository query, `matches`, `SemanticRetrievalService`.
7. **semantic score가 최종 순위에 어떻게 영향 주나요?** — 코드상 `retrievalScore` 1차, `semanticSimilarity` 2차, deterministic order 후순위; signal 없으면 deterministic. 코드: `RestaurantRecommendationService`.
8. **왜 Qdrant 결과를 그대로 최종 응답으로 안 쓰나요?** — Qdrant는 claim point를 찾고 Spring은 hard filter, source candidate, Venue dedup, max3를 최종 결정한다.
9. **Venue dedup은 왜 필요하고 어떻게 적용하나요?** — 한 장소에 복수 Restaurant row가 있을 수 있어 confirmed active Venue key로 dedup; 최근 방문 제외에도 사용한다. 코드: `confirmedVenueIds`.
10. **예산을 semantic search에 맡기지 않는 이유는?** — unknown price는 증거 없는 조건 통과가 되며 가격은 structured field 비교가 정확하다. 코드: `matches`.

## Embedding / Qdrant / Retrieval

11. **무엇을 embedding하나요?** — runtime은 사용자 query. document indexing은 별도 offline path이며 이번 frozen runtime이 수행하지 않는다. 코드: `embed`, `SemanticRetrievalService.retrieve`.
12. **같은 embedding space가 왜 필요한가요?** — query/document vector cosine 비교가 같은 모델·차원·representation에서 유효하기 때문이다.
13. **Qdrant와 Spring 중 누가 ranking하나요?** — Qdrant point score와 FastAPI hybrid retrievalScore 제공, Spring이 최종 restaurant 순서 결정.
14. **candidate leakage를 어떻게 막나요?** — Qdrant filter, Python payload validation, Java response scope validation, tests. 코드: `retrieve`, `FastApiSemanticClient.retrieve`.
15. **retrievalScore와 semanticSimilarity의 차이는?** — retrievalScore는 lexical tier/source 및 semantic 보조를 합친 hybrid ordering 값, semanticSimilarity는 vector score 원값.

## Data pipeline / Evidence grounding

16. **왜 raw review를 바로 embedding하지 않았나요?** — 긴 원문과 source 의미/추적성이 불명확해질 수 있어 Evidence→Claim→validation을 시도했다. 단 현재 full pipeline은 frozen experimental.
17. **Evidence ID만 있으면 충분한가요?** — 아니다. 실제 원문 resolve, ownership, exact quote, entailment가 각각 필요하다. 코드: `semantic_profile_quality_gate.py`.
18. **Atomicizer와 Verifier 역할은?** — Atomicizer는 복합 문장 분해, Verifier는 각 assertion을 evidence와 대조; Python이 전체 verdict를 집계한다.
19. **Source Scope Guard는 무엇을 해결하나요?** — MENU vs 고객 언급의 epistemic scope를 source type으로 결정하고 customer text에 provenance prefix를 둔다. 코드: `semantic_profile_source_scope.py`.
20. **legacy v12 collection도 guard가 보호하나요?** — 아니다. guard는 새 index input을 막지만, 기존 40 legacy points는 소급 수정되지 않았다.

## LangGraph / Retry / Failure

21. **왜 LangGraph를 넣었나요?** — skip/success/retry/fallback의 state transition과 bounded loop, trace를 명시적으로 보기 위해. 코드: `recommendation_graph.py`.
22. **State와 checkpoint는 같은 건가요?** — 아니다. graph state는 한 execution 중 공유되는 값이며 durable checkpoint store는 설정된 것을 확인하지 못했다.
23. **어떤 오류를 재시도하나요?** — transient transport와 HTTP 500/502/503/504만 graph에서 최대 1회. 코드: `_raise_retrieval_failure`.
24. **왜 429/4xx는 재시도하지 않나요?** — quota/request 문제는 짧은 동일 재시도로 해결된다는 근거가 없고 중복 부하를 만들기 때문이다.
25. **empty result도 retry하나요?** — 아니다. 정상 검색 결과가 0인 것이므로 동일 요청 반복은 의미 없고 empty fallback으로 간다.

## Testing / Trade-off / Retrospective

26. **Graph unit과 Browser E2E의 차이는?** — unit은 분기/입력을 정밀 검증, browser E2E는 React→Spring SSE 전체 연결. 어느 쪽도 전체 profile 진실성을 증명하지 않는다.
27. **어떤 성능 결과를 갖고 있나요?** — 저장된 bounded benchmark와 4 query E2E 결과가 있지만 scope/data에 한정된다. 전체 운영 정답률로 주장하지 않는다. artifact: `langgraph_recommendation_v1_compose_e2e.json`.
28. **이 프로젝트에서 AI가 불필요했던 부분은?** — ZeroPay, hours, budget, recent meal, dedup, cap은 deterministic code. Runtime intent도 현재 rule-based다.
29. **React→FastAPI로 단순화할 수 있었나요?** — greenfield AI-centric system은 가능하지만 현재 Spring auth/data/business owner를 옮겨야 해 현 경계에서는 장단점과 이관비가 있다.
30. **다시 만든다면 무엇을 줄이나요?** — 중복 intent hop, 실험 indexing 경로/artifact 폭을 줄이되 candidate scope, source provenance, fallback, final ranking ownership은 유지한다.

## 답변 연습 규칙

각 질문은 30~60초로 답하고, 숫자를 말하면 해당 artifact와 cohort/환경도 함께 말한다. “테스트 통과”를 “운영 보장”으로 바꾸지 않는다. README/AGENTS 설명과 실제 코드가 다른 경우에는 현재 code path를 확인했다고 설명한다.
