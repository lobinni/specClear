"""End-to-end SpecClear lifecycle sample (Direct Mode, no network).

This file is a narrated, runnable walkthrough of the full primitive:

    market creation -> vocabulary sealing -> epoch open -> order intake ->
    consensus profiling -> epoch freeze -> deterministic clearing ->
    fill verification -> gated consumption

Run it with the pinned testing toolchain:

    pytest samples/end_to_end.py -q -s

The `-s` flag surfaces the step-by-step narration. Direct Mode executes the
leader path locally and simulates validator re-execution, so every LLM call
below is routed through a deterministic mock keyed on the profiler prompt
tag — exactly what happens under consensus on a real network, minus the
network.
"""

import json
import sys
from datetime import datetime, timedelta

BASE = "2026-11-05T09:30:00+00:00"
PROFILER = "SPECCLEAR / ORDER PROFILE"

ATTRIBUTE_VOCABULARY = [
    ("CONFIDENTIAL_COMPUTE", "Offer affirmatively supports confidential-compute attested GPU enclaves."),
    ("NVLINK_FABRIC", "Offer affirmatively provides NVLink interconnected multi-GPU fabric."),
    ("EU_RESIDENCY", "Offer affirmatively guarantees data residency inside the European Union."),
    ("CARBON_NEUTRAL", "Offer affirmatively evidences certified carbon-neutral power usage."),
]

REQUEST_PROFILE = {
    "required_mask": 0b0011,   # must have enclaves + NVLink fabric
    "forbidden_mask": 0b0000,
    "preferred_mask": 0b1000,  # carbon-neutral is nice to have
    "ambiguous_mask": 0b0000,
    "reason": "explicit requirements at bits 0-1, preference at bit 3",
}
FULL_PROFILE = {
    "present_mask": 0b1111,
    "absent_mask": 0b0000,
    "ambiguous_mask": 0b0000,
    "reason": "all four capabilities affirmatively described",
}
BASIC_PROFILE = {
    "present_mask": 0b0011,
    "absent_mask": 0b1100,
    "ambiguous_mask": 0b0000,
    "reason": "enclaves and fabric present; residency and carbon explicitly denied",
}


def _apply_datetime_mirror():
    """Mirror vm.warp() into gl.message_raw["datetime"] (same patch the
    shipped conftest applies for the packaged suites)."""
    from gltest.direct.vm import VMContext

    original_refresh = VMContext._refresh_gl_message

    def refresh_and_mirror_datetime(vm):
        original_refresh(vm)
        gl_module = sys.modules.get("genlayer.gl")
        raw_message = getattr(gl_module, "message_raw", None) if gl_module else None
        if isinstance(raw_message, dict):
            raw_message["datetime"] = vm._datetime

    VMContext._refresh_gl_message = refresh_and_mirror_datetime


_apply_datetime_mirror()


def step(number, label):
    print(f"\n--- step {number:02d} | {label}")


def test_end_to_end_lifecycle(direct_vm, direct_deploy):
    from gltest.direct import create_address as addr

    def at(seconds):
        return (datetime.fromisoformat(BASE) + timedelta(seconds=seconds)).isoformat()

    def digest(fragment):
        return (str(fragment) * 64)[:64].ljust(64, "0")

    def mock(vm, payload):
        vm.clear_mocks()
        vm.mock_llm(PROFILER, json.dumps(payload))

    step(1, "deploy the primitive and open a draft market")
    direct_vm.warp(BASE)
    clearing = direct_deploy("contracts/spec_clear.py")
    direct_vm.sender = addr("owner")
    market = clearing.create_market(
        "Accelerated compute capacity",
        "Batch market for reserved GPU compute capacity with qualitative platform requirements.",
    )
    print("market id:", int(market))

    step(2, "define and seal the bounded attribute vocabulary")
    for label, definition in ATTRIBUTE_VOCABULARY:
        bit = clearing.add_attribute(market, label, definition)
        print(f"bit {int(bit)}: {label}")
    definition_hash = clearing.seal_market(market)
    print("definition hash:", definition_hash)

    step(3, "open an epoch pinned to the sealed definition")
    epoch = clearing.open_epoch(market)
    print("epoch id:", int(epoch))

    step(4, "submit one request and two offers (qualitative text + explicit price/quantity)")
    direct_vm.sender = addr("buyer")
    direct_vm.warp(at(1))
    request = clearing.submit_request(
        epoch,
        "Training run needs attested confidential enclaves on an NVLink fabric; carbon-neutral power preferred.",
        2,
        5000,
        digest("req-1"),
    )
    direct_vm.sender = addr("seller_a")
    direct_vm.warp(at(2))
    offer_a = clearing.submit_offer(epoch, "Attested enclave nodes on NVLink fabric, EU hosted, fully carbon-neutral certified.", 1, 4000, digest("off-a"))
    direct_vm.sender = addr("seller_b")
    direct_vm.warp(at(3))
    offer_b = clearing.submit_offer(epoch, "Attested enclave nodes on NVLink fabric, fossil powered, non-EU.", 2, 3500, digest("off-b"))
    print("request:", int(request), "offers:", int(offer_a), int(offer_b))

    step(5, "consensus profiling: one order at a time, masks only")
    mock(direct_vm, REQUEST_PROFILE)
    print("request profile hash:", clearing.assess_order(request))
    mock(direct_vm, FULL_PROFILE)
    print("offer A profile hash:", clearing.assess_order(offer_a))
    mock(direct_vm, BASIC_PROFILE)
    print("offer B profile hash:", clearing.assess_order(offer_b))

    step(6, "freeze the epoch (commits every assessed order hash)")
    direct_vm.sender = addr("owner")
    epoch_hash = clearing.freeze_epoch(epoch)
    print("epoch hash:", epoch_hash)

    step(7, "preview the deterministic clearing, then execute it")
    preview = clearing.preview_clear(epoch)
    print("planned fills:", preview)
    direct_vm.sender = addr("keeper")  # clearing is permissionless
    fill_count = clearing.clear_epoch(epoch)
    assert int(fill_count) == len(preview)
    first, second = clearing.get_fill(1), clearing.get_fill(2)
    print("fill 1:", {k: first[k] for k in ("request_id", "offer_id", "quantity", "unit_price", "preference_score")})
    print("fill 2:", {k: second[k] for k in ("request_id", "offer_id", "quantity", "unit_price", "preference_score")})
    assert first["offer_id"] == int(offer_a), "semantic preference must outrank the cheaper offer"
    assert second["offer_id"] == int(offer_b)
    epoch_data = clearing.get_epoch(epoch)
    print("settlement root:", epoch_data["settlement_root"])

    step(8, "verify fills and consume one through the gate contract")
    assert clearing.is_fill_valid(1, definition_hash, epoch_hash, first["fill_hash"])
    assert clearing.is_fill_party(1, definition_hash, epoch_hash, first["fill_hash"], addr("seller_a"))
    try:
        gate = direct_deploy("contracts/fill_gate.py", args=[clearing.address])
    except TypeError:
        gate = direct_deploy("contracts/fill_gate.py", clearing.address)
    direct_vm.sender = addr("seller_a")
    gate.redeem_fill(1, definition_hash, epoch_hash, first["fill_hash"], digest("action-1"))
    assert gate.was_redeemed(digest("action-1"))
    print("redeemed action hash:", digest("action-1"))
    print("\nsample complete — the LLM profiled orders; never matched, priced, or ranked them.")
