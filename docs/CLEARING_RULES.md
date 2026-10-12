# Clearing Rules — exact deterministic arithmetic

Everything on this page is integer arithmetic replicated identically by every
validator. There is no model involvement after `assess_order` finalizes a
profile.

## Masks

For a vocabulary of `n ≤ 16` attributes, every profile is a set of `u32`
bitmasks over bits `0..n-1`.

| Side | Mask set | Meaning |
|---|---|---|
| REQUEST | `required`, `forbidden`, `preferred`, `ambiguous` | what the demand side states it needs / bans / prefers / left undecided |
| OFFER | `present`, `absent`, `ambiguous` | what the supply side affirmatively evidences / denies / leaves silent |

`allowed = (1 << n) - 1` bounds all masks. Buckets within one profile are
pairwise disjoint — enforced at normalization or the profile fails closed.

## Compatibility predicate

`compatible(R, O)` holds iff **all** of:

1. `R.side == REQUEST ∧ O.side == OFFER`
2. `R.epoch_id == O.epoch_id` (and therefore same pinned `market_hash`)
3. `R.profile_status == O.profile_status == READY`
4. `O.ask ≤ R.max_bid`
5. `R.required & ~O.present == 0` — every required bit affirmatively present
6. `R.forbidden & O.present == 0` — no forbidden bit present
7. `(R.required | R.forbidden) & O.ambiguous == 0` — constrained dimensions
   may not be ambiguous on the offer (**fail-closed rule**)

Note what the predicate does *not* consult: descriptions, reasons, owners,
quantities, anything textual. Text influenced masks exactly once, during
single-order profiling.

## Preference score

```
score(R, O) = popcount(R.preferred & O.present)
```

An integer in `[0, 16]`. It never overrides price ceilings or constraints;
it only ranks offers that already passed the compatibility predicate.

## Total ordering

Epoch clearing order is a total order — no ties can survive:

* **Requests**: `(−max_bid, submitted_at, order_id)`
* **Offers per request**: `(−score, ask, submitted_at, order_id)`

`submitted_at` comes from the transaction datetime; `order_id` is a
strictly increasing counter. Two orders cannot share both.

## Fill mechanics

For each request in ranked order, iterate its ranked compatible offers that
still hold remaining supply:

```
take  = min(R.remaining, O.remaining)
price = O.ask                 # always the offer ask
```

Decrement both remainders; an order reaching `remaining == 0` becomes
`FILLED`, otherwise `PARTIAL`. Supply and demand clear onward within the
epoch — one request can draw many fills, one offer can serve many requests.

## Worked example (from `samples/market_definition.json`)

Vocabulary: bit0 CONFIDENTIAL_COMPUTE, bit1 NVLINK_FABRIC, bit2 EU_RESIDENCY,
bit3 CARBON_NEUTRAL.

* Request R: `required=0b0011, preferred=0b1000`, qty 2, bid 5000
* Offer A: `present=0b1111`, qty 1, ask 4000 → compatible; score = popcount(0b1000) = **1**
* Offer B: `present=0b0011, absent=0b1100`, qty 2, ask 3500 → compatible; score = **0**

Execution: R → fill(A, qty 1 @ 4000); R has 1 remaining → fill(B, qty 1 @ 3500).
Offer A is preferred over the cheaper offer B **because preference score
outranks ask**, exactly as encoded in the ordering tuple.

A fourth hypothetical offer `present=0b0001, ambiguous=0b1110, ask=1000`
fails rule 7 (NVLINK_FABRIC required but ambiguous) — cheapness cannot buy
clarity. This is the fail-closed guarantee working as intended.
