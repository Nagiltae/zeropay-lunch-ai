# Semantic Profile Verifier V2.1 Review

Date: 2026-09-26 (Asia/Seoul)

## Final decision

**SEMANTIC PROFILE VERIFIER V2.1 = BLOCKED_SHADOW_QUALITY**

The frozen fixture gate passed on all 8 fixtures over 3 independent runs. The subsequent read-only review of all 40 v12 points completed, but 12/40 claims ended in `ERROR` after bounded retry. This is too many unresolved shadow decisions to authorize the next Generator-fix stage. No verifier prompt/model change, fixture-specific code, or Generator change was made.

## Fixture semantics and frozen suite

The old 9571 fixture expected `PARTIAL` for a claim that menu titles proved pizza topping composition. Under the direct-evidence policy, `불고기피자` and `야채퀘사디아피자` prove those listed item names, not their recipe/topping construction. The frozen V2.1 version therefore expects `UNSUPPORTED` for that compound topping claim; the old V2 artifact remains preserved. A separate mixed fixture uses literal menu-listing language and two exact menu rows, with an unsupported third listed item, to test `PARTIAL` without culinary inference. The policy audit was written before the V2.1 verifier runs.

Frozen suite: 4 negative, 1 mixed, 3 positive. All expectations were frozen before verifier calls.

| Fixture | Expected | Three observed verdicts | Result |
|---|---|---|---|
| 9559 deliciousness → tenderness | UNSUPPORTED | U / U / U | PASS |
| 9559 group gathering → corporate/family | UNSUPPORTED | U / U / U | PASS |
| 9571 menu titles → topping composition | UNSUPPORTED | U / U / U | PASS |
| 9568 gathering + spacious → comfortable casual dining | PARTIAL | P / P / P | PASS |
| 9571 listed items + unsupported chicken-pizza listing | PARTIAL | P / P / P | PASS |
| 9617 menu items | SUPPORTED | S / S / S | PASS |
| 9617 solo/quick context | SUPPORTED | S / S / S | PASS |
| 9617 friendly review keyword | SUPPORTED | S / S / S | PASS |

Fixture metrics: false acceptance 0; positive false rejection 0; expected PARTIAL correct 6/6; atomicizer/verifier errors 0; retries 0. Atomicizer calls 24, assertion-verifier calls 57, total local model calls 81. The model remained `qwen3.5:9b`, temperature 0.

## 40-point read-only shadow review

Because the fixture gate passed, the existing `zeropay_semantic_claim_pilot_v12` 40 points were then read and reviewed. Results:

| Verdict | Count |
|---|---:|
| SUPPORTED | 6 |
| PARTIAL | 18 |
| UNSUPPORTED | 4 |
| ERROR | 12 |

The 12 errors were all `ATOMICIZER / SCHEMA_ERROR`; bounded retry did not resolve them. Ten were FOOD_MENTION, with the remaining two in DINING_CONTEXT/TASTE. Thus the key remaining defect is not false approval but failure to obtain a valid decomposition for 30% of this legacy claim set.

### V1 → V2.1 transitions

| Transition | Count |
|---|---:|
| SUPPORTED → SUPPORTED | 6 |
| SUPPORTED → PARTIAL | 13 |
| SUPPORTED → UNSUPPORTED | 2 |
| SUPPORTED → ERROR | 12 |
| UNSUPPORTED → PARTIAL | 5 |
| ERROR → UNSUPPORTED | 2 |

15 claims previously marked SUPPORTED were downgraded to PARTIAL/UNSUPPORTED; another 12 could not be judged due to error. These are diagnostic shadow outcomes only. Existing claims have no stored exact supportQuote, so **indexable under current policy remains false for all 40**, including the six SUPPORTED results.

### Claim type and source breakdown

| Claim type | SUPPORTED | PARTIAL | UNSUPPORTED | ERROR |
|---|---:|---:|---:|---:|
| DINING_CONTEXT | 1 | 2 | 0 | 1 |
| FOOD_MENTION | 0 | 5 | 1 | 10 |
| FOOD_TYPE | 1 | 2 | 1 | 0 |
| MENU_CHARACTERISTIC | 0 | 4 | 1 | 0 |
| TASTE | 3 | 3 | 0 | 1 |
| VENUE_CHARACTERISTIC | 1 | 2 | 1 | 0 |

Source counts are overlapping because a claim may cite multiple source types. Keyword-associated claims: 5 supported, 12 partial, 2 unsupported, 12 error; menu-associated: 1 supported, 6 partial, 2 unsupported; review-associated: 1 error. These are not mutually exclusive denominators.

### Human-readable sample review

