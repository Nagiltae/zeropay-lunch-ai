# Semantic Profile Evidence-Grounded Quality Review

Audit date: 2026-09-26 (Asia/Seoul)

## Outcome

**SEMANTIC PROFILE QUALITY = BLOCKED_VERIFIER**

The deterministic evidence resolver and exact-quote checks work, but the independent semantic verifier is not reliable enough to authorize profile expansion: one frozen known-overclaim fixture was incorrectly marked `SUPPORTED` and indexable. No new profiles were generated and no existing index data was changed.

## Existing pipeline and its gap

The current flow is `semantic_profile_shadow.build_input()` (MySQL SELECT) → Python `build_evidence_catalog()` → local Qwen claim generation → schema/source/lifecycle validation → approved claim artifact → hybrid point construction and embedding/indexing. Evidence IDs are assigned by Python. Generated claims may cite several evidence items and currently have no `supportQuotes` field. Existing validation checks schema, ID existence, allowed claim/source combinations, lifecycle and some claim-type rules; it does not test semantic entailment. See [semantic_profile_quality_current_state.md](semantic_profile_quality_current_state.md).

Consequently, a real Evidence ID does not establish that the wording is supported. “Reviews say it is delicious” does not entail tenderness, and “good for group gatherings” does not entail a spacious room or suitability for corporate/family occasions.

## New shadow gate

- Deterministic validation verifies schema, claim type/length, restaurant ownership, evidence resolution/source/status/raw text, duplicate claims, and exact support quotes. Quote comparison permits whitespace normalization only.
- An independent local verifier sees the claim and source Evidence only—not generator rationale, confidence, approval state, or old index status. It returns structured `SUPPORTED`, `PARTIAL`, or `UNSUPPORTED` plus short diagnostics.
- Indexability requires deterministic PASS, exact-quote PASS, and semantic `SUPPORTED`. `PARTIAL`, `UNSUPPORTED`, missing/invalid quotes, invalid Evidence, malformed verifier output, and verifier errors all fail closed.
- Claims should be atomic; source semantics must remain explicit (for example, review mention is not proof of an official menu). Feature text remains open-ended; no exhaustive dining/taste keyword taxonomy or keyword scoring was added.

The verifier used the existing local model `qwen3.5:9b`; this was a separate verifier prompt/call, not a model-selection experiment. No Generator prompt rewrite or optional three-restaurant generation pilot was performed.

## Frozen v12 shadow review

Qdrant `zeropay_semantic_claim_pilot_v12` was read-only. The live collection contained 40 points and matched the frozen indexing manifest exactly (40/40; no mismatches). Its schema is 1024-dimensional cosine. The 40 point Restaurant IDs were 9617, 9731, 9567, 9580, 9568, 9569, 9570, 9571, 9574, and 9590. All 40 Evidence references resolved to hash-verified catalogs belonging to the same Restaurant; invalid Evidence count was 0.

| Shadow verdict | Count |
|---|---:|
| SUPPORTED | 33 |
| PARTIAL | 0 |
| UNSUPPORTED | 5 |
| Verifier error | 2 |

All 40 legacy points lack persisted support quotes: exact quote passes 0/40, missing quote 40/40, and indexable under the new contract 0/40. This is not retroactively repaired by manufacturing quotes. Structural Evidence validity and semantic support are separate measurements.

Claim type counts (SUPPORTED / PARTIAL / UNSUPPORTED / ERROR):

| Claim type | Counts |
|---|---|
| DINING_CONTEXT | 3 / 0 / 1 / 0 |
| FOOD_MENTION | 16 / 0 / 0 / 0 |
| FOOD_TYPE | 2 / 0 / 1 / 1 |
| MENU_CHARACTERISTIC | 1 / 0 / 3 / 1 |
| TASTE | 7 / 0 / 0 / 0 |
| VENUE_CHARACTERISTIC | 4 / 0 / 0 / 0 |

Evidence-source counts overlap when one claim cites multiple source types: keyword 30 supported/1 unsupported; menu 3 supported/4 unsupported/2 verifier errors; review 1 supported. The artifact marks these source denominators as overlapping, so they must not be summed as unique claims.

