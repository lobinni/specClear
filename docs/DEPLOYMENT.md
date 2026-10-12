# Deployment

## Target network

SpecClear targets **GenLayer Studionet** for developer deployment and
validation.

| Property | Value |
|---|---|
| Alias | `studionet` |
| Chain ID | `61999` |
| RPC | `https://studio.genlayer.com/api` |
| Explorer | `https://explorer-studio.genlayer.com` |

## GenVM lint compliance (E022)

Reviewer feedback identified a GenVM lint failure **E022** on the
`_require_owner` guard: it was declared as an `@staticmethod` inside the
contract class, and decorated methods are not lint-valid on `gl.Contract`
subclasses. The guard is now a plain instance method —

```python
def _require_owner(self, market: Market) -> None:
    if gl.message.sender_address != market.owner:
        raise gl.vm.UserError(f"{ERR_EXPECTED}: caller is not the market owner")
```

— with identical semantics at every call site (`self._require_owner(market)`).
No other decorated methods exist in either artifact. The fix is enforced
going forward by `scripts/preflight.py` (`lint E022` checks) and
`tests/unit::test_owner_guard_is_a_lint_valid_instance_method`.

**Redeployment completed.** The corrected artifacts are live at the
addresses below (stable Studionet, chain 61999).

## Verified live deployment (lint-corrected artifacts)

