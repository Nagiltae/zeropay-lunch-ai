# Serving Projection Contract Audit

**Date:** 2026-09-25  
**Scope:** design + read-only dry-run for the current ProfileReadiness cohort (26 restaurants).  
**Decision:** serving projection contract is not yet safe to persist; no DB/code/schema/model writes or external requests were performed.

## 1. Three distinct data layers

```text
KOMSCO Restaurant master ── identity, active, legal dong, ZeroPay
          │
          ├─ verified NAVER Detail ── source menus / hours / reviews
          │             │
          │             ├─ Serving Projection ── Spring filters and response fields
          │             └─ Semantic Profile ── AI search claims/evidence
          │
          └─ Spring Recommendation ── hard filters, ranking, final output
```

`ProfileReadiness` certifies enough current, source-grounded data to build Semantic Claims. It does not populate or certify Spring serving state. `Serving Projection` must preserve provenance and only mark ready after all required Spring fields and schedule semantics are resolved.

## 2. Existing Spring contract

Sources inspected: `Restaurant.java`, `RestaurantCategory.java`, `RestaurantJpaRepository.findOpenRestaurants`, `RestaurantRecommendationService`, V1/V4 migrations, sample SQL, and integration fixture SQL.

| Field / table | Storage and Java shape | Runtime role | Required for a serving row? | Current source situation |
|---|---|---|---|---|
| `restaurants.category` | DB `VARCHAR(40)` nullable after V4; Java `RestaurantCategory` enum, nullable | exact category filter, disliked/preferred-category logic, score; response label via `category.label()` | Yes in current response path; null can fail during response construction | Spring enum has only `KOREAN`, `KOREAN_SOUP`, `SALAD`; NAVER/Kakao taxonomies are broader/inconsistent |
| `representative_menu` | DB `VARCHAR(120)` nullable; Java `String` | returned in `RecommendationItem`/card | Response contract expects a string; no observed ranking use | menu rows retain names, but menu type/set/signature metadata are absent or only embedded in names |
| `average_price` | DB `INT` nullable after V4; Java `Integer`, response currently uses primitive `int` | budget hard filter (`averagePrice > budget` excludes); deterministic score; ascending-price tie-break; response | Yes when budget is present and in response conversion; null can unbox/fail | NAVER has per-menu prices, not a defined representative single-person price |
| `recommendation_ready` | DB non-null boolean, default TRUE in V4; Java `boolean` | mandatory condition in repository query | Yes | New KOMSCO entities explicitly start false; no promotion owner |
| `restaurant_schedules` | `id`, restaurant FK, name | joins the recurring schedule tree | Yes | 0 rows across the 26 READY restaurants |
| `restaurant_operating_days` | schedule FK + weekday string | weekday hard filter | Yes | Can associate one/more weekdays with a schedule |
| `restaurant_operating_hours` | schedule FK + `opens_at TIME`, `closes_at TIME`; check `opens_at < closes_at` | current-time hard filter; multiple intervals can be rows under one schedule | Yes | Supports multiple same-day periods structurally, but not overnight interval as stored; LocalTime also has no `24:00` |
| `restaurant_closed_days` | restaurant FK + weekday | recurring weekday exclusion | Optional when there is no recurring closure; needed to model one | Can represent weekly closure |
| `restaurant_closed_hours` | schedule FK + start/end TIME; check start < end | exclusion for recurring breaks/closed intervals | Optional | Can express recurring break if source is parsed and normalized |

V1 originally made category/menu/price non-null and V4 relaxed them for source-only KOMSCO rows. Sample fixtures explicitly seed all serving fields and schedules; they are not a mapping policy. Recommendation service checks price and category (not just display), then builds response fields from the same Restaurant. Consequently null projection values cannot safely pass as “ready.”

## 3. Source candidates and Category options

The current DOM HOME crawler captures a category string in `DomCollectedDetail.category`, but `place_detail_persistence.py` does not persist that field into a serving category column. The verified NAVER `restaurant_external_places` row has null category in this cohort. Separate `KAKAO` and historical `NAVER_LOCAL` mappings often have category strings; several cohort members have both, with different provider-specific granularity. KOMSCO's `industry_code=561` identifies the food-service industry but not a usable cuisine category. Those candidates are not values from Spring's 3-member enum.

