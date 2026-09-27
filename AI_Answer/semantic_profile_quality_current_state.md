# Semantic Profile Quality — Current-State Audit

Audit date: 2026-09-26 (Asia/Seoul)

## Existing profile generation and evidence flow

1. `ai/app/semantic_profile_shadow.py:build_input()` loads Restaurant, detail rows, lifecycle state, and current identity from MySQL using SELECT statements. Its CLI writes generated input/catalog/result JSON artifacts; it does not persist claims to MySQL.
2. `build_evidence_catalog()` assigns Evidence IDs in Python and records the source field, section, lifecycle state, evidence type, and copied source content. Current source types include `identity`, `menu`, `keyword`, `review`, and `business_hours` (lowercase values in the existing catalog schema).
3. `_evidence_prompt()` gives the catalog to the configured local profile generator and asks for `claimType`, claim text, confidence, and Evidence IDs. `EvidenceClaim` does not contain `supportQuote`; the model may cite multiple IDs in a single claim.
4. `validate_evidence_output()` checks Pydantic shape, allowed claim type, Evidence ID existence, source-type compatibility, and `SUCCESS` lifecycle. `classify_claims()` additionally checks source-type rules, menu-vs-review distinctions, and a keyword mention threshold. It does not decide whether the complete meaning of a claim is entailed by the cited source.
5. `benchmark_eligible_claims()` only selects claims classified `AUTO_APPROVED` with successful evidence and acceptable identity/lifecycle conditions. This is a structural/status gate, not semantic entailment verification.
6. `ai/app/semantic_retrieval_hybrid_v2.py` builds normalized claim text and repeated-review `FOOD_MENTION` points. `AI_Answer/semantic_retrieval_hybrid_indexing_manifest.json` records the v12 point list and catalog hash for generated profile claims. It does not record `supportQuotes`; derived FOOD_MENTION entries also lack a catalog hash in that manifest, although their restaurant can be bound to the unique catalog hash of that restaurant’s profile points.
7. The runtime Qdrant v12 payload is a derived representation. It contains the claim, restaurant, type, and Evidence IDs but not the raw source Evidence text. A consumer must resolve IDs through the source catalog artifacts.

## What current validation proves—and does not prove

It proves schema validity, allowed claim types/source types, cited ID existence at generation time, and successful source-section lifecycle. It does **not** prove that every material assertion in the claim follows from the actual Evidence. Thus an existing Evidence ID can resolve correctly while the claim still adds tenderness, spaciousness, occasion type, menu variety, or other unsupported detail.

The existing catalog items preserve copied source values and have an `inputHash`/`catalogHash`. For this review, catalog hash was matched to the v12 indexing manifest; hash contents were recomputed; profile input artifacts were matched by `inputHash` to verify Restaurant ownership. All 40 live Qdrant points matched the v12 index manifest, and all 40 claims’ cited Evidence resolved to a hash-matched catalog owned by the same Restaurant.

## New shadow policy implemented for this review

- Deterministic layer: validate claim structure/type/length, Restaurant identity, Evidence resolution and ownership, source type, `SUCCESS` state, non-empty raw text, duplicate claims, and exact support-quote substrings after whitespace normalization only.
- Semantic layer: an independent local Qwen verifier receives only claim type/text and cited Evidence ID/source type/raw text. It returns structured `SUPPORTED`, `PARTIAL`, or `UNSUPPORTED`, short supported/unsupported portions, and cited IDs. It receives no generator rationale, confidence, old approval state, or old Qdrant status.
- Indexability requires deterministic validation PASS, exact quote validation PASS, and semantic `SUPPORTED`. `PARTIAL`, `UNSUPPORTED`, missing quote, invalid evidence, malformed output, or verifier error all fail closed.
- The 40 legacy v12 claims have no stored support quotes. No quotes are retroactively invented, so their new-policy indexability is false regardless of semantic verdict. Semantic verification is still run for diagnosis when Evidence is valid.

## Runtime/data boundary

The shadow verifier is not wired into Spring, FastAPI recommendation runtime, embedding generation, or Qdrant indexing. Runtime ranking, feature flags, and point payloads are unchanged. This review performs only Qdrant reads and local Ollama text-generation calls; it does not use Gemini, MySQL writes, embedding calls, or vector writes.
