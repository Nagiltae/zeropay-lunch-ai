# Semantic Profile Generator V2.1 — Small Expansion Review

## Final decision

**SEMANTIC PROFILE SMALL EXPANSION = BLOCKED_SOURCE_BIAS**

The frozen 8-Restaurant cohort completed one DRY-RUN. Korean sentence generation
and the existing grounding/verification gates worked for the approved claims,
but all 36 approved claims still came from MENU. No REVIEW_KEYWORD or REVIEW
claim was approved, despite abundant source evidence. The explicit Run 2 gate
requires at least some non-menu approved claims; therefore Run 2 was not run.

## Source bias audit and changes

The prior Generator V2 preserved the evidence catalog’s source-block order:
all MENU, then REVIEW_KEYWORD, then REVIEW. The prompt was asked for at most
five claims, allowing a menu-heavy opening segment to fill the output. Menu
listing claims were also simpler for the model to phrase literally. This is a
credible combined bias, not proof of a single cause.

V2.1 round-robins successful MENU / keyword / review evidence while preserving
within-source order. It uses Korean instructions, explicitly distinguishes
menu listings from customer evaluations/mentions, asks the model to consider
directly useful non-menu evidence without quotas, and raises the maximum from
5 to 8 without requiring the model to fill the cap. The claim schema, source
ownership checks, exact source quote validation, Atomicizer V2.2, and Assertion
Verifier V2.2 remain in force. A generic Korean-dominance check rejects English
boilerplate but permits Latin-script names in Korean prose.

The initial attempt stopped after exposing a shared Pydantic max-5 versus V2.1
max-8 mismatch. It is preserved separately; after aligning the model limit, the
completed Run 1 finished all eight Restaurants. The interrupted attempt is not
counted as a completed run.

## Frozen cohort and Run 1

The cohort was selected and frozen before any V2.1 Generator call. All 8 were
strict ProfileReady with current input/catalog hashes and MENU, REVIEW_KEYWORD,
and REVIEW evidence. IDs: `9568, 9569, 9570, 9574, 9580, 9659, 9801, 10042`.
The earlier 9559/9603/9639 pilot restaurants were excluded. No Restaurant was
replaced after seeing results.

| Restaurant | Generated | Approved | MENU approved | Keyword approved | REVIEW approved |
|---|---:|---:|---:|---:|---:|
| 9568 청기와 | 6 | 6 | 6 | 0 | 0 |
| 9569 산곰장어 | 6 | 0 | 0 | 0 | 0 |
| 9570 블러프 | 7 | 5 | 5 | 0 | 0 |
| 9574 청담머구리 | 8 | 8 | 8 | 0 | 0 |
| 9580 빨간모자피자 | 6 | 3 | 3 | 0 | 0 |
| 9659 만석 | 8 | 2 | 2 | 0 | 0 |
| 9801 공리 | 6 | 6 | 6 | 0 | 0 |
| 10042 주래등 | 6 | 6 | 6 | 0 | 0 |
| **Total** | **53** | **36** | **36** | **0** | **0** |

The generated source counts are overlapping: 47 claims cited at least one MENU
Evidence, 8 cited at least one keyword Evidence, and 0 cited REVIEW Evidence.
Two claims cited both MENU and keyword evidence. All 53 outputs used
`MENU_CHARACTERISTIC`; the six keyword-only claims and two mixed-source claims
were rejected because the generated type/source contract did not match and/or
their quotes were incomplete. In particular, Restaurant 9569 produced six
keyword-backed “official sale” claims, all rejected by the deterministic
source-type gate. This is not a successful review/keyword Claim path.

## Quality and source review

- Korean-dominant: 53/53 (100%); English-dominant: 0.
- Schema errors: 0 in completed Run 1.
- Deterministic pass: 43/53; deterministic failures: 10.
- Exact quote pass: 49/53; quote mismatch: 0; missing quote accounts for
  failures. All 36 approved Claims have exact quotes from their cited MENU row.
