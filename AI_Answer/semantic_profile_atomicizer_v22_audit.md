# Semantic Profile Atomicizer V2.2 Audit

## Scope and source

Audited the current offline quality-gate implementation and the frozen V2.1 40-point shadow artifact. The 12 failing claims were extracted without changing their text or expected verdicts into `semantic_profile_atomicizer_v22_failure_set.json`; this is a reproduction corpus, not a ground-truth fixture. Baseline diagnostics are in `semantic_profile_atomicizer_v22_diagnostics.json`.

## V2.1 contract

`ai/app/semantic_profile_quality_gate.py` defines Pydantic models for an atomicizer response and validates the result in `parse_atomicization`. The Ollama client is called with a JSON Schema `format`; this was not prompt-only JSON. The former model-generated output included `assertionId`, `text`, and `sourceSpan`. Python then checked that each source span was an exact whitespace-normalized substring of the Claim. IDs and ordering therefore mixed model responsibilities with deterministic integrity checks.

The baseline was one fresh call for each of the 12 frozen failures. JSON parsing and Pydantic/schema validation succeeded in all 12. Every failure occurred later because the generated `sourceSpan` paraphrased rather than exactly copied a Claim substring (`SOURCE_SPAN_NOT_IN_CLAIM`, location `assertions[*].sourceSpan`). Thus the recorded `SCHEMA_ERROR` was too coarse: it hid a deterministic source-trace validation failure. This was not a semantic-verdict failure.

Distribution was recomputed from V2.1: FOOD_MENTION 10, DINING_CONTEXT 1, TASTE 1. The concentration is an observed correlation with those Claim forms, not evidence that claim type caused the defect. No ClaimType-specific handling is warranted.

## V2.2 contract

The model now returns only assertion text and inclusive `startToken`/`endToken` indices into the original Claim token sequence. Ollama receives a bounded JSON Schema whose token indices are enumerated. Python validates the shape/range/count, derives exact `sourceSpan` by slicing the original Claim, assigns `A1…` IDs, rejects duplicate assertion text/ranges, and orders assertions by source position. The contract keeps exact source traceability without asking the model to reproduce a substring byte-for-byte. Shared predicate phrases may require overlapping source ranges, so overlap alone is not rejected; duplicate assertions remain invalid.

The Atomicizer still receives only Claim type and Claim text, sees no Evidence, and cannot issue semantic verdicts. A failed call gets at most one generic contract-correction retry; no food, restaurant, ClaimType, or fixture-specific correction is used. JSON parsing, schema validation, token-range validation, and semantic atomicity remain separate concerns. The assertion verifier and Python aggregator policy were not changed.

## Outcome

The original 12 failures are structurally explained by the exact-span contract and are resolved in the final retry9 run: 36/36 Atomicizer calls succeeded, with zero terminal errors, empty outputs, invalid source traces, duplicate failures, or assertion-limit violations. The frozen 8-fixture suite passed 24/24 runs. The gated shadow rerun completed all 40 points with zero terminal errors.

Review note: legacy Claim text sometimes appends explanatory `근거:` material. A few decompositions treat that trailing citation text as an assertion, producing a PARTIAL verdict. This does not create an indexable Claim (the legacy points lack required supportQuotes), but it is a limitation when interpreting legacy verdict distribution and a useful requirement for the next Generator contract: keep claim prose separate from provenance text. No special-case stripping or Claim rewrite was introduced in this task.
