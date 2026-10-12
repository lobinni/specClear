# Testing Guide

SpecClear ships three layers of verification, from fastest to deepest.

```
python scripts/preflight.py     # static gate: compile + boundary + artifacts
pytest tests/unit -q            # source-boundary checks (no VM, milliseconds)
pytest tests/direct -q          # full protocol suite in Direct Mode
pytest samples/end_to_end.py -q -s   # narrated runnable lifecycle sample
```

## 1. Environment

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` pins `genlayer-testing-suite==0.29.2`, which provides the
`gltest` Direct Mode runtime and the `direct_vm` / `direct_deploy` pytest
fixtures. Python 3.11+ is recommended.

## 2. Direct Mode mental model

Direct Mode loads a contract into a local GenVM — no chain, no accounts to
fund, no real model calls.

| Fixture capability | What it does |
|---|---|
| `direct_deploy(path)` | deploys a contract file; returns a proxy whose public methods are directly callable. Constructor args: `direct_deploy(path, args=[...])`. |
| `direct_vm.sender = create_address("name")` | switches `gl.message.sender_address` for subsequent calls. Named addresses are deterministic — `"buyer"` is the same address everywhere. |
| `direct_vm.warp(iso8601)` | sets the transaction datetime (`gl.message_raw["datetime"]`) the contract reads. The shipped `tests/conftest.py` mirrors this value, and also patches a Windows-specific loader quirk. |
| `direct_vm.mock_llm(substring, result)` | any nondet LLM call whose prompt contains `substring` resolves to `result`. SpecClear anchors mocks on the `SPECCLEAR / ORDER PROFILE` tag. |
| `direct_vm.run_validator(leader_result=...)` | re-executes the validator path of the last equivalence block; returns whether it agrees. Pass a forged `leader_result` to prove validators reject it. |
| `direct_vm.expect_revert(fragment)` | context manager asserting a `UserError` whose message carries `fragment`. |
| `direct_vm.clear_mocks()` | resets LLM mocks (needed before re-keying a mock). |

Storage is inspectable: `contract.orders[1]` returns the stored dataclass,
and helper functions inside the contract module are reachable via
`sys.modules["_contract_<filename>"]` (used to inspect profiling prompts).

## 3. Suite map

| File | Focus |
|---|---|
| `tests/direct/test_spec_clear.py` | lifecycle, intake guards, pause/resume, consensus agreement & forged-leader rejection, prompt-injection inertness, fail-closed normalization, freeze/cancel rules |
| `tests/direct/test_clearing_policy.py` | the deterministic core: preference vs price, ask-priced trades, price ceilings, required/forbidden/ambiguous predicates, partial fills, request/offer tie-breaking, preview ≡ execution, single-clear finality |
| `tests/direct/test_fill_gate.py` | typed consumption, party checks, global + per-party replay protection, invalid-pin rejection, digest hygiene, constructor address normalization |
| `tests/unit/test_static_boundaries.py` | one-LLM-callsite boundary, single-order prompts, exact-agreement criteria, integer-only clearing, pinned runner headers (byte-exact), GenVM E022 lint guard, submission byte-identity, deployment-address sync |

## 4. Writing new scenarios

1. Reuse the fixtures in `tests/direct/test_spec_clear.py`: `setup_market`
   seals a 4-attribute GPU-capacity market; `submit_profiled_request` /
   `submit_profiled_offer` combine submission, mocking, and assessment in
   one call, with optional `warp=at(seconds)` for submission-time control.
2. Build masks by hand over bits `0..3` (see the comment block at the top of
   the suite) — hand-computed expectations are the point: they prove the
   clearing arithmetic independent of any model.
3. Never assert on reason text: it is explicitly non-consensus.
4. To test adversarial model behavior, mock a malformed payload directly and
   assert the fail-closed masks (`ambiguous == 0b1111`).

## 5. CI sketch

```yaml
steps:
  - run: pip install -r requirements.txt
  - run: python scripts/preflight.py
  - run: pytest tests/unit -q
  - run: pytest tests/direct -q
```

The unit layer is deliberately VM-free so boundary regressions surface even
if the chain toolchain is unavailable.

## 6. Testing the live Studionet deployment

Both contracts are live on stable Studionet (chain 61999) — the
lint-corrected artifacts:

* SpecClear — `0x304ad1FA90c4C48E82175d53596cb5632BAcd16e`
  ([explorer](https://explorer-studio.genlayer.com/address/0x304ad1FA90c4C48E82175d53596cb5632BAcd16e))
* FillGate — `0xd2c9489fe919594B711e49088f2672C2c962A7c8`
  ([explorer](https://explorer-studio.genlayer.com/address/0xd2c9489fe919594B711e49088f2672C2c962A7c8))

### 6.1 Read-only smoke checks (no funds, no writes)

```bash
npm install genlayer-js
node samples/studionet_smoke.mjs
```

The script asserts, in order:

1. `get_stats()` returns the counter dictionary — proves the primitive is
   reachable and the view ABI matches the source on disk.
2. `total_redemptions()` returns a number — proves FillGate deployed and its
   constructor accepted the SpecClear address.
3. `was_redeemed(<random digest>)` is `false` — proves the replay window
   starts empty.
4. `is_fill_valid(1, h, h, h)` is `false` for arbitrary digests — proves the
   pin check rejects uncommitted fills on-chain.
5. `deterministic_compatible(1, 2)` reverts with "order does not exist" while
   the counters are zero — proves guard rails live in production, not only
   in Direct Mode.

### 6.2 Full lifecycle dry-run against GenLayer Studio

For write flows, prefer the Studio UI (accounts and rate limits are managed
there). Exercise the exact sequence below — every step names the view that
proves success:

| # | Call | Proof via view |
|---|---|---|
| 1 | `create_market("Live check", "Studionet lifecycle verification market.")` | `get_market(1)` → `status_name == "DRAFT"` |
| 2 | `add_attribute(1, "RUSH", "Affirmative accelerated delivery evidence.")` ×2–4 variants | `get_market(1).attribute_count` grows |
| 3 | `seal_market(1)` | `definition_hash` non-empty; a follow-up `add_attribute` reverts with `vocabulary is sealed` |
| 4 | `open_epoch(1)` | `get_epoch(1).market_hash == definition_hash` |
| 5 | `submit_request(...)` / `submit_offer(...)` (unique 64-hex `client_order_hash` each) | `get_order(id).profile_ready == false` |
| 6 | `assess_order(id)` | transaction finalizes; `get_order(id).profile_ready == true` (consensus may take longer than ordinary writes — this is the LLM profiling step) |
| 7 | `freeze_epoch(1)` as market owner | reverts with `not yet assessed` if any active order lacks a profile — test this intentionally |
| 8 | `preview_clear(1)` → planned fills; then `clear_epoch(1)` from **any** account | `preview_clear` output equals recorded fills exactly |
| 9 | `is_fill_valid` / `is_fill_party` on each fill | `true` only for the exact hash triples and parties |
| 10 | `redeem_fill(...)` on FillGate, then replay it | first succeeds, replay reverts `already redeemed` |

### 6.3 Adversarial spot-checks worth running live

* duplicate `client_order_hash` → `already registered`
* uppercase digest anywhere → `lowercase hex digest`
* offer above the request bid → remains `ACTIVE` after clearing
* cancel from a non-owner account → `not the order owner`
* `clear_epoch` twice → `not frozen`

Every one of these is covered deterministically by the packaged Direct Mode
suite; the live pass exists to prove the identical bytecode behaves
identically under real consensus.
