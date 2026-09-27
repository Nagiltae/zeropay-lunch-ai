# Semantic Runtime — Current State Audit

Audit date: 2026-09-26 (Asia/Seoul)

## Actual request flow

```text
React chat composer
  → Spring ChatController / ChatStreamService
  → RecommendationContextService
      → Spring fallback intent analysis, or FastApiIntentAnalysisAdapter when opted in
  → RestaurantRecommendationService
      → legacy repository open query OR VerifiedNaverServingCandidateService
      → Spring hard filters and recent-Venue exclusion
      → SemanticCandidateEnricher(message, hardFilteredRestaurantIds)
          → FastAPI /internal/v1/semantic-retrieval
          → Ollama qwen3-embedding:0.6b query embedding
          → Qdrant query with restaurantId AND claimType filters
      → Spring final sort
      → confirmed ACTIVE Venue dedup
      → max 3
      → optional RecommendationExplanationEnricher
  → ChatStreamService persists response and emits recommendations/completed SSE events
  → React useChatStream → MessageList recommendation cards
```

The public Chat/SSE request itself was not invoked in this audit because its service path persists messages. The live Spring/FastAPI contract test used mocked MySQL repository reads.

## Ownership and filters

Spring owns candidate eligibility and the final order. The legacy SQL candidate query requires `active`, `recommendation_ready`, `ELIGIBLE`, ZeroPay, target legal dong, open schedule, and no recurring/date-period closure. The KOMSCO verified-detail path (`VerifiedNaverServingCandidateService`) does not gate on the stale legacy readiness boolean; it requires verified numeric NAVER identity/unique ownership, current successful menu and hours lifecycle, active menu/hour source rows, target area, ZeroPay, and OPEN hours. An explicit budget is fail-closed until approved menu budget classifications exist. Spring applies the remaining ZeroPay/budget/category/dislike/recent-meal filters and removes recently eaten confirmed Venue IDs before semantic retrieval.

Semantic retrieval receives only those final hard-filtered IDs. FastAPI sends both `restaurantId match any candidateRestaurantIds` and `claimType match any analyzed claimTypes` in the Qdrant query filter; it then validates payload scope again. Spring's client/enricher independently rejects response IDs outside its candidate scope and preserves every Spring candidate when retrieval is unavailable.

## Intent and retrieval contract

* `POST /internal/v1/intent-analysis`: deterministic Python router (`app.semantic_runtime.analyze` / `app.hybrid_policy._route_v2`), not an LLM. Returns intent, food terms, dining contexts, taste traits, budget, primary intent, and claim types.
* `POST /internal/v1/semantic-retrieval`: original user query, candidateRestaurantIds, and topK. Embeds the original query with Ollama `qwen3-embedding:0.6b`, then issues a read-only Qdrant query.
* The Qdrant query-level filter is applied before retrieval, not only after the response. Response candidates contain restaurantId, retrievalScore, raw vector semanticSimilarity, and a matched claim with claimType, relation flags, claim text, and evidence IDs.
* Raw cosine values observed in the formal run were approximately 0.2603–0.5869. Qdrant collection uses Cosine; Spring clamps semanticSimilarity to `[0,1]` before using it as a secondary comparator signal.
* Existing `hybrid_policy._aggregate` computes `retrievalScore = match-tier * 100 + source-strength * 10 + semanticSimilarity / 1000` (with the existing quantitative-count branch). The tier/source constants predate this task and live in FastAPI, not Spring.
* An `UNKNOWN` primary intent now returns an empty retrieval result before embedding/Qdrant. Existing recognized secondary dining/taste/venue signals are unioned into claimTypes, so a food-primary composite request can still retrieve its secondary evidence.

## Ranking before and after this task

Before: `RestaurantRecommendationService` sorted by Spring deterministic score first; raw semanticSimilarity only broke deterministic-score ties. For the live KOMSCO cohort the deterministic fields are null, so many rows tie and stable ID order dominates.

After: when the FastAPI response has at least one semantic candidate, Spring sorts by the existing FastAPI hybrid retrievalScore first, raw cosine second, then the unchanged Spring deterministic order. This lets evidence match tier and semantic retrieval relevance alter the actual result order without adding Spring keyword rules or new Spring weights. If no semantic signal exists or FastAPI fails, the prior deterministic ordering remains.

The direct cosine is not used as the sole primary score: live probe output showed a larger cosine for a weak/unrelated FOOD claim than for the exact 떡볶이 menu claim. The existing hybrid score preserves exact/source evidence precedence while its cosine component orders candidates within those existing relation tiers. Spring still performs the final sort, Venue dedup, and max-three limit.

## Current data and read-only overlap

* MySQL database checked: `zeropay_lunch`; Restaurant total 517.
* Current legacy recommendation-ready hard-filter population: 0 KOMSCO rows.
* Verified source-hour/menu base query before current-time OPEN evaluation: 32 rows.
* At deterministic reference clock `2026-09-24 18:00 KST`, source-hour policy yields 26 candidate IDs; 7 intersect v12: `9568, 9569, 9570, 9571, 9574, 9580, 9617`.
* At actual audit clock `2026-09-26 01:28 KST`, all Qdrant-overlap candidates are CLOSED or UNKNOWN; current open overlap is 0. This is time-dependent and not an invariant coverage count.
* Qdrant v12 read-only metadata: 40 points, 10 Restaurants, 1024 dimensions, Cosine, embedding model `qwen3-embedding:0.6b`. Claim point distribution: FOOD_MENTION 16, TASTE 7, MENU_CHARACTERISTIC 5, FOOD_TYPE 4, DINING_CONTEXT 4, VENUE_CHARACTERISTIC 4.
* The 10 indexed IDs are recorded in `semantic_candidate_overlap.json`; indexed ID 9731 is outside the current verified-serving base population.

## Flags and failure behavior

`AI_SEMANTIC_RUNTIME_ENABLED` defaults to false in Spring configuration and Compose. When false, FastAPI intent/retrieval clients are not registered and deterministic Spring recommendation continues. When true, FastAPI intent analysis and candidate-scoped semantic retrieval are enabled. `AI_LLM_EXPLANATION_ENABLED` defaults false; the explanation stage remains deterministic and does not call Qwen generation. FastAPI failure with fallback enabled leaves Spring candidates intact and returns to deterministic order.

## Runtime environment discrepancy

The running Compose AI container returned HTTP 404 for `/internal/v1/semantic-retrieval`, despite the current repository source defining the endpoint. Formal retrieval used the current `ai/app` source in a temporary host process on port 8002 against the existing local Ollama and Qdrant services. A Spring live-contract test passed against that process with mocked MySQL. The running Compose image should be rebuilt before enabling the semantic flag; no container rebuild or public Chat/SSE run was done here.

## Explanation and UI

`RecommendationExplanationEnricher` runs only after Spring selected/deduplicated/limited results. LLM explanation is flag-controlled and off by default. The current AI recommendation workflow has no generative LLM in the runtime path: the Python intent router is deterministic, embeddings are local Ollama, and the reason path is deterministic when LLM explanation is off. React consumes the existing `recommendations` SSE event and displays `items[].reason` in `MessageList`.

## Side effects

MySQL: SELECT only; writes 0. Qdrant: collection metadata, scroll, and query only; writes 0. Gemini requests: 0. Semantic Profile/embedding generation: 0. Query embedding was used only for bounded retrieval requests. No production/default flag was enabled.
