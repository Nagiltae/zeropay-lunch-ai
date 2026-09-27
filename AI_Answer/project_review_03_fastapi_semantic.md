# 프로젝트 학습 3 — FastAPI와 Semantic Retrieval

## 경계와 계약

FastAPI는 내부 서비스다. `ai/app/main.py`에서 `/health`, `/internal/v1/intent-analysis`, `/internal/v1/semantic-retrieval`, 별도 `/internal/v1/recommendation-explanations`를 등록한다. 추천 retrieval 경로는 MySQL을 읽지 않고, Spring이 준 query와 candidate IDs만 받는다.

`RetrievalRequest`는 query 1~2000자, positive integer `candidateRestaurantIds`(최대 1000), `topK` 1~100을 받는다. Response는 candidates의 restaurant ID, retrievalScore, semanticSimilarity, matchedClaims와 evidence IDs, policyVersion을 반환한다. Pydantic `extra="forbid"`로 미정의 필드를 받지 않는다.

Spring은 실제 호출 순서로 intent endpoint를 먼저 사용해 intent contract를 받고, filter를 완료한 뒤 retrieval endpoint를 호출한다. Graph의 `intent_analysis` node도 query에 같은 deterministic `analyze()`를 적용한다. 현재 호출 경로에서는 intent 분석이 두 번 일어날 수 있지만, 생성형 model 호출은 아니다.

## Intent가 실제로 하는 일

`semantic_runtime.py::analyze`는 `hybrid_policy.py::_route_v2`의 규칙과 정규식으로 FOOD, DINING_CONTEXT, TASTE, VENUE_CHARACTERISTIC 또는 UNKNOWN을 정한다. 추가로 food terms, dining context, taste traits, 원화 예산을 추출한다. 예를 들어 `혼밥하기 좋은 곳`은 DINING_CONTEXT이며 해당 claim type으로 retrieval 가능하다. 알 수 없는/일반 질문은 UNKNOWN이다.

이것은 범용 LLM intent agent가 아니다. 현재 지원된 표현을 deterministic routing으로 다루며, arbitrary semantic intent coverage는 한계다. 규칙이 있는 이유는 embedding/Qdrant를 불필요한 질문에 호출하지 않고 허용 claim type을 제한하기 위해서다.

## Query embedding과 Qdrant

`SemanticRetrievalService.retrieve`는 비어 있는 candidate list면 dependency call 없이 빈 결과를 낸다. UNKNOWN intent도 embedding/Qdrant 전에 empty result로 끝난다. 그 외에는:

1. Query text만 `embed(OLLAMA_BASE_URL, query, timeout=3.0)`로 전달한다.
2. 모델은 `qwen3-embedding:0.6b`; runtime은 벡터 길이가 1024이고 모든 값이 finite인지 검증한다.
3. Qdrant `POST /collections/{QDRANT_SEMANTIC_COLLECTION}/points/query`에 vector, `limit=200`, payload, 두 개의 `must` filter를 보낸다.
4. `restaurantId`는 Spring candidate IDs의 distinct/sorted 집합, `claimType`은 intent가 허용한 type이다. 필터는 Qdrant query 단계에 걸린다.
5. 결과 point를 Python에서도 restaurant scope/type, evidence IDs, claim ID, finite score 관점에서 검증한다.
6. `_aggregate`는 point를 restaurant별로 묶고 가장 높은 해당 query의 point를 대표로 선택한다.

Runtime은 문서 vector를 생성하거나 적재하지 않는다. Document vectors는 앞선 offline indexing 작업에서 만들어졌어야 한다. Query와 document가 같은 모델/차원/embedding space여야 cosine 비교가 의미 있다. Indexer의 `semantic_embedding_qdrant_pilot.py::main`은 실제 Qdrant write를 포함하므로 현재 frozen 상태에서는 절대 실행하지 않는다.

## Collection과 payload

기본 env는 `QDRANT_SEMANTIC_COLLECTION=zeropay_semantic_claim_pilot_v12`. 최근 기록된 격리 Compose E2E는 이 collection에 40 points가 있었고 테스트 전후 point count 40, Qdrant writes 0을 기록했다 (`AI_Answer/langgraph_recommendation_v1_compose_e2e.json`). 본 학습 작업에서는 현재 live Qdrant를 새로 조회하지 않았으므로 이 숫자는 “최신 기록된 관측”이지 오늘의 실시간 조회값이라고 주장하지 않는다.

E2E에서 실제 payload 관측 필드에는 `restaurantId`, `claimId`, `claimType`, `evidenceIds`, claim text가 포함됐다. Runtime은 Qdrant payload를 그대로 Spring에 덤프하지 않고 `MatchedClaim` 계약으로 필요한 내용을 제한한다. Collection 설정에 차원/distance가 있는지는 offline indexer 코드에서 생성 시 vector size와 `Cosine`을 정하지만, current v12 collection metadata를 이 문서 작업 중 live 조회하진 않았다. v12의 정확한 생성 manifest가 별도로 확인되지 않으면 그 속성을 확정적으로 말하지 않는다.

## Hybrid aggregation

`hybrid_policy.py::_aggregate`는 lexical relation tier(정확, synonym, category)와 claim source tier, 필요 시 mention count, cosine similarity를 한 retrievalScore로 구성한다. 현재 코드의 hybrid score는 대략 `tier*100 + source*10 + quantitative mention contribution + semantic/1000`이며, semanticSimilarity 원값도 별도 반환한다. 이는 Spring의 최종 점수가 아니라 FastAPI 내부 retrieval relevance signal이다. Python에서 restaurant별 aggregate/topK를 만든 뒤 Spring에 전달한다.

Qdrant는 query vector에 대한 근접 point 검색을 수행하지만, business eligibility나 최종 restaurant rank를 확정하지 않는다. Qdrant candidate filter + Python post-validation이 leakage를 막고, Spring도 response IDs를 다시 요청 scope와 대조한다. E2E 기록은 scope violation 0이다.

## Failure contract

`HTTPError` 500/502/503/504 및 timeout/connection 계열은 `RetryableDependencyUnavailable`; 429·나머지 HTTP 오류는 `DependencyUnavailable`로 분류한다. 잘못된 vector 차원·malformed Qdrant JSON/payload도 non-retryable dependency failure다. `/semantic-retrieval`는 graph의 최종 failure route를 sanitized HTTP 503으로 바꾸고, detail/raw provider response는 내보내지 않는다. Empty result는 HTTP 200 empty candidates다.

### 다시 읽기

- `ai/app/main.py::semantic_retrieval`
- `ai/app/semantic_runtime.py::RetrievalRequest`, `analyze`, `SemanticRetrievalService.retrieve`
- `ai/app/hybrid_policy.py::_route_v2`, `_aggregate`
- `ai/app/semantic_embedding_qdrant_pilot.py::embed`
- `ai/tests/test_semantic_runtime.py::test_scope_is_in_qdrant_request_and_response_preserves_evidence`

### 내가 이해했는지 확인

- Embedding하는 것은 query인가 document인가?
- candidate ID filter는 Python slicing과 Qdrant filter 중 어디에 적용되는가?
- `retrievalScore`와 `semanticSimilarity`는 같은 값인가?
- Qdrant가 Spring의 최종 추천 순서를 결정하는가?
