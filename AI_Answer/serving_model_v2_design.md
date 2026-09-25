# Serving Model v2 — Design and Implemented Boundary

## Responsibility split

```text
KOMSCO Restaurant master
  + VERIFIED Numeric NAVER mapping
  + MENU SUCCESS / active NAVER menu rows
  + BUSINESS_HOURS SUCCESS / active source hours
                  ↓
Spring ServingReadinessPolicy
  identity + scope + ZeroPay + fresh source + current-hour interpretation
                  ↓
Spring Recommendation service
  hard filters → ranking → venue dedup → max 3

NAVER menu rows → source-ordered `menuExamples` for display
Qwen menu-role artifact → NOT authoritative until Spring validation/import
```

ProfileReadiness remains an AI feature-input gate. It is not the Spring serving gate.

## Implemented in this change

- KOMSCO candidates are read from the existing verified mapping, section lifecycle, menu, and business-hours tables. The KOMSCO path computes current serving eligibility and does not require the legacy `recommendation_ready` bit or legacy schedule rows.
- Spring owns `ServingReadinessPolicy`; unknown/closed hours do not become OPEN. Its input query requires ACTIVE, ELIGIBLE, ZeroPay, the fixed legal-dong scope, a unique numeric NAVER mapping, VERIFIED provenance, fresh MENU/HOURS SUCCESS, and active source menu/hour rows.
- `VerifiedHoursPolicy` supports same-day intervals, overnight intervals across midnight, `00:00–24:00`, recurring closed weekdays, parseable date-specific closures, and parseable break intervals. Unresolved irregular/night closures and unparseable breaks return UNKNOWN.
- KOMSCO `category` and `representative_menu` are nullable and are not readiness requirements. Unknown category does not reject a KOMSCO candidate. Existing enums remain for old sample/preferences compatibility; this change adds no food-category enum values.
- New recommendation DTOs may carry up to three `menuExamples`; those are active NAVER menu rows ordered by crawler's `dom-N` source sequence, and the UI calls them “메뉴 예시”. Legacy fixture responses retain `representativeMenu`/`averagePrice` compatibility.
- Null/unknown scalar price is not treated as an explicit-budget pass. A budgeted KOMSCO candidate is withheld until an approved menu-role classification has crossed a Spring persistence/import boundary.

## Menu budget classification contract

Pilot schema roles: `MEAL_CANDIDATE`, `SIDE`, `DRINK`, `ALCOHOL`, `MULTI_PERSON`, `COURSE`, `WEIGHT_BASED`, `UNKNOWN`. Qwen sees only existing menu IDs, names/descriptions, and persisted prices. It cannot create or change a menu or price. Python validates IDs/duplicates/role enum and checkpoints each restaurant; omitted rows become UNKNOWN. No classification is written to MySQL in this pilot.

The output is not yet trusted for serving. A Qwen schema-valid response is only a candidate classification, not approval. A Spring-owned, versioned importer/table and operator-reviewed acceptance policy are still required before the classification can affect a hard budget filter. Therefore no migration or DB import was made after the bounded model pilot exposed timeouts and semantic mistakes.

## Deliberately not implemented

- No category master/crosswalk: provider categories are metadata, not a new mandatory Spring taxonomy.
- No HOME category persistence: it is unnecessary for serving readiness and taxonomy intent remains an AI concern.
- No `average_price` recomputation or use as KOMSCO budget source.
- No date-specific closure table. Uncertain closure evidence safely withholds a current OPEN decision.
- No writes to `recommendation_ready`; KOMSCO readiness is evaluated dynamically by Spring. The historical boolean remains for legacy fixtures and is no longer authoritative in the new KOMSCO read path.
- No MySQL migration, Qwen import, category/menu/master update, or Qdrant write.

## Remaining schema/data issues

`restaurant_business_hours` has a unique provider/place/day key, while DOM collection can parse multiple intervals for one day. Repeated same-day rows can therefore collapse during persistence. The current pilot policy handles a single verified interval and explicit break interval; it cannot recover split-hour intervals already collapsed by persistence. Date-specific closure source is free text and is only recognized when the weekday/date/closure phrase is explicit. This is why ambiguous cases remain UNKNOWN rather than being promoted.
