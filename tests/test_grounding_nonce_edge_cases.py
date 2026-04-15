from __future__ import annotations

import pytest

from quran_mcp.middleware.grounding_gate import (
    GroundingGatekeeperMiddleware,
    _NONCE_FOOTER_TEMPLATE,
    _NONCE_TTL_SECONDS,
    _RETAINED_IDENTITY_TTL_SECONDS,
)


@pytest.fixture
def gate() -> GroundingGatekeeperMiddleware:
    return GroundingGatekeeperMiddleware(authority_a_enabled=False)


_IDENTITY = "claude-cc:edge-test"


class TestMalformedNonceTypes:
    @pytest.mark.parametrize("value", [42, True, False, None, ["gnd-abc"], {"nonce": "gnd-abc"}])
    def test_invalid_types_return_false(self, gate, value):
        assert gate._validate_nonce(value, _IDENTITY) is False


class TestOversizedNonce:
    def test_1000_char_string_returns_false(self, gate):
        assert gate._validate_nonce("a" * 1000, _IDENTITY) is False


class TestNonceUniqueness:
    def test_100_nonces_all_unique(self, gate):
        nonces = {gate._issue_nonce(_IDENTITY) for _ in range(100)}
        assert len(nonces) == 100


class TestNonceReplay:
    def test_same_nonce_validates_twice(self, gate):
        nonce = gate._issue_nonce(_IDENTITY)
        assert gate._validate_nonce(nonce, _IDENTITY) is True
        assert gate._validate_nonce(nonce, _IDENTITY) is True


class TestServerRestartInvalidation:
    def test_old_nonce_fails_on_new_instance(self):
        gate_old = GroundingGatekeeperMiddleware(authority_a_enabled=False)
        nonce = gate_old._issue_nonce(_IDENTITY)
        assert gate_old._validate_nonce(nonce, _IDENTITY) is True

        gate_new = GroundingGatekeeperMiddleware(authority_a_enabled=False)
        assert gate_new._validate_nonce(nonce, _IDENTITY) is False


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
        nonce = gate._issue_nonce(_IDENTITY)
        assert gate._validate_nonce(f"  {nonce}  ", _IDENTITY) is False

    def test_stripped_nonce_validates(self, gate):
        nonce = gate._issue_nonce(_IDENTITY)
        padded = f"  {nonce}  "
        assert gate._validate_nonce(padded.strip(), _IDENTITY) is True


class TestEmptyStringNonce:
    def test_empty_string_returns_false(self, gate):
        assert gate._validate_nonce("", _IDENTITY) is False


class TestNonceWithoutPrefix:
    def test_missing_gnd_prefix_returns_false(self, gate):
        assert gate._validate_nonce("abcdef0123456789", _IDENTITY) is False

    def test_wrong_prefix_returns_false(self, gate):
        assert gate._validate_nonce("xyz-abcdef0123456789", _IDENTITY) is False


class TestNonceTTLExpiration:
    """Nonces must expire after _NONCE_TTL_SECONDS."""

    def test_nonce_valid_within_ttl(self, gate):
        nonce = gate._issue_nonce(_IDENTITY)
        assert gate._validate_nonce(nonce, _IDENTITY) is True

    def test_nonce_invalid_after_ttl(self, gate):
        nonce = gate._issue_nonce(_IDENTITY)
        # Simulate TTL expiration by backdating the issued_at timestamp
        entry = gate._valid_nonces[nonce]
        issued_at, identity = entry
        expired_ts = issued_at - _NONCE_TTL_SECONDS - 1
        gate._valid_nonces[nonce] = (expired_ts, identity)
        assert gate._validate_nonce(nonce, _IDENTITY) is False

    def test_expired_nonce_removed_from_store(self, gate):
        nonce = gate._issue_nonce(_IDENTITY)
        entry = gate._valid_nonces[nonce]
        issued_at, identity = entry
        expired_ts = issued_at - _NONCE_TTL_SECONDS - 1
        gate._valid_nonces[nonce] = (expired_ts, identity)
        gate._validate_nonce(nonce, _IDENTITY)
        assert nonce not in gate._valid_nonces


class TestNonceIdentityBinding:
    """A nonce issued to one identity must NOT validate for a different identity."""

    def test_cross_identity_replay_blocked(self, gate):
        alice = "claude-cc:alice-session-123"
        bob = "openai-conv:bob-session-456"
        nonce = gate._issue_nonce(alice)
        assert gate._validate_nonce(nonce, alice) is True
        assert gate._validate_nonce(nonce, bob) is False

    def test_same_nonce_different_identities_all_blocked(self, gate):
        original = "claude-cc:original-session"
        attacker_ids = [
            "openai-conv:attacker",
            "claude-ai:attacker",
            "ip:192.168.1.1",
        ]
        nonce = gate._issue_nonce(original)
        for attacker_id in attacker_ids:
            assert gate._validate_nonce(nonce, attacker_id) is False


class TestExplicitGroundingTTLExpiration:
    """Authority A identity ACKs must expire after _RETAINED_IDENTITY_TTL_SECONDS."""

    def test_identity_ack_valid_within_ttl(self):
        gate = GroundingGatekeeperMiddleware(authority_a_enabled=True)
        identity = "claude-cc:ack-test"
        gate._mark(gate._explicit_grounding, identity)
        assert gate._has(gate._explicit_grounding, identity) is True

    def test_identity_ack_invalid_after_ttl(self):
        gate = GroundingGatekeeperMiddleware(authority_a_enabled=True)
        identity = "claude-cc:ack-test"
        gate._mark(gate._explicit_grounding, identity)
        # Backdate the timestamp to simulate expiration
        ts = gate._explicit_grounding[identity]
        gate._explicit_grounding[identity] = ts - _RETAINED_IDENTITY_TTL_SECONDS - 1
        assert gate._has(gate._explicit_grounding, identity) is False

    def test_non_retained_identity_never_acknowledged(self):
        gate = GroundingGatekeeperMiddleware(authority_a_enabled=True)
        gate._mark(gate._explicit_grounding, "unknown:ephemeral")
        assert gate._has(gate._explicit_grounding, "unknown:ephemeral") is False
