# Semantic Profile Generator V2.2 — Source Contract Audit

## Existing implementation findings

The V2.1 Generator prompt said only that REVIEW / REVIEW_KEYWORD are customer
mentions/evaluations and not official sale. It did not define each ClaimType,
map ClaimTypes to source categories, or tell the model how to phrase an
unqualified food keyword. The input serialized `sourceType` and `rawText`, but
the generator had no compact per-source examples or operational type-selection
contract. Thus a keyword such as `꼼장어` was turned into “산곰장어는 꼼장어를
판매합니다.” with `MENU_CHARACTERISTIC`; the existing validator correctly
rejected it because that type accepts only MENU. This was a Generator contract
failure, not a validator/verifier failure.

V2.1 source/type map in `semantic_profile_generator_v2.py`:

| ClaimType | Allowed evidence source |
|---|---|
| `FOOD_TYPE` | MENU |
| `MENU_CHARACTERISTIC` | MENU |
| `TASTE` | REVIEW_KEYWORD / REVIEW |
| `DINING_CONTEXT` | REVIEW_KEYWORD / REVIEW |
| `VENUE_CHARACTERISTIC` | REVIEW_KEYWORD / REVIEW |

`FOOD_MENTION` already exists in the shared quality-gate ClaimType set and
legacy semantic data, but Generator V2 had omitted it from its schema and
source map. This omission left no source-correct type for a customer food-name
mention such as `꼼장어`. V2.2 reuses that existing type for REVIEW_KEYWORD /
REVIEW mention-only Claims. It does not introduce a new taxonomy. `FOOD_TYPE`
and `MENU_CHARACTERISTIC` remain MENU-only; validator safety is not relaxed.

The structured output contract already required ClaimType, Korean claimText,
Evidence IDs, and supportQuotes. Exact quote validation checks that the quote
is a whitespace-normalized substring of the raw Evidence; Evidence ownership,
SUCCESS lifecycle, source compatibility, duplicate IDs, provenance text,
unknown IDs, and duplicate Claim checks are deterministic. V2.2 does not
weaken these checks. V2.2 does not modify Atomicizer V2.2, Assertion Verifier
V2.2, or the verdict aggregator.

## Source semantics clarified in Generator prompt

- MENU can state a listing fact and only menu-display qualities directly
  present in its text.
- REVIEW_KEYWORD can state that customers mention a term or express the
  evaluation represented by the keyword; it cannot establish official sale,
  facilities, policy, or classification.
- REVIEW can state what a customer reports experiencing/evaluating. A review
  mentioning that someone ate a dish does not establish an official menu row.
- ClaimType descriptions now match the existing allowed-source map, including
  existing `FOOD_MENTION` for customer food mentions.
- Restaurant name is omitted from the Generator input. `restaurantId` remains
  Python metadata and is not required in claimText.
- Quotes remain verbatim source text; only the claim sentence is Korean.

The validator change is narrowly additive for the already-existing
`FOOD_MENTION` type, whose only compatible sources are customer REVIEW and
REVIEW_KEYWORD. No MENU claim type gained customer sources, no customer source
gained an official-menu type, and no other source/type pairing changed.

## Frozen evaluation data

Before any V2.2 Generator call, the runner reads only the selected current
ProfileReady catalogs and freezes 11 source-semantic cases (3 MENU, 4
REVIEW_KEYWORD, 4 REVIEW) plus a 3-Restaurant cohort. Each fixture stores the
actual source item and source hashes, but does not prescribe exact generated
wording. Restaurant IDs are evaluation metadata, not special rules.

## Safety

No source keyword dictionary, quota, Restaurant-specific runtime branch, or
review-to-official-fact exception was added. No MySQL write, Qdrant access,
Embedding, or Gemini call is part of this path. The existing V2/V2.1 artifacts
are preserved.

## Bounded V2.2 execution outcome (2026-09-26)

Three frozen fixture snapshots were evaluated because each prompt revision was
made only after the preceding frozen run had completed. The original v1 suite
was underspecified about the expected ClaimType: 10/11 passed its broad gate,
but service/favorability cases could be emitted under an unrelated type and a
non-contiguous review quote failed exact validation. The v2 suite froze source-
and ClaimType-specific expectations before model calls; 8/11 passed. The v3
suite kept those expectations frozen and clarified the generic distinctions
between bare food mentions, explicit food evaluations, dining context, and
venue evaluations, plus atomic treatment of linked clauses; 8/11 passed.

V3 found a safety failure despite deterministic quote and source validation:
two REVIEW_KEYWORD solo-dining claims were approved as the unqualified fact
`혼밥하기에 좋은 식당입니다.` rather than as a customer evaluation. The raw
keyword is an aggregate customer signal, not an objective/official restaurant
attribute. These claims were structurally valid and the semantic verifier
returned SUPPORTED, so this is a source-attribution/entailment false acceptance
at the Generator→Quality-Gate boundary. They are not official-menu promotion,
but they do exceed the source's epistemic scope. The bounded work therefore
stops before Restaurant-level generation. Full per-fixture results and the
human review are recorded in `semantic_profile_generator_v22_review.md`.
