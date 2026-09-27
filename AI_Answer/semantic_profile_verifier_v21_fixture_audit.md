# Verifier V2.1 Fixture Semantics Audit

Date: 2026-09-26 (Asia/Seoul)

## Decision: correct the fixture expectation; do not alter the verifier

The preserved V2 fixture `menu-evidence-does-not-entail-chicken-topping-9571` used the claim “불고기와 닭고기, 채소를 포함한 다양한 피자 토핑을 제공한다.” and cited three menu titles: `비프타코피자`, `불고기피자`, and `야채퀘사디아피자`.

The source supports that those exact menu entries were present in the captured MENU data. It does not, by itself, establish the composition of toppings, ingredients beyond the literal item names, preparation details, or a full topping catalogue. In particular:

- A. `불고기피자` directly supports “the menu contains an item named 불고기피자.” It does not independently prove the culinary construction “불고기를 topping으로 제공한다.”
- B. `야채퀘사디아피자` directly supports “the menu contains an item named 야채퀘사디아피자.” It does not independently prove the more specific construction “채소를 pizza topping으로 제공한다.”
- C. `비프타코피자` does not support a chicken-topping assertion. No chicken wording occurs in the cited menu titles.

Accordingly, the old fixture’s broad topping claim has no directly supported atomic assertion under the adopted conservative reading: “topping을 제공한다” is more specific than the source’s item-name fact. Its final expected verdict is corrected to **UNSUPPORTED** in the new V2.1 fixture version. The old `semantic-profile-verifier-v2-frozen-1` artifact remains unchanged; the correction is documented before the V2.1 runs and is not based on choosing a verdict merely to make the model pass.

## Clear replacement PARTIAL fixture

The new mixed fixture uses the direct menu-presence wording:

> 메뉴에 불고기피자, 야채퀘사디아피자, 닭고기피자 항목이 있다.

Its cited Evidence is the exact `불고기피자` and `야채퀘사디아피자` menu rows. The first two item-presence assertions are literal, direct matches; the cited Evidence does not support a `닭고기피자` item. This tests mixed aggregation without inferring toppings, recipes, synonyms, or restaurant-wide menu absence. The unknown item is treated as unsupported by the supplied evidence, not as proof that no such item exists in the real restaurant.

The fixture is frozen with source snapshots/hashes and expected final verdict PARTIAL before V2.1 verifier calls. No keyword mapping, menu-name parser, Restaurant-ID exception, model prompt loosening, or verifier code change was used to target 9571.
