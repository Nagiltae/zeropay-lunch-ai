# LangGraph Recommendation Workflow V1 — Study Notes

## Why this project uses a graph

The FastAPI retrieval request has meaningful routes: generic intent skips vector work; successful retrieval returns evidence; empty results stop without wasting another call; transient provider/network failure gets one bounded retry; and terminal failure preserves Spring's existing fallback boundary. These are explicit workflow states, not merely a list of functions.

## State

State is the request-local snapshot passed between graph nodes. Here it holds the original query, an immutable tuple of Spring-authorized candidate IDs, the deterministic intent, semantic eligibility, retrieval response/status, retry limit/count, fallback reason, categorized errors, timing and trace. It does not hold Restaurant database rows, secrets, raw provider payloads or model output.

## Node

A node performs one named step and returns state updates. `prepare` freezes the request inputs; `intent_analysis` reuses the existing deterministic analyzer; `semantic_retrieval` calls the existing retrieval service; `retrieval_evaluation` classifies the service result; `bounded_retry` increments the one retry counter; `fallback` creates the empty semantic result; and `finalize` records the route and response.

## Edge and conditional edge

An edge says which node runs next. Ordinary edges handle fixed transitions such as prepare → intent. A conditional edge chooses a route from state: intent eligibility selects skip versus retrieval; retrieval evaluation selects success-finalize, retry, or fallback. This keeps routing visible and directly testable.

## Bounded retry

Only the typed transient failure category enters the retry route. The retry uses the same query and same candidate tuple, and the maximum is one retry (two total retrieval attempts). Empty results, HTTP 429/4xx and invalid payloads do not retry. There is no query rewrite or LLM decision about retry.

## One request through the code

1. Spring calls its current intent API, applies hard filters, then sends only the surviving IDs to the current retrieval endpoint.
2. The FastAPI endpoint invokes the compiled graph asynchronously. The graph runs deterministic intent eligibility; `UNKNOWN` goes to skip, so Ollama and Qdrant are untouched.
3. An eligible request calls the existing embedding/Qdrant retrieval service with those same IDs. Qdrant itself filters by the IDs, and Python retains the existing scope validation.
4. A non-empty result finalizes with the existing response schema. Empty returns the existing empty response. A retryable failure gets one retry; terminal failure becomes the existing sanitized 503.
5. Spring remains responsible for candidate selection, ranking, Venue deduplication and max three. FastAPI does not make the final recommendation.

## Responsibility boundary

LangGraph is inside FastAPI. It never reads MySQL or changes Spring's authoritative eligibility rules. The Spring→FastAPI request/response JSON contracts are unchanged. The graph orchestrates the frozen retrieval path; it does not create semantic profiles or vectors and does not write Qdrant.

For the canonical API semantics and graph model, see the [LangGraph Graph API overview](https://docs.langchain.com/oss/python/langgraph/graph-api).
