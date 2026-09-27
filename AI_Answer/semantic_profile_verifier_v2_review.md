# Semantic Profile Verifier V2 — Review

Date: 2026-09-26 (Asia/Seoul)

## Result

**SEMANTIC PROFILE VERIFIER V2 = BLOCKED_REGRESSION**

V2 resolves the central 9568 failure: its four atomic assertions aggregate to `PARTIAL` in all three runs, so the unsupported “comfortable casual meal” assertion cannot make the full claim indexable. But the 9571 fixture is consistently over-rejected as wholly `UNSUPPORTED` rather than the required `PARTIAL`. Because an expected verdict boundary failed, the frozen 40-claim Qdrant shadow rerun was not performed.

## V1 audit and V2 design

V1 sent each whole claim plus its Evidence to one model call and accepted a model-selected 3-way result. `supportedPortion` and `unsupportedPortion` were diagnostic strings only; no code decomposed or aggregated assertions. Thus V1 could report the 9568 composite claim as SUPPORTED after treating the supported solo/group/spacious portions as representative of the whole claim. V1 had a PARTIAL enum but no mechanical way to require mixed assertion outcomes to become PARTIAL.

The two prior point-level `ValueError`s are not diagnosable more precisely from V1 artifacts: the runner recorded only the exception class and suppressed the exception message/raw output. V1 parser source shows possible invalid-output/schema and unknown-evidence-ID branches, but the saved data cannot distinguish them. V2 now uses categorized safe errors.

V2 has two separate model prompts/contracts: an Evidence-blind Atomicizer and a per-assertion binary Evidence verifier. Atomicization validates 1–8 unique assertions and source spans; Stage B independently checks each assertion against source type/raw Evidence. Python aggregates all-SUPPORTED → SUPPORTED, mixed → PARTIAL, all-UNSUPPORTED → UNSUPPORTED. Any stage error becomes VERIFIER_ERROR and is non-indexable. PARTIAL is never requested from the model. The model remained `qwen3.5:9b`, temperature 0; one retry maximum is permitted after a call/schema error.

## Frozen fixture results

Four negative/mixed and three positive fixtures were frozen before V2 runs with Evidence snapshots, catalog hashes, exact source quotes and expected verdicts.

| Fixture | Expected | Run 1 | Run 2 | Run 3 | Outcome |
|---|---|---|---|---|---|
| 9559 deliciousness → tenderness | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | PASS |
| 9559 group → corporate/family | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | PASS |
| 9571 menu names → chicken topping | PARTIAL | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | FAIL: over-rejection |
| 9568 solo/group/spacious → casual comfort | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS |
| 9617 listed menu items | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | PASS |
| 9617 solo/quick meal evidence | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | PASS |
| 9617 friendly review keyword | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | PASS |

Final corrected suite metrics: 7 fixtures × 3; 4 negative/mixed, 3 positive; false acceptance 0; positive false rejection 0 (9/9 positive runs accepted); expected PARTIAL cases 6 runs, correct 3/6; atomicizer errors 0; verifier errors 0; 21 atomicizer calls + 48 assertion checks = 69 Qwen calls; retries 0; elapsed 196.4 seconds. All verdicts were stable across the three runs, but stability alone does not satisfy the expected boundary for 9571.

For 9571 the Atomicizer separated beef, chicken, and vegetable assertions, but the Evidence verifier returned UNSUPPORTED for all three. Thus the mixed assertion was collapsed to all-unsupported, not PARTIAL. The fixed 9568 decomposition was A1 solo dining SUPPORTED, A2 group dining SUPPORTED, A3 spacious SUPPORTED, A4 comfortable casual meal UNSUPPORTED; Python correctly aggregated PARTIAL. No word-specific code or keyword taxonomy was added.

## Diagnostic attempts and side effects

The first execution stopped after one local model response because the runner's error counter raised `KeyError`; that call produced an Atomicizer schema error and no accepted result. The first 3-run diagnostic suite then made 69 Qwen calls (21 atomicizer, 48 assertion-verifier), with 12 bounded retries and 24 schema errors because unsupported results were incorrectly required to cite at least one Evidence ID. It is preserved in `semantic_profile_verifier_v2_*_schema_diagnostic.json` and was superseded after correcting the contract. The final corrected suite made another 69 calls. Total local Qwen requests across these attempts: 139 (43 Atomicizer, 96 assertion-verifier); total retries 12. The final-suite metrics remain separately reported in the primary metrics artifact.

Other side effects: MySQL reads/writes 0; Qdrant reads/writes 0 in V2 (fixtures use frozen source snapshots); embedding calls 0; Gemini calls 0. Existing v12 points and the V1 artifacts were not modified. No Generator prompt, runtime, ranking, Spring, React, SSE or serving policy changes were made. Support quotes were not backfilled into any existing claims.

## Full 40-point review

**NOT RUN.** The 9571 regression did not meet the required PARTIAL verdict, so the conditional gate prohibits the 40-claim rerun. `semantic_profile_verifier_v2_shadow_review.json` records this status; V1→V2 transition metrics are not computed.

## Harness

- Targeted quality-gate tests: PASS, 25 passed.
- `./scripts/check-ai.sh`: PASS, 299 passed, 1 skipped; one existing third-party deprecation warning.
- Targeted quality-gate tests: PASS, 25 passed.
- Ruff: PASS for the new verifier module, runner and targeted tests.
- `git diff --check`: pending final final-tree check.
- Backend/frontend harness: NOT_REQUIRED; no backend/frontend changes.

## Q1–Q15

1. V1 accepted the 9568 composite because it judged one sentence holistically with a single verdict; no mandatory per-assertion check or code aggregation existed. Diagnostic portions did not affect approval.
2. V2 decomposes claims into Atomic Assertions and validates source spans.
3. Does the LLM choose PARTIAL? **NO.** Python aggregates binary assertion outcomes.
4. 9568 final verdict: **PARTIAL in 3/3 runs.**
5. 9571 chicken-topping final verdict: **UNSUPPORTED in 3/3, expected PARTIAL; regression failure.**
6. 9559 tenderness: **UNSUPPORTED in 3/3.**
7. 9559 corporate/family: **UNSUPPORTED in 3/3.**
8. Positive fixtures all SUPPORTED? **YES, 3/3 each (9/9 runs).**
9. Did any known overclaim become SUPPORTED in the corrected 3-run suite? **NO.**
10. Can verifier errors approve a claim? **NO; error is fail-closed.**
11. Was keyword taxonomy added? **NO.**
12. Were existing Qdrant points modified? **NO.**
13. Was MySQL modified? **NO.**
14. Was Gemini called? **NO.**
15. If stable, what is next? After fixing the 9571 partial boundary and passing all fixture gates, the next step is a separate max-3-Restaurant DRY-RUN of Generator → atomic claims/exact quotes → deterministic validation → V2 verifier. It is not authorized by this blocked result.

## Next action

Do not run the 40-point review or expand profiles. Improve the general menu-name entailment boundary so explicitly listed menu items can support only the item-name facts they literally contain, while the unsupported chicken assertion remains UNSUPPORTED. Keep this rule general and source-semantic; do not add fixture-specific words or Restaurant IDs. Then freeze a new fixture version and repeat the 3× suite.