The measured semantic overclaim rate among returned verdicts is `(PARTIAL + UNSUPPORTED) / 40 = 12.5%`; the two verifier errors are separately reported and fail closed. The diagnostic approval rate of 82.5% (`SUPPORTED / 40`) is **not** an approval rate for indexing because quote validation fails for every legacy claim.

## Known regression fixtures

Four source-bound fixtures were frozen before the final verifier run. Two were classified as expected non-support and blocked. One tenderness fixture returned a verifier error (therefore safely non-indexable, but not a successful semantic regression classification). Most importantly, the 9568 composite claim (“solo/group dining, spacious, comfortable casual meal”) was marked `SUPPORTED` and indexable despite the evidence not supporting every assertion. This is a critical false acceptance and establishes `BLOCKED_VERIFIER`.

The 9571 chicken-topping fixture was returned as `UNSUPPORTED`; the verifier did not use `PARTIAL` for its supported/unsupported portions. This did not make it indexable, but also indicates the requested three-way boundary needs stronger validation. Known regression cases did **not** all pass safely.

## Artifact provenance and execution

The first pass is preserved as `*_diagnostic_v1.json`. It is superseded because its verifier prompt omitted keyword source metadata such as mention counts, and one fixture had a stale lifecycle snapshot. The final artifacts use the corrected source-bound frozen fixture and include source metadata in verifier input. The first-pass artifacts were not deleted or overwritten.

Final pass: 40 existing claims + 4 regression cases, 44 local Qwen generation/verifier requests, sequential, no retries; elapsed time approximately 185.6 seconds. The final artifacts are [semantic_profile_shadow_review.json](semantic_profile_shadow_review.json), [semantic_profile_quality_metrics.json](semantic_profile_quality_metrics.json), and [semantic_profile_regression_fixtures.json](semantic_profile_regression_fixtures.json). The v1 diagnostic counterparts remain alongside them.

Side effects in this work: MySQL writes 0 (review resolved from frozen artifacts; no database query was needed); Qdrant reads 40 points; Qdrant writes 0; embedding calls/writes 0; Gemini calls 0; local verifier calls 44 in the final pass. No Spring, React, SSE, ranking, or runtime contract was changed.

## Harness and tests

- `poetry run pytest tests/test_semantic_profile_quality_gate.py -q`: PASS, 15 passed.
- `./scripts/check-ai.sh`: PASS, 289 passed, 1 skipped; one third-party deprecation warning.
- `poetry run ruff check app/semantic_profile_quality_gate.py scripts/run_semantic_profile_shadow_review.py tests/test_semantic_profile_quality_gate.py`: PASS.
- `git diff --check`: PASS.
- Backend/frontend harness: NOT_REQUIRED (no backend/frontend source changes for this task).

## Q1–Q13

1. Existing validation did **not** test semantic entailment; it checked structure, source eligibility, IDs and lifecycle.
2. Final 40-claim verdicts: SUPPORTED 33, PARTIAL 0, UNSUPPORTED 5; verifier errors 2.
3. Is Evidence-ID existence alone sufficient for approval? **NO.**
4. Are support quotes actual substrings? For legacy points, no support quotes were stored, so 0/40 pass. In the regression fixtures, quotes were exact source substrings after whitespace normalization.
5. Is PARTIAL indexable? **NO.**
6. Is UNSUPPORTED indexable? **NO.**
7. Does verifier failure approve a claim? **NO.**
8. Was an exhaustive dining/taste keyword taxonomy added? **NO.**
9. Were the existing 40 Qdrant points modified? **NO.**
10. Was MySQL source data modified? **NO.**
11. Was Gemini called? **NO.**
12. Did all known overclaim regressions pass safely? **NO**—the 9568 composite overclaim was incorrectly accepted.
13. Is profile generation expansion safe now? **NO**—the verifier must be fixed and regression-tested first.

## Next step

Improve verifier reliability using the frozen failing fixtures, especially atomic-assertion decomposition and conservative handling of mixed claims; add deterministic regression expectations around indexability, then rerun the bounded shadow set. Do not expand profiles, embed, or write Qdrant until every known overclaim is blocked and the verifier’s error/partial behavior is reliable.
