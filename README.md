# SpecClear

**Consensus-profiled semantic batch clearing for GenLayer — a reusable Intelligent Contract primitive.**

SpecClear serves batch markets whose requirements are partly qualitative —
"attested confidential-compute enclaves", "EU data residency", "NVLink
fabric" — requirements a numeric order book cannot compare safely and an
AI-matched marketplace cannot settle deterministically.

SpecClear separates the two concerns completely:

| | What decides | Runs at |
|---|---|---|
| **Consensus-backed profiling** | Each order, **alone**, is classified against a sealed market-local attribute dictionary into bounded bitmasks. | GenLayer LLM consensus (non-comparative equivalence) |
| **Deterministic clearing** | Compatibility, price ceilings, preference ranking, tie-breaking, partial fills, fill hashes, settlement roots, replay-safe consumption. | Pure contract arithmetic — identical on every validator |

The LLM **never** compares two orders, chooses counterparties, sets prices,
determines quantities, or selects winners. Ambiguous semantic evidence
fails closed: a dimension without affirmative evidence can never satisfy a
constrained counterparty.

---

## Last update

**2026-09-26 — lint-corrected redeployment + workspace split**

* **GenVM lint E022 fixed.** `_require_owner` is a plain instance method
  (decorated helpers on contract classes are lint-invalid). Regression
  guards: `scripts/preflight.py` + unit boundary tests.
* **Redeployed on stable Studionet (chain 61999)** with the corrected
  artifacts — live addresses in the table below; earlier instances
  (`0xa0fc…8264`, `0x9F4F…36A8`) are superseded.
* **Runner-header hygiene guards added** (byte-level: BOM-free, LF-only,
  ASCII quotes, exactly pinned hash) after hitting
  `invalid_contract runner malformed` from a wrong-network/Devnet session;
  full failure table in `docs/DEPLOYMENT.md` → Troubleshooting.
* **Workspace split finalized**: this directory is the submittable project;
  the documentation website lives in the sibling `frontend/` workspace
  folder and is never submitted nor pushed.
* **GitHub publishing guide** added: `docs/GITHUB.md` (first push, tagging
  the submittable state, one-liner submission zip via `git archive`).

## Live deployment — stable Studionet (chain 61999)

