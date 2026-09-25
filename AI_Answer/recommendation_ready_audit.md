# Recommendation Ready Audit (Phase A, Read-only)

**Audit date:** 2026-09-25  
**Decision:** `MIXED: CASE 2 + CASE 3`  
**Phase B:** `STOP AFTER AUDIT` — no code or DB writes.

## Executive summary

`recommendation_ready` is a Spring serving-query gate, but the repository has no service, importer, Detail persistence path, scheduler, admin endpoint, or batch that promotes it when data becomes ready. New KOMSCO entities explicitly start `false`. The four current `true` rows are sample/integration fixtures, not KOMSCO restaurants.

The recent Detail Backfill correctly updated only NAVER Detail and Lifecycle data. It did not update the separate Spring-serving projection. All 26 restaurants that pass the current Semantic Profile readiness policy are still `recommendation_ready=false`; they also have no Spring `restaurant_schedules` and have null `category`, `representative_menu`, and `average_price`. Therefore this is not safely fixed by toggling a flag. The serving projection and an explicit promotion contract are missing.

No recommendation-ready values, Restaurant master fields, schedules, or other DB rows were changed in this audit.

## 1. `recommendation_ready`: definition and owner

### Schema and defaults

- `V4__add_komsco_restaurant_source_fields.sql` adds `recommendation_ready BOOLEAN NOT NULL DEFAULT TRUE`. Current `information_schema` confirms non-null boolean/tinyint and default `1`.
- `V17__add_korean_schema_comments.sql` retains default `TRUE` and comments it as “추천 데이터 구축 완료 여부.”
- `V7__add_restaurant_recommendation_eligibility.sql` changes eligibility for sample data only; it does not calculate this flag.
- `Restaurant.fromExternalSource(...)` explicitly sets `recommendationReady=false` for KOMSCO imports.
- `RestaurantImportWriter`'s later synchronization calls `applyExternalSource`, which does not touch `recommendationReady`. No setter or update method for this field exists.
- Search across source, migrations, API/service, importer, scheduler, and fixtures found no production promotion/recalculation owner. Test/sample fixtures inherit the schema default or explicitly include `true`.

### Runtime meaning

`RestaurantJpaRepository.findOpenRestaurants(...)` requires the flag to be true before a row can become a candidate. The same query also requires `active`, `ELIGIBLE`, ZeroPay, legal dong `11680108`, a matching operating day/time, and absence of a closed day/period. `RestaurantRecommendationService` then applies budget/category/dislike/recent-meal rules, optional semantic enrichment as a tie-break signal, confirmed active Venue dedup, and a maximum of three.

Thus the flag is an independent serving gate—not the AI `ProfileReadiness` result and not an automatically maintained summary of Detail sections.

## 2. Current population and the four `true` rows

Current development-MySQL SELECT results:

| Measure | Count |
|---|---:|
| Restaurant rows | 517 |
| ACTIVE | 517 |
| ACTIVE + ELIGIBLE | 405 |
| ACTIVE + ELIGIBLE + Nonhyeon (`11680108`) | 402 |
| `recommendation_ready=true` overall | 4 |
| Above serving-scope intersection with `recommendation_ready=true` and ZeroPay | 1 |

The four true rows are all `sample_data=true` fixtures. IDs 1001–1003 are out of the Nonhyeon legal-dong scope; 1003 also has ZeroPay disabled. ID 1004 is the integration fixture “논현 통합검사 국밥집,” has ZeroPay and the target legal-dong code, and is the one-row static intersection. All four have fixture category/menu/price and one Spring schedule; none has NAVER Detail rows or Detail Lifecycle. They are not evidence that the 401 KOMSCO rows were promoted.

The V4 default helps explain how legacy/sample rows can be true, but it does not explain a promotion of KOMSCO rows: KOMSCO creation overrides the default with false, and subsequent synchronization preserves the existing flag.

## 3. Strict-ready 26 comparison

The live 360-row matched-Numeric-NAVER cohort was re-evaluated with `profile_readiness_audit.audit_rows()` and the shared `ProfileReadinessPolicy` (freshness TTL 30 days). The result is 26 READY. Every one is ACTIVE, ELIGIBLE, in the target legal dong, ZeroPay-enabled, has a unique verified numeric NAVER Place ID, MENU/REVIEW/BUSINESS_HOURS Lifecycle SUCCESS, at least one priced menu, and at least one source-grounded structured hour. Yet every row has `recommendation_ready=false`, no Spring schedule, and null Spring category/representative menu/average price.

