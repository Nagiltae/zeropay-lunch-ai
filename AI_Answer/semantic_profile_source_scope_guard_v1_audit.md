# Semantic Profile Source Scope Guard V1 — Code Audit

## Existing boundaries

- Generator V2 emits `claimType`, `claimText`, `evidenceIds`, and exact
  `supportQuotes`. It does not emit `sourceScope`.
- `validate_generator_output()` resolves IDs against that Restaurant's
  Evidence Catalog, checks ownership, `SUCCESS`, source/ClaimType compatibility,
  quote-to-Evidence pairing, exact normalized substring, duplicates,
  provenance leakage, and language constraints. Its result is deterministic
  validity (`valid`); it is not an indexability decision.
- The V2.2 runner calls Atomicizer V2.2 and Assertion Verifier V2.2. Its legacy
  `approved` property means the semantic verdict is `SUPPORTED` (subject to
  deterministic validation and atomicity in that runner). Before this task,
  there was no separate `indexable` field or derived source provenance.
- Therefore `approved` and `indexable` were not equivalent contracts. In
  particular, `SUPPORTED` did not prove that customer attribution was retained
  in the representation to be embedded.

## Existing downstream text paths

`semantic_embedding_qdrant_pilot.load_documents()` previously built
`embeddingText` directly from `claimType` and the legacy `claim["text"]` value.
It did not require source provenance, `searchText`, or an indexability decision.
The new guard makes this loader accept only claims with `indexable=true`, a
recognized non-mixed `sourceScope`, and non-empty `searchText`; it has no
fallback to raw `claimText`/legacy `text`. Existing legacy profile artifacts do
not carry this contract and now fail closed before any embedding request.

The same audit found additional old claim-vector builders:
`semantic_claim_retrieval_pilot.build_claim_points()`,
`semantic_retrieval_tenth_benchmark._normalized_text()`, and the hybrid-v2
manifest re-embedding loop. They previously assembled vectors from legacy
`text`/`normalizedClaimText` fields, and the claim pilot also appended derived
review-keyword food mentions without the V2.2 semantic approval contract. All
three indexing paths now call the shared source-scope/indexability text guard;
legacy claims and unapproved derived mentions fail closed. Existing read-only
query/retrieval code is unchanged. No Qdrant operation was invoked.

Other observed V1 APIs include `classify_claims()` and
`benchmark_eligible_claims()` in `semantic_profile_shadow.py`. Those are a
separate legacy pipeline: `AUTO_APPROVED` is deterministic evidence/source
eligibility, not V2.2 semantic verifier approval. Their output is not allowed
to bypass the updated embedding loader's scope contract.

No current Generator V2 code serializes a `근거:` tail into `claimText`; the
provenance marker detector rejects that pattern. Historical Qdrant claims may
contain such tails (the V2.2 atomicizer review documented that legacy issue),
but they are not input to this read-only scope evaluation.

## Guard placement and mapping

At the runner boundary, immediately after evidence resolution and the existing
deterministic/Atomicizer/verifier checks, Python derives `sourceScope` from the
resolved `evidenceType` values:

| Resolved Evidence sources | Derived scope | Index policy |
|---|---|---|
| all `menu` | `LISTING_FACT` | Search text is the validated claim text |
| all `review` / `keyword` | `CUSTOMER_REPORTED` | Search text gets a generic customer-review provenance prefix |
| both groups | `MIXED` | Reject, `MIXED_SOURCE_SCOPE` |
| empty or any unrecognized source | `UNKNOWN` | Reject, `UNKNOWN_SOURCE_SCOPE` |

The model cannot choose or override this value. The guard never inspects
Restaurant IDs, words such as “혼밥”, or Claim meaning. It does not rewrite
sentences; for customer-derived text it constructs
`고객 리뷰 기반 정보: {raw claimText}`.

The raw `claimText` remains preserved as the Generator/verifier record.
`searchText` is a separate field, and `indexText` is populated only when all
guards pass. The only embedding loader in the bounded profile-index pilot now
uses the helper that consumes `searchText`; a customer raw claim cannot be used
as embedding text. A missing scoped text, unrecognized scope, mixed scope,
non-indexable claim, deterministic failure, quote failure, semantic rejection,
or non-atomic claim fails closed.

The embedding helper also enforces canonical representation: LISTING_FACT
`searchText` must equal the trimmed raw claim; CUSTOMER_REPORTED `searchText`
must equal the exact generic provenance prefix plus the unchanged trimmed raw
claim. A caller cannot supply an arbitrary sentence under a valid-looking
scope.

## Why verifier behavior is unchanged

The two solo-dining records remain semantically `SUPPORTED` in the reused V3
artifact. The guard records that verdict as `semanticApproved=true`, then
independently adds source scope and produces customer-attributed search text.
This keeps the verifier observation intact while separating entailment from
provenance preservation. Atomicizer V2.2, Assertion Verifier V2.2, their schema,
prompts, and aggregation rules are unchanged. Generator prompt and ClaimType
taxonomy are also unchanged in this task.

## V3 artifact reuse and side effects

The frozen `semantic_profile_generator_v22_fixture_results_v3.json` contains
all 11 raw claims, resolved evidence, exact-quote validation, assertions, and
verdicts, so it is sufficient to test the deterministic scope boundary.
No Generator, Atomicizer, or Assertion Verifier call was needed. The evaluator
reuses this artifact and writes only new scope-guard artifacts. There were no
MySQL reads/writes, Qdrant reads/writes, Embedding calls/writes, or Gemini calls
in this task.
