"""Deterministic clearing policy tests for SpecClear epochs.

Every assertion in this file runs against pure contract arithmetic: once
profiles are assessed, the LLM is completely out of the loop. The scenarios
pin down the exact total order used by `clear_epoch`:

* requests rank by max unit price descending, submission time, order id
* offers rank per request by preference score descending, ask ascending,
  submission time, order id
* trade price is always the offer ask
* quantities may partially fill and remaining supply clears onward
"""

from test_spec_clear import (
    ALL_MASK,
    addr,
    at,
    h,
    offer_profile,
    request_profile,
    setup_market,
    submit_profiled_offer,
    submit_profiled_request,
)

NEED = "Must have attested confidential enclaves and NVLink fabric; carbon-neutral preferred."
SUPPLY_FULL = "Attested confidential enclaves on NVLink fabric; certified carbon-neutral; EU residency guaranteed."
SUPPLY_BASIC = "Attested confidential enclaves on NVLink fabric; fossil powered; no residency guarantees."


def run_two_offer_epoch(direct_vm, direct_deploy):
    """One request (qty 2) against a preferred-but-pricier offer and a
    cheaper-but-plain offer. Returns (contract, market_hash, epoch, ids)."""
    c, market, market_hash, epoch = setup_market(direct_vm, direct_deploy)
    request = submit_profiled_request(
        c, direct_vm, epoch, "buyer", NEED, 2, 5000, h("cp-r"),
        request_profile(required=3, preferred=8), warp=at(1),
    )
    offer_a = submit_profiled_offer(
        c, direct_vm, epoch, "seller_a", SUPPLY_FULL, 1, 4000, h("cp-a"),
        offer_profile(present=ALL_MASK, ambiguous=0), warp=at(2),
    )
    offer_b = submit_profiled_offer(
        c, direct_vm, epoch, "seller_b", SUPPLY_BASIC, 2, 3500, h("cp-b"),
        offer_profile(present=3, absent=12, ambiguous=0), warp=at(3),
    )
    direct_vm.sender = addr("owner")
    epoch_hash = c.freeze_epoch(epoch)
    return c, market_hash, epoch_hash, epoch, request, offer_a, offer_b


def test_clear_is_deterministic_and_preference_outranks_price(direct_vm, direct_deploy):
    c, market_hash, epoch_hash, epoch, request, offer_a, offer_b = run_two_offer_epoch(direct_vm, direct_deploy)
    direct_vm.sender = addr("anyone")  # clearing is permissionless
    count = c.clear_epoch(epoch)
    assert count == 2
    first = c.get_fill(1)
    second = c.get_fill(2)
    # Higher semantic preference outranks the cheaper offer.
    assert first["offer_id"] == offer_a
    assert first["request_id"] == request
    assert first["unit_price"] == 4000
    assert first["preference_score"] == 1
    assert second["offer_id"] == offer_b
    assert second["unit_price"] == 3500
    assert second["preference_score"] == 0
    # Every fill pins the exact commitments and verifies standalone.
    assert c.is_fill_valid(1, market_hash, epoch_hash, first["fill_hash"]) is True
    assert c.is_fill_valid(1, market_hash, epoch_hash, second["fill_hash"]) is False
    assert c.is_fill_party(1, market_hash, epoch_hash, first["fill_hash"], addr("seller_a")) is True
    assert c.is_fill_party(1, market_hash, epoch_hash, first["fill_hash"], addr("outsider")) is False
    epoch_data = c.get_epoch(epoch)
    assert epoch_data["status_name"] == "CLEARED"
    assert len(epoch_data["settlement_root"]) == 64
    assert epoch_data["fill_count"] == 2


def test_trade_price_is_offer_ask_not_bid(direct_vm, direct_deploy):
    c, _, _, epoch, _, offer_a, _ = run_two_offer_epoch(direct_vm, direct_deploy)
    c.clear_epoch(epoch)
    fill = c.get_fill(1)
    assert fill["unit_price"] == 4000  # ask, despite the 5000 bid
    assert fill["offer_id"] == offer_a


