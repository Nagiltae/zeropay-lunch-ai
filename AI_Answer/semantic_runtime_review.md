# Semantic Recommendation Vertical Slice Review

Date: 2026-09-26

## Executive result

Spring previously treated semantic similarity as a tie-breaker after deterministic score. The implementation now gives FastAPI's pre-existing hybrid `retrievalScore` primary ordering ownership whenever semantic matches exist; cosine and existing deterministic score are subsequent tie-breakers. No semantic keyword scoring was added to Spring. In a nine-query, evidence-labeled fixed-clock replay, all nine top-1 and top-3 lists changed; Hit@3 rose from 4/9 to 9/9 and P@3 from 0.185 to 0.667 under the frozen labels.

This is a bounded retrieval/ranking vertical slice, not a full user Chat/SSE E2E. Actual current clock had zero open Restaurant overlap with v12, and the running Compose AI image is stale (semantic endpoint 404). The local source FastAPI process and actual Ollama/Qdrant were used for the formal query batch; Spring ordering/fallback contracts were exercised through automated tests.

## Runtime architecture and responsibility

Spring remains owner of the Spring API/SSE, MySQL, serving hard filters, recent meal/Venue exclusions, final ordering, confirmed Venue dedup, max 3, and safe fallback. FastAPI owns deterministic query routing and candidate-scoped semantic retrieval. Ollama `qwen3-embedding:0.6b` creates query embeddings; Qdrant v12 is read-only. No Gemini or generative LLM was used.

Chat flow source: `ChatController` → `ChatStreamService` → `RestaurantRecommendationService` → persist and `recommendations`/`completed` SSE events → React `useChatStream`/`MessageList`. Public Chat/SSE was not called because it persists messages.

## Audit findings

* Semantic API exists in source at `/internal/v1/intent-analysis` and `/internal/v1/semantic-retrieval`.
* Original query is passed through Spring semantic enricher to FastAPI and embedded as-is.
* Spring sends only post-hard-filter, post-recent-Venue-exclusion candidate IDs.
* Qdrant query filter applies candidate restaurant IDs and claim types before retrieval; response payload and Spring client verify scope again.
* The actual current Qdrant vector config is 1024-dimensional Cosine, 40 points over 10 Restaurant IDs.
* Raw cosine observed: approximately 0.2603–0.5869. Existing FastAPI hybrid retrievalScore observed: approximately 10.00026–320.00056.
* Before the change, deterministic Spring score was primary and raw cosine was only a tie-breaker. After the change, the existing FastAPI hybrid retrievalScore is the primary AI ordering signal, then raw cosine, then deterministic Spring ordering.
* Generic `UNKNOWN` intent now short-circuits before embedding/Qdrant. Known secondary dining/taste/venue intent types are retained even when FOOD is primary.
* AI-off and dependency-failure behavior remains deterministic. Hard filters precede semantic retrieval; AI cannot reintroduce an excluded ID. Spring Venue dedup and max3 remain after final ranking.

## Qdrant and MySQL overlap

Qdrant v12 has 40 points across IDs `9567, 9568, 9569, 9570, 9571, 9574, 9580, 9590, 9617, 9731`. Details and per-claim-type counts are in `semantic_candidate_overlap.json`.

MySQL `zeropay_lunch` contains 517 Restaurants. The legacy `recommendation_ready=true` hard-filter intersection is 0. The verified-detail service's source predicates return 32 before current OPEN evaluation. At the fixed Thursday 18:00 reference clock, 26 source candidates remain and 7 overlap v12. At the actual audit clock (Saturday 01:28 KST), the indexed overlap OPEN count is 0. This is why formal ranking metrics use the explicitly declared deterministic reference clock and must not be represented as a claim that the candidates are open now.

The paired baseline/replay has no explicit/default budget, preferred/disliked category, or recent meals; all 26 serving rows have null category and average_price, deterministic score 50, and stable Restaurant ID tie ordering. Six verified source-hour rows are UNKNOWN/unparseable for the reference clock and were not put in scope. No unknown/closed restaurant was used to inflate the scope.

## Frozen benchmark and results

Ground truth was frozen in `semantic_ranking_benchmark.json` before the corrected-scope formal batch. One initial contract smoke query and an exploratory batch against the pre-hours 32-row set occurred before the corrected freeze; those 22 calls are disclosed and excluded. The final nine query labels come from Qdrant claim/evidence payloads, not returned ranks. After the final secondary-intent code change, the nine-query formal set was executed and then repeated once as a source repeatability check. Total post-freeze retrieval/embedding requests: 18 (9 metric run + 9 repeatability checks); metrics below use only the first final-code nine-query run.

| Metric | Semantic OFF | Semantic ON |
|---|---:|---:|
| Precision@3 | 0.185 | 0.667 |
| Hit@3 | 0.444 | 1.000 |
| Mean reciprocal rank | 0.273 | 0.944 |
| Mean first relevant rank | 4.889 | 1.111 |
| Query top-1 changed | — | 9/9 |
| Query top-3 changed | — | 9/9 |

Semantic ON top-1 was an expected evidence-backed Restaurant for all nine frozen queries. Food exact-match claims correctly outranked broad vector neighbors, while context/taste/venue queries were ordered by their existing hybrid relation/source and query-vector signals. There are still non-relevant items in some top-3 positions; P@3 is not perfect.