- **SUPPORTED, FOOD_TYPE (9568):** menu Evidence `순대국`, `한우차돌박이`, `된장찌개+비빔밥` supports the corresponding served-item assertions. The review does not treat review mentions as official menu proof.
- **SUPPORTED, DINING_CONTEXT (9569):** “단체모임 하기 좋아요” and “매장이 넓어요” support group suitability and spaciousness as customer-reported characteristics.
- **SUPPORTED, TASTE (9580):** the customer-selected “음식이 맛있어요” keyword supports a customer-reported deliciousness assertion, not an unobserved texture or preparation claim.
- **PARTIAL, FOOD_TYPE (9617):** the claim includes “김밥과 떡볶이가 메뉴에서 확인된다,” supported by menu rows, alongside a separate generic “김밥은 음식 종류이다” assertion that the verifier did not ground in the cited rows. This illustrates why a claim can be PARTIAL even when its central direct menu-presence statement is supported; it also flags potential over-decomposition for future analysis, not a reason to loosen the verifier here.
- **PARTIAL, TASTE (9731):** deliciousness and freshness have keyword evidence; “savory” does not, so it is unsupported.
- **PARTIAL, MENU_CHARACTERISTIC (9580):** set-menu presence is supported; “variety of pizza sizes” is not supported by the cited `슬림세트 R` / `세트메뉴 R` rows.
- **UNSUPPORTED examples:** four shadow claims were wholly unsupported. The exact records and cited source snapshots are in the shadow JSON for review; no one pattern was converted into a keyword rule.

FOOD_MENTION remains semantically distinct from official MENU evidence: a review keyword can establish that customers mentioned a food, not that the restaurant officially sells it. The high FOOD_MENTION atomicizer error count prevents a confident quality conclusion for that type.

## Side effects and execution

- Qdrant reads: 40; writes: 0.
- MySQL reads/writes: 0 / 0.
- Embedding calls: 0.
- Gemini calls: 0.
- Local Qwen calls: fixtures 81 + shadow 133 = 214.
- Shadow calls: atomicizer 52, assertion verifier 81, retries 12, terminal verifier errors 12.
- Existing Qdrant points/artifacts were not modified. Generator and runtime code were not changed.
- Fixture gate permitted shadow execution; no Qdrant shadow ran before that gate.

## Harness

Targeted verifier tests: **PASS**, 25 passed. Ruff on the quality-gate module, V2.1 runner, and related tests: **PASS**. Full `./scripts/check-ai.sh`: **PASS**, 299 passed, 1 skipped (live semantic runtime test), with one upstream Starlette deprecation warning. JSON artifacts parsed successfully; all 40 shadow rows have `indexableUnderCurrentPolicy=false`. `git diff --check`: **PASS**. Secret-pattern scan: no matches. Backend/frontend harnesses: `NOT_REQUIRED` (no changes to those modules). No MySQL/Qdrant writes or Gemini requests occurred during verification.

## Answers

1. **Was the old 9571 PARTIAL expectation policy-consistent?** No. Its cited menu names did not directly establish topping composition; the frozen V2.1 version expects UNSUPPORTED.
2. **What does “불고기피자” directly establish?** That a menu row with that exact name was listed, not a verified recipe/topping construction.
3. **Was the fixture changed after seeing verifier output?** No. The evidence-policy audit and new frozen version preceded the V2.1 runs; the old artifact is preserved.
4. **Does the new PARTIAL fixture separate supported and unsupported assertions?** Yes: two exact menu listing assertions have cited rows; the cited rows do not support the third named item.
5. **Did all fixtures pass 3/3?** Yes, 8/8 fixtures.
6. **False acceptance?** 0.
7. **Positive false rejection?** 0.
8. **Fixture verifier errors?** 0. In the later shadow review, 12 errors occurred.
9. **Keyword taxonomy/fixture-specific hack added?** No.
10. **Was the 40-claim review run before fixture gate passed?** No.
11. **Was it run after the gate passed?** Yes, all 40 points, read-only.
12. **How many V1 SUPPORTED claims moved to PARTIAL/UNSUPPORTED?** 15 (13 PARTIAL, 2 UNSUPPORTED); 12 more became ERROR.
13. **Were Qdrant points modified?** No.
14. **MySQL writes?** 0.
15. **Embedding generated?** 0.
16. **Gemini called?** 0.

## Next step

Do not expand profiles. First diagnose and correct the generic Atomicizer structured-output/schema failure affecting shadow claims, especially FOOD_MENTION, without adding semantic keyword rules. Then rerun the bounded verifier shadow review before starting Generator changes. The 9571 fixture correction and successful fixture suite are useful, but do not override the 12/40 unresolved shadow outcomes.
