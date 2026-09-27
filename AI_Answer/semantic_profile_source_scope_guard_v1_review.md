# Semantic Profile Source Scope Guard V1 — Review

## Final decision

**SEMANTIC PROFILE SOURCE SCOPE GUARD = READY_FOR_DATA_PIPELINE_FREEZE**

Python derives provenance from resolved Evidence source types; neither the
Generator nor the verifier supplies it. Customer-derived raw text is retained
for audit but cannot be passed to the profile embedding loader. All 11 frozen
V3 source cases were reevaluated without model calls.

## Guard contract

| Evidence sources | `sourceScope` | Search representation |
|---|---|---|
| MENU only (`menu`) | `LISTING_FACT` | Validated raw `claimText` |
| REVIEW / REVIEW_KEYWORD only (`review`, `keyword`) | `CUSTOMER_REPORTED` | `고객 리뷰 기반 정보: {claimText}` |
| MENU + customer source | `MIXED` | `indexable=false`, `MIXED_SOURCE_SCOPE` |
| empty / unknown source | `UNKNOWN` | `indexable=false`, `UNKNOWN_SOURCE_SCOPE` |

`semanticApproved` preserves the existing verifier's result. `indexable` is a
separate decision requiring deterministic validation, exact quote validity, a
SUPPORTED semantic verdict, exactly one assertion, a recognized non-mixed
scope, and a non-empty safe `searchText`. The `indexText` field is populated
only for an indexable claim. No source semantics are inferred from claim words.

The embedding loader and historical claim/tenth/hybrid-v2 point builders now
call `embedding_text_from_indexable_claims()` and have no raw
`text`/`claimText`/`normalizedClaimText` fallback. Legacy profiles without the
new scope and indexability metadata, plus derived review-keyword candidates
without semantic approval, fail closed before the first embedding API call.

## Eleven fixture results

| Fixture | Source | Scope | Semantic | Assertions | Indexable | Safe search text |
|---|---|---|---|---:|---|---|
| menu-9568-1 | MENU | LISTING_FACT | SUPPORTED | 1 | yes | 메뉴에 순대국이 등록되어 있습니다. |
| menu-9569-1 | MENU | LISTING_FACT | SUPPORTED | 1 | yes | 산곰장어가 메뉴에 등록되어 있습니다. |
| menu-10042-1 | MENU | LISTING_FACT | SUPPORTED | 1 | yes | 메뉴에 고추짬뽕이 있습니다. |
| keyword-food-mention | REVIEW_KEYWORD | CUSTOMER_REPORTED | SUPPORTED | 1 | yes | 고객 리뷰 기반 정보: 고객 리뷰에서 꼼장어가 언급된다. |
| keyword-solo-9568 | REVIEW_KEYWORD | CUSTOMER_REPORTED | SUPPORTED | 1 | yes | 고객 리뷰 기반 정보: 혼밥하기에 좋은 식당입니다. |
| keyword-service-9568 | REVIEW_KEYWORD | CUSTOMER_REPORTED | SUPPORTED | 1 | yes | 고객 리뷰 기반 정보: 고객 리뷰에서 친절함이 언급된다. |
| keyword-solo-10042 | REVIEW_KEYWORD | CUSTOMER_REPORTED | SUPPORTED | 1 | yes | 고객 리뷰 기반 정보: 혼밥하기에 좋은 식당입니다. |
| review-food-experience | REVIEW | CUSTOMER_REPORTED | SUPPORTED | 1 | yes | 고객 리뷰 기반 정보: 고객 리뷰에서 꼼장어가 언급된다. |
| review-venue-context | REVIEW | CUSTOMER_REPORTED | not approved | 2 | no | 고객 리뷰 기반 정보: 매장이 넓어서 편하게 식사 가능했다. |
| review-taste-9568 | REVIEW | CUSTOMER_REPORTED | SUPPORTED | 1 | yes | 고객 리뷰 기반 정보: 고객 리뷰에서 청국장이 언급된다. |
| review-quick-meal | REVIEW | CUSTOMER_REPORTED | SUPPORTED | 1 | yes | 고객 리뷰 기반 정보: 점심시간에는 줄이 길다. |

