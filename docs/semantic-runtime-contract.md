# Internal semantic runtime pilot

Implemented in the existing FastAPI app and connected to Spring Recommendation
behind `AI_SEMANTIC_RUNTIME_ENABLED` (default `false`). React does not call it
directly; no FastAPI database access or public Spring controller is added.

## Local configuration

```sh
cd ai
QDRANT_SEMANTIC_COLLECTION=zeropay_semantic_claim_pilot_v12 \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 18091
```

Collection must be explicitly configured. `QDRANT_URL` and `OLLAMA_BASE_URL`
retain local defaults. Embedding: qwen3-embedding:0.6b, 1024 dimensions, existing
Cosine collection. No indexing or profile generation. Each dependency has a 3s
socket timeout, no retries; Spring uses existing 2s connect/8s response settings.
JDK HTTP/1.1 avoids Uvicorn h2c incompatibility; redirects are disabled.
Use a private network/loopback. No application-level API authentication added;
public exposure and production deployment are outside this pilot.

## HTTP contracts

GET /health retains `{status:ok,service:ai}` without dependency calls.

POST /internal/v1/intent-analysis accepts `{query}` and returns:
`intent=RESTAURANT_RECOMMENDATION`, `foodTerms`, `diningContexts`, `tasteTraits`,
nullable `maxBudget`, `quantitativeTaste`, `primaryIntent`, `claimTypes`.
Budget is explicit won parsing, not affordability verification. Compound
food/context queries expose both; retrieval preserves offline primary routing.
No LLM is called. Supplied intent is not accepted in v1: bounded deterministic
analysis is cheap and avoids trusting caller-provided routing.

POST /internal/v1/semantic-retrieval accepts:

```json
{"query":"떡볶이 먹고 싶어","candidateRestaurantIds":[9617],"topK":10}
```

Query: nonblank, <=2000 characters. IDs: required positive strict integers,
<=1000. topK: 1..100. Empty scope avoids all dependency calls. Duplicate IDs
are collapsed. Both restaurantId.any and claimType.any are in the Qdrant filter
before Top-K. Response scope/type/evidence are checked again. Bounded overfetch
of 200 is sufficient for this 40-point pilot, not a scale recall guarantee.

Response has `candidates` and `policyVersion=hybrid-v2-capped-count`. Each
candidate contains restaurantId, retrievalScore, semanticSimilarity and
matchedClaims. A winning claim includes claimId, claimType, semanticSimilarity,
matchType (EXACT/SYNONYM/CATEGORY/TRAIT/SEMANTIC), match booleans, mentionCount
and evidenceIds. Retrieval priority (e.g. 320) is not cosine or a final score.
No generated explanation. Missing/unindexed Spring candidates remain intact
in the Spring enrichment adapter.

Errors are JSON `{code,message}`: 400 INVALID_REQUEST; 503
SEMANTIC_RETRIEVAL_UNAVAILABLE for configuration/dependency/malformed payload
or scope violation; 500 INTERNAL_ERROR. No exception details are returned.

## Shared policy and limits

`hybrid_policy.py` is used by both benchmark and runtime. Offline artifacts
are not imported or opened by runtime. Existing policy caps quantitative count
at 999 and preserves food priority/source strength/max aggregation. v12 count
is a claim-level keyword maximum, not guaranteed query-specific. Trait flags
also retain offline behavior (food exact can set traitMatch); matchType favors
EXACT/SYNONYM/CATEGORY first. No ratio or new weight is inferred. These inherited
limitations require offline revalidation before broad activation.

## Spring responsibility

With the opt-in flag enabled, a conditional FastAPI client backs the existing
`AiIntentAnalysisClient` seam and `SemanticCandidateEnricher`. FastAPI intent is
mapped to the existing `AnalyzedIntent`; Spring preferences, allergies and meal
history remain authoritative. Intent failure uses the existing deterministic
analyzer when fallback is enabled.

