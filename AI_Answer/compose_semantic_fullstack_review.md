# Compose Semantic Runtime Full-Stack Review

Date: 2026-09-26 (Asia/Seoul)

## Result

**COMPOSE SEMANTIC RUNTIME = READY_FOR_PROFILE_QUALITY**

The rebuilt Compose FastAPI is reachable from Spring and completed the isolated Browser → React → Spring Chat/SSE → FastAPI → embedding-only Ollama → read-only Qdrant → Spring ranking flow. Four frozen query cases returned their evidence-backed expected top result, with no scope leakage or hard-filter resurrection. OFF and unavailable-AI fallback paths also passed.

## Runtime path and isolation

The default Compose `ai` image was rebuilt from current `ai/` source and only that default service was recreated. For the full-stack runs, `scripts/check-mvp-e2e.sh` created a unique Compose project with its own disposable MySQL database `zeropay_lunch_mvp_e2e`, backend, frontend, and AI service. The test profile injected fixed time `2026-09-24T09:00:00Z` (= 2026-09-24 18:00 KST). No test user or conversation was written to the shared development database.

The isolated AI reached Qdrant and Ollama through guarded host proxies:

```text
isolated Spring → ai:8001
isolated FastAPI → host read-only Qdrant proxy :6335 → existing v12 collection
isolated FastAPI → host embedding-only Ollama proxy :11435 → qwen3-embedding:0.6b
```

The default Compose topology uses `qdrant:6333` and `host.docker.internal:11434` respectively. The Spring default semantic flag remains OFF; only the isolated E2E profile enabled semantic runtime. Explanation remained OFF throughout.

## ON run: frozen Browser Chat/SSE queries

Each browser query used six hard-filtered candidate IDs `[9568, 9569, 9570, 9571, 9580, 9617]`. Restaurant 9620, outside the required legal-dong scope, was excluded. The browser observed the `recommendations` SSE event, rendered its reason, and verified the displayed recommendation payload matched the SSE payload.

| Query | Evidence-backed expected top | Spring final IDs (max 3) | Outcome |
|---|---:|---|---|
| 떡볶이 먹고 싶어 | 9617 | 9617, 9568, 9571 | PASS |
| 피자 먹고 싶어 | 9571 | 9571, 9580, 9569 | PASS |
| 혼밥하기 좋은 곳 | 9568 | 9568, 9617, 9569 | PASS |
| 단체 모임하기 좋은 곳 | 9569 | 9569, 9568, 9570 | PASS |

For these same four queries, supplemental direct requests to the rebuilt FastAPI captured its hybrid retrieval score and matched claims/evidence. Examples: the exact 떡볶이 FOOD_TYPE match for 9617 had `retrievalScore=320.00047271246`; the exact pizza match for 9571 had `320.000562562`. Spring’s final top result matched each frozen expected restaurant. These direct diagnostic calls are distinguished from the four browser-triggered semantic requests in the JSON artifact.

## Runtime and safety counts

| Check | Result |
|---|---:|
| Browser Chat/SSE queries (ON) | 4/4 PASS |
| Browser-triggered intent requests | 4 |
| Browser-triggered semantic retrieval requests | 4 |
| Supplemental direct FastAPI semantic requests | 4 |
| Total semantic endpoint requests in ON run | 8 |
| Embedding proxy calls (browser + diagnostics) | 12 |
| Read-only Qdrant queries (browser + diagnostics) | 12 |
| Candidate-scope leakage | 0 |
| Hard-filter violation/resurrection | 0 |
| Recommendations per query | 3 (never above max 3) |
| LLM generation / explanation calls | 0 |
| Shared/development MySQL writes | 0 |
| Isolated MySQL writes | 7 fixture restaurants, 1 test user, 1 conversation, 8 chat messages, 12 recommendations |
| Qdrant writes | 0 |
| Qdrant v12 point count | 40 before / 40 after |
| Gemini API calls | 0 |

The isolated fixture had `recommendation_ready=false` for its verified KOMSCO candidates, so this run exercised the current verified-serving-candidate path rather than relying on the legacy flag. The negative legal-dong fixture was not returned.

## OFF and failure fallback

- Semantic OFF: separate isolated Browser run passed all four queries. Intent/semantic calls, embeddings, Qdrant queries, and generation calls were all zero; stable deterministic ordering was `[9617, 9568, 9569]` for each query.
- AI unavailable: the harness stopped only the isolated AI container before browser requests. All four Chat/SSE requests still returned deterministic recommendations in the same stable order, with no semantic, embedding, Qdrant, or generation calls.
- Neither path changed the production/default feature flag.

## Previous 404 and image rebuild

The old default AI container had only the health route registered; intent and semantic routers present in current `ai/app/main.py` were missing. Its container/image timestamps were roughly 45 hours old / 2026-09-23 18:58 UTC, and it had no source revision labels. The defensible cause is a stale image, not a source endpoint omission. Its exact source commit cannot be established. Compose also lacked explicit collection and Ollama runtime settings; these are now configured. After rebuilding, health, intent, and semantic routes returned successful responses; the isolated Spring browser requests used the rebuilt service.

## Tests and cleanup

- `./scripts/check-ai.sh`: PASS (274 passed, 1 skipped; one deprecation warning).
- `./scripts/check-backend.sh`: PASS.
- `./scripts/check-frontend.sh`: PASS (production build; 12 tests passed).
- Isolated Browser E2E: PASS for semantic ON, semantic OFF, and AI-unavailable fallback.
- `git diff --check`: PASS.
- Shared-DB integration harness: NOT_RUN; isolated E2E replaced it for this verification to avoid writes to shared development data.
- Chat/SSE was exercised in an isolated Browser stack; no public/shared-data Chat E2E was run.
- The isolated Compose project, its dedicated MySQL volume, and the two local guard proxy processes were cleaned up. Existing default MySQL/Qdrant volumes and services were not removed. The rebuilt default AI service remains healthy, with semantic runtime still OFF by default.

## Remaining boundary

This verifies runtime wiring and semantic ordering against the existing 40-point pilot collection. It does not validate or improve Semantic Profile claim quality, expand the index, or imply that the data is broad enough for production coverage. The next scoped phase can address evidence-grounded profile quality; it should retain the same read-only collection/write safety and should not turn the default feature flag on as part of this result.