def test_price_ceiling_excludes_overpriced_offers(direct_vm, direct_deploy):
    c, _, _, epoch = setup_market(direct_vm, direct_deploy)
    submit_profiled_request(
        c, direct_vm, epoch, "buyer", NEED, 1, 5000, h("pc-r"),
        request_profile(required=3, preferred=8), warp=at(1),
    )
    cheap = submit_profiled_offer(
        c, direct_vm, epoch, "seller_cheap", SUPPLY_FULL, 1, 4500, h("pc-c"),
        offer_profile(present=ALL_MASK, ambiguous=0), warp=at(2),
    )
    pricey = submit_profiled_offer(
        c, direct_vm, epoch, "seller_pricey", SUPPLY_FULL, 1, 6000, h("pc-p"),
        offer_profile(present=ALL_MASK, ambiguous=0), warp=at(3),
    )
    assert c.deterministic_compatible(1, cheap) is True
    assert c.deterministic_compatible(1, pricey) is False  # 6000 ask > 5000 bid
    direct_vm.sender = addr("owner")
    c.freeze_epoch(epoch)
    assert c.clear_epoch(epoch) == 1
    assert c.get_fill(1)["offer_id"] == cheap
    assert c.get_order(pricey)["status_name"] == "ACTIVE"  # never cleared
    assert c.get_order(pricey)["remaining"] == 1


def test_missing_required_bit_is_incompatible(direct_vm, direct_deploy):
    c, _, _, epoch = setup_market(direct_vm, direct_deploy)
    request = submit_profiled_request(
        c, direct_vm, epoch, "buyer", NEED, 1, 5000, h("rq-1"),
        request_profile(required=3, preferred=0), warp=at(1),
    )
    offer = submit_profiled_offer(
        c, direct_vm, epoch, "seller", "Attested enclaves only; no fabric.", 1, 1000, h("rq-2"),
        offer_profile(present=1, absent=14, ambiguous=0), warp=at(2),
    )
    assert c.deterministic_compatible(request, offer) is False
    direct_vm.sender = addr("owner")
    c.freeze_epoch(epoch)
    assert c.clear_epoch(epoch) == 0


def test_forbidden_bit_present_is_incompatible(direct_vm, direct_deploy):
    c, _, _, epoch = setup_market(direct_vm, direct_deploy)
    submit_profiled_request(
        c, direct_vm, epoch, "buyer", "Must exclude EU residency entirely.", 1, 5000, h("fb-1"),
        request_profile(required=1, forbidden=4, preferred=0), warp=at(1),
    )
    submit_profiled_offer(
        c, direct_vm, epoch, "seller", SUPPLY_FULL, 1, 1000, h("fb-2"),
        offer_profile(present=ALL_MASK, ambiguous=0), warp=at(2),
    )
    assert c.deterministic_compatible(1, 2) is False


def test_ambiguous_offer_evidence_fails_closed_on_constrained_bits(direct_vm, direct_deploy):
    c, _, _, epoch = setup_market(direct_vm, direct_deploy)
    submit_profiled_request(
        c, direct_vm, epoch, "buyer", NEED, 1, 5000, h("am-1"),
        request_profile(required=3, preferred=8), warp=at(1),
    )
    # Offer is silent (ambiguous) on NVLINK_FABRIC (bit 1): even though the
    # ask is cheap and nothing is forbidden, it must not clear.
    submit_profiled_offer(
        c, direct_vm, epoch, "seller", "Attested enclaves; fabric unclear.", 1, 1000, h("am-2"),
        offer_profile(present=1, absent=0, ambiguous=14), warp=at(2),
    )
    assert c.deterministic_compatible(1, 2) is False
    direct_vm.sender = addr("owner")
    c.freeze_epoch(epoch)
    assert c.clear_epoch(epoch) == 0


def test_partial_fills_consume_supply_in_rank_order(direct_vm, direct_deploy):
    c, _, _, epoch = setup_market(direct_vm, direct_deploy)
    submit_profiled_request(
        c, direct_vm, epoch, "buyer", NEED, 5, 5000, h("pf-r"),
        request_profile(required=3, preferred=8), warp=at(1),
    )
    submit_profiled_offer(
        c, direct_vm, epoch, "seller_a", SUPPLY_FULL, 2, 4000, h("pf-a"),
        offer_profile(present=ALL_MASK, ambiguous=0), warp=at(2),
    )
    submit_profiled_offer(
        c, direct_vm, epoch, "seller_b", SUPPLY_BASIC, 4, 3500, h("pf-b"),
        offer_profile(present=3, absent=12, ambiguous=0), warp=at(3),
    )
    direct_vm.sender = addr("owner")
    c.freeze_epoch(epoch)
    assert c.clear_epoch(epoch) == 2
    first, second = c.get_fill(1), c.get_fill(2)
    assert (first["offer_id"], first["quantity"]) == (2, 2)    # preferred offer fully consumed
    assert (second["offer_id"], second["quantity"]) == (3, 3)  # remaining demand partially fills
    assert c.get_order(3)["status_name"] == "PARTIAL"
    assert c.get_order(3)["remaining"] == 1
    assert c.get_order(1)["status_name"] == "FILLED"