| ID | Restaurant | Profile ready | Menu / priced | Review SUCCESS | Hours SUCCESS / structured | Spring ready | Spring schedule |
|---:|---|---|---:|---|---|---|---:|
| 9559 | 모우리 | Yes | 28 / 28 | Yes | Yes / 4 | No | 0 |
| 9568 | 청기와 | Yes | 22 / 22 | Yes | Yes / 1 | No | 0 |
| 9569 | 산곰장어 | Yes | 10 / 8 | Yes | Yes / 4 | No | 0 |
| 9570 | 블러프 | Yes | 7 / 7 | Yes | Yes / 4 | No | 0 |
| 9571 | 피자스쿨 강남논현점 | Yes | 42 / 42 | Yes | Yes / 1 | No | 0 |
| 9574 | 청담머구리 | Yes | 12 / 11 | Yes | Yes / 1 | No | 0 |
| 9580 | 빨간모자피자 | Yes | 55 / 55 | Yes | Yes / 6 | No | 0 |
| 9603 | 본죽&비빔밥 논현점 | Yes | 63 / 63 | Yes | Yes / 4 | No | 0 |
| 9617 | (주)에스지푸드 논현역 마성떡볶이 | Yes | 24 / 24 | Yes | Yes / 1 | No | 0 |
| 9639 | 이자카야나무(논현) | Yes | 64 / 64 | Yes | Yes / 1 | No | 0 |
| 9659 | 만석 | Yes | 89 / 89 | Yes | Yes / 1 | No | 0 |
| 9715 | 교촌치킨 논현1호점 | Yes | 81 / 81 | Yes | Yes / 1 | No | 0 |
| 9759 | 특별한 오복수산 가로수길점 | Yes | 56 / 56 | Yes | Yes / 5 | No | 0 |
| 9791 | 비비큐 논현중앙점 | Yes | 72 / 72 | Yes | Yes / 1 | No | 0 |
| 9801 | 공리 | Yes | 59 / 59 | Yes | Yes / 5 | No | 0 |
| 9826 | 삼호짱뚱이 | Yes | 54 / 53 | Yes | Yes / 6 | No | 0 |
| 9839 | 상무초밥 강남역 | Yes | 51 / 51 | Yes | Yes / 7 | No | 0 |
| 9853 | 팔당닭발 | Yes | 52 / 51 | Yes | Yes / 6 | No | 0 |
| 9865 | 구월의 소철 | Yes | 141 / 141 | Yes | Yes / 4 | No | 0 |
| 9904 | 생생돈까스논현 | Yes | 69 / 69 | Yes | Yes / 1 | No | 0 |
| 9954 | 딸바요 | Yes | 62 / 62 | Yes | Yes / 1 | No | 0 |
| 9973 | 주식회사 써브웨이학동역점 | Yes | 52 / 52 | Yes | Yes / 1 | No | 0 |
| 9996 | 파리바게뜨 강남구청센터점 | Yes | 77 / 77 | Yes | Yes / 5 | No | 0 |
| 10021 | 싸다김밥 강남구청역점 | Yes | 83 / 83 | Yes | Yes / 5 | No | 0 |
| 10042 | 주래등 | Yes | 72 / 72 | Yes | Yes / 1 | No | 0 |
| 10053 | 파리바게뜨 신논현교보타워 | Yes | 48 / 48 | Yes | Yes / 1 | No | 0 |

All 26 also have `active=1`, `eligibility=ELIGIBLE`, `legal_dong_code=11680108`, and `zero_pay_available=1`. “Profile ready” is specific to generating evidence-backed AI claims; it does not certify that Spring's independent category/price/schedule tables have been populated.

## 4. Legacy Detail and the recent Backfill

Current SELECT counts show NAVER menu rows for 325 restaurants, review keywords for 344, business-hour rows for 360, but section Lifecycle rows for only 35. Legacy rows record previously collected content; Lifecycle records that the current section pipeline verified a section and its status. The former does not imply the latter.