Ground Truth caveat: for `FOOD-02`, Qdrant returned Restaurant 9569 with evidence `E012`, whose source menu is `김밥추가`. The frozen expected set only contains 9617. Labels were not edited after retrieval; the result is therefore conservative and signals a possible frozen multi-label omission. No score threshold or query-specific tuning was applied.

## Safety and invariant checks

* Hard-filter violations in the replay scope: 0.
* Qdrant candidate scope leakage: 0. FastAPI query filter and Spring response validation both constrain IDs.
* Evidence trace: 100% of returned candidates have non-empty evidence IDs (47/47 returned candidate records over the nine final-code queries). The friendly-service query also retrieves TASTE claim-type candidates as a secondary intent; its top 3 remained unchanged.
* Duplicate Restaurant per retrieval response: 0. Confirmed ACTIVE Venue associations among the 26 source candidates: 0; Spring's Venue dedup regression tests still pass.
* Max recommendations: 3, unchanged.
* FastAPI failure fallback: existing tests pass; candidates remain and deterministic order is used.
* Explicit budget remains fail-closed; existing serving readiness regression tests pass.
* MySQL writes 0; Qdrant writes 0; Flyway migrations 0; Gemini API calls 0; LLM explanation generation calls 0.

Evidence trace confirms IDs are resolvable, not that every previously generated natural-language profile claim is semantically perfect. The v12 profile overclaim concern remains a separate data-quality blocker; the benchmark surfaced false-positive top-3 neighbors rather than hiding them.

## Code change summary

1. `RestaurantRecommendationService`: when semantic results exist, sort by existing FastAPI `retrievalScore` first, raw cosine second, deterministic score/price/ID last. No candidate creation/removal or new Spring keyword scoring. With no semantic signal, preserve old deterministic sort.
2. `SemanticRetrievalService`: skip embedding/Qdrant for `UNKNOWN` intent, and union already-recognized secondary dining/taste/venue claim types into retrieval filters for composite queries.
3. Tests: prove semantic/hybrid relevance can outrank deterministic preference score; unknown/generic queries skip retrieval; composite FOOD+dining filters include both types.

## Tests and harness

* Targeted AI tests: PASS, 23 tests (`tests/test_semantic_runtime.py`).
* `./scripts/check-ai.sh`: PASS, 274 passed, 1 skipped; one dependency deprecation warning.
* Targeted backend ranking/client tests: PASS.
* `./scripts/check-backend.sh`: PASS (Gradle build/tests).
* Live Spring→current-source FastAPI/Ollama/Qdrant contract test with mocked MySQL: PASS (`RecommendationFastApiLiveFlowTests`).
* Integration harness: NOT RUN; it writes test users, conversations, restaurant fixtures into the shared Compose MySQL.
* Frontend harness: NOT RUN; frontend/SSE contract was not changed and no browser request was made.
* `git diff --check`: recorded separately after artifact generation.

## Runtime/collection and flags

`AI_SEMANTIC_RUNTIME_ENABLED` remains default false. `AI_LLM_EXPLANATION_ENABLED` remains default false. The running Compose AI image returned 404 for semantic retrieval, while repository source has the endpoint; formal requests therefore used a temporary local current-source FastAPI process on port 8002 connected to existing Ollama/Qdrant. No Compose rebuild was done. Rebuild/verify the image before any flag-on full-stack test.

## Final assessment

`SEMANTIC RUNTIME = READY_FOR_DATA_EXPANSION` for the bounded source-level retrieval/ranking contract: candidate scoping is enforced, ranking changes materially, evidence IDs trace, and hard-filter/fallback behavior remains covered. This is not production rollout approval. Actual-clock open overlap was zero, runtime default remains OFF, profile quality/coverage is small, and the current Compose AI image is stale. Next: rebuild current AI image in an isolated environment; run fixed-clock/isolated-database Spring candidate-to-FastAPI test; review v12 false-positive claims and expand only approved evidence-backed profiles. Do not enable production default based on this pilot alone.

## Required answers

1. Before: deterministic score ranked first; cosine only tie-broke. Now: FastAPI hybrid retrievalScore is the primary AI ordering signal, raw cosine the next signal.
2. Yes, semantic/hybrid relevance changed top-1 and top-3 for 9/9 benchmark queries; ranking effect is measured, not assumed.
3. No Spring rules for 혼밥/매운맛/분위기 were added.
4. No hard-filtered Restaurant was restored (0).
5. No Qdrant result escaped `candidateRestaurantIds` (0).
6. Yes; all nine top-1 ranks moved to frozen evidence-backed targets, though top-3 precision remains 0.667 and one GT label may be incomplete.
7. Not identical: current fixed-clock replay changed top1/top3 in all queries. Generic UNKNOWN queries now skip semantic retrieval and retain deterministic fallback.
8. Enough to prove the scoped retrieval-to-ordering mechanism on a tiny pilot, not enough to establish production recommendation quality or broad coverage.
9. Next priority is profile/evidence quality and coverage plus isolated full-stack verification; no further Spring rank framework is indicated by this bounded test.
10. Gemini API calls: 0.
