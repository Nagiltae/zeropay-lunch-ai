# LangGraph Recommendation Workflow V1 — Audit

## Existing request path

1. Spring `RecommendationContextService` invokes `AiIntentAnalyzer`. With the opt-in FastAPI adapter, `FastApiSemanticClient.analyze()` calls `POST /internal/v1/intent-analysis`; FastAPI `main.intent_analysis()` calls deterministic `semantic_runtime.analyze()`.
2. Spring applies its authoritative service-area, active/serving, ZeroPay, hours, budget, preference, recent-meal and venue rules. Only surviving IDs are passed to `SemanticCandidateEnricher`.
3. `FastApiSemanticClient.retrieve()` calls `POST /internal/v1/semantic-retrieval` with the original query and those candidate IDs. FastAPI `SemanticRetrievalService.retrieve()` embeds the query with Ollama and calls Qdrant using a query-level `restaurantId` and `claimType` filter. It validates every returned point against the candidate scope before aggregation.
4. FastAPI returns retrieval scores and matched evidence. Spring attaches signals to the original hard-filtered set, applies the established ranking, deduplicates Venue, and returns at most three.

The optional recommendation-explanations endpoint is a separate post-ranking path and is not part of this graph.

## Audit questions

1. Spring calls `/internal/v1/intent-analysis` and `/internal/v1/semantic-retrieval` as separate requests. The retrieval request remains candidate-scoped.
2. Intent is deterministic `analyze()` in `semantic_runtime.py`. Retrieval is `SemanticRetrievalService.retrieve()`, backed by `embed()` and `_request()`; hybrid aggregation and payload validation remain in their existing modules.
3. `primaryIntent == UNKNOWN` yields no semantic results and makes no embedding or Qdrant call. Generic input is not reinterpreted by a new model.
4. Before this change, retrieval dependency failures were sanitized to HTTP 503. Spring's `SemanticCandidateEnricher` catches that as `AiUnavailableException`; when configured, it retains the same candidates with no semantic signals so deterministic ranking remains in force. A valid empty retrieval is HTTP 200 with an empty candidate list.
5. The smallest boundary is inside the existing `/internal/v1/semantic-retrieval` handler. Its request and response schemas remain unchanged; the graph wraps the existing intent and retrieval service, and the handler preserves the existing 503 failure boundary.
6. No retry existed in the urllib Ollama/Qdrant client. Spring's `AI_MAX_ATTEMPTS` defaults to one (no extra retry). The graph is the sole new retry owner: one retry maximum for classified transient transport errors or HTTP 500/502/503/504. HTTP 429, 4xx, malformed payload/schema and other deterministic failures are not retried.

## Scope and invariants

- Spring's hard-filter candidate list is copied into a tuple in graph state. Each retrieval call receives the same IDs and query; no graph node can add/remove candidates or rewrite the query.
- The Qdrant query-level candidate filter and existing response leakage validation are unchanged.
- Source Scope Guard, profile generation, embedding/indexing and Qdrant write paths are not imported or called by the graph.
- Workflow trace and categorized, non-sensitive error codes stay in sanitized FastAPI logs/state. They do not add fields to the Spring-facing response.
- Graph compile is cached once per process through the FastAPI dependency provider.

## Dependency

Added the standalone `langgraph` package constraint `>=1.0,<2`; Poetry resolved 1.2.12 in the current lock. No LangChain integration/model package was added directly. The graph uses the documented `StateGraph`, node, edge, conditional edge, compile and `ainvoke` API.