| Option | Benefits | Risks / decision |
|---|---|---|
| A. Copy Provider category directly | Low transformation, source traceable | Provider strings differ and are hierarchical/free text; cannot safely deserialize as current enum or satisfy stable preference codes. **Not safe as-is.** |
| B. LLM classification to enum | Can interpret multiple category/menu signals; could use constrained output | Not authoritative; disagreement/low confidence and taxonomy drift; requires evidence, schema validation, review path. Gemini/Qwen call is not part of this task. **Possible suggestion-only aid, never direct promotion.** |
| C. Evolve category model | Stable, extensible taxonomy IDs with display labels, parent/alias relations, source mappings, and versioned crosswalk; unknown/review state | Requires deliberate API/schema/preferences migration. **Recommended long-term contract.** |

Recommendation: a versioned category catalog/crosswalk owned with Spring domain data, fed by provider taxonomy candidates and evidence, with deterministic mappings where unambiguous and `UNKNOWN/REVIEW` otherwise. Do not grow Java enum by adding every cuisine or use restaurant-ID mappings. Current 26 dry-run: 26 have at least one external provider category candidate, but 0 have a validated projection to a supported Spring category under an existing crosswalk (none exists).

## 4. Representative menu

The current crawler stores menu `name`, description, numeric/text price, and nullable `price_type`, `menu_type`, `is_set_menu`. It does not persist a separate provider “representative item” rank/flag. In the 26 targets, all 1,445 active NAVER menu rows have null `menu_type` and `is_set_menu`. Five restaurants have explicit name markers such as `시그니처`, `인기메뉴`, or `[BEST]`; several contain multiple marked items, marker semantics differ, and some are bundles or packaged products. Thus the marker is useful evidence for a candidate, but it does not yield one unambiguous item for the scalar `representative_menu` field.

Policy proposal: select a scalar representative menu only from an explicit, source-provided representative/signature marker with one unique eligible item; if zero or multiple candidates, leave unresolved. Prefer changing the serving response/model to a small list of source-labelled menu highlights rather than pretending one scalar is canonical. Never choose first, cheapest, most expensive, or random.

Dry-run result: **0/26 single representative menu resolved**. Marker candidates remain recorded in the dry-run artifact.

## 5. Price and budget semantics

`average_price` is not merely display metadata: service uses it to hard-reject candidates above a user budget and to rank/tie-break. Treating all menu prices as one restaurant average would therefore create false exclusions and false budget claims.

Read-only calculation over active NAVER menu rows:

- 1,445 menu rows; 1,440 have positive numeric `price_value`.
- For every restaurant, min/max/arithmetic mean/median of those numeric rows are recorded in `serving_projection_dry_run.json`.
- All 26 have null `price_type`, `menu_type`, and `is_set_menu` on these rows.
- The observed names include per-100g products, sets/courses, large portions, drinks/alcohol and sides; examples include 100g beef, 2/4-person sashimi sets, courses, and menu prices as low as 1/100/300/500 won. These are source rows, not necessarily individual lunch meals.

| Method | What it measures | Decision for hard lunch budget |
|---|---|---|
| Arithmetic mean | Mean of heterogeneous menu rows | Reject: skewed by expensive courses/sets and row-count/catalog composition |
| Median | Middle of heterogeneous rows | Better robust catalog summary, but still not “one-person lunch price” |
| Explicitly marked representative item's price | Price of a source-highlighted item | Only if unique, single-serving, currently priced and marker semantics are verified; none resolved as a single item in this cohort |
| Eligible one-person main-meal price | Closest to user budget intent | Preferred eventual basis, but current data has no dependable item-kind/serving-size fields to identify it across providers |
| Price range / structured candidates | Honest uncertainty and source detail | Recommended model/API direction; hard budget should use a defined policy over eligible meal candidates, not an all-menu mean |

Therefore raw statistics are computed for analysis, but **proposed serving price is null for all 26**. No price is inferred or persisted.

## 6. Business-hours mapping

NAVER detail source uses `restaurant_business_hours` with one row per `(provider, external_place_id, day_of_week)`, text `description`, optional `open_time`/`close_time`, `break_hours`, and closure strings. Spring instead relates `restaurant_schedules → operating_days` and `operating_hours`; optional closure tables are separate. A schedule can group days sharing hours, and multiple operating-hour rows can express multiple periods. The current source row key only permits one row per weekday; split intervals are currently retained as break text/description, not a normalized interval list.

