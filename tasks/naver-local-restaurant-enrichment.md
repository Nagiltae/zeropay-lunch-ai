# Task: Enrich KOMSCO restaurants with NAVER Local

Status: Complete (20-restaurant approved validation completed on 2026-09-18)

## Goal

Match active KOMSCO restaurants in Gangnam-gu against NAVER API HUB Local Search and persist deterministic enrichment results without changing KOMSCO source data.

## In scope

- Spring Boot NAVER Local client, DTOs, matching policy and manual runner
- A separate MySQL table for NAVER enrichment and match audit data
- A new forward-only Flyway migration
- Unit/integration tests that do not require the real NAVER API
- Local and Docker environment-variable wiring and related documentation

## Out of scope

- FastAPI, LLM, Qdrant and NAVER Blog API
- A public HTTP endpoint or scheduler
- Updating KOMSCO-owned fields in `restaurants`
- Running enrichment for all restaurants during this task

## Functional requirements

1. Search with `<restaurant name> <legal dong>` and make at most one fallback search with `<restaurant name> Gangnam-gu`.
2. Evaluate at most five candidates using normalized name, normalized address, WGS84 distance and food category.
3. Classify each restaurant as `MATCHED`, `AMBIGUOUS` or `UNMATCHED` using one centralized policy.
4. Upsert one `NAVER` enrichment row per restaurant.
5. Treat 401/403 as a fatal configuration error; isolate other per-restaurant failures.
6. Keep API execution disabled by default. The initial implementation used a default limit of 20; subsequent validation/incremental behavior is specified by `tasks/naver-local-matching-lifecycle.md`.
7. Never log API credentials or overwrite KOMSCO source fields.

## Data model impact

- Add `restaurant_external_places` through `V5__create_restaurant_external_places.sql`.
- Enforce uniqueness on `(restaurant_id, provider)`.
- Store only service-relevant result fields and match audit information, not raw JSON.

## Acceptance criteria

- The required parsing, normalization, distance, matching, failure and idempotency cases are covered without a real API call.
- `./scripts/check-backend.sh` passes.
- A real 20-restaurant run happens only after the user approves the redacted request shape.

## Validation outcome

- The approved 20-restaurant run produced 14 `MATCHED`, 2 `AMBIGUOUS` and 4 `UNMATCHED` rows with no API failures.
- A diagnostic request showed that the API can return WGS84 coordinates as integers scaled by `10^7`; the parser now accepts both scaled integers and decimal degrees.
- Re-running the same 20 restaurants updated the same 20 `(restaurant_id, NAVER)` rows without duplicates.

## Verification

```bash
./scripts/check-backend.sh
```

Run `./scripts/check-all.sh` because environment and Compose contracts also change.

## Documentation updates

- `docs/architecture.md`
- `docs/database.md`
- `docs/deployment.md`
- `AI_CHANGELOG.md`
