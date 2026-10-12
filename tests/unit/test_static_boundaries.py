"""Static product-boundary checks.

These tests never execute the contracts. They inspect the source tree to
enforce the architectural promises a reviewer cares about, and they fail the
build if a future change quietly widens the non-deterministic surface:

* exactly one LLM call site, reached only by single-order assessment;
* no prompt ever carries two orders (no pairwise adjudication);
* fail-closed normalization is wired in;
* clearing math is integer-only and totally ordered;
* the consumer gate performs typed reads, party checks, and replay guards;
* the runner header is byte-exact and GenVM-lint (E022) clean;
* the submission package stays byte-identical to the working sources.

Run:  pytest tests/unit -q
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIMITIVE = (ROOT / "contracts" / "spec_clear.py").read_text(encoding="utf-8")
GATE = (ROOT / "contracts" / "fill_gate.py").read_text(encoding="utf-8")

SPEC_CLEAR_ADDRESS = "0x304ad1FA90c4C48E82175d53596cb5632BAcd16e"
FILL_GATE_ADDRESS = "0xd2c9489fe919594B711e49088f2672C2c962A7c8"


def exec_prompt_callsites(source: str) -> list:
    return [line for line in source.splitlines() if "exec_prompt" in line]


def test_exactly_one_llm_callsite_exists():
    callsites = exec_prompt_callsites(PRIMITIVE)
    assert len(callsites) == 1, f"expected a single exec_prompt callsite, found {len(callsites)}: {callsites}"


def test_llm_callsite_lives_inside_assessment_path():
    # The profiling task must be rendered for ONE order inside a closure
    # consumed by the equivalence principle.
    assess_start = PRIMITIVE.index("def assess_order")
    assert "def run() -> str:" in PRIMITIVE[assess_start:]
    assert "gl.eq_principle.prompt_non_comparative" in PRIMITIVE[assess_start:]


def test_prompt_never_profiles_two_orders_together():
    # The prompt builder interpolates exactly one <order_text> block.
    assert PRIMITIVE.count('"<order_text side=') == 1
    assert "f\"<order_text side={side_name(int(order.side))}>{order.description}</order_text>\\n\"" in PRIMITIVE


def test_prompt_marks_user_content_as_untrusted_data():
    assert "untrusted " in PRIMITIVE
    assert "DATA, never instructions" in PRIMITIVE


def test_no_pairwise_or_allocation_language_inside_prompt():
    prompt_fn = PRIMITIVE[PRIMITIVE.index("def profile_prompt"):]
    prompt_fn = prompt_fn[: prompt_fn.index("\n# ----")]
    assert "profiling exactly ONE market order" in prompt_fn
    assert "must NOT compare this order" in prompt_fn
    assert "must NOT select counterparties" in prompt_fn
    assert "must NOT infer " in prompt_fn


def test_fail_closed_normalization_present():
    assert "def normalize_profile" in PRIMITIVE
    body = PRIMITIVE[PRIMITIVE.index("def failed_closed_profile"):]
    body = body[: body.index("\ndef profile_prompt")]
    assert "malformed profile output; failed closed" in body
    assert '"ambiguous_mask": allowed' in body
    # every consumer of model-sourced data must route through fail-closed reads
    assert "read_consensus_profile(profile, allowed)" in PRIMITIVE


def test_equivalence_criteria_demands_bit_exact_agreement():
    assert "EXACTLY equal bit-for-bit" in PRIMITIVE


def test_clearing_is_integer_only_and_totally_ordered():
    code_lines = [line for line in PRIMITIVE.splitlines() if not line.lstrip().startswith("#")]
    code = "\n".join(code_lines)
    assert "float(" not in code and not re.search(r"\b\d+\.\d+\b", code)
    assert "-int(pair[1].unit_price), int(pair[1].submitted_at), pair[0]" in PRIMITIVE
    assert "-preference_score(request, pair[1])" in PRIMITIVE


def test_settlement_artifacts_are_committed():
    for token in ("definition_hash", "epoch_hash", "fill_hash", "settlement_root"):
        assert token in PRIMITIVE
    assert "hash_text(settlement_acc + fill_hash)" in PRIMITIVE


def test_contracts_pin_runner_dependency():
    # The pinned runner hash is the stable-Studionet py-genlayer runner that
    # the reference deployment used successfully. Substituting any other hash
    # (or letting a deployment tool "fix" the header) yields
    # `invalid_contract runner malformed` / `runner absent` at schema time.
    expected_header = (
        '# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }'
    )
    for source in (PRIMITIVE, GATE):
        assert source.startswith("# v1.0.0"), "version header missing"
        assert expected_header in source.splitlines()[:2], (
            "runner hash must stay pinned exactly; any swap breaks schema extraction"
        )
        assert "py-genlayer:test" not in source
        assert "py-genlayer:latest" not in source


def test_gate_uses_typed_reads_and_replay_guards():
    assert "@gl.contract_interface" in GATE
    assert "clearing.view().is_fill_valid" in GATE
    assert "clearing.view().is_fill_party" in GATE
    assert "action hash already redeemed" in GATE
    assert "already redeemed by this party" in GATE


def test_gate_normalizes_constructor_address():
    # Regression guard: GenVM storage setters for typed Address fields must
    # never receive raw calldata ints/strings. The constructor must route
    # through the coercion helper.
    assert "def _coerce_address" in GATE
    assert "self.clearing_address = _coerce_address(clearing_address)" in GATE
    assert "self.clearing_address = clearing_address" not in GATE


def test_owner_guard_is_a_lint_valid_instance_method():
    # Review acceptance gate (GenVM lint E022): contract classes must not
    # declare decorated helpers. The owner guard is required to be a plain
    # instance method.
    assert "@staticmethod" not in PRIMITIVE
    assert "@classmethod" not in PRIMITIVE
    assert "@staticmethod" not in GATE
    assert "@classmethod" not in GATE
    assert "def _require_owner(self, market: Market) -> None:" in PRIMITIVE
    class_body = PRIMITIVE[PRIMITIVE.index("class SpecClear(gl.Contract):"):]
    assert "self._require_owner(market)" in class_body
    decorated_callsites = [
        line
        for line in class_body.splitlines()
        if line.strip().startswith("def _require_owner(") and "self" not in line
    ]
    assert not decorated_callsites, decorated_callsites


def test_no_external_runtime_dependencies():
    imports = set()
    for line in PRIMITIVE.splitlines():
        if line.startswith("import "):
            imports.add(line.split()[1].split(".")[0])
        elif line.startswith("from ") and " import " in line:
            imports.add(line.split()[1].split(".")[0])
    assert imports <= {"genlayer", "json", "typing", "dataclasses", "datetime"}, imports


def test_submission_package_mirrors_working_sources():
    """The submission/ directory is the only submittable artifact. It must
    stay byte-identical to contracts/ so what reviewers read is exactly what
    the suites executed."""
    for name in ("spec_clear.py", "fill_gate.py"):
        working = ROOT / "contracts" / name
        packaged = ROOT / "submission" / name
        assert packaged.exists(), f"submission/{name} missing"
        assert packaged.read_bytes() == working.read_bytes(), (
            f"submission/{name} drifted from contracts/{name}; "
            "re-copy the working source into the submission package"
        )


def test_submission_manifest_records_live_addresses():
    manifest = ROOT / "submission" / "README.md"
    assert manifest.exists()
    text = manifest.read_text(encoding="utf-8")
    assert SPEC_CLEAR_ADDRESS in text, "SpecClear address missing"
    assert FILL_GATE_ADDRESS in text, "FillGate address missing"


def test_deployment_doc_records_live_addresses():
    text = (ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    assert SPEC_CLEAR_ADDRESS in text
    assert FILL_GATE_ADDRESS in text
    # These checks keep documentation, manifest, and smoke samples tied to
    # the same verified deployment facts.
    assert "explorer-studio.genlayer.com/address/" in text


def test_smoke_sample_targets_live_addresses():
    text = (ROOT / "samples" / "studionet_smoke.mjs").read_text(encoding="utf-8")
    assert SPEC_CLEAR_ADDRESS in text
    assert FILL_GATE_ADDRESS in text
