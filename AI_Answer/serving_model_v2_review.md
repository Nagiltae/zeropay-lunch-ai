# Serving Model v2 — Review

## Result

**PARTIAL / NOT READY FOR BUDGETED SERVING.** A source-backed KOMSCO candidate read path, separate serving-readiness and schedule policies, nullable legacy fields, and menu-example UI contract were added. The bounded five-restaurant Qwen pilot produced two schema-valid outputs and three 60-second timeouts; manual review found unsupported or contradictory labels. No classification was promoted, no migration was created, and no MySQL/Qdrant write occurred. Explicit-budget KOMSCO recommendations remain safely withheld.

## Implemented contract

- Spring reads KOMSCO candidates from the existing verified numeric NAVER mapping, fresh MENU and BUSINESS_HOURS SUCCESS, active source rows, single Place-ID ownership, ACTIVE+ELIGIBLE+ZeroPay, and legal dong `11680108`. It does not require legacy `recommendation_ready` or `restaurant_schedules` for KOMSCO rows.
- `ServingReadinessPolicy` is separate from ProfileReadiness. It rejects inactive/ineligible/out-of-scope/non-ZeroPay, missing/stale source, CLOSED/UNKNOWN hours, and explicit budget without an approved menu classification.
- `VerifiedHoursPolicy` handles same-day intervals, overnight intervals across midnight, `00:00–24:00`, recurring weekly closure text, clear current-date closure text, and structured break ranges. Ambiguous night/date closure or unparseable breaks are UNKNOWN.
- Category is nullable in the new serving response path; the three-value enum remains for legacy preferences/fixtures only. Category is not required for KOMSCO admission. No provider taxonomy is forced into a new enum.
- `representativeMenu` and `averagePrice` remain nullable for compatibility. KOMSCO results can carry up to three active, verified, source-ordered `menuExamples`; the UI labels them “메뉴 예시”. Unknown scalar price is hidden.
- Explicit budget is not passed using catalog mean/median or missing values. Until a Spring-validated classification exists, KOMSCO budget queries fail closed.

## Five-restaurant pilot

The target list was frozen before generation: `9617` (snack), `9571` (pizza), `9568` (Korean), `10042` (Chinese), and `9559` (weight-based meat/alcohol/multi-person price mix). MySQL SELECT-only found 188 active menu rows, all with positive numeric prices. Plan/input hashes are in `serving_model_v2_pilot_plan.json`.

| Restaurant | Menus | Qwen | Hours at observed 2026-09-25 22:23 KST | Serving outcome |
|---:|---:|---|---|---|
| 9617 | 24 | One schema-valid result; 48.579s | 07:00–20:30, closed | Not candidate now; budget labels unapproved |
| 9571 | 42 | Timeout, one call | 11:00–21:30, closed | Not candidate now; budget unknown |
| 9568 | 22 | Timeout, one call | 9/25 holiday closure plus vague weekend night closure | CLOSED/UNKNOWN; not candidate |
| 10042 | 72 | Timeout, one call | 10:00–20:30, closed | Not candidate now; budget unknown |
| 9559 | 28 | One schema-valid result; 50.365s | source names 9/25 holiday closure; no Friday recurring interval | Closed/uncertain; budget labels unapproved |

Qwen total: **5 calls / 2 successful structured outputs / 3 timeouts / 0 retries**. The 52 emitted menu IDs existed and were unique; this validates output shape only. **Approved classifications: 0.**

### Manual sample review

- `9617 / 마성세트((1.5인)) / ₩19,500` → MULTI_PERSON: supported by source name/description.
- `9617 / 부산어묵(1인분 (2꼬치)) / ₩3,400` → MEAL_CANDIDATE: plausible, but whether a snack counts as a budget meal needs explicit policy.
- `9559 / 한우 꽃등심토마호크100g / ₩26,000` → MEAL_CANDIDATE: conflicts with explicit 100g/unit pricing; should be WEIGHT_BASED or UNKNOWN for a one-person meal price.
- `9559 / 500–800g T-bone / ₩25,000` → MEAL_CANDIDATE: hundreds of grams does not establish one-person lunch suitability.
- A 9559 rationale says “price fits lunch budget” despite no numeric budget being supplied; that claim is unsupported. Two alcoholic products were labelled DRINK while most wine/liquor rows were ALCOHOL, showing inconsistent classification boundaries.

No result was rerun or persisted. This is not enough quality for a hard serving filter.

## Candidate smoke and persistence

