# Invariants

Reviewer-facing properties the codebase must always satisfy. Each invariant
names its enforcement point (contract code, unit tests, direct tests).

## Boundary invariants

**I1 — One LLM call site.**
There is exactly one `exec_prompt` call, inside the `assess_order` closure.
*Enforced by `tests/unit/test_static_boundaries.py::test_exactly_one_llm_callsite_exists`.*

**I2 — Single-order profiling.**
The prompt builder renders exactly one `<order_text>` block. No code path
ever places two orders inside one model call.
*Enforced by unit static checks and the shape of `profile_prompt`.*

**I3 — The model never allocates.**
No model output contains prices, quantities, counterparties, or rankings.
Model output is constrained to integer masks plus a bounded reason.
*Enforced by output-contract validation in `validate_profile_shape`.*

**I4 — Determinism after assessment.**
`freeze_epoch`, `clear_epoch`, compatibility, and all hash derivation are
pure functions of stored state. No floats anywhere in the primitive.
*Enforced by unit static checks and direct clearing-policy tests.*

## Safety invariants

**I5 — Fail-closed normalization.**
Any malformed profile — unparseable, mistyped, overlapping buckets, bits
outside the sealed vocabulary — normalizes to `ambiguous = all-ones` with
every other mask zero.
*Enforced by `normalize_profile` + `test_malformed_profile_fails_closed` +
parametrized invalid-profile tests.*

**I6 — Vocabulary finality.**
Once sealed, a market's vocabulary, and therefore `definition_hash`, can
never change. Pausing toggles intake only, not definitions.
*Enforced by `add_attribute` status guard + `test_seal_pins_definition_and_freezes_vocabulary`.*

**I7 — Profiling is one-shot.**
An assessed order cannot be re-assessed; masks cannot be edited afterwards.
There is no setter for any mask field.
*Enforced by `assess_order` one-shot guard + absence of mask mutators.*

**I8 — Freeze completeness.**
`freeze_epoch` rejects while any non-cancelled order lacks a ready profile,
and requires live orders on both sides, so a cleared epoch always has exactly
one fully-assessed order set.
*Enforced by the freeze guard loop + `test_freeze_rejects_pending_assessment`.*

**I9 — Clearing is final.**
An epoch clears at most once; fills are append-only and hash-committed the
moment they are created; orders frozen into one epoch can never be cleared
under a different `epoch_hash`.
*Enforced by the `EPOCH_FROZEN` status guard + `test_epoch_cannot_clear_twice`
+ fill-pin assertions.*

**I10 — Replay-safe consumption.**
Consumer checks pin (market, epoch, fill) hashes bytewise and require the
caller to be a fill party. Consumed action hashes are never reusable, and
each (fill, party) pair redeems at most once.
*Enforced by `FillGate.redeem_fill` + `tests/direct/test_fill_gate.py`.*

## Economic invariants

**I11 — Intake idempotency.**
One `client_order_hash` maps to at most one order for the life of the
contract, across all markets. Retry-safe submission for flaky clients.

**I11′ — Intake bounds.**
Per-epoch per-side capacity is capped (`MAX_ORDERS_PER_SIDE`), vocabulary
size is capped, and every free-text field is length-capped and whitespace-
normalized, bounding consensus cost and storage.

**I12 — Ask-priced trades.**
A fill always executes at the offer's ask. Bids express ceilings and
ordering only; no model or market operator can change the trade price.

**I13 — Total ordering.**
Clearing order is a total order over `(price, time, id)` tuples — equal
outcomes on every validator, every replay, every re-run.