def test_requests_rank_by_bid_then_submission_time(direct_vm, direct_deploy):
    c, _, _, epoch = setup_market(direct_vm, direct_deploy)
    low_bid = submit_profiled_request(
        c, direct_vm, epoch, "buyer_low", NEED, 1, 4000, h("tb-r1"),
        request_profile(required=3, preferred=0), warp=at(1),
    )
    high_bid = submit_profiled_request(
        c, direct_vm, epoch, "buyer_high", NEED, 1, 4500, h("tb-r2"),
        request_profile(required=3, preferred=0), warp=at(2),
    )
    tied_early = submit_profiled_request(
        c, direct_vm, epoch, "buyer_tie_a", NEED, 1, 4500, h("tb-r3"),
        request_profile(required=3, preferred=0), warp=at(3),
    )
    tied_late = submit_profiled_request(
        c, direct_vm, epoch, "buyer_tie_b", NEED, 1, 4500, h("tb-r4"),
        request_profile(required=3, preferred=0), warp=at(4),
    )
    for index, seller in enumerate(("s1", "s2", "s3", "s4")):
        submit_profiled_offer(
            c, direct_vm, epoch, seller, SUPPLY_BASIC, 1, 3000, h(f"tb-o{index}"),
            offer_profile(present=3, absent=12, ambiguous=0), warp=at(10 + index),
        )
    direct_vm.sender = addr("owner")
    c.freeze_epoch(epoch)
    assert c.clear_epoch(epoch) == 4
    served = [c.get_fill(i)["request_id"] for i in range(1, 5)]
    assert served == [high_bid, tied_early, tied_late, low_bid]


def test_offer_ties_break_by_time_then_id(direct_vm, direct_deploy):
    c, _, _, epoch = setup_market(direct_vm, direct_deploy)
    request = submit_profiled_request(
        c, direct_vm, epoch, "buyer", NEED, 2, 5000, h("to-r"),
        request_profile(required=3, preferred=0), warp=at(1),
    )
    early = submit_profiled_offer(
        c, direct_vm, epoch, "seller_early", SUPPLY_BASIC, 1, 3000, h("to-a"),
        offer_profile(present=3, absent=12, ambiguous=0), warp=at(2),
    )
    late = submit_profiled_offer(
        c, direct_vm, epoch, "seller_late", SUPPLY_BASIC, 1, 3000, h("to-b"),
        offer_profile(present=3, absent=12, ambiguous=0), warp=at(3),
    )
    direct_vm.sender = addr("owner")
    c.freeze_epoch(epoch)
    assert c.clear_epoch(epoch) == 2
    assert c.get_fill(1)["offer_id"] == early
    assert c.get_fill(2)["offer_id"] == late


def test_epoch_cannot_clear_twice(direct_vm, direct_deploy):
    c, _, _, epoch, *_ = run_two_offer_epoch(direct_vm, direct_deploy)
    assert c.clear_epoch(epoch) == 2
    with direct_vm.expect_revert("not frozen"):
        c.clear_epoch(epoch)


def test_preview_matches_executed_clearing_exactly(direct_vm, direct_deploy):
    c, _, _, epoch, *_ = run_two_offer_epoch(direct_vm, direct_deploy)
    preview = c.preview_clear(epoch)
    assert len(preview) == 2
    c.clear_epoch(epoch)
    executed = [
        {k: c.get_fill(i)[k] for k in ("request_id", "offer_id", "quantity", "unit_price")}
        for i in (1, 2)
    ]
    previewed = [
        {k: row[k] for k in ("request_id", "offer_id", "quantity", "unit_price")}
        for row in preview
    ]
    assert previewed == executed
    # After clearing, the preview replays the recorded fills.
    replay = c.preview_clear(epoch)
    assert [row["offer_id"] for row in replay] == [row["offer_id"] for row in preview]