Existing filters: repository active/recommendation-ready/ELIGIBLE/ZeroPay/legal
dong/operating schedules/closed periods; service budget/disliked categories/
recent meals/active confirmed Venue. There is no distance/500m filter. Spring
passes the complete remaining IDs after these hard filters and before final
Venue deduplication and max-3. The Qdrant query has restaurant and claim type
payload filters; Java validates that returned IDs remain in scope. Unindexed
restaurants remain. On configured retrieval fallback, all Spring candidates
remain. Semantic cosine is clamped to [0,1] and only breaks ties in the existing
deterministic score; internal `retrievalScore` is never added to Spring ranking.
Spring retains Venue deduplication, final ranking and max 3.

## Recommendation explanation (opt-in with semantic runtime)

After Spring has completed deterministic ranking, confirmed-active Venue
deduplication and the max-three limit, it makes at most one grouped call to
`POST /internal/v1/recommendation-explanations`. The request contains the
selected IDs, approved matched Claim text/Evidence IDs and deterministic facts.
FastAPI may perform one supplemental Qdrant lookup, filtered by these final
Restaurant IDs and only the Claim Types implied by the query (including
secondary dining/taste intent). It never changes retrieval ranking. Restaurant
labels and deterministic operational facts are stripped before the LLM prompt;
the LLM sees only query, opaque IDs and Python-generated Safe Facts. Safe Facts
are emitted only when the query term and the claim's explicit wording agree.
The LLM does not receive raw Claim text. FastAPI has no MySQL access and cannot
select, remove or reorder restaurants.
The response must preserve exactly the same IDs and order; Spring changes only
the existing `reason` field. The response includes `availableEvidenceIds` from
the scoped Safe Fact construction and `usedEvidenceIds`; Spring checks the
latter is a subset of the former (supplemental IDs need not have appeared in
its original retrieval response). Invalid, timed-out or unavailable explanation
responses preserve Spring's original reasons. Unindexed restaurants receive
deterministic fallback text.

The contract permits 1–3 restaurants and up to 10 claims each. Output is a
single Korean sentence (<=320 characters) per restaurant, with supplied
Evidence IDs. FastAPI checks schema, ID/order, evidence subset, length and
known unsupported assertions; this is a bounded guard, not a semantic truth
verifier. A prior pilot exposed ZeroPay wording confusion. The LLM is not given
operational flags, restaurant names, prices or budget facts; forbidden
payment/location/popularity/price language and semantic markers absent from the
Safe Facts cause deterministic fallback. Spring reason text remains
authoritative for operational facts. Fallback sentences are built from Safe
Facts and keep the corresponding Evidence IDs.
There is no retry. Semantic intent/retrieval is controlled by
`AI_SEMANTIC_RUNTIME_ENABLED` (default false). Explanation always has a
deterministic Safe Fact path. Qwen is attempted only when both Spring's
`AI_LLM_EXPLANATION_ENABLED` request opt-in and FastAPI's same server-side
setting are true; both default false. Thus the MVP can enable semantic
retrieval while keeping Ollama explanation calls at zero. The LLM path retains
the configured Qwen model, a bounded 24-second
`RECOMMENDATION_EXPLANATION_TIMEOUT_SECONDS` (1–60) and 256 output tokens.
Spring's `AI_EXPLANATION_RESPONSE_TIMEOUT` defaults to 27 seconds.

If LLM explanation is true while semantic runtime is false, the explanation
client is not registered and the setting has no effect; ordinary Spring
recommendation reasons remain in use. The supported experimental combination
is semantic=true, LLM=true; local MVP validation uses semantic=true, LLM=false.

## Opt-in live tests

Python: SEMANTIC_RUNTIME_LIVE=1 pytest tests/test_semantic_runtime_live.py.
Java: FASTAPI_CONTRACT_URL=http://127.0.0.1:18091 ./gradlew test --tests
'*FastApiSemanticLiveContractTests'. Both reuse v12 without writes. Default
Harness skips live tests; JDK ephemeral HTTP server covers timeout and errors.
