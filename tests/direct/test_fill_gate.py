"""FillGate consumption tests: typed IC-to-IC reads and replay protection.

A settled SpecClear fill is a reusable capability for downstream contracts.
These tests pin the required consumption discipline:

* the gate verifies the fill through typed typed reads against the primitive,
  never through caller-supplied metadata;
* the caller must be a party of the pinned fill;
* an action hash redeems exactly once, globally;
* each (fill, party) pair redeems exactly once.
"""

from gltest.direct import create_address as addr

from test_spec_clear import (
    ALL_MASK,
    at,
    h,
    offer_profile,
    request_profile,
    setup_market,
    submit_profiled_offer,
    submit_profiled_request,
)

GATE = "contracts/fill_gate.py"


def contract_address(proxy):
    for name in ("address", "contract_address"):
        value = getattr(proxy, name, None)
        if value is not None:
            return value
    raise AssertionError("direct mode deploy proxy does not expose an address")


def deploy_gate(direct_deploy, clearing_address):
    try:
        return direct_deploy(GATE, args=[clearing_address])
    except TypeError:
        return direct_deploy(GATE, clearing_address)


def settled_epoch(direct_vm, direct_deploy):
    """Produce one cleared epoch with a single fill and return everything a
    consumer needs to reference it."""
    c, _, _, epoch = setup_market(direct_vm, direct_deploy)
    submit_profiled_request(
        c, direct_vm, epoch, "buyer", "Attested enclaves on NVLink fabric.", 1, 5000, h("gt-r"),
        request_profile(required=3, preferred=0), warp=at(1),
    )
    submit_profiled_offer(
        c, direct_vm, epoch, "seller", "Attested enclaves on NVLink fabric, EU hosted.", 1, 4000, h("gt-o"),
        offer_profile(present=ALL_MASK, ambiguous=0), warp=at(2),
    )
    direct_vm.sender = addr("owner")
    epoch_hash = c.freeze_epoch(epoch)
    assert c.clear_epoch(epoch) == 1
    market_hash = c.get_market(1)["definition_hash"]
    fill = c.get_fill(1)
    return c, market_hash, epoch_hash, fill


def test_fill_party_can_redeem_action(direct_vm, direct_deploy):
    c, market_hash, epoch_hash, fill = settled_epoch(direct_vm, direct_deploy)
    gate = deploy_gate(direct_deploy, contract_address(c))
    direct_vm.sender = addr("seller")
    gate.redeem_fill(1, market_hash, epoch_hash, fill["fill_hash"], h("act-1"))
    assert gate.was_redeemed(h("act-1")) is True
    record = gate.get_redemption(h("act-1"))
    assert record["fill_id"] == 1
    assert record["fill_hash"] == fill["fill_hash"]
    assert gate.total_redemptions() == 1


def test_action_hash_cannot_be_replayed(direct_vm, direct_deploy):
    c, market_hash, epoch_hash, fill = settled_epoch(direct_vm, direct_deploy)
    gate = deploy_gate(direct_deploy, contract_address(c))
    direct_vm.sender = addr("seller")
    gate.redeem_fill(1, market_hash, epoch_hash, fill["fill_hash"], h("act-2"))
    with direct_vm.expect_revert("already redeemed"):
        gate.redeem_fill(1, market_hash, epoch_hash, fill["fill_hash"], h("act-2"))
    direct_vm.sender = addr("buyer")
    with direct_vm.expect_revert("already redeemed"):
        gate.redeem_fill(1, market_hash, epoch_hash, fill["fill_hash"], h("act-2"))


def test_non_party_cannot_redeem(direct_vm, direct_deploy):
    c, market_hash, epoch_hash, fill = settled_epoch(direct_vm, direct_deploy)
    gate = deploy_gate(direct_deploy, contract_address(c))
    direct_vm.sender = addr("outsider")
    with direct_vm.expect_revert("not a party"):
        gate.redeem_fill(1, market_hash, epoch_hash, fill["fill_hash"], h("act-3"))
    assert gate.was_redeemed(h("act-3")) is False


