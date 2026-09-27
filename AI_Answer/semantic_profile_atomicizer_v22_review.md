# Semantic Profile Atomicizer V2.2 Review

## Final status

**SEMANTIC PROFILE ATOMICIZER V2.2 = READY_FOR_GENERATOR_FIX**

The status means the Atomicizer contract is stable on the frozen reproductions and fixtures, and the read-only 40-point shadow completed without terminal errors. It does not approve legacy points for indexing or authorize Profile expansion.

## Root cause and change

All 12 V2.1 Atomicizer failures had valid JSON and valid schema. They failed the later exact `sourceSpan` check because the model paraphrased the Claim fragment. The earlier `SCHEMA_ERROR` label conflated parsing/schema and deterministic trace validation. FOOD_MENTION accounted for 10 cases, with one DINING_CONTEXT and one TASTE; evidence supports a common contract problem, not a ClaimType-specific semantic defect.

V2.2 asks the model for assertion text plus bounded token indices. Python constructs IDs and exact source spans from the original Claim, validates limits/ranges/duplicates, and preserves source order. One generic correction retry is bounded. No keyword taxonomy, ClaimType-specific rule, Restaurant-specific logic, or Generator change was added.

## Gates

| Gate | Result |
|---|---:|
| Failure corpus | 12 claims × 3 = 36/36 successful; terminal errors 0; retry 0 |
| Frozen fixtures | 8 × 3 = 24/24 pass |
| Negative / mixed expectations | 9559 negatives UNSUPPORTED 3/3 each; 9568 PARTIAL 3/3; 9571 topping-composition UNSUPPORTED 3/3; listed-menu mixed case PARTIAL 3/3 |
| Positive expectations | 3 fixtures SUPPORTED 3/3 each |
| False acceptance / positive false rejection | 0 / 0 |
| Fixture Atomicizer / assertion-verifier errors | 0 / 0 |
| Gated shadow | 40 points; terminal ERROR 0 |

The 9571 topping-composition result remains conservative: menu names do not establish the asserted topping composition. The separate mixed fixture tests a directly evidenced listed item plus an explicitly unsupported item.

## 40-point read-only shadow

| Verdict | Count |
|---|---:|
| SUPPORTED | 5 |
| PARTIAL | 29 |
| UNSUPPORTED | 6 |
| ERROR | 0 |

V1→V2.2 transitions: SUPPORTED→SUPPORTED 5, SUPPORTED→PARTIAL 25, SUPPORTED→UNSUPPORTED 3, ERROR→PARTIAL 1, ERROR→UNSUPPORTED 1, UNSUPPORTED→PARTIAL 3, UNSUPPORTED→UNSUPPORTED 2. In particular, SUPPORTED→ERROR is zero. FOOD_MENTION: 16 total, 15 PARTIAL, 1 UNSUPPORTED, 0 ERROR.

Type breakdown: DINING_CONTEXT 2 SUPPORTED / 2 PARTIAL; FOOD_MENTION 15 PARTIAL / 1 UNSUPPORTED; FOOD_TYPE 4 PARTIAL; MENU_CHARACTERISTIC 2 PARTIAL / 3 UNSUPPORTED; TASTE 2 SUPPORTED / 5 PARTIAL; VENUE_CHARACTERISTIC 1 SUPPORTED / 1 PARTIAL / 2 UNSUPPORTED. Source counts overlap because a Claim may cite multiple source types: keyword 5/23/3 (S/P/U), menu 0/6/3, review 1/0/0.

Representative reading:

- SUPPORTED: group gathering + spacious venue (9569) decomposed into two separately supported assertions.
- PARTIAL: menu Claim listing 김밥 and 떡볶이 (9617) produced one supported menu statement plus an unsupported provenance-tail assertion. This is over-decomposition of legacy Claim formatting, not a new factual approval.
- UNSUPPORTED: “friendly staff service” (9580) was not established by the cited evidence in the resolved source set.
- FOOD_MENTION: “customer review keyword mentions 떡볶이” (9617) retained the review-mention meaning and was supported; the appended “not an official menu” clause was unsupported because absence of a MENU row is not positive evidence of non-sale.

The `근거:` tail issue is disclosed rather than hidden. It can inflate PARTIAL/UNSUPPORTED among legacy Claims. All 40 remain `indexableUnderCurrentPolicy=false` because they have no stored exact supportQuote. The shadow verdicts diagnose verifier behavior; they do not re-approve the existing Qdrant data.

## Calls and side effects

- Failure corpus Atomicizer: 36 calls, 0 retry.
- Frozen fixture suite: 24 Atomicizer + 48 assertion-verifier calls; 72 local Qwen calls total, 0 retry.
- 40-point shadow: 41 Atomicizer + 99 assertion-verifier calls; 140 local Qwen calls, 1 bounded retry.
- Across these final gates: 101 Atomicizer + 147 assertion-verifier = 248 local Qwen calls; one retry total.
- Qdrant: 40 reads, 0 writes.
- MySQL reads/writes: 0 / 0.
- Embeddings: 0. Gemini: 0.
- Generator changes/Profile expansion: none.

## Verification

Targeted quality-gate tests: **39 passed**. Full `./scripts/check-ai.sh`: **313 passed, 1 skipped** (the live semantic runtime test), one third-party deprecation warning. Ruff passed for the changed Python files. `git diff --check` is recorded after artifact validation. Backend and frontend harnesses were not required because neither module was changed. Runtime, ranking, and serving paths were not changed.

## Next step

Proceed only to a separate bounded Generator-fix task: produce atomic claims with Evidence IDs and exact supportQuotes, then DRY-RUN at most three Restaurants through deterministic validation and Verifier V2.2. Keep database, embedding, and Qdrant writes at zero for that initial pilot.
