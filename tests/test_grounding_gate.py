from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools import ToolResult

from quran_mcp.middleware.grounding_gate import (
    GroundingGatekeeperMiddleware,
    _set_grounding_field,
)

_IDENTITY_PATCH = "quran_mcp.lib.context.request.resolve_client_identity"


@dataclass
class FakeMessage:
    name: str = ""
    arguments: dict[str, Any] | None = None


def _make_context(tool_name: str, arguments: dict[str, Any] | None = None) -> MiddlewareContext:
    return MiddlewareContext(message=FakeMessage(name=tool_name, arguments=arguments))


def _text_result(text: str = "ok") -> ToolResult:
    return ToolResult(content=text)


def _structured_result(sc: dict[str, Any]) -> ToolResult:
    return ToolResult(content="ok", structured_content=sc)


async def _passthrough(context: MiddlewareContext) -> ToolResult:
    return _text_result("rules text")


@pytest.fixture
def gate() -> GroundingGatekeeperMiddleware:
    return GroundingGatekeeperMiddleware(authority_a_enabled=False)


@pytest.fixture
def gate_a() -> GroundingGatekeeperMiddleware:
    return GroundingGatekeeperMiddleware(authority_a_enabled=True)


class TestNonceIssuance:
    def test_nonce_has_gnd_prefix(self, gate):
        nonce = gate._issue_nonce()
        assert nonce.startswith("gnd-")

    def test_nonce_is_string_of_expected_length(self, gate):
        nonce = gate._issue_nonce()
        assert isinstance(nonce, str)
        assert len(nonce) == 4 + 16  # "gnd-" + 8 bytes hex

    def test_issued_nonce_validates(self, gate):
        nonce = gate._issue_nonce()
        assert gate._validate_nonce(nonce) is True

    def test_random_string_fails_validation(self, gate):
        assert gate._validate_nonce("gnd-notreal1234567") is False

    def test_empty_string_fails_validation(self, gate):
        assert gate._validate_nonce("") is False


class TestNonceXmlStripping:
    @pytest.mark.asyncio
    async def test_xml_wrapped_nonce_validates(self, gate):
        ctx_rules = _make_context("fetch_grounding_rules")

        with patch(_IDENTITY_PATCH, return_value="openai-conv:abc"):
            await gate.on_call_tool(ctx_rules, _passthrough)

        issued_nonce = next(iter(gate._valid_nonces))
        wrapped = f"<grounding_nonce>{issued_nonce}</grounding_nonce>"

        async def _sc_next(ctx):
            return _structured_result({"warnings": None})

        ctx_gated = _make_context("fetch_quran", {"grounding_nonce": wrapped})
        with patch(_IDENTITY_PATCH, return_value="openai-conv:abc"):
            result = await gate.on_call_tool(ctx_gated, _sc_next)

        assert result.structured_content.get("grounding_rules") is None


class TestAuthorityA:
    @pytest.mark.asyncio
    async def test_identity_suppresses_on_second_call(self, gate_a):
        identity = "openai-conv:session-xyz"

        with patch(_IDENTITY_PATCH, return_value=identity):
            ctx_rules = _make_context("fetch_grounding_rules")
            await gate_a.on_call_tool(ctx_rules, _passthrough)

            async def _sc_next(ctx):
                return _structured_result({"warnings": None})

            ctx_gated = _make_context("fetch_quran")
            result = await gate_a.on_call_tool(ctx_gated, _sc_next)

        assert "grounding_rules" not in result.structured_content

    @pytest.mark.asyncio
    async def test_disabled_authority_a_no_suppression(self, gate):
        identity = "openai-conv:session-xyz"

        with patch(_IDENTITY_PATCH, return_value=identity):
            ctx_rules = _make_context("fetch_grounding_rules")
            await gate.on_call_tool(ctx_rules, _passthrough)

            async def _sc_next(ctx):
                return _structured_result({"warnings": None})

            ctx_gated = _make_context("fetch_quran")
            result = await gate.on_call_tool(ctx_gated, _sc_next)

        assert "grounding_rules" in result.structured_content


class TestLRUCapacity:
    def test_oldest_nonce_evicted_after_max(self, gate):
        first_nonce = gate._issue_nonce()
        for _ in range(10_000):
            gate._issue_nonce()

        assert gate._validate_nonce(first_nonce) is False
        assert len(gate._valid_nonces) == 10_000


class TestGroundingWarningDedup:
    def test_single_warning_when_warnings_is_none(self):
        result = _structured_result({"warnings": None})
        _set_grounding_field(result, "rules")
        assert len(result.structured_content["warnings"]) == 1
        assert result.structured_content["warnings"][0]["type"] == "grounding"

    def test_no_duplicate_warning(self):
        result = _structured_result(
            {"warnings": [{"type": "grounding", "message": "existing"}]}
        )
        _set_grounding_field(result, "rules")
        grounding_warnings = [
            w for w in result.structured_content["warnings"]
            if w.get("type") == "grounding"
        ]
        assert len(grounding_warnings) == 1

    def test_warning_appended_when_empty_list(self):
        result = _structured_result({"warnings": []})
        _set_grounding_field(result, "rules")
        assert len(result.structured_content["warnings"]) == 1
        assert result.structured_content["warnings"][0]["type"] == "grounding"

    def test_no_warning_key_means_no_warning_added(self):
        result = _structured_result({"data": "value"})
        _set_grounding_field(result, "rules")
        assert "warnings" not in result.structured_content
        assert result.structured_content["grounding_rules"] == "rules"


class TestGroundingPayloadLoading:
    @pytest.mark.asyncio
    async def test_loader_called_when_unsuppressed(self, gate, monkeypatch: pytest.MonkeyPatch):
        calls = {"count": 0}

        def _fake_payload() -> str:
            calls["count"] += 1
            return "lazy-rules"

        monkeypatch.setattr(
            "quran_mcp.middleware.grounding_gate._grounding_rules_payload",
            _fake_payload,
        )

        async def _sc_next(ctx):
            return _structured_result({"warnings": None})

        with patch(_IDENTITY_PATCH, return_value="openai-conv:abc"):
            result = await gate.on_call_tool(_make_context("fetch_quran"), _sc_next)

        assert calls["count"] == 1
        assert result.structured_content["grounding_rules"] == "lazy-rules"

    @pytest.mark.asyncio
    async def test_loader_not_called_when_nonce_suppresses(self, gate, monkeypatch: pytest.MonkeyPatch):
        calls = {"count": 0}

        def _fake_payload() -> str:
            calls["count"] += 1
            return "lazy-rules"

        monkeypatch.setattr(
            "quran_mcp.middleware.grounding_gate._grounding_rules_payload",
            _fake_payload,
        )

        with patch(_IDENTITY_PATCH, return_value="openai-conv:abc"):
            await gate.on_call_tool(_make_context("fetch_grounding_rules"), _passthrough)

        issued_nonce = next(iter(gate._valid_nonces))

        async def _sc_next(ctx):
            return _structured_result({"warnings": None})

        with patch(_IDENTITY_PATCH, return_value="openai-conv:abc"):
            result = await gate.on_call_tool(
                _make_context("fetch_quran", {"grounding_nonce": issued_nonce}),
                _sc_next,
            )

        assert calls["count"] == 0
        assert "grounding_rules" not in result.structured_content