- Unknown Evidence IDs: 0; provenance leakage: 0; duplicate claims: 0.
- Atomicizer calls: 43; non-atomic: 4.
- Assertion verifier calls: 39; SUPPORTED: 36; UNSUPPORTED: 3; verifier errors: 0.
- All 36 approved claims were atomic and SUPPORTED by V2.2.
- No review-derived claim was approved; human review count for approved REVIEW
  claims is therefore zero. Five MENU approvals were manually checked across
  Restaurants and source forms; their exact cited menu text supports the named
  listing. The first Restaurant’s generated prefix “청기에는” is malformed
  Korean for its actual name “청기와”; it remains a language-quality defect
  even though the menu item evidence is valid. This shows the generic language
  guard checks language dominance, not fluency or entity-name correctness.
- Manual review of all 53 generated claims found zero of the known historical
  overclaim patterns among approved output. Non-menu claims that implied
  official sale were rejected by the source-type validator.
- No source quota, semantic keyword dictionary, Restaurant-ID mapping, or
  taxonomy rule was added.

## Claim/source examples

Approved MENU example:

> Claim: “공리에는 차돌짬뽕 메뉴가 있습니다.”
> Evidence quote: “차돌짬뽕/밥”

This is a Korean menu-listing statement with a verbatim source quote.

Rejected keyword example:

> Claim: “산곰장어는 꼼장어를 판매합니다.”
> Evidence type: REVIEW_KEYWORD (`꼼장어`)
> Rejection: `EVIDENCE_SOURCE_TYPE_NOT_ALLOWED`

The keyword source is a customer mention signal, not proof of official menu
status. The fail-closed rejection is correct; the Generator’s source semantics
and claim type selection still need improvement.

## Run 2

Run 2 was **not run**. Although the structural/safety gate was clean enough for
human inspection, there were zero non-menu approved claims. The user-defined
Run 2 precondition was not met, so no second generator pass was made.

## Side effects and verification

- MySQL reads: 208 SELECT statements estimated from the fixed 8-query
  `build_input` path: 64 cohort freeze + 64 source inspection + 64 completed
  Run 1 + 16 interrupted attempt. MySQL writes: 0.
- Qdrant reads/writes: 0 / 0.
- Embedding calls/writes: 0 / 0.
- Gemini calls: 0.
- Qwen calls: 10 total across attempts: 2 started in the interrupted attempt
  (one response completed, one request interrupted) plus 8 completed Run 1
  requests. The interrupted first Restaurant response yielded zero validated
  claims; raw output was intentionally not retained, so its exact parse/empty
  cause is unknown.
- Model: `qwen3.5:9b`, temperature 0.
- Targeted tests: PASS; Ruff: PASS. `./scripts/check-ai.sh`: PASS — 330 passed,
  1 skipped, 1 third-party deprecation warning.
- Backend / Frontend harness: NOT_REQUIRED (no code changes in those modules).
- `git diff --check`: PASS. All four generated JSON artifacts parse successfully.
- Secret scan of V2.1 artifacts: no Gemini API key-pattern match.

## Answers

1. V2’s source-block ordering and five-claim cap plausibly reinforced MENU
   selection. In V2.1, source interleaving alone did not fix it; model/source
   type mismatch also caused keyword outputs to fail closed.
2. Yes, all 53 parsed claims were Korean-dominant; one approved Restaurant-name
   prefix was malformed and is called out above.
3. No. Quotes were checked against raw source; none was translated. All approved
   quotes are exact evidence substrings.
4. No REVIEW_KEYWORD Claim was approved. Eight generated claims cited keywords;
   all were rejected.
5. No REVIEW Claim was generated or approved.
6. Yes. All eight restaurants had review/keyword evidence, and the model still
   produced zero non-menu approvals.
7. No source ratios or quotas were enforced.
8. No keyword taxonomy was added.
9. Yes. All 36 approved Claims yielded exactly one Atomicizer assertion.
10. Yes. All 36 approved Claims received `SUPPORTED`.
11. No known historical overclaim was approved in the completed output.
12. No review mention was approved as an official menu fact. Such generated
    cases were rejected by source-type validation.
13. No. Atomicizer and Verifier V2.2 were unchanged.
14. No Qdrant writes.
15. No embeddings.
16. No Gemini calls.

## Next step

Do not expand Profiles or run a second pass under this cohort. Improve the
generic Generator prompt’s source/claim-type contract so it can express
customer evaluations and contexts as customer evaluations without treating
keyword mentions as official-menu facts. Then add focused offline contract
tests and run a separately frozen bounded evaluation. No source quotas or
keyword-to-claim code should be introduced.
