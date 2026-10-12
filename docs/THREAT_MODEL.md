# Threat Model

## Assets

1. **Integrity of allocation** — fills must follow the documented policy and
   nothing else. This is the primary asset.
2. **Finality of commitments** — `definition_hash`, `epoch_hash`,
   `fill_hash`, `settlement_root` must remain tamper-evident and replayable.
3. **Liveness of epochs** — bounded markets should reach clearing.
4. **Reusability of fills** — downstream contracts must be able to consume
   fill proofs without trusting callers.

## Adversaries

- **Order submitter** seeking allocation they do not qualify for
  (overstating capabilities, prompt injection, replaying identities).
- **Market owner** seeking quiet redefinition of a live vocabulary or gate
  manipulation after commitments exist (owner is trusted for intake-flow
  administration only).
- **LLM leader** producing a forged, malformed, or manipulated profile.
- **External consumer contract** replaying or forging fill proofs.
- **Validator disagreement** caused by genuine model nondeterminism.

## Threats and mitigations

| Threat | Mitigation |
|---|---|
| Inflated capability claims in offer text | Offer bits require *affirmative* evidence; the fail-closed predicate treats silence as ambiguous, and ambiguity on constrained bits blocks compatibility. Overclaiming is merely text; clearing trusts masks agreed on by consensus. |
| Prompt injection embedded in order text or attribute definitions | Prompt frames dictionary rows and order text as *untrusted DATA, never instructions*; output contract is bounded (masks + short reason); anything outside the contract fails closed. Tests assert the framing survives (incl. adversarial dictionary rows). |
| Forged or malformed leader profile | `prompt_non_comparative` validators independently rerun the identical task and must agree **bit-for-bit** on masks; malformed model output normalizes to all-ambiguous before it can influence anything. Forged-leader simulations are tested to revert at validator re-execution. |
| Vocabulary drift after profiles exist | Sealing pins `definition_hash`; orders and epochs pin it too; vocabulary mutators lock permanently at seal. |
| Owner reorders or censors a batch | Owner only opens/freezes epochs. **Clearing is permissionless** and its ordering is a documented total order over stored state — the owner cannot influence rank, price, or quantity at clear time. Owner can pause *intake* (not definitions, not settlement). |
| Duplicate submission of the same economic order | `client_order_hash` uniqueness, validated as a canonical lowercase digest (no case folding). |
| Clearing divergence across validators | Integer-only arithmetic; total ordering `(price, time, id)`; no wall-clock at clear time (only stored timestamps); no iteration over unordered maps during matching. |
| Fill proof replay/forgery by consumers | Fills are verified by typed IC-to-IC reads pinning three hashes; party membership is checked on-chain; action hashes are single-use globally and per party. Invalid-pin and non-party attempts are tested to revert without consuming action hashes. |
| Consensus-level model nondeterminism (honest) | Consensus scope is minimal: bounded masks only, free-text excluded from agreement surface, abnormal outputs degrade to inactivity rather than to permissive matching. |

## Explicit non-goals

- **Privacy of order text** — descriptions are calldata-visible public state.
- **Payment/asset movement** — the primitive settles *allocation*, not
  transfers. Integrators gate their own value movement on consumed fills
  (see `FillGate`).
- **Cross-epoch order persistence** — uncleared orders do not roll into the
  next epoch; re-submission is cheap and explicit.
- **Model selection of winners** — permanently out of scope by design; the
  unit suite fails the build if a second LLM call site ever appears.

## Failure modes (by design)

| Failure | Result |
|---|---|
| Malformed model output | order profile = all-ambiguous; cannot satisfy constrained demand; may still trade against *unconstrained* requests |
| Validator disagreement on masks | equivalence fails; assessment does not finalize; order remains unassessed and the epoch cannot freeze |
| Freeze with pending order | revert; epoch simply stays open |
| Clear on unfrozen/cleared epoch | revert; idempotent finality |
| Overpriced offer | deterministically incompatible; remains uncleared in place |