def test_invalid_pin_cannot_redeem(direct_vm, direct_deploy):
    c, market_hash, epoch_hash, fill = settled_epoch(direct_vm, direct_deploy)
    gate = deploy_gate(direct_deploy, contract_address(c))
    direct_vm.sender = addr("seller")
    with direct_vm.expect_revert("pinned market/epoch/fill"):
        gate.redeem_fill(1, market_hash, epoch_hash, h("badfill"), h("act-4"))
    with direct_vm.expect_revert("pinned market/epoch/fill"):
        gate.redeem_fill(1, h("badmkt"), epoch_hash, fill["fill_hash"], h("act-5"))
    # Failed attempts must not consume fresh action hashes.
    assert gate.was_redeemed(h("act-4")) is False
    assert gate.was_redeemed(h("act-5")) is False


def test_each_party_redeems_at_most_once(direct_vm, direct_deploy):
    c, market_hash, epoch_hash, fill = settled_epoch(direct_vm, direct_deploy)
    gate = deploy_gate(direct_deploy, contract_address(c))
    direct_vm.sender = addr("seller")
    gate.redeem_fill(1, market_hash, epoch_hash, fill["fill_hash"], h("act-6"))
    with direct_vm.expect_revert("already redeemed by this party"):
        gate.redeem_fill(1, market_hash, epoch_hash, fill["fill_hash"], h("act-7"))
    # The counterparty redeems independently with a distinct action hash.
    direct_vm.sender = addr("buyer")
    gate.redeem_fill(1, market_hash, epoch_hash, fill["fill_hash"], h("act-8"))
    assert gate.total_redemptions() == 2


def test_digest_format_enforced(direct_vm, direct_deploy):
    c, market_hash, epoch_hash, fill = settled_epoch(direct_vm, direct_deploy)
    gate = deploy_gate(direct_deploy, contract_address(c))
    direct_vm.sender = addr("seller")
    with direct_vm.expect_revert("lowercase hex digest"):
        gate.redeem_fill(1, market_hash.upper(), epoch_hash, fill["fill_hash"], h("act-9"))


# ---------------------------------------------------------------------------
# Constructor address normalization
#
# GenVM's storage setter for typed Address fields demands a real Address
# object; deployment frontends may deliver constructor calldata as a plain
# integer (JSON number), hex string, or bytes. The constructor must coerce
# every accepted form instead of crashing inside the storage layer.
# ---------------------------------------------------------------------------


def test_constructor_accepts_integer_address(direct_vm, direct_deploy):
    c, market_hash, epoch_hash, fill = settled_epoch(direct_vm, direct_deploy)
    address_as_int = int(str(contract_address(c)), 16)
    gate = deploy_gate(direct_deploy, address_as_int)
    direct_vm.sender = addr("seller")
    gate.redeem_fill(1, market_hash, epoch_hash, fill["fill_hash"], h("act-int"))
    assert gate.was_redeemed(h("act-int")) is True


def test_constructor_accepts_hex_string_forms(direct_vm, direct_deploy):
    c, market_hash, epoch_hash, fill = settled_epoch(direct_vm, direct_deploy)
    unprefixed = str(contract_address(c)).lower().removeprefix("0x")
    gate = deploy_gate(direct_deploy, unprefixed)
    direct_vm.sender = addr("seller")
    gate.redeem_fill(1, market_hash, epoch_hash, fill["fill_hash"], h("act-hex"))
    assert gate.total_redemptions() == 1


def test_constructor_rejects_malformed_address(direct_vm, direct_deploy):
    c, _, _, _ = settled_epoch(direct_vm, direct_deploy)
    with direct_vm.expect_revert("out of range"):
        deploy_gate(direct_deploy, -12)
    with direct_vm.expect_revert("out of range"):
        deploy_gate(direct_deploy, (1 << 160) + 5)
    with direct_vm.expect_revert("40 hex chars"):
        deploy_gate(direct_deploy, "0x1234")
    with direct_vm.expect_revert("invalid clearing address"):
        deploy_gate(direct_deploy, True)
