# Semantic Profile Generator V2 Review

## Result

**SEMANTIC PROFILE GENERATOR V2 = READY_FOR_SMALL_EXPANSION**

The bounded DRY-RUN passed the stated safety and usefulness gates for this three-Restaurant cohort. This is not authorization to persist, embed, index, or expand to all ProfileReady Restaurants.

## Frozen cohort and execution

The cohort was frozen before any Generator call: 9559 모우리, 9603 본죽&비빔밥 논현점, 9639 이자카야나무(논현). Current READ-ONLY DB/ProfileReadiness checks passed for all three. Frozen source hashes matched on both inference runs. There was no cohort substitution.

Two independent runs were allowed after run1 passed structure/quote checks and human review found no known overclaim approval. Each run made one Generator call per Restaurant. Both runs produced the same 15 claim texts, Evidence IDs and exact supportQuotes.

The total of 26 approvals below counts repeated approvals across the two runs. Since the candidate payloads were identical, there are **13 unique approved claims** across the frozen cohort, revalidated in both runs.

| Metric | Run 1 | Run 2 | Total |
|---|---:|---:|---:|
| Restaurants | 3 | 3 | 3 unique |
| Generator candidates | 15 | 15 | 30 |
| Schema-valid candidates | 15 | 15 | 30 |
| Deterministic validation pass | 15 | 15 | 30 |
| Exact supportQuote pass | 15 | 15 | 30 |
| Non-atomic rejected | 2 | 2 | 4 |
| Semantic SUPPORTED | 13 | 13 | 26 |
| Semantic UNSUPPORTED / PARTIAL | 0 / 0 | 0 / 0 | 0 / 0 |
| Approved | 13 | 13 | 26 |
| Unknown Evidence / quote mismatch / provenance leak | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Atomicizer/verifier errors; retries | 0; 0 | 0; 0 | 0; 0 |

By Restaurant, both runs approved: 9559 **3/5** (two compound claims rejected), 9603 **5/5**, 9639 **5/5**. Each has at least one usable approved claim. All 26 approved claims have exactly one Atomicizer assertion and a SUPPORTED verifier verdict.

The four rejected candidates were two repeated 9559 descriptions that combined menu presence with a popularity/limited-status assertion; V2.2 decomposed each into two assertions, so they were rejected rather than weakened or auto-rewritten.

## Human review and known overclaims

The approved set consists only of source-backed menu statements. Examples include 9559's listed signature-item names; 9603's menu entries explicitly marked `[NEW]`, `[시즌한정]` or `[아침추천]`; and 9639's listed dishes/set entries. Their quotes are copied from the cited menu row; no price or new menu item is generated. Both runs happened to emit English claim sentences with Korean menu names, and did not select any available review/keyword Evidence. This is usable menu coverage, but not yet evidence of broad Korean review-feature coverage; language/source diversity should be assessed in the next cohort.

No claim in either run asserted tenderness/juiciness, corporate/family event suitability, spacious layout, cooking/preparation quality, unsupported menu combinations, or combined solo/cleanliness attributes. Consequently known-overclaim false acceptance among approved claims is **0**. This safety result partly reflects conservative source selection: despite review Evidence being available, the Generator selected only menu Evidence in this pilot. The result demonstrates grounded menu claims, not broad coverage of review-derived dining/taste features. No review mention was promoted to an official menu fact.

The `claimText` values contain no `근거:`, `Evidence:`, ClaimType prefix or Evidence IDs. Provenance remains in separate `evidenceIds` and `supportQuotes` fields. One nuance from the audit: legacy `근거:` text was appended by the downstream embedding-text serializer (`_normalized_text()`), not by the old Generator's raw claim `text`. This task fixes the Generator contract and leaves that legacy serializer/runtime untouched.

## Calls and side effects

- Generator calls: **6** (3 Restaurants × 2 runs).
- Atomicizer calls: **30**; assertion-verifier calls: **26**; retries: **0**.
- MySQL SELECT queries: **96 total** — initial current-state check, cohort freeze, and pre-inference source/hash revalidation for each of the two runs (24 per three-Restaurant pass). MySQL writes: **0**.
- Qdrant reads/writes: **0 / 0**. Embedding calls/writes: **0 / 0**. Gemini calls: **0**.
- No Profile artifact, runtime, serving, or recommendation data was persisted.

## Verification

Targeted Generator + V2.2 quality-gate tests: **51 passed**. Full `./scripts/check-ai.sh`: **325 passed, 1 skipped** (the live semantic runtime test), with one third-party deprecation warning. Ruff passed for changed Python files and `git diff --check` passed. Backend and frontend harnesses are not required; those modules were not changed. The existing V2.2 frozen verifier fixtures remain unchanged.

## Next step

Expand only to a separate 5–10 Restaurant offline cohort after reviewing the multilingual/menu-heavy output limitation and preserving current safety gates. Continue artifact-only DRY-RUN first. Do not create embeddings or Qdrant points until that broader cohort demonstrates useful, diverse, evidence-supported Claims and receives a separate approval decision.
