# Serving Projection Dry-run Review

## Result

**Target cohort:** 26 current strict Profile-READY restaurants.  
**Dry-run mode:** MySQL SELECT-only; no source/model/provider calls and no writes.  
**Fully Spring Serving-READY under a defensible current policy: 0/26.**

The row-level calculations and evidence flags are in [serving_projection_dry_run.json](serving_projection_dry_run.json). Contract decisions and code/schema references are in [serving_projection_contract_audit.md](serving_projection_contract_audit.md).

| Coverage item | Result | Why |
|---|---:|---|
| Target restaurants | 26 | Current shared ProfileReadinessPolicy over verified numeric NAVER cohort |
| Raw provider category candidate | 26 | External mapping has Kakao/NAVER_LOCAL category in each target; current verified NAVER category is null and HOME category is not persisted |
| Category resolved to current Spring contract | 0 | No provider-to-enum crosswalk; enum currently has only three values |
| Unique representative menu resolved | 0 | Only 5 restaurants have explicit signature/best/popular name markers, with multiple or semantically different marked products; no separate representative flag/rank |
| Any positive numeric menu price | 26 | 1,440 of 1,445 active menu rows |
| Valid single-person lunch-budget price | 0 | 26 catalogs have no populated `menu_type`/`is_set_menu`; heterogeneous price rows include sides, beverages, sets, portions, per-weight and course candidates |
| Basic schedule interval shape potentially representable | 15 | 26 minus 8 overnight and 3 `00:00–24:00`; 4 break evidence cases and closures still require normalization/policy |
| Lossless complete schedule projection established | 0 | No projection policy; 11 irregular/date-specific closure evidence cases have no date-aware Spring table; break/day grouping also needs validated mapping |
| Fully serving-ready | **0** | Category, representative-menu and suitable price are unresolved for the current serving contract; schedule fidelity is also not established |

The schedule shape categories overlap: overnight 8, 24-hour encoding 3, break evidence 4, recurring closed-day evidence 8, irregular/date-specific closure evidence 11. These are source evidence flags, not persisted Spring schedule rows.

## Per-restaurant summary

`CAT` = source candidate exists but no validated crosswalk; `REP` = no unambiguous single source-designated item; `PRICE` = raw stats only, not safe for hard budget; `SCH` = schedule normalization needed. Detailed min/max/mean/median and evidence candidates are in JSON.

| ID | Restaurant | Raw menu prices (n / min–max) | Category | Representative menu | Schedule observations | Final |
|---:|---|---|---|---|---|---|
| 9559 | 모우리 | 28 / 20,000–450,000 | CAT | multiple signature/popular | weekly + irregular closure | NOT_READY |
| 9568 | 청기와 | 22 / 3,000–30,000 | CAT | unresolved | 24h + irregular closure | NOT_READY |
| 9569 | 산곰장어 | 8/10 / 4,000–80,000 | CAT | unresolved | overnight + weekly/irregular closure | NOT_READY |
| 9570 | 블러프 | 7 / 25,000–90,000 | provider disagreement | unresolved | overnight + weekly/irregular closure | NOT_READY |
| 9571 | 피자스쿨 강남논현점 | 42 / 500–15,900 | CAT | unresolved | basic interval; policy needed | NOT_READY |
| 9574 | 청담머구리 | 11/12 / 10,000–150,000 | CAT | unresolved | recurring weekly closure | NOT_READY |
| 9580 | 빨간모자피자 | 55 / 1,700–41,800 | CAT | unresolved | overnight + irregular closure | NOT_READY |
| 9603 | 본죽&비빔밥 논현점 | 63 / 300–27,000 | CAT | multiple signature items | break + weekly/irregular closure | NOT_READY |
| 9617 | 마성떡볶이 | 24 / 2,000–19,500 | CAT | unresolved | basic interval; policy needed | NOT_READY |
| 9639 | 이자카야나무(논현) | 64 / 11,000–169,900 | CAT | unresolved | overnight | NOT_READY |
| 9659 | 만석 | 89 / 1,500–81,000 | CAT | multiple signature bundles | basic interval; policy needed | NOT_READY |
| 9715 | 교촌치킨 논현1호점 | 81 / 500–29,000 | CAT | unresolved | overnight | NOT_READY |
| 9759 | 특별한 오복수산 가로수길점 | 56 / 7,000–79,000 | CAT | unresolved | break + irregular closure | NOT_READY |
| 9791 | 비비큐 논현중앙점 | 72 / 500–52,000 | CAT | unresolved | overnight | NOT_READY |
| 9801 | 공리 | 59 / 7,000–100,000 | CAT | unresolved | irregular closure | NOT_READY |
| 9826 | 삼호짱뚱이 | 53/54 / 10,000–180,000 | CAT | unresolved | break + weekly closure | NOT_READY |
| 9839 | 상무초밥 강남역 | 51 / 100–54,000 | CAT | `[BEST]` is not unique representative proof | basic interval; policy needed | NOT_READY |
| 9853 | 팔당닭발 | 51/52 / 3,000–54,000 | CAT | unresolved | overnight + irregular closure | NOT_READY |
| 9865 | 구월의 소철 | 141 / 5,000–690,000 | provider disagreement | unresolved | break + weekly/irregular closure | NOT_READY |
| 9904 | 생생돈까스논현 | 69 / 1,000–20,900 | CAT | unresolved | basic interval; policy needed | NOT_READY |
| 9954 | 딸바요 | 62 / 1,000–10,000 | CAT | unresolved | 24h | NOT_READY |
| 9973 | 써브웨이학동역점 | 52 / 1,600–14,900 | CAT | unresolved | 24h | NOT_READY |
| 9996 | 파리바게뜨 강남구청센터점 | 77 / 990–39,500 | CAT | multiple `[Best]` items | irregular closure | NOT_READY |
| 10021 | 싸다김밥 강남구청역점 | 83 / 2,500–11,500 | CAT | unresolved | weekly closure | NOT_READY |
| 10042 | 주래등 | 72 / 1–130,000 | CAT | unresolved | basic interval; inspect 1-won row | NOT_READY |
| 10053 | 파리바게뜨 신논현교보타워 | 48 / 1,200–28,000 | CAT | unresolved | overnight | NOT_READY |