| Contract | Artifact | Address | Explorer |
|---|---|---|---|
| SpecClear (primitive) | `submission/spec_clear.py` | `0x304ad1FA90c4C48E82175d53596cb5632BAcd16e` | [link](https://explorer-studio.genlayer.com/address/0x304ad1FA90c4C48E82175d53596cb5632BAcd16e) |
| FillGate (consumer) | `submission/fill_gate.py` | `0xd2c9489fe919594B711e49088f2672C2c962A7c8` | [link](https://explorer-studio.genlayer.com/address/0xd2c9489fe919594B711e49088f2672C2c962A7c8) |

Superseded history (pre-lint-fix source, archived only):
`0xa0fc975486d67745C291D4740C804008c8D58264` (primitive) and
`0x9F4FD16bD14D9DA4E2AF5BffC79C2131b8B436A8` (consumer), both on
stable Studionet.

Deployment facts:

* `fill_gate.py` deployed with constructor argument
  `clearing_address = 0x304ad1FA90c4C48E82175d53596cb5632BAcd16e`. The
  constructor coerces the argument into a native `Address` internally, so
  string/bytes/integer/native calldata encodings all succeed; malformed
  encodings revert with a readable `EXPECTED:` reason.
* `spec_clear.py` deployed with no constructor arguments.

Instant read-only verification (any SDK/Studio console):

```
spec_clear.get_stats()      → { markets: 0, epochs: 0, orders: 0, fills: 0 }
fill_gate.total_redemptions() → 0
fill_gate.is_fill_valid(1, <any 64-hex>, <any 64-hex>, <any 64-hex>) → false
```

The `samples/studionet_smoke.mjs` script performs these calls automatically;
see `docs/TESTING.md` §6 for the full live-network test playbook.

## Troubleshooting (failure classes actually hit and fixed here)

| Symptom | Root cause | Fix |
|---|---|---|
| GenVM lint **E022** on `_require_owner` | `@staticmethod` decorator on a contract-class method — decorated helpers are not lint-valid on `gl.Contract` subclasses | Done in this package: the guard is a plain instance method (`self`) everywhere |
| `gen_getContractSchemaForCode` → `VM_ERROR: invalid_contract runner malformed` fails **instantly with empty stdout/stderr and `compiled_modules: 0`** — for **every** contract tried, including ones that deployed successfully before | **Wrong network.** Studio Devnet (`studio-dev.genlayer.com/api`, chain **61997**) and stable Studio (`studio.genlayer.com/api`, chain **61999**) run **different runner registries** — identical sources that deploy on stable fail schema extraction on Devnet. This failure mode is contract-independent, which is the giveaway | Switch the Studio network / RPC back to **stable Studionet (61999)** and retry the identical bytes |
| Same `runner malformed` error — but only on your file, while a minimal known-good contract schema-generates fine on the same network | **Corrupted upload bytes.** A BOM (`EF BB BF`) on line 1, CRLF line endings, or curly quotes (`“ ”`) replacing ASCII `"` inside the two-line runner header breaks the schema-time header parse before any Python runs (hence: empty stdout/stderr) | Upload the file object itself (do not re-paste from a chat/markdown view). The repo bytes pass `scripts/preflight.py` byte-level checks (BOM-free, LF-only, ASCII quotes, valid header JSON) |
| `invalid_contract runner absent` with a pinned header on the correct network | Runner alias like `py-genlayer:test` / `:latest`, or a hand-swapped runner hash unknown to the node's registry | Keep the exact pinned header shipped in `submission/`; never re-pin |

**Verify the header of the exact bytes you are about to upload:**

```bash
head -n 2 submission/spec_clear.py
# must print exactly:
# v1.0.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

Both checks are enforced locally: `python scripts/preflight.py` fails on any
header drift, and `tests/unit::test_contracts_pin_runner_dependency` pins the
expected header verbatim. A gasless schema dry-run before real deployment is
also possible via `gen_getContractSchemaForCode` on the Studionet RPC — it
surfaces lint/schema problems without spending a transaction.

## Lifecycle checklist

1. **Preflight** — `python scripts/preflight.py` must pass.
2. **Local suites** — `pytest tests/unit -q && pytest tests/direct -q` green
   against the pinned `genlayer-testing-suite==0.29.2`.
3. **Deploy the primitive** — deploy `submission/spec_clear.py` (no
   constructor arguments). Record the contract address.
4. **Deploy the reference consumer** *(optional)* — deploy
   `submission/fill_gate.py` with constructor arg
   `clearing_address = <primitive address>`. The constructor normalizes the
   provided address itself: `0x`-prefixed or bare hex strings, raw bytes, a
   plain integer, or an `Address` value are all accepted, so Studio/CLI JSON
   calldata cannot crash the typed storage setter. Malformed values revert
   with a clear `EXPECTED:` reason instead.
5. **Configure a market** — `create_market` → `add_attribute` ≤ 16 times →
   `seal_market`. Verify `definition_hash` off-chain by re-hashing the
   canonical JSON definition.
6. **Open an epoch** — `open_epoch(market_id)`; the epoch pins the sealed
   `definition_hash`.
7. **Intake + profiling** — participants `submit_request` / `submit_offer`;
   each new order is finalized by exactly one `assess_order` call (anyone
   may trigger it; profiling is one-shot).
8. **Freeze** — market owner calls `freeze_epoch`; it reverts while any
   active order is unassessed.
9. **Clear** — anyone calls `clear_epoch`; fills, `epoch_hash`-pinned
   `fill_hash`es, and `settlement_root` become queryable via views.
10. **Consume** — downstream contracts reference fills by
    `(fill_id, market_hash, epoch_hash, fill_hash)` and validate them with
    `is_fill_valid` / `is_fill_party` — or via the shipped `FillGate`.

## Verification runbook (what "success" looks like)

After step 9 on Studionet, confirm on the explorer or via SDK reads:

- `get_epoch(...)` reports `status_name == "CLEARED"`, a non-empty
  `settlement_root`, and `fill_count` matching `preview_clear` taken
  pre-clear.
- Every `get_fill(...)` triple `(market_hash, epoch_hash, fill_hash)`
  satisfies `is_fill_valid`.
- Ranking evidence: with the sample market
  (`samples/market_definition.json`), the *preferred* offer (carbon-neutral,
  ask 4000) fills **before** the cheaper plain offer (ask 3500) — semantic
  preference outranking price is the protocol's signature behavior.

## CLI (genlayer-js SDK)

```bash
npm install -g genlayer
genlayer network login          # select studionet
genlayer deploy submission/spec_clear.py
genlayer deploy submission/fill_gate.py --args '["0x304ad1FA90c4C48E82175d53596cb5632BAcd16e"]'
genlayer call <spec_clear_address> create_market --args '["Accelerated compute capacity","Batch market for reserved GPU compute capacity."]'
```

Prefer the GenLayer Studio UI (`https://studio.genlayer.com`) for
interactive iteration; keep the CLI transcripts in your submission notes.

## Operational notes

- **One `assess_order` transaction per order.** Batch intake, then assess;
  freeze reverts until every active order carries a profile.
- **Timestamps** come from the consensus transaction datetime at each
  transition (`submitted_at`, `assessed_at`, `frozen_at`, `cleared_at`) —
  tie-breaking already reflects real submission order.
- **Gas/model cost** is driven by prompt size: keep attribute definitions
  tight (≤ 420 chars by construction) and vocabularies small.
- **Upgrades** — market vocabularies are immutable post-seal; deploy new
  primitives for protocol changes and migrate by opening fresh markets.
