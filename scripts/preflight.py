#!/usr/bin/env python3
"""Preflight gate: cheap static verification before test runs or submission.

Checks performed:
  1. both contracts byte-compile under CPython (syntax validity);
  2. runner dependency headers are byte-exact (BOM-free, LF-only, ASCII
     quotes, pinned hash — swapped/malformed headers fail schema time with
     'invalid_contract runner malformed');
  3. the primitive keeps exactly one LLM callsite and never embeds two
     <order_text> blocks in its prompt builder (protocol boundary);
  4. GenVM lint E022: no decorated helpers on contract classes;
  5. the submission package exists and is byte-identical to the working
     sources, so the artifact under review is the artifact under test;
  6. required repository artifacts exist (docs, samples, tests).

Exit code 0 means the package is structurally submittable.
"""

import json
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURES = []

CONTRACT_BASENAMES = ("spec_clear.py", "fill_gate.py")
PINNED_HEADER = "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6"


def check(label, ok, detail=""):
    status = "ok  " if ok else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(label)


def main():
    primitive = ROOT / "contracts" / "spec_clear.py"
    gate = ROOT / "contracts" / "fill_gate.py"

    for path in (primitive, gate):
        try:
            py_compile.compile(str(path), doraise=True)
            check(f"compiles: {path.relative_to(ROOT)}", True)
        except py_compile.PyCompileError as error:
            check(f"compiles: {path.relative_to(ROOT)}", False, str(error))
            continue

        # Byte-level upload hygiene. gen_getContractSchemaForCode fails with
        # 'invalid_contract runner malformed' BEFORE any Python runs when the
        # two-line runner header is corrupted — BOM markers, CRLF endings, or
        # curly (smart) quotes pasted in place of ASCII quotes all break the
        # schema-time header parse. Guard the exact bytes, not just the text.
        raw = path.read_bytes()
        check(f"no BOM: {path.name}", not raw.startswith(b"\xef\xbb\xbf"))
        check(f"LF-only line endings: {path.name}", b"\r" not in raw)
        check(f"header starts column 0: {path.name}", raw.startswith(b"# v1.0.0\n"))
        head_line2 = raw.split(b"\n")[1] if raw.startswith(b"# v1.0.0\n") else b""
        head_text = head_line2.decode("utf-8", errors="replace")
        check(
            f"header uses ASCII quotes: {path.name}",
            '"' in head_text and not any(q in head_text for q in ("\u201c", "\u201d", "\u2018", "\u2019")),
        )
        try:
            meta = json.loads(head_line2.lstrip(b"# ").decode("ascii"))
            header_ok = meta.get("Depends") == PINNED_HEADER
        except Exception:
            header_ok = False
        check(
            f"header JSON valid + runner pinned exactly: {path.name}",
            header_ok,
            "swapped/malformed runner hashes fail schema extraction with 'runner malformed'",
        )

        source = raw.decode("utf-8")
        check(f"no floating runner alias: {path.name}", "py-genlayer:test" not in source and "py-genlayer:latest" not in source)
        # GenVM lint E022: contract classes must not declare decorated helpers.
        check(f"lint E022 clean: {path.name}", "@staticmethod" not in source and "@classmethod" not in source)
    check(
        "lint E022: owner guard is instance method",
        "def _require_owner(self, market: Market) -> None:" in primitive.read_text(encoding="utf-8"),
    )

    source = primitive.read_text(encoding="utf-8")
    check("single LLM callsite", source.count("exec_prompt") == 1)
    check("prompt is single-order", source.count('"<order_text side=') == 1 and source.count("</order_text>") == 1)
    check("fail-closed normalization", "malformed profile output; failed closed" in source)
    check("typed consumer interface", "@gl.contract_interface" in gate.read_text(encoding="utf-8"))

    # The submission package must mirror the working sources byte for byte.
    for name in CONTRACT_BASENAMES:
        working = ROOT / "contracts" / name
        packaged = ROOT / "submission" / name
        exists = packaged.exists()
        check(f"submission artifact: submission/{name}", exists, "missing from submission package")
        if exists:
            check(
                f"byte-identical: submission/{name}",
                packaged.read_bytes() == working.read_bytes(),
                "submission drifted from contracts/ — re-copy before submitting",
            )
    check("submission manifest", (ROOT / "submission" / "README.md").exists())

    for artifact in (
        "README.md",
        "docs/ARCHITECTURE.md",
        "docs/CLEARING_RULES.md",
        "docs/INVARIANTS.md",
        "docs/THREAT_MODEL.md",
        "docs/TESTING.md",
        "docs/DEPLOYMENT.md",
        "docs/GITHUB.md",
        "samples/end_to_end.py",
        "samples/studionet_smoke.mjs",
        "samples/market_definition.json",
        "tests/direct/test_spec_clear.py",
        "tests/direct/test_clearing_policy.py",
        "tests/direct/test_fill_gate.py",
        "tests/unit/test_static_boundaries.py",
        "requirements.txt",
        "pytest.ini",
    ):
        check(f"artifact: {artifact}", (ROOT / artifact).exists())

    if FAILURES:
        print(f"\npreflight FAILED ({len(FAILURES)} problem(s))")
        return 1
    print("\npreflight passed — package is structurally submittable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
