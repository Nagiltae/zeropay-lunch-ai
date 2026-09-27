# Semantic Profile Verifier V1 Audit

Date: 2026-09-26 (Asia/Seoul)

## V1 implementation findings

The previous `OllamaSemanticVerifier` sent the complete claim and all cited Evidence in one call. Its output schema returned one `SUPPORTED | PARTIAL | UNSUPPORTED` verdict plus free-form `supportedPortion` and `unsupportedPortion`. The runner stored those portions for diagnosis but did not use them to calculate the verdict. No assertion decomposition, assertion-count integrity check, or Python aggregation existed.

This explains the V1 failure mode structurally: the model was asked to judge one composite sentence holistically, so it could accept the whole sentence after recognizing the supported solo/group/spacious pieces, without a separate mandatory decision for “comfortable casual meal.” The prompt discouraged inference, but neither the contract nor code forced each assertion to be independently accounted for. `PARTIAL` was representable in the schema, but use was left entirely to one model-level judgment; V1 produced zero PARTIAL results across the 40-point review.

For Restaurant 9568, the V1 response marked the full composite claim SUPPORTED and copied the whole claim into `supportedPortion`. Since those text fields were diagnostic only, they did not expose or correct the missing support for comfortable/casual dining.

## V1 error observability

The two 40-point failures and one regression-fixture failure were recorded only as `verifierErrorCode: "ValueError"`. The runner intentionally omitted raw model output and the exception message. In code, V1 `parse_verdict()` can raise `ValueError("INVALID_VERIFIER_OUTPUT")` for JSON/schema parse errors or `ValueError("VERIFIER_RETURNED_UNKNOWN_EVIDENCE")` for an out-of-scope ID. The saved artifacts do not preserve which branch occurred. Therefore it is **not possible to prove retrospectively** whether those specific errors were malformed model JSON/schema or an evidence-ID response. They were not timeout/provider errors based on the recorded exception class, but the exact cause is UNKNOWN. V2 now emits safe error categories without retaining raw responses.

## V2 design implemented for the bounded fixture suite

1. Atomicizer input is only `claimType` and `claimText`; Evidence is excluded. It must return 1–8 unique assertions with a source span traceable to the claim after whitespace normalization.
2. Each assertion is sent separately with the cited Evidence and receives only `SUPPORTED` or `UNSUPPORTED`.
3. Python computes the whole Claim verdict: all supported → SUPPORTED; a mix → PARTIAL; all unsupported → UNSUPPORTED. Any atomicizer/assertion/aggregation error → VERIFIER_ERROR and non-indexable.
4. A bounded retry permits initial call plus one retry; raw model/provider bodies are not placed in artifacts. Model is pinned to `qwen3.5:9b`, temperature is zero, and no fallback is configured.
5. New-policy indexability still requires deterministic source/quote validation and final SUPPORTED. This suite does not modify or retrofit old Qdrant claims.

The 7-case suite consists of the 4 existing source-bound regression fixtures plus 3 positive fixtures frozen from existing v12-related Evidence catalogs before V2 verifier execution. The fixture artifact stores Evidence snapshots and hashes. It is not altered after observing V2 results.

## V2 execution findings

The first fixture-suite attempt exposed a contract mismatch: the assertion verifier required at least one Evidence ID even for `UNSUPPORTED`, although an unsupported assertion may correctly have no supporting Evidence. A schema-diagnostic run then returned 12 exhausted assertion-verifier failures across the negative/mixed cases (24 schema errors including the bounded retries); the positive cases passed. The schema was corrected so `evidenceIds` may be empty for `UNSUPPORTED`, while `SUPPORTED` still requires at least one valid cited Evidence ID. Those diagnostic artifacts are preserved as `*_schema_diagnostic.json` and are not treated as the final suite.

The corrected frozen suite completed 3 independent runs: all three positives passed 3/3; 9559 tenderness and corporate/family cases were `UNSUPPORTED` 3/3; the 9568 composite overclaim was `PARTIAL` 3/3. However, the 9571 chicken-topping case was `UNSUPPORTED` rather than expected `PARTIAL` in all 3 runs. The V2 system therefore remains blocked by the required verdict boundary, despite 0 false acceptance and 100% positive fixture recall. The 40-point rerun was correctly not executed.

## Boundaries

No Runtime, Generator prompt, Spring, FastAPI retrieval, ranking, MySQL, Qdrant, embedding, or Gemini behavior is changed. The V1 review artifacts remain preserved. The runner will only perform the 3× fixture suite first; the 40-point V2 shadow rerun is prohibited unless every required positive/negative stability gate passes.
