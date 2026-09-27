# Compose Semantic Runtime Audit

Date: 2026-09-26 (Asia/Seoul)

## Finding

The old running Compose `ai` container was stale relative to the repository. Its FastAPI route table contained `/health` but did not contain the internal intent or semantic-retrieval routers, so the semantic POST returned 404 before retrieval could begin. The container had been created roughly 45 hours before this audit; its image creation timestamp was 2026-09-23 18:58 UTC. The image had no source revision labels, so its exact source commit cannot be proven. Current `ai/app/main.py` registers `/internal/v1/intent-analysis`, `/internal/v1/semantic-retrieval`, and `/internal/v1/recommendation-explanations`.

There was also a Compose configuration gap: the default AI service did not explicitly provide the semantic collection or Ollama URL. The service now uses the existing Qdrant service name and the host Ollama endpoint, while preserving semantic runtime OFF by default in Spring.

## Runtime configuration inspected

| Area | Current Compose/runtime value | Evidence |
|---|---|---|
| AI image build | `ai/Dockerfile`, copies repository `app/`; `uvicorn app.main:app` | Compose `ai` build context and Dockerfile |
| FastAPI routes | health, intent-analysis, semantic-retrieval, recommendation-explanations | `ai/app/main.py` |
| Spring → AI | `AI_BASE_URL=http://ai:8001` | `docker-compose.yml`, `application-e2e.yml` |
| Semantic flag | Spring default `false`; isolated E2E explicitly sets `true` | `application.yml`, `docker-compose.yml`, `docker-compose.mvp-e2e.yml` |
| Explanation flag | `false` by default and forced false in isolated E2E | Compose configuration |
| AI → Qdrant | `http://qdrant:6333`, collection `zeropay_semantic_claim_pilot_v12` | Compose service configuration |
| AI → Ollama | `http://host.docker.internal:11434`; host-gateway mapping | Compose service configuration |
| AI health | `/health`, independent of Qdrant/Ollama liveness | `ai/app/main.py` |
| Isolated Qdrant/Ollama | AI container routes through local read-only proxies on 6335/11435 | `docker-compose.mvp-e2e.yml`, `scripts/e2e/read_only_dependency_proxy.py` |

## Rebuild and smoke verification

Rebuilt only the default Compose `ai` image with `docker compose build ai` and recreated only that service using `docker compose up -d --no-deps ai`. The new container became healthy. Its route table and HTTP smoke checks confirmed:

- `GET /health`: 200.
- `POST /internal/v1/intent-analysis`: 200; “떡볶이 먹고 싶어” produced FOOD intent.
- `POST /internal/v1/semantic-retrieval`: 200; candidate 9617 returned hybrid `retrievalScore=320.00047271246`, cosine similarity `0.47271246`, FOOD_TYPE, evidence E003/E011.
- Qdrant collection metadata was read-only: 40 points, 1024-dimensional Cosine vector.

The isolated full-stack Compose rebuild also built the current AI source and passed Browser Chat/SSE requests through the rebuilt image. The full results are in `compose_semantic_fullstack_results.json`.

## Safety and residual limits

- Production/default `AI_SEMANTIC_RUNTIME_ENABLED=false` is unchanged.
- The default development MySQL was not used for fixture or chat writes; browser E2E used a dedicated disposable Compose project/database and its dedicated volume was removed by the harness trap.
- Qdrant was accessed through a read-only proxy for query only; collection point count remained 40.
- Ollama was accessed through an embedding-only proxy. No chat/generation route was allowed.
- No Gemini API request was made.
- The old image’s exact source revision is UNKNOWN because it carried no source metadata; the stale router table and image/container timestamps establish that it did not contain the currently registered endpoints.
