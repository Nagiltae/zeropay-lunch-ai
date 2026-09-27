# Semantic Profile Generator V2.2 — Source Semantics Review

## Final decision

**SEMANTIC PROFILE SOURCE CONTRACT = BLOCKED_SAFETY**

The source contract is not safe to freeze yet. Two REVIEW_KEYWORD claims passed
the existing deterministic and semantic gates as unqualified restaurant facts,
although the evidence only records customer evaluations. No Restaurant-level
run was started because the frozen source fixture gate failed.

## Audit and changes

V2.1 described REVIEW/REVIEW_KEYWORD generally as customer mentions or
evaluations, but did not provide an operational distinction among `FOOD_MENTION`,
`TASTE`, `DINING_CONTEXT`, and `VENUE_CHARACTERISTIC`. `FOOD_MENTION` was already
an existing shared ClaimType but had been omitted from the Generator contract;
without it, a bare customer food mention was liable to be phrased as official
sale under a menu ClaimType and then correctly rejected by the source/type
validator.

V2.2 adds that existing `FOOD_MENTION` to the generator contract for customer
REVIEW/REVIEW_KEYWORD sources only and clarifies the generic meanings of the
existing types. It also instructs the Generator to preserve explicit review
evaluation rather than reduce it to a bare food mention, preserve customer
attribution, and quote one short contiguous substring. No Validator was
loosened. MENU-only source compatibility stayed MENU-only; exact quote checks,
ownership/lifecycle checks and type-source validation were unchanged.
Atomicizer V2.2, Assertion Verifier V2.2, and the verdict aggregator were not
modified. No keyword dictionary, source quota, Restaurant-ID exception, or new
food taxonomy was added.

## Frozen fixture evaluations

All three snapshots reuse the same pre-existing frozen source rows and hashes.
Each snapshot's expectations were frozen before its Generator calls. The v1
artifact was intentionally preserved even though its broad semantic boundaries
did not constrain ClaimType. V2 added source/ClaimType boundaries. V3 retained
those boundaries and followed one generic prompt clarification; no expected
result was changed after seeing a result.

| Snapshot | MENU | REVIEW_KEYWORD | REVIEW | Pass | Main observation |
|---|---:|---:|---:|---:|---|
| v1 | 3/3 | 4/4 | 3/4 | 10/11 | One non-contiguous quote; customer-service ClaimType was misassigned |
| v2 | 3/3 | 4/4 | 1/4 | 8/11 | Food evaluations reduced to mention; venue statement became non-atomic |
| v3 | 3/3 | 4/4 | 1/4 | 8/11 | Same REVIEW coverage gap; two keyword claims exceeded customer-attribution scope |

V3 is the final bounded evaluation. Detailed generated output is in
`semantic_profile_generator_v22_fixture_results_v3.json`; the source and
expectations are in `semantic_profile_generator_v22_source_fixtures_v3.json`.

## Human source-boundary review — V3

All 11 generated claims were reviewed. Three MENU claims correctly describe
listed items. Four REVIEW_KEYWORD claims used the pre-existing, compatible
ClaimTypes and passed quote/semantic checks:

- Food-term signal: `고객 리뷰에서 꼼장어가 언급된다.` — source-correct `FOOD_MENTION`.
- Service signal: `고객 리뷰에서 친절함이 언급된다.` — customer-attributed
  `VENUE_CHARACTERISTIC`.
- Two solo-dining signals: `혼밥하기에 좋은 식당입니다.` — both were accepted by
  the existing gates, but omit that this is a customer evaluation. They convert
  an aggregate keyword signal into an unqualified restaurant attribute and are
  counted as source-scope false acceptances.

Of the four REVIEW fixtures, only the lunch-queue statement passed the frozen
type/atomicity boundary: `점심시간에는 줄이 길다.` It is a direct customer
experience (`DINING_CONTEXT`) and does not claim guaranteed service speed. A
food-evaluation review was reduced to a mention-only `FOOD_MENTION`; the explicit
evaluation was not preserved as `TASTE`. A venue review combined spaciousness
and comfortable dining into a two-assertion claim and was rejected as
`GENERATOR_NON_ATOMIC`.

