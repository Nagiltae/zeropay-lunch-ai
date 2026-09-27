# Semantic Profile Generator V2 Audit

## Current Generator V1 and the provenance-text finding

The current Python source of truth is `ai/app/semantic_profile_shadow.py`:

- `build_input()` reads Restaurant, menu, hours, review summary, review keywords, representative reviews, lifecycle and Place ID verification data. It applies `assess_profile_readiness`.
- `build_evidence_catalog()` assigns deterministic per-Restaurant Evidence IDs and carries source field, content, section, lifecycle state and source type.
- V1's `EvidenceClaim` contains `claimType`, `text`, `confidence` and `evidenceIds`. The model selects Evidence IDs. It does not return a quote. `validate_evidence_output()` checks the schema, Evidence ID/source-type compatibility and SUCCESS lifecycle, but not exact quote provenance or semantic entailment.
- `classify_claims()` and `benchmark_eligible_claims()` add source/lifecycle restrictions and an AUTO/REVIEW/REJECT classification. Confidence is generated but does not prove support.
- The profile output and final artifact writer preserve source claims and attached Evidence; they do not make quotes.

Important correction to the initial premise: the inspected raw V1 Generator outputs do **not** place `근거:` inside the generated `text`. For example, `AI_Answer/semantic_profile_expansion_v2/9559/qwen_raw_output.json` stores `text` separately from `evidenceIds`. The legacy text seen by the Atomicizer was assembled later by `ai/app/semantic_retrieval_tenth_benchmark.py::_normalized_text()`, which formats `claimType + text + 근거: cited menu/keyword strings` for the embedding/search point. Thus the provenance text was an indexing representation, not the original Generator claim. V2 keeps `claimText`, `evidenceIds`, and `supportQuotes` separate; no runtime/indexing serializer was changed here.

## Generator V2 contract

The new offline schema accepts only:

```json
{
  "claims": [
    {
      "claimType": "MENU_CHARACTERISTIC",
      "claimText": "The restaurant offers the listed menu item.",
      "evidenceIds": ["E003"],
      "supportQuotes": [{"evidenceId": "E003", "quote": "exact source text"}]
    }
  ]
}
```

The schema does not ask the model for Restaurant/Claim IDs, confidence, rationale, lifecycle, hashes, ordering or approval state. Python creates a deterministic Claim ID after validation. V2 uses the existing high-level ClaimType values and open-ended sentence text; it adds no taxonomy or keyword dictionary. The prompt receives only SUCCESS MENU, REVIEW_KEYWORD and REVIEW Evidence for that Restaurant, with source role preserved.

The deterministic validator rejects malformed/extra fields, invalid ClaimType, empty/duplicate claims, provenance markers in claimText, unknown or disallowed-source Evidence IDs, non-SUCCESS Evidence, missing/mismatched quotes and quotes that are not a whitespace-normalized exact substring of their cited raw Evidence. Structural rejects do not reach the verifier. A structurally valid claim is converted to the existing V2.2 `ClaimCandidate`, passed through the unchanged Atomicizer, and rejected as `GENERATOR_NON_ATOMIC` unless exactly one assertion results. Only an unchanged V2.2 assertion-verifier `SUPPORTED` result can be approved. Atomicizer/assertion errors remain fail-closed with the existing bounded retry.

`FOOD_MENTION` is intentionally outside this Generator's allowed ClaimTypes and allowed source mappings. Its existing derived/indexing path is not modified. No embedding, Qdrant or MySQL persistence boundary is invoked.

## Frozen cohort preflight

The current database was re-read using the existing `build_input()` + common ProfileReadiness policy. The three requested historical-overclaim targets were all currently strict ProfileReady, with matching frozen input/catalog hashes and SUCCESS menu/review lifecycle. They were frozen before Generator calls in `semantic_profile_generator_v2_cohort.json`; no replacement was needed.

| ID | Restaurant | ProfileReady | Menu | Keyword | Review | Hours | Total Evidence |
|---:|---|---:|---:|---:|---:|---:|---:|
| 9559 | 모우리 | Yes | 28 | 37 | 4 | 4 | 75 |
| 9603 | 본죽&비빔밥 논현점 | Yes | 58 | 36 | 1 | 4 | 101 |
| 9639 | 이자카야나무(논현) | Yes | 64 | 39 | 4 | 1 | 110 |

Counts above are catalog item counts by source type; identity items are also in total Evidence (2 each). Freeze-time current input hashes match the previous expansion plan and are checked again before each run. The runner refuses source drift.

## V2.2 connection and compatibility

The Generator V2 runner imports the existing `OllamaAtomicClaimVerifier`, `ClaimCandidate` and Python verdict aggregator from `ai/app/semantic_profile_quality_gate.py`; it does not edit that module. The V1 `EvidenceOutput`/downstream classifier contract remains untouched. V2 is a separate DRY-RUN artifact/version and is not wired to runtime, embedding generation, Qdrant indexing, or legacy profile writers.
