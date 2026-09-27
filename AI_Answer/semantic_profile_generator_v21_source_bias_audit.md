# Semantic Profile Generator V2.1 — Source Bias Audit

## Code findings before generation

The V2 catalog is serialized in source blocks: identity, all MENU rows, all
REVIEW_KEYWORD rows, representative REVIEW rows, then hours. The V2 prompt
runner retained that order when selecting successful semantic evidence, so a
large contiguous MENU prefix was presented to the model. The V2 contract also
allowed at most five claims and asked for “up to five”; this permitted five
literal menu-listing claims to fill the entire response. The prompt distinguished
MENU from REVIEW semantics but did not ask the model to compare the usefulness
of available sources. These facts make ordering plus the small output cap a
credible structural contributor. They do not prove that source order was the
only cause; MENU statements are also unusually easy to quote literally and
verify safely.

The prior 3-restaurant output confirms the observed result, not a unique cause:
all approved claims were English boilerplate wrapped around Korean menu names,
and no review or keyword claim was approved. The current path did not implement
source quotas or source-specific claim creation.

## V2.1 changes

- Keep the V2 claim/evidence/quote schema and the existing V2.2 Atomicizer and
  Assertion Verifier unchanged.
- Round-robin successful MENU, REVIEW_KEYWORD, and REVIEW evidence in the
  V2.1 prompt input, preserving source order within each source. This reduces a
  long MENU prefix; it does not assign output quotas or guarantee source usage.
- Use a Korean prompt that requests natural Korean standalone claim sentences,
  asks the model to consider directly useful review-derived evidence without
  forcing it, and reiterates that exact quotes must remain in their source
  language.
- Raise only the maximum output cap from five to eight after auditing the
  previous five-claim cap. The model may return fewer claims.
- Add a generic language guard: reject claims with no Hangul or with at least
  12 Latin letters and more than twice as many Latin as Hangul letters. This
  catches the previous English boilerplate while allowing short Latin-script
  names in Korean prose. It is not a food/meaning keyword rule.

The first execution attempt exposed a contract mismatch: the V2.1 request
schema allowed eight items, while the shared Pydantic response model still
limited the list to five. That attempt was interrupted during Restaurant 9569;
its partial status is preserved in
`semantic_profile_generator_v21_interrupted_attempt.json`. The model cap was
aligned to eight (the legacy V2 request schema remains capped at five) and a
targeted regression test was added before the completed Run 1. No raw model
response from the interrupted attempt was retained.

## Frozen cohort

The V2.1 cohort was frozen before any V2.1 Generator call. Current read-only DB
preflight confirmed strict ProfileReadiness and source hashes for Restaurant
IDs `9568, 9569, 9570, 9574, 9580, 9659, 9801, 10042`. All have successful
MENU, REVIEW_KEYWORD, and representative REVIEW evidence. The frozen counts
and hashes are in `semantic_profile_generator_v21_cohort.json`. Prior V2 pilot
IDs `9559, 9603, 9639` are excluded.

Human inspection of current source snapshots confirmed that this cohort contains
direct customer-evaluation/context material in both review keywords and review
text, alongside menu rows. Examples include source statements about freshness,
solo dining, store size, service, and review sentences describing lunch context,
food qualities, or service. These are candidate source facts only; none are
pre-approved claims. Generator results must still pass exact-quote validation,
Atomicity, and V2.2 semantic verification.

## Safety / boundary

No source-specific ratios, claim-type quotas, restaurant-ID rules, or keyword
mapping were added. Existing source-meaning restrictions and exact substring
validation remain in force. This audit and cohort freeze are read-only; no
Generator result was used to select or replace a Restaurant.