| Source case | Current Spring representation | Dry-run finding |
|---|---|---|
| Ordinary same-day interval | Direct `TIME` pair + weekday | Structurally expressible, but requires an explicit day/grouping projection and provenance |
| Split periods / break | Multiple operating-hour rows, or an exclusion in `closed_hours` | Spring can model it. Source currently has only a break string/description and no tested projection; 4/26 show break evidence. Do not discard the break or widen open hours |
| Overnight, e.g. 16:30–03:00 | V1 CHECK rejects `opens_at >= closes_at`; LocalTime has no next-day bit | **Not directly representable**. 8/26 have overnight source rows. A split-across-days policy needs explicit semantics and tests for closing-day/closed-day interactions |
| 24-hour, e.g. 00:00–24:00 | Java `LocalTime` has no 24:00; database TIME may encode it but application comparison does not | **Not faithfully representable by current Java contract**. 3/26 |
| Recurring closed weekday | `restaurant_closed_days` | Expressible; 8/26 contain recurring-closure evidence |
| Irregular/date-specific closure | No date column/table in current closure model | **Not representable**; 11/26 have irregular/date-specific closure evidence |
| Ambiguous/missing interval | No safe interval | Keep unresolved; none of the 26 failed ProfileReadiness solely for missing source-grounded structured hours, but this does not prove serving normalization |

These are overlapping evidence categories. `serving_projection_dry_run.json` records the flags per restaurant. Fully lossless schedule projections under current exact semantics: **0/26 established**. At least the 8 overnight and 3 24-hour cases require a contract/schema or a tested normalization policy; dated closures need a date-aware model if they are to be enforced.

## 7. Proposed readiness and promotion ownership

Recommended meaning:

> `recommendation_ready=true` only when the current, verified Restaurant identity is in scope; category contract is resolved; budget-price basis is valid for the serving policy; any required display menu is source-grounded; recurring schedule/closures are normalized without loss; and the projection has passed validation.

Keep this separate from `ProfileReadiness`. Readiness should be an explicit `ServingReadinessPolicy` result with stable reason codes (for example `CATEGORY_UNRESOLVED`, `PRICE_BASIS_UNRESOLVED`, `REPRESENTATIVE_MENU_UNRESOLVED`, `OVERNIGHT_UNSUPPORTED`, `ALL_DAY_UNSUPPORTED`, `DATED_CLOSURE_UNSUPPORTED`, `SOURCE_STALE`, `IDENTITY_NOT_VERIFIED`). The boolean should be derived only from successful projection state, not manually toggled.

**Owner recommendation: Spring serving-projection service/batch (Option B).** Spring owns the DB, recommendation rules, schema, and final candidate semantics. Python can continue collecting NAVER Detail and can produce read-only projection previews, but should not authoritatively update Spring serving tables. Spring should read verified source rows, compute/validate a versioned projection, persist transactionally per Restaurant in a later approved phase, and record source IDs/fingerprints/policy version. Do not run it now.

## 8. Options for Gemini (planned only)

`PLANNED_GEMINI_CANDIDATE`: optionally suggest a broad category from provider category + menu names against a fixed controlled vocabulary. The response must be schema constrained, evidence-linked, confidence-gated, and reviewed for conflicts; Spring's deterministic policy alone decides persistence. Do not use Gemini to invent menu prices, serving sizes, hours, or closures. It is not a current runtime role and no Gemini request was made.

## 9. Unresolved decisions before persistence

1. Expand/replace the three-value enum and preference/API contract with a stable category catalog.
2. Define how one or multiple menu highlights are returned; current data does not select one scalar for 26/26.
3. Define a verified “one-person main meal” price basis; all-menu mean/median is not suitable for a hard budget gate.
4. Decide schedule model support for overnight and 24-hour operations and date-specific closures.
5. Define projection version, source freshness, evidence links, rerun/idempotency, manual review, rollback, and the exact ready predicate.

No Flyway migration, production Spring code, DB write, provider request, Qwen/Gemini call, Embedding, or Qdrant operation was performed.
