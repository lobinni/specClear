# v1.0.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""FillGate — minimal consumer proving a SpecClear fill can gate another action.

This contract demonstrates the recommended consumption pattern for SpecClear
fills as typed, replay-safe capabilities:

1. The caller pins the exact market definition hash, epoch hash, and fill
   hash it believes authorizes the action.
2. FillGate performs typed IC-to-IC reads against SpecClear — it never trusts
   free-form results or caller-supplied metadata.
3. The caller must be one of the two fill parties.
4. Each action hash may be redeemed exactly once globally, and each
   (fill, party) pair may redeem exactly once, so a settled fill cannot be
   double-consumed across actions nor replayed by either counterparty.
"""

from genlayer import *

import typing
from dataclasses import dataclass


@gl.contract_interface
class ISpecClear:
    class View:
        def is_fill_valid(self, fill_id: u256, expected_market_hash: str, expected_epoch_hash: str, expected_fill_hash: str) -> bool: ...
        def is_fill_party(self, fill_id: u256, expected_market_hash: str, expected_epoch_hash: str, expected_fill_hash: str, actor: Address) -> bool: ...

    class Write:
        pass


@allow_storage
@dataclass
class Redemption:
    fill_id: u256
    actor: Address
    market_hash: str
    epoch_hash: str
    fill_hash: str
    action_hash: str
    redeemed_at: u256


class FillRedeemed(gl.Event):
    indexed: typing.ClassVar[tuple[str, ...]] = ("action_hash",)

    def __init__(self, action_hash: str, fill_id: u256, /, **blob): ...


def _require_digest(value: str, field: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise gl.vm.UserError(f"EXPECTED: {field} must be a 32-byte lowercase hex digest")
    return text


def _coerce_address(value: typing.Any) -> Address:
    """Normalize a constructor-provided address to a real ``Address`` object.

    GenVM's storage setter for typed ``Address`` fields requires an actual
    ``Address`` instance: assigning a plain ``int`` (for example when the
    address reaches the runner as a JSON number) crashes inside the storage
    layer with ``'int' object has no attribute 'as_bytes'``. Deployment
    frontends may encode constructor calldata as an Address, a hex string
    (with or without ``0x``), raw bytes, or a plain integer, so every form
    is normalized here instead of trusting the caller's encoding.
    """
    if isinstance(value, Address):
        return value
    if isinstance(value, bool):
        raise gl.vm.UserError("EXPECTED: invalid clearing address")
    if isinstance(value, int):
        if value < 0 or value >= (1 << 160):
            raise gl.vm.UserError("EXPECTED: clearing address out of range")
        value = "0x" + format(value, "040x")
    elif isinstance(value, (bytes, bytearray, memoryview)):
        value = "0x" + bytes(value).hex()
    text = str(value).strip().lower()
    if not text.startswith("0x"):
        text = "0x" + text
    body = text[2:]
    if len(body) != 40 or any(c not in "0123456789abcdef" for c in body):
        raise gl.vm.UserError("EXPECTED: clearing address must be 20 bytes (40 hex chars)")
    return Address(text)


def _message_timestamp() -> int:
    message = getattr(gl, "message", None)
    raw_message = getattr(message, "raw", None)
    raw = getattr(raw_message, "datetime", None)
    if raw in (None, ""):
        mapping = getattr(gl, "message_raw", None)
        raw = mapping.get("datetime", "") if isinstance(mapping, dict) else ""
    if isinstance(raw, int):
        return int(raw)
    if not isinstance(raw, str) or raw.strip() == "":
        raise gl.vm.UserError("EXPECTED: transaction timestamp unavailable")
    from datetime import datetime, timezone

    parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


class FillGate(gl.Contract):
    clearing_address: Address
    redeemed: TreeMap[str, Redemption]
    party_index: TreeMap[str, str]
    redemption_count: u256

    def __init__(self, clearing_address: Address):
        self.clearing_address = _coerce_address(clearing_address)
        self.redemption_count = u256(0)

    @gl.public.write
    def redeem_fill(
        self,
        fill_id: u256,
        expected_market_hash: str,
        expected_epoch_hash: str,
        expected_fill_hash: str,
        action_hash: str,
    ) -> None:
        market_hash = _require_digest(expected_market_hash, "market_hash")
        epoch_hash = _require_digest(expected_epoch_hash, "epoch_hash")
        fill_hash = _require_digest(expected_fill_hash, "fill_hash")
        action = _require_digest(action_hash, "action_hash")
        if action in self.redeemed:
            raise gl.vm.UserError("EXPECTED: action hash already redeemed")
        clearing = ISpecClear(self.clearing_address)
        if not clearing.view().is_fill_valid(fill_id, market_hash, epoch_hash, fill_hash):
            raise gl.vm.UserError("EXPECTED: fill does not match pinned market/epoch/fill hashes")
        actor = gl.message.sender_address
        if not clearing.view().is_fill_party(fill_id, market_hash, epoch_hash, fill_hash, actor):
            raise gl.vm.UserError("EXPECTED: caller is not a party to the fill")
        party_key = str(int(fill_id)) + ":" + str(actor).lower()
        if party_key in self.party_index:
            raise gl.vm.UserError("EXPECTED: this fill was already redeemed by this party")
        self.redeemed[action] = Redemption(
            fill_id=fill_id,
            actor=actor,
            market_hash=market_hash,
            epoch_hash=epoch_hash,
            fill_hash=fill_hash,
            action_hash=action,
            redeemed_at=u256(_message_timestamp()),
        )
        self.party_index[party_key] = action
        self.redemption_count = u256(int(self.redemption_count) + 1)
        FillRedeemed(action, fill_id, actor=str(actor)).emit()

    @gl.public.view
    def was_redeemed(self, action_hash: str) -> bool:
        return str(action_hash).strip().lower() in self.redeemed

    @gl.public.view
    def get_redemption(self, action_hash: str) -> dict:
        key = str(action_hash).strip().lower()
        if key not in self.redeemed:
            raise gl.vm.UserError("EXPECTED: action hash not redeemed")
        record = self.redeemed[key]
        return {
            "fill_id": int(record.fill_id),
            "actor": str(record.actor),
            "market_hash": record.market_hash,
            "epoch_hash": record.epoch_hash,
            "fill_hash": record.fill_hash,
            "action_hash": record.action_hash,
            "redeemed_at": int(record.redeemed_at),
        }

    @gl.public.view
    def total_redemptions(self) -> u256:
        return self.redemption_count
