# Recommendation Ready Reconciliation Review

## Outcome

**STOP AFTER AUDIT — no reconciliation performed.** The audit confirms a mixed cause: `recommendation_ready` has no promotion/recalculation owner (CASE 2), while the actual KOMSCO serving projection and Spring schedule data are also missing (CASE 3). The 26 AI Profile-READY restaurants are not yet Spring-serving-ready.

See [recommendation_ready_audit.md](recommendation_ready_audit.md) for source/code details and the full 26-row comparison; machine-readable results are in [recommendation_ready_audit.json](recommendation_ready_audit.json).

## Required findings

1. **Definition:** `recommendation_ready` is an independent required Spring candidate gate. It is not an AI Profile readiness flag.
2. **Owner:** KOMSCO entity construction initializes false. No production service, Detail persistence, scheduler, admin endpoint, or batch updates it. Later KOMSCO synchronization does not change it.
3. **Why four:** all four true rows are sample/integration fixtures. Three are outside the target legal dong; the only in-scope one, ID 1004, is an integration fixture.
4. **Backfill separation:** the completed 27-restaurant Detail Backfill only wrote NAVER Detail/Lifecycle tables. It explicitly left Restaurant master and Spring schedule state unchanged; Qwen/Profile/Embedding/Qdrant writes were zero.
5. **Strict-ready comparison:** live shared-policy SELECT audit finds 26. All 26 are active/eligible/Nonhyeon/ZeroPay, have verified numeric NAVER identity and successful fresh Detail sections, priced menu evidence, and source-grounded structured hours. All remain `recommendation_ready=false`, have null Spring category/representative menu/average price, and have zero Spring schedules.
6. **Legacy data:** current row counts are NAVER menus 325 restaurants, review keywords 344, business hours 360, Lifecycle 35. Legacy content rows are not equivalent to current verified Lifecycle.
7. **Cases:** mixed CASE 2 + CASE 3; CASE 1 alone is rejected as incomplete.
8. **Modification:** none. Hard-coded ID updates or bulk flag toggles would be unsafe and would not satisfy the serving query.
9. **Before/after:** `recommendation_ready` stayed at 4 overall; in-scope ACTIVE+ELIGIBLE+Nonhyeon+ZeroPay intersection stayed at 1 (fixture 1004). No after snapshot was needed because no write occurred.
10. **Serving implication:** current KOMSCO rows passing the repository's static serving gate: 0. Strict Profile readiness alone does not make a restaurant recommendable.
11. **Tests/Harness:** NOT_RUN because there were no code changes; DB-mutating integration checks were not appropriate for a read-only audit. DB SELECT and source/artifact inspection completed. No claim of test PASS is made.
12. **Next step:** specify and test the serving-data projection (category/menu/price/schedules/closures), then dry-run a bounded reconciliation with a guarded write path.

## User answers

- **Why only four after Backfill?** The Backfill did not own Spring serving state; no code promotes the flag when Detail becomes complete.
- **Why were those four true?** They are seeded sample/integration restaurants, not KOMSCO rows promoted from collected Detail.
- **Why are 26 different?** They meet the AI evidence/profile gate, but not the separate Spring serving data/schedule contract.
- **How many real candidates now?** Zero KOMSCO candidates pass the current serving gate; the one static in-scope match is a synthetic integration fixture.
- **Data or logic?** Both: missing serving projection plus missing flag lifecycle. Not merely a stale boolean.
- **What changed?** Only audit findings were recorded. No source, DB, schedule, or recommendation behavior changed.

## Safety and verification

- MySQL: SELECT-only; DB writes 0.
- Qdrant: not accessed or changed.
- Crawls, model calls, Profile generation, Embedding: 0.
- Git add/commit/push/reset/clean: not run.
- Existing working tree preserved.
- Test suites: NOT_RUN. `git diff --check`: passed for the tracked working-tree diff; JSON syntax validation passed for the new machine-readable audit.