| V3 metric | Result |
|---|---:|
| Fixture cases / pass | 11 / 8 |
| Generated claims | 11 |
| Generator / Atomicizer / Assertion Verifier calls | 11 / 11 / 10 |
| Approved by source before human source-boundary review | MENU 3, keyword 4, review 3 |
| Fixture ClaimType mismatches | 3 (all REVIEW cases) |
| Non-atomic claims | 1 |
| Exact quote mismatches | 0 |
| Unknown evidence IDs | 0 |
| Deterministic source/type mismatches | 0 |
| Verifier errors / retries | 0 / 0 |
| Source-scope false acceptances found by human review | 2 |
| Official-menu promotions found | 0 |
| Known historical overclaim approvals in this fixture set | 0 |

“Approved by source” is the validator/verifier output, not a claim that the
failed source-semantics fixture passed. The two solo-dining claims demonstrate
that exact quotes and a `SUPPORTED` verifier verdict alone do not ensure the
customer-evaluation attribution survives in claimText.

## Restaurant-level run and effects

The 3-Restaurant DRY-RUN was **NOT_RUN** because the frozen fixture gate failed.
No cohort member was dropped or replaced after seeing model output. The already
frozen cohort is 9568, 9569, and 10042; its source hashes matched the earlier
V2.1 frozen cohort. No Restaurant-level Generator/Atomicizer/Verifier calls
were made for this task.

- MySQL: 24 read queries during the initial source/cohort freeze; no writes.
  V2/V3 evaluations used frozen local artifacts.
- Qdrant reads/writes: 0 / 0.
- Embedding calls/writes: 0 / 0.
- Gemini calls: 0.
- Generator calls across the three fixture evaluations: 33.
- Atomicizer / Assertion Verifier calls: 32 / 30.
- Retries and terminal verifier errors: 0 / 0.
- Atomicizer V2.2 / verifier V2.2 / aggregator changes: none.
- Backend and frontend changes: none for this task.

## Answers to required questions

1. **Why did the prior Generator produce official-sale claims from keywords?**
   The old prompt lacked an operational ClaimType distinction, and the
   Generator lacked a source-correct `FOOD_MENTION` output path. The validator
   rejected that mismatch; it was not relaxed.
2. **Was the Validator loosened?** No.
3. **Was a REVIEW_KEYWORD promoted to official menu?** No official-menu claim
   was produced in V2/V3. However, two keyword evaluations were promoted to
   unqualified restaurant suitability claims and passed the verifier; this is
   the safety blocker.
4. **Were source-correct keyword claims generated and approved?** Yes: a food
   mention and a customer-attributed service evaluation. Two solo claims were
   not source-faithful in attribution and are not accepted by this review.
5. **Were source-correct REVIEW claims generated and approved?** Yes, one direct
   dining-context experience about the lunch queue. Review evaluation coverage
   remained limited; explicit food evaluation and a venue evaluation failed the
   frozen boundary.
6. **Did a customer source pass as an official fact?** Yes in the broader
   source-scope sense: two aggregate solo-dining evaluations became unqualified
   restaurant attributes. This triggers `BLOCKED_SAFETY`, even though no
   official-menu promotion occurred.
7–9. **Keyword taxonomy, source quota, Restaurant-specific exception?** No to
   all three.
10–12. **Approved claims exact-quoted, atomic, and SUPPORTED?** All claims marked
   approved by the pipeline had exact quote validation and a `SUPPORTED`
   verdict; the venue composite was rejected as non-atomic. Pipeline approval
   did not catch the two attribution overstatements.
13–15. **Known historical overclaim, Atomicizer/Verifier changes?** No known
   historical overclaim was in these fixtures; neither Atomicizer nor Verifier
   was modified.
16–18. **Qdrant writes, Embeddings, Gemini?** 0, 0, 0.

## Verification and next step

Targeted Generator tests: **21 passed**. `./scripts/check-ai.sh`: **PASS — 335
passed, 1 skipped** (one existing deprecation warning). Ruff: PASS. `git diff
--check`: PASS. Backend/frontend harnesses: NOT_REQUIRED (no changes to those
modules). Data-pipeline expansion, Embedding, and indexing remain
stopped. The specified bounded fixture work is complete; do not continue
prompt-tuning within this task. Record this attribution failure and move to the
separately scoped LangGraph work only after treating the source-grounding
limitation as an explicit constraint; do not consume these claims as approved
semantic profile data.
