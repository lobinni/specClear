# Architecture

SpecClear is built around one non-negotiable boundary: **non-deterministic
evidence extraction happens once per order; everything compositional is
deterministic.**

## 1. Market-local semantic vocabulary

A market owns a bounded list of up to **16 attributes**. Each attribute has a
single-token label and a human-readable evidence definition. Draft
vocabularies are mutable by the market owner only. `seal_market` freezes the
vocabulary and derives `definition_hash = keccak256(canonical_json(definition))`.
Every order and epoch pins this hash, so a profile can never be reinterpreted
against a drifted dictionary.

Why 16 attributes: the vocabulary must be small enough that a reviewer can
read it entirely, every validator LLM sees the identical bounded task, and
all masks fit in a `u32` (bits 0–15 used) with room to spare.

## 2. Independent profiling, never pairwise adjudication

`assess_order` targets exactly one order. The prompt builder renders:

* a fixed role header (`SPECCLEAR / ORDER PROFILE`);
* fail-closed evidence rules (silence ⇒ ambiguous, never affirmative);
* an anti-injection framing — dictionary rows and order text are wrapped as
  untrusted DATA, never instructions;
* the sealed dictionary (bit index, label, definition);
* the single order text;
* a bounded output contract — integer masks plus a short reason.

Requests emit `required / forbidden / preferred / ambiguous` buckets.
Offers emit `present / absent / ambiguous` buckets. Buckets must be pairwise
disjoint; masks referencing undefined bits are invalid. Any violation — bad
JSON, wrong types, overlapping buckets, out-of-range bits — fails closed:
`ambiguous = all-ones`, nothing else. A failed-closed order can still be
priced and stored, but it cannot satisfy constrained counterparties.

Consensus runs through `gl.eq_principle.prompt_non_comparative`: the leader
normalizes its model output into canonical mask JSON, validators
independently rerun the identical task and must agree **bit-for-bit** on the
masks; only the free-text reason may differ in wording. Only bounded decision
masks carry consensus-critical state — rationale text never does.

## 3. Deterministic compatibility

`compatible(request, offer)` is pure arithmetic over the two stored profiles.
See `CLEARING_RULES.md` for the exact predicate and worked examples. It is
exposed read-only as `deterministic_compatible(request_id, offer_id)` for
integrators and frontends.

## 4. Deterministic batch clearing

`freeze_epoch` commits `epoch_hash` over the ordered hashes of every active,
assessed order in the epoch. `clear_epoch` (permissionless) computes the
fill plan via `_match_plan` — the same function `preview_clear` serves
read-only, so a preview can never diverge from execution. Fills chain into a
`settlement_root` by folding `fill_hash` values in creation order:
`root_i = keccak256(root_{i-1} ‖ fill_hash_i)` starting from `epoch_hash`.

## 5. Idempotency and intake

Every order carries a `client_order_hash` (32-byte lowercase hex digest)
chosen by the submitter. The contract rejects duplicate digests, so a
client/frontend retry after an uncertain submission cannot create duplicate
economic orders. Digests are validated bytewise — no case folding, no
normalization — because client identities are canonical inputs.

## 6. Consumer proofs

`fill_gate.py` is the reference pattern for building on top of settled
fills. It performs typed IC-to-IC reads of `is_fill_valid` and
`is_fill_party`, never trusts free-form results, requires the caller to be a
fill party, and rejects replayed action hashes both globally and per
(fill, party) pair.

## 7. Storage model

| Record | Key | Highlights |
|---|---|---|
| `Market` | `market_id` | owner, enum status, `DynArray` vocabulary, `definition_hash` |
| `Epoch` | `epoch_id` | status, pinned `market_hash`, per-side order id lists, `epoch_hash`, `settlement_root`, `fill_ids` |
| `Order` | `order_id` | side, quantitative terms, six masks, `order_hash`, `profile_hash`, lifecycle timestamps |
| `Fill` | `fill_id` | both parties, quantity, ask price, preference score, three commitment hashes |

All enumeration used by clearing goes through epoch-scoped id lists, so
clearing order is submission order — never dict iteration.
