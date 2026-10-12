# Samples

Runnable, copy-friendly material for exploring SpecClear without writing any
setup code.

## Contents

| File | What it is |
|---|---|
| `end_to_end.py` | Narrated full lifecycle: draft → seal → epoch → intake → consensus profiling → freeze → deterministic clear → fill verification → gated consumption. Runs in Direct Mode. |
| `studionet_smoke.mjs` | Read-only smoke checks against the **live Studionet deployment** (addresses below); optional `--write` lifecycle pass with a funded key. |
| `market_definition.json` | The canonical sample market (4-bit GPU-capacity vocabulary), the sample orders, and the expected clearing outcome — use it to validate your own harness. |
| `profiles/request_profile.json` | Mocked request profile (required / preferred masks). |
| `profiles/offer_full.json` | Mocked offer profile with every attribute affirmatively present. |
| `profiles/offer_basic.json` | Mocked offer profile with constraints satisfied and preferences explicitly denied. |

## Live deployment (stable Studionet, chain 61999)

* SpecClear — `0x304ad1FA90c4C48E82175d53596cb5632BAcd16e`
  ([explorer](https://explorer-studio.genlayer.com/address/0x304ad1FA90c4C48E82175d53596cb5632BAcd16e))
* FillGate — `0xd2c9489fe919594B711e49088f2672C2c962A7c8`
  ([explorer](https://explorer-studio.genlayer.com/address/0xd2c9489fe919594B711e49088f2672C2c962A7c8))

```bash
npm install genlayer-js
node samples/studionet_smoke.mjs          # read-only checks
SPEC_CLEAR_PRIVATE_KEY=0x... node samples/studionet_smoke.mjs --write
```

## Run the walkthrough

```bash
pip install -r requirements.txt
pytest samples/end_to_end.py -q -s
```

Expect the final assertion — the semantically preferred offer fills ahead of
the cheaper one — to pass silently, and the narration to print every
commitment hash along the way.

## Reuse the payloads in your own tests

```python
import json, pathlib

profiles = pathlib.Path("samples/profiles")
request_payload = (profiles / "request_profile.json").read_text()
vm.mock_llm("SPECCLEAR / ORDER PROFILE", request_payload)
```

Masks are plain integers over the bits declared in `market_definition.json`;
author new scenarios by editing descriptions and masks side by side, then
let the deterministic clearing rules (in `docs/CLEARING_RULES.md`) decide
what should happen — never the other way around.
