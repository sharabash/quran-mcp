from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

import quran_mcp
from quran_mcp import build_mcp, get_or_create_mcp, peek_mcp
from quran_mcp.lib.assets import asset_text
from quran_mcp.lib.goodmem import client as goodmem_client_module
from quran_mcp.lib.site import manifest
from quran_mcp.mcp.prompts import register_all_core_prompts
from quran_mcp.mcp.resources import register_all_core_resources
from quran_mcp.mcp.resources.doc import grounding_rules, skill_guide
from quran_mcp.mcp.tools._tool_context import resolve_app_context
from quran_mcp.mcp.tools._tool_errors import (
    invalid_request_error,
    not_found_error,
    require_db_pool,
    service_unavailable_error,
)


class TestTopLevelPackageExports:
    def test_package_reexports_server_entrypoints(self) -> None:
        assert quran_mcp.build_mcp is build_mcp
        assert quran_mcp.get_or_create_mcp is get_or_create_mcp
        assert quran_mcp.peek_mcp is peek_mcp
        assert quran_mcp.__all__ == ["build_mcp", "get_or_create_mcp", "peek_mcp"]


class _StubResourceModule:
    def __init__(self) -> None:
        self.calls: list[FastMCP] = []

    def register(self, mcp: FastMCP) -> None:
        self.calls.append(mcp)


class TestCoreResourceRegistrar:
    def test_include_non_ga_registers_all_modules(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ga_1 = _StubResourceModule()
        ga_2 = _StubResourceModule()
        non_ga = _StubResourceModule()
        monkeypatch.setattr(
            "quran_mcp.mcp.resources._GA_RESOURCE_MODULES",
            (ga_1, ga_2),
        )
        monkeypatch.setattr(
            "quran_mcp.mcp.resources._NON_GA_RESOURCE_MODULES",
            (non_ga,),
        )

        server = FastMCP("resource-registry-test")
        register_all_core_resources(server)

        assert ga_1.calls == [server]
        assert ga_2.calls == [server]
        assert non_ga.calls == [server]

    def test_excluding_non_ga_skips_optional_modules(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ga_1 = _StubResourceModule()
        ga_2 = _StubResourceModule()
        non_ga = _StubResourceModule()
        monkeypatch.setattr(
            "quran_mcp.mcp.resources._GA_RESOURCE_MODULES",
            (ga_1, ga_2),
        )
        monkeypatch.setattr(
            "quran_mcp.mcp.resources._NON_GA_RESOURCE_MODULES",
            (non_ga,),
        )

        server = FastMCP("resource-registry-test")
        register_all_core_resources(server, include_non_ga=False)

        assert ga_1.calls == [server]
        assert ga_2.calls == [server]
        assert non_ga.calls == []


class TestDocumentResources:
    @pytest.mark.asyncio
    async def test_grounding_rules_resource_matches_asset_text(self) -> None:
        server = FastMCP("grounding-rules-resource-test")
        grounding_rules.register(server)

        async with Client(server) as client:
            resources = await client.list_resources()
            resource_uris = {str(resource.uri) for resource in resources}
            assert "document://grounding_rules.md" in resource_uris
            contents = await client.read_resource("document://grounding_rules.md")

        assert contents[0].text == asset_text("GROUNDING_RULES.md")

    @pytest.mark.asyncio
    async def test_skill_guide_resource_matches_asset_text(self) -> None:
        server = FastMCP("skill-guide-resource-test")
        skill_guide.register(server)

        async with Client(server) as client:
            resources = await client.list_resources()
            resource_uris = {str(resource.uri) for resource in resources}
            assert "document://skill_guide.md" in resource_uris
            contents = await client.read_resource("document://skill_guide.md")

        assert contents[0].text == asset_text("SKILL.md")


class TestPromptRegistrar:
    @pytest.mark.asyncio
    async def test_register_all_core_prompts_is_currently_empty(self) -> None:
        server = FastMCP("prompts-test")
        register_all_core_prompts(server)

        async with Client(server) as client:
            prompts = await client.list_prompts()

        assert prompts == []


class TestManifestContracts:
    def test_required_assets_validate(self) -> None:
        assert manifest.validate_required_assets() == []

    def test_download_routes_include_canonical_assets(self) -> None:
        assert "/SKILL.md" in manifest.routes["downloads"]
        assert "/GROUNDING_RULES.md" in manifest.routes["downloads"]


class TestToolErrorHelpers:
    def test_invalid_request_error_prefix(self) -> None:
        err = invalid_request_error("bad input")
        assert isinstance(err, ToolError)
        assert str(err) == "[invalid_request] bad input"

    def test_service_unavailable_error_prefix(self) -> None:
        err = service_unavailable_error()
        assert isinstance(err, ToolError)
        assert str(err) == "[service_unavailable] Database not available"

    def test_not_found_error_prefix(self) -> None:
        err = not_found_error("missing verse")
        assert isinstance(err, ToolError)
        assert str(err) == "[not_found] missing verse"

    def test_resolve_app_context_extracts_lifespan_context(self) -> None:
        app_context = object()
        runtime_ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=app_context)
        )

        assert resolve_app_context(runtime_ctx) is app_context

    def test_require_db_pool_uses_application_context_pool(self) -> None:
        pool = object()
        runtime_ctx = SimpleNamespace(
            request_context=SimpleNamespace(
                lifespan_context=SimpleNamespace(db_pool=pool)
            )
        )

        assert require_db_pool(runtime_ctx) is pool


class TestGoodMemClientFacade:
    def test_client_module_exports_core_symbols(self) -> None:
        assert hasattr(goodmem_client_module, "GoodMemClient")
        assert hasattr(goodmem_client_module, "GoodMemConfig")
        assert hasattr(goodmem_client_module, "GoodMemMemory")
        assert hasattr(goodmem_client_module, "with_retry")


class TestFacadePrivateExports:
    def test_goodmem_package_excludes_private_filter_helpers(self) -> None:
        import quran_mcp.lib.goodmem as goodmem

        assert "_cast_clause" not in goodmem.__all__
        assert "_format_literal" not in goodmem.__all__
        assert "_infer_value_type" not in goodmem.__all__

    def test_pagination_facade_excludes_continuation_primitives(self) -> None:
        import quran_mcp.lib.presentation.pagination as pagination

        assert "_ContinuationToken" not in pagination.__all__
        assert "_b64url_decode" not in pagination.__all__
        assert "_b64url_encode" not in pagination.__all__
        assert "_canonical_json" not in pagination.__all__
        assert "_derive_continuation_secret" not in pagination.__all__

    def test_sampling_handler_facade_excludes_private_helpers(self) -> None:
        import quran_mcp.lib.sampling.handler as sampling_handler

        assert "_apply_input_overrides" not in sampling_handler.__all__
        assert "_build_openai_message" not in sampling_handler.__all__
        assert "_build_sampling_result" not in sampling_handler.__all__
        assert "_deep_update" not in sampling_handler.__all__
        assert "_determine_audio_format" not in sampling_handler.__all__
        assert "_determine_image_detail" not in sampling_handler.__all__
        assert "_extract_openai_config" not in sampling_handler.__all__
        assert "_iter_model_preferences" not in sampling_handler.__all__
        assert "_normalize_role" not in sampling_handler.__all__
        assert "_normalize_usage_payload" not in sampling_handler.__all__
        assert "_require_text_content" not in sampling_handler.__all__
        assert "_text_content_to_openai" not in sampling_handler.__all__
