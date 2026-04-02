from __future__ import annotations

import pytest

from quran_mcp.middleware.grounding_gate import (
    GroundingGatekeeperMiddleware,
    _NONCE_FOOTER_TEMPLATE,
)


@pytest.fixture
def gate() -> GroundingGatekeeperMiddleware:
    return GroundingGatekeeperMiddleware(authority_a_enabled=False)


class TestMalformedNonceTypes:
    @pytest.mark.parametrize("value", [42, True, False, None, ["gnd-abc"], {"nonce": "gnd-abc"}])
    def test_invalid_types_return_false(self, gate, value):
        assert gate._validate_nonce(value) is False


class TestOversizedNonce:
    def test_1000_char_string_returns_false(self, gate):
        assert gate._validate_nonce("a" * 1000) is False


class TestNonceUniqueness:
    def test_100_nonces_all_unique(self, gate):
        nonces = {gate._issue_nonce() for _ in range(100)}
        assert len(nonces) == 100


class TestNonceReplay:
    def test_same_nonce_validates_twice(self, gate):
        nonce = gate._issue_nonce()
        assert gate._validate_nonce(nonce) is True
        assert gate._validate_nonce(nonce) is True


class TestServerRestartInvalidation:
    def test_old_nonce_fails_on_new_instance(self):
        gate_old = GroundingGatekeeperMiddleware(authority_a_enabled=False)
        nonce = gate_old._issue_nonce()
        assert gate_old._validate_nonce(nonce) is True

        gate_new = GroundingGatekeeperMiddleware(authority_a_enabled=False)
        assert gate_new._validate_nonce(nonce) is False


class TestDualFormatNonceFooter:
    def test_footer_contains_key_value_format(self):
        rendered = _NONCE_FOOTER_TEMPLATE.format(nonce="gnd-test1234")
        assert "GROUNDING_NONCE: gnd-test1234" in rendered

    def test_footer_contains_xml_format(self):
        rendered = _NONCE_FOOTER_TEMPLATE.format(nonce="gnd-test1234")
        assert "<grounding_nonce>gnd-test1234</grounding_nonce>" in rendered

    def test_both_formats_carry_same_nonce(self):
        nonce = "gnd-abc123def456"
        rendered = _NONCE_FOOTER_TEMPLATE.format(nonce=nonce)
        assert f"GROUNDING_NONCE: {nonce}" in rendered
        assert f"<grounding_nonce>{nonce}</grounding_nonce>" in rendered


class TestWhitespaceHandling:
    def test_raw_whitespace_padded_nonce_fails(self, gate):
        nonce = gate._issue_nonce()
        assert gate._validate_nonce(f"  {nonce}  ") is False

    def test_stripped_nonce_validates(self, gate):
        nonce = gate._issue_nonce()
        padded = f"  {nonce}  "
        assert gate._validate_nonce(padded.strip()) is True


class TestEmptyStringNonce:
    def test_empty_string_returns_false(self, gate):
        assert gate._validate_nonce("") is False


class TestNonceWithoutPrefix:
    def test_missing_gnd_prefix_returns_false(self, gate):
        assert gate._validate_nonce("abcdef0123456789") is False

    def test_wrong_prefix_returns_false(self, gate):
        assert gate._validate_nonce("xyz-abcdef0123456789") is False