The two previously unsafe solo-dining claims preserve their original
`semanticApproved=true` result, but the only indexable representation has the
generic customer-review attribution prefix. The raw unqualified claim is not
the index text. `sourceScopeFalseAcceptanceCount=0` and
`unscopedCustomerTextCount=0`. No customer-derived claim was assigned
`LISTING_FACT`; official/listing promotion count is 0.

The REVIEW limitations remain visible and were not “fixed” with new prompting:
explicit food evaluations were sometimes reduced to a mention-only claim, and
one venue statement was non-atomic. The latter is non-indexable. Mention-only
claims that are themselves supported remain customer-scoped, not listing facts.

## Metrics

| Metric | Result |
|---|---:|
| Fixtures evaluated | 11/11 |
| `LISTING_FACT` / `CUSTOMER_REPORTED` / `MIXED` / `UNKNOWN` | 3 / 8 / 0 / 0 |
| Semantic supported / not approved | 10 / 1 |
| Indexable / non-indexable | 10 / 1 |
| Customer-reported indexable | 7 |
| Source-scope false acceptance / unscoped customer text | 0 / 0 |
| Official/listing promotion false acceptance | 0 |
| Mixed / unknown rejected | 0 fixture rows; both policies pass targeted tests |
| Non-atomic / quote mismatch / verifier error | 1 / 0 / 0 |

The semantic “not approved” count includes the two-assertion venue claim, which
did not reach assertion verification; it is not a verifier rejection.

## Required answers

1. **Who derives `sourceScope`?** Deterministic Python, from resolved source
   types.
2. **Can the LLM set or override it?** No; it is absent from the Generator
   schema.
3. **MENU-only scope?** `LISTING_FACT`.
4. **REVIEW/REVIEW_KEYWORD-only scope?** `CUSTOMER_REPORTED`.
5. **Mixed MENU/customer evidence?** `MIXED`, non-indexable.
6. **Can raw customer `claimText` be embedded?** No. Only the prefixed
   `searchText` is accepted by the embedding text helper.
7. **Are the two solo claims still indexable without provenance?** No. They
   have customer-attributed `searchText`; their raw strings are retained only
   as claim records.
8–9. **Atomicizer / verifier changed?** No.
10. **Generator prompt retuned?** No.
11–12. **Keyword taxonomy / Restaurant-ID rules?** None.
13. **Profile expansion?** No.
14–16. **Embedding / Qdrant write / Gemini?** 0 / 0 / 0.

## Calls and side effects

The frozen V3 artifact was reused; this task made **0 Generator, 0 Atomicizer,
0 Assertion Verifier calls, and 0 retries**. It performed **0 MySQL reads and
writes**, **0 Qdrant reads and writes**, **0 Embedding calls and writes**, and
**0 Gemini calls**. The prior V3 Generator calls are historical input to this
evaluation, not calls made by the scope-guard task.

## Verification and handoff

Targeted source-scope, embedding-loader, legacy claim-builder, hybrid guard,
and Generator tests: **42 passed**. Full `./scripts/check-ai.sh`: **PASS — 348
passed, 1 skipped** (one existing Starlette deprecation warning). Focused Ruff
checks passed for import/name errors across touched modules and line length in
new scope-guard files. An unrestricted Ruff check of the historical claim/tenth
pilot modules reports numerous pre-existing long-line/style findings; those
were not mass-formatted as unrelated legacy code. `git diff --check`: PASS.
Backend/frontend harnesses: NOT_REQUIRED. The embedding-loader regression
test confirms legacy unscoped artifacts fail before embedding.

The data pipeline can now be frozen as **EXPERIMENTAL / FROZEN**: do not expand
Profiles or index legacy claims. Future indexing must consume only guard-
approved `searchText`. The next separate task may move to LangGraph with that
boundary enforced. REVIEW quality/usefulness limitations remain documented and
must not be represented as broader coverage than the evidence supports.