At the observed local time, read-only source-hour evaluation projects all five targets as closed or uncertain (**projected 0**). The five real DB IDs were **not** executed through a live Spring runtime; live five-ID candidate execution is NOT_RUN. A Spring Boot/H2 transactional integration fixture with `recommendation_ready=false` showed that the verified-detail candidate query returns its source-backed candidate when currently open and no budget is requested; the same fixture was withheld under an explicit budget when classification was unknown. That fixture is not counted among the five actual restaurants.

No development MySQL write was performed. No DDL migration was added, and no Qwen role was stored. KOMSCO `recommendation_ready` is computed dynamically in Spring's new read path; the legacy column was not changed. There was no broad promotion.

## Ownership and remaining gaps

Spring owns serving readiness, current-hour evaluation, budget filtering, authoritative reads, and final recommendation. Python only emits the bounded classification artifact. Before budget serving can activate, add Spring-side validation/import persistence tied to menu ID plus source name/price fingerprint, and a reviewed policy for accepting model labels. No schema was added because the pilot did not pass semantic review.

Provider categories remain source metadata; HOME category was not persisted because it is not required for serving eligibility. User food-category meaning remains an AI semantic concern rather than a growing Spring enum.

`restaurant_business_hours` has a unique provider/place/day key while DOM collection can parse multiple intervals per weekday; repeated same-day intervals can collapse at persistence. The current evaluator cannot reconstruct lost split intervals. Date-specific closure source is free text and only clear weekday/date/closure phrases are classified; other cases stay UNKNOWN.

## Verification

- Backend targeted tests: PASS; full `./scripts/check-backend.sh` PASS (compile, full tests, build). Covers hours/readiness policies, verified-candidate H2 integration, ranking/fallback, and explanation/chat compatibility.
- AI pilot tests: PASS (5 targeted); full `./scripts/check-ai.sh`: **247 passed, 1 skipped**; Ruff PASS.
- Frontend recommendation-card tests: PASS (4); full `./scripts/check-frontend.sh`: build PASS, **12 tests passed**.
- `./scripts/check-integration.sh`: NOT_RUN. No schema/runtime integration claim was needed for this bounded no-write pilot; no dev DB candidate call was made.
- MySQL writes 0; Qdrant writes 0; Profile generation/embedding/Gemini/LangGraph calls 0.
- `git diff --check`: PASS.

## Answers to Q1–Q10

1. Some KOMSCO rows can now enter the Spring source-backed candidate path when identity, freshness, and current hours pass; explicit-budget requests remain blocked until menu roles are validated/imported.
2. The KOREAN/KOREAN_SOUP/SALAD enum is no longer required for KOMSCO eligibility; it remains for legacy preferences/fixtures. No provider taxonomy mapping was created.
3. Up to three active NAVER source-order rows are displayed as “메뉴 예시”; no singular representative is fabricated.
4. Budget will use source menu price only for Spring-imported approved `MEAL_CANDIDATE` rows whose source snapshot still matches. Unknown is not treated as pass or fail price evidence; an explicit-budget candidate is withheld.
5. Qwen classified supplied menu IDs only; it did not create menu names/prices. Its results are not trusted or persisted.
6. Overnight wraps across midnight; `00:00–24:00` is 24h; known recurring closure is CLOSED; ambiguous date/night closure and unparseable break are UNKNOWN.
7. UNKNOWN never becomes OPEN and is excluded from current candidates.
8. Spring v2 readiness requires ACTIVE+ELIGIBLE+ZeroPay+target area, unique verified numeric NAVER identity, fresh successful menu/hours data, usable menu and OPEN hours. Explicit budget additionally requires a validated menu classification and an eligible menu within budget. Category and representative menu are not required.
9. Spring owns readiness, serving projection, and classification import; Python produces artifacts only.
10. Five-target live Spring candidate count: **NOT_RUN**. Read-only source snapshot projected **0** candidates at 22:23 KST because the sampled hours were closed/uncertain. H2 fixture coverage: one no-budget candidate. An open-time live five-place result is not established.

## Next

1. Tighten classifier output to avoid unsupported rationales and ambiguous classifications. Test fixtures before any second bounded pilot.
2. Human-review an accepted policy and add Spring validation/import storage before budget classifications affect serving.
3. Correct source persistence for multiple intervals per weekday; then add validated date-specific closure normalization or keep those cases UNKNOWN.
4. Run a separately gated pilot at an open time after classifier/import quality passes; do not promote all 26.