| Contract | Address | Explorer |
|---|---|---|
| **SpecClear** (primitive) | `0x304ad1FA90c4C48E82175d53596cb5632BAcd16e` | [view on explorer-studio](https://explorer-studio.genlayer.com/address/0x304ad1FA90c4C48E82175d53596cb5632BAcd16e) |
| **FillGate** (reference consumer) | `0xd2c9489fe919594B711e49088f2672C2c962A7c8` | [view on explorer-studio](https://explorer-studio.genlayer.com/address/0xd2c9489fe919594B711e49088f2672C2c962A7c8) |

The FillGate instance is wired to the deployed SpecClear address above.
Quick read-only verification: `get_stats()` on SpecClear and
`total_redemptions()` on FillGate. Full runbook: `docs/DEPLOYMENT.md`.

---

## Protocol state machine

```
 DRAFT ──add_attribute──▶ SEALED ──open_epoch──▶  EPOCH OPEN
 market grows bounded      definition_hash         pinned to market_hash
 vocabulary (≤16 bits)     freezes vocabulary       orders enter with
                                                    qualitative text +
                                                    explicit price/qty
                                                        │
                             assess_order (consensus, one order at a time)
                                                        ▼
 CLEARED ◀──clear_epoch── FROZEN                profiles READY
 settlement_root,          epoch_hash commits         required/forbidden/
 fill hashes               the order set              preferred/present/
 (permissionless)                                    absent/ambiguous masks
```

1. `create_market(name, semantics)` — owner opens a draft market.
2. `add_attribute(market, label, definition)` — up to 16 bounded semantic
   dimensions, each with a human-readable evidence definition.
3. `seal_market(market)` — freezes the vocabulary and pins `definition_hash`.
4. `open_epoch(market)` — opens an order batch pinned to that hash.
5. `submit_request` / `submit_offer` — qualitative description plus explicit
   quantitative `quantity` + `max_unit_price` / `ask_unit_price`, and a
   client identity digest for idempotency.
6. `assess_order(order)` — GenLayer consensus profiles **that single order**
   into integer masks (requests: required/forbidden/preferred/ambiguous;
   offers: present/absent/ambiguous). Malformed output fails closed into
   all-ambiguous.
7. `freeze_epoch(epoch)` — owner commits the assessed order set into
   `epoch_hash`. Permissionless `clear_epoch` then runs mechanically.
8. `clear_epoch(epoch)` — deterministic matching with documented total
   ordering; emits fills pinning market/epoch/fill hashes and a folded
   `settlement_root`.
9. `fill_gate.py` — reference consumer proving fills are typed,
   replay-safe capabilities for downstream contracts.

## Deterministic clearing policy

* Requests rank by **max unit price descending**, then submission time, then
  order id.
* For each request, compatible offers rank by **semantic preference score**
  (`popcount(preferred_req & present_offer)`) descending, then ask
  ascending, then submission time, then order id.
* Compatibility requires: same frozen epoch, both profiles ready,
  `ask ≤ max_bid`, all required bits affirmatively present on the offer, no
  forbidden bit present, and no constrained bit ambiguous on the offer.
* Trade price is always the **offer ask**. Quantities partially fill and
  remaining supply/demand clears onward within the epoch.

No LLM call participates in any of the above. `tests/unit` enforces the
boundary statically — there is exactly one `exec_prompt` call site in the
codebase, inside the single-order assessment path.

## Repository layout

```
submission/            THE SUBMITTABLE PACKAGE — upload this directory only
  spec_clear.py        primary primitive (byte-identical to contracts/)
  fill_gate.py         reference consumer IC (byte-identical to contracts/)
  README.md            artifact manifest + live deployment addresses
contracts/             canonical working sources (mirrored into submission/)
tests/
  conftest.py          Direct Mode VM patches (timestamps, Windows loader)
  direct/              protocol, adversarial, clearing-policy, and gate tests
  unit/                static product-boundary checks (no VM required)
samples/
  end_to_end.py        runnable narrated lifecycle (pytest, Direct Mode)
  studionet_smoke.mjs  read/write smoke calls against the live deployment
  market_definition.json  canonical GPU-capacity market + expected clearing
  profiles/            canonical mock profile payloads
scripts/
  preflight.py         static final gate (compile + boundary + artifacts)
docs/
  ARCHITECTURE.md      design, protocol split, state model
  CLEARING_RULES.md    exact matching arithmetic with worked examples
  INVARIANTS.md        reviewer-facing invariants
  THREAT_MODEL.md      failure and adversary model
  TESTING.md           local Direct Mode playbook + live-network testing
  DEPLOYMENT.md        network targets, runbook, verified live deployment
  GITHUB.md            git/GitHub publishing + submission zip commands
requirements.txt       pinned toolchain
pytest.ini
.gitignore             python/node/build caches excluded from git
```

**Submission rule:** submit the **`submission/` directory only** — it holds
the exact Intelligent Contract artifacts (and a tiny manifest), nothing
else. The project ships a pure GenLayer Intelligent Contract protocol; the
companion documentation website lives outside this directory (sibling
`frontend/` workspace folder) and is never part of any submission.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/preflight.py          # static gate
pytest tests/unit -q                 # boundary checks (fast, no VM)
pytest tests/direct -q               # full protocol suite (Direct Mode)
pytest samples/end_to_end.py -q -s   # narrated lifecycle walkthrough
```

Against the live Studionet deployment:

```bash
npm install genlayer-js              # one extra dependency, lives outside submission/
node samples/studionet_smoke.mjs     # read-only smoke checks by default
```

Publish to GitHub: see **`docs/GITHUB.md`** — `git init -b main && git add .
&& git commit …` from inside this directory, tagging the submittable state,
and the one-liner `git archive --format=zip … main:submission` that produces
the exact upload package.

See `docs/TESTING.md` for mocking/validator details and the live testing
guide, and `docs/DEPLOYMENT.md` for the network runbook.

## Why not "AI matches buyers and sellers"?

Pairwise AI adjudication is unreviewable: the same pair can match or not
across validators, across replays, across time. SpecClear's profile is
**one order, one dictionary, one mask** — validators independently re-derive
it, disagreement is measurable, and every downstream decision traces to
integer arithmetic any auditor can recompute. That is the entire product.