The completed Backfill manifest records 27/27 success, 27 external-request targets, detail-only writes, 22 newly READY Profiles, zero Profile generation, and zero Qdrant writes. The before/after report says it changed Detail/Lifecycle tables only; Restaurant master and verification/ownership remained unchanged. It intentionally did not update `restaurants.recommendation_ready`, `restaurant_schedules`, category, representative menu, or average price.

That is why a successful Detail Backfill left the flag untouched: it fulfilled the AI-source-data task, not a Spring serving-data promotion task. The collected NAVER hours live in `restaurant_business_hours`; Spring's open-candidate query joins the distinct `restaurant_schedules`, `restaurant_operating_days`, and `restaurant_operating_hours` tables.

## 5. CASE assessment and serving-data gap

- **CASE 1 — STALE FLAG:** not a sufficient diagnosis. There is no recomputation path, but the target rows lack more than a flag.
- **CASE 2 — WRONG/OLD/UNOWNED RULE:** confirmed as a lifecycle/ownership issue. The schema defaults true, KOMSCO construction explicitly sets false, and no promotion owner bridges the two.
- **CASE 3 — REAL DATA GAP:** confirmed for the serving cohort. Among the 402 ACTIVE+ELIGIBLE+Nonhyeon rows, 401 are KOMSCO and all 401 have null category, representative menu, and average price and no `restaurant_schedules`. The one remaining in-scope row is sample integration fixture 1004.

The findings are therefore mixed: an orphaned/legacy flag lifecycle plus a real missing serving projection. At present, the actual KOMSCO serving-candidate count is zero. The static in-scope intersection count of one is the synthetic integration fixture, not a real KOMSCO location.

## 6. Phase B gate and outcome

The prerequisite for reconciliation is not met. No current rule specifies how to transform a Detail menu set into Spring `category`, `representative_menu`, and `average_price`, nor how to produce Spring weekday schedule/closure rows from source-grounded NAVER hours (including split periods, breaks, overnight hours, and closed days). ProfileReadiness intentionally does not define those serving semantics.

Setting `recommendation_ready=true` by ID or for all Profile-READY records would be unsafe and ineffective: the repository query still requires Spring schedule rows, and the service uses category/average price for filtering and ranking. Accordingly:

- Phase B reconciliation: **not run**.
- DB writes / snapshots: **0 / not created**.
- Source code changes: **0**.
- Tests and Harness: **NOT_RUN**; no code changed, and integration/backend scripts may modify fixtures or DB state.
- `git diff --check`: passed for the tracked working-tree diff (the new untracked audit files are not included by Git's diff check); the JSON artifact separately parsed successfully.

### Recommended next bounded design step

Define and test a separate, reproducible serving-data promotion policy: authoritative category mapping, representative-menu selection, price aggregation, verified source/freshness criteria, schedule normalization (including closures/overnight cases), and rollback/audit semantics. Then dry-run it over a bounded set and only after its output is reviewable perform a guarded reconciliation. Do not equate ProfileReadiness with serving readiness.

## 7. User-facing answers

**Q1. Why did `recommendation_ready` remain at four after Detail Backfill?**  
The Backfill was deliberately scoped to NAVER menu/hours/review and Lifecycle tables. It did not write Restaurant master or Spring schedules, and there is no code that promotes the flag after Detail completion.

**Q2. Why were those four true?**  
They are sample/integration fixtures. The three general fixtures get the database default and have sample category/menu/price/schedule. The fourth is an integration fixture in Nonhyeon. They are not the newly enriched KOMSCO records.

**Q3. Why are 26 Profile-READY restaurants different from `recommendation_ready`?**  
The 26 passed the AI-source evidence quality gate. Spring needs a separate serving representation and schedule; all 26 lack the master serving fields and Spring schedule and remain false.

**Q4. How many real restaurants can the current serving query recommend?**  
The static population has one in-scope ready+ZeroPay row, but it is synthetic fixture 1004. There are zero KOMSCO rows passing the current serving gate. Live-time schedule availability is an additional query condition.

**Q5. Is this a data issue, logic issue, or stale value?**  
Both a missing serving-data projection (real data gap) and a missing flag-promotion owner (lifecycle/rule gap). “Stale flag only” is not supported.

**Q6. What changed in this task?**  
No code or database state changed. The audit artifacts now document the cause and the safe stop condition; Phase B was intentionally not run.