“Raw menu prices” use positive numeric source `price_value`; `n/min–max` is not a meal-price recommendation. Low prices can be add-ons and highs can be bundles/courses; the mean/median values are separately recorded for every target in the JSON artifact. No arbitrary outlier threshold was selected; risk flags are lexical review cues only.

## Policy recommendation and answers

- Do not promote any target in this dry-run. Proposed category, scalar representative menu, and user-budget price remain unresolved for all 26.
- Develop a stable category catalog/crosswalk outside the Java enum; provider taxonomies can seed candidates but should not be copied directly.
- Only use a source-explicit, unique signature/representative item for a scalar; otherwise prefer a list of source-labelled menu highlights or leave it unset.
- Do not use the all-menu mean or median for a hard single-person budget. Define eligible meal-item/portion metadata and a transparent budget policy first.
- Spring schedule schema handles weekday groups, multiple intervals, recurring closed days, and recurring breaks structurally, but direct overnight and 24:00 are not faithful under current Java/constraints; date-specific exceptions have no date-aware closure table.
- Spring should own the serving projection and promotion because it owns the MySQL serving contract and recommendation semantics. Python remains the Detail collector and may create a preview only.
- Keep ProfileReadiness separate from ServingReadiness. `recommendation_ready=true` should mean all current, validated Spring serving fields and schedule data have been projected—not merely that AI source evidence exists.

### Q1–Q10

1. Backfill completed NAVER Detail/Lifecycle writes, not Spring master/schedule projection.
2. Current Spring requires active, eligible, ZeroPay, target legal dong, `recommendation_ready`, a matching weekday/time schedule without closure, plus category/price for filtering/ranking and fields for response.
3. NAVER Detail provides useful source candidates and raw prices/hours, but not enough safe semantics to fill all current serving values for these 26.
4. Use a versioned category catalog with provider crosswalk and unknown/review state; avoid a growing enum or per-restaurant mapping.
5. Use an explicit unique provider signature marker; absent or ambiguous means unresolved. Current result: 0 single items resolved.
6. A classified one-person main-meal price is preferable. Current raw mean/median are catalog statistics, not a defensible budget proxy.
7. Not losslessly for all cases: overnight, 24h and date-specific exception gaps exist; break intervals need tested normalization.
8. `true` only after identity/freshness, category, price basis, required menu display, schedule/closure projection and validation all pass.
9. Spring serving-projection service/batch should own authoritative persistence; Python can provide a read-only preview.
10. Current policy: **0 of 26** fully serving-ready. This is an honest contract result, not a failed attempt to coerce the data.

## Safety and verification

- MySQL: SELECT-only; writes 0.
- NAVER/Kakao/provider calls: 0.
- Qwen/Gemini/Embedding calls: 0.
- Qdrant writes: 0; Qdrant was not needed.
- Spring/React/runtime/migration changes: 0.
- Dry-run scripts/tests: no new executable code added; no test suite run.
- Existing working tree preserved; no Git staging/commit/push/reset/clean.
