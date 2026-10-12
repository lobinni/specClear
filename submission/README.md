# SpecClear — Submission Artifacts

This directory is the **entire submittable package**. It contains exactly the
two GenLayer Intelligent Contracts of the SpecClear protocol and nothing
else — no frontend, no test harness, no documentation code. Zip or upload
this folder as-is.

```
submission/
├── spec_clear.py   primary primitive — semantic-profile batch clearing
└── fill_gate.py    reference consumer IC — replay-safe fill redemption
```

Both files are byte-identical to the working sources in `../contracts/`;
byte equality is enforced continuously by `tests/unit` and
`scripts/preflight.py`, so the submission can never drift from what the test
suite verifies.

## Live deployments (stable Studionet, chain 61999)

The artifacts in this package are the **lint-corrected** sources (GenVM
E022: `_require_owner` is a plain instance method), and they are deployed
live at these addresses:

| Contract | Address | Explorer |
|---|---|---|
| SpecClear (primitive) | `0x304ad1FA90c4C48E82175d53596cb5632BAcd16e` | [explorer-studio](https://explorer-studio.genlayer.com/address/0x304ad1FA90c4C48E82175d53596cb5632BAcd16e) |
| FillGate (consumer) | `0xd2c9489fe919594B711e49088f2672C2c962A7c8` | [explorer-studio](https://explorer-studio.genlayer.com/address/0xd2c9489fe919594B711e49088f2672C2c962A7c8) |

`fill_gate.py` was deployed with constructor argument
`clearing_address = 0x304ad1FA90c4C48E82175d53596cb5632BAcd16e`
(the live SpecClear instance). The constructor normalizes the address
argument itself, so hex-string, bare-hex, bytes, integer, or native Address
calldata all deploy cleanly.

Superseded history (pre-lint-fix source, archived only):
`0xa0fc975486d67745C291D4740C804008c8D58264` and
`0x9F4FD16bD14D9DA4E2AF5BffC79C2131b8B436A8`.

## Deploy order

1. `spec_clear.py` — no constructor arguments.
2. `fill_gate.py` — constructor arg: the address of the deployed SpecClear contract.

**Do not touch the two-line runner header.** Both files must keep, verbatim:

```
# v1.0.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

Swapping or re-pinning that hash (by hand or via a tool) fails schema
extraction with `invalid_contract runner malformed` / `runner absent`.
Verify before upload: `head -n 2 submission/spec_clear.py`. See
`../docs/DEPLOYMENT.md` → Troubleshooting for the full failure table.

**If schema extraction fails instantly (empty stdout/stderr,
`compiled_modules: 0`), triage in this order:**

1. **Network** — confirm you are on **stable Studio** (`studio.genlayer.com`,
   chain 61999), *not* Studio Devnet (`studio-dev.genlayer.com`, chain
   61997). Devnet runs a different runner registry; identical sources that
   deploy on stable fail there for every contract, no matter the header.
2. **Bytes** — upload the file object itself rather than pasting source into
   an editor field. Pasted text can silently gain a BOM, CRLF endings, or
   curly quotes inside the runner header; all three produce the same
   pre-execution `runner malformed` failure. The repo bytes are byte-clean
   and guarded by `../scripts/preflight.py` (BOM-free, LF-only, ASCII
   quotes, valid header JSON).

## Verify quickly

Call the read-only methods from Studio or any GenLayer SDK client:

```
get_stats()          → { markets, epochs, orders, fills }   (all zero on a fresh deploy)
total_redemptions()  → 0                                     (on FillGate)
```

A full on-chain lifecycle (market → seal → epoch → orders → profiling →
freeze → deterministic clearing → fill redemption) plus adversarial
scenarios is exercised by the packaged Direct Mode suites; see
`../docs/TESTING.md` for the playbook and `../docs/DEPLOYMENT.md` for the
network runbook.
