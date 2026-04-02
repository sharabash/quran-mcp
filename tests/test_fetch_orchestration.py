"""Unit tests for shared fetch-wrapper orchestration helpers."""

from __future__ import annotations

import importlib.util
import sys
from types import SimpleNamespace
from pathlib import Path
from typing import Any, cast

import pytest
from fastmcp.exceptions import ToolError
from pydantic import BaseModel

from quran_mcp.lib.ayah_parsing import normalize_ayah_key
from quran_mcp.lib.editions.errors import DataNotFoundError, DataStoreError
from quran_mcp.lib.quran.fetch import QuranEntry
from quran_mcp.lib.presentation.pagination import encode_continuation_token
from quran_mcp.lib.presentation.warnings import DataGapWarning, UnresolvedEditionWarning
from quran_mcp.lib.tafsir.fetch import TafsirEntry
from quran_mcp.lib.translation.fetch import TranslationEntry


def _load_fetch_orchestration_module() -> Any:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "quran_mcp"
        / "mcp"
        / "tools"
        / "_fetch_orchestration.py"
    )
    spec = importlib.util.spec_from_file_location("test_fetch_orchestration_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_fetch_orchestration = _load_fetch_orchestration_module()
MISSING_AYAHS_AND_EDITIONS_MESSAGE = _fetch_orchestration.MISSING_AYAHS_AND_EDITIONS_MESSAGE
MISSING_AYAHS_MESSAGE = _fetch_orchestration.MISSING_AYAHS_MESSAGE
FetchAyahsEditionsRequestState = _fetch_orchestration.FetchAyahsEditionsRequestState
ResolvedFetchRequest = _fetch_orchestration.ResolvedFetchRequest
build_fetch_warnings = _fetch_orchestration.build_fetch_warnings
execute_fetch_tool = _fetch_orchestration.execute_fetch_tool
paginate_fetch_results = _fetch_orchestration.paginate_fetch_results
recompute_page_ayahs = _fetch_orchestration.recompute_page_ayahs
resolve_fetch_request = _fetch_orchestration.resolve_fetch_request
resolve_fetch_runtime_context = _fetch_orchestration.resolve_fetch_runtime_context


class _Entry(BaseModel):
    ayah: str
    text: str


def test_resolve_fetch_request_without_continuation_uses_default_edition() -> None:
    request = resolve_fetch_request(
        tool_name="fetch_quran",
        host=None,
        continuation=None,
        ayahs="2:255-256",
        editions=None,
        default_editions="ar-simple-clean",
        missing_inputs_message=MISSING_AYAHS_MESSAGE,
    )

    assert request.requested_page == 1
    assert request.state.ayahs == ["2:255", "2:256"]
    assert request.state.editions == "ar-simple-clean"


def test_resolve_fetch_request_requires_expected_inputs() -> None:
    with pytest.raises(ToolError, match=r"^\[invalid_request\] ayahs is required unless continuation is provided$"):
        resolve_fetch_request(
            tool_name="fetch_quran",
            host=None,
            continuation=None,
            ayahs=None,
            editions=None,
            default_editions="ar-simple-clean",
            missing_inputs_message=MISSING_AYAHS_MESSAGE,
        )

    with pytest.raises(
        ToolError,
        match=r"^\[invalid_request\] ayahs and editions are required unless continuation is provided$",
    ):
        resolve_fetch_request(
            tool_name="fetch_tafsir",
            host=None,
            continuation=None,
            ayahs="2:255",
            editions=None,
            default_editions=None,
            missing_inputs_message=MISSING_AYAHS_AND_EDITIONS_MESSAGE,
        )


def test_resolve_fetch_request_maps_ayah_parse_errors_to_invalid_request() -> None:
    with pytest.raises(ToolError, match=r"^\[invalid_request\] "):
        resolve_fetch_request(
            tool_name="fetch_quran",
            host=None,
            continuation=None,
            ayahs="2:x-255",
            editions="ar-simple-clean",
            default_editions="ar-simple-clean",
            missing_inputs_message=MISSING_AYAHS_MESSAGE,
        )


def test_resolve_fetch_runtime_context_requires_context() -> None:
    with pytest.raises(
        ToolError,
        match=r"^\[invalid_request\] runtime context is required$",
    ):
        resolve_fetch_runtime_context(None)


def test_resolve_fetch_runtime_context_returns_app_context_and_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_ctx = SimpleNamespace()
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=app_ctx),
    )
    monkeypatch.setattr(_fetch_orchestration, "detect_client_hint", lambda _ctx: {"host": "claude"})

    resolved_app_ctx, host = resolve_fetch_runtime_context(cast(Any, ctx))

    assert resolved_app_ctx is app_ctx
    assert host == "claude"


def test_resolve_fetch_request_continuation_conflict_maps_to_contract_error() -> None:
    token = encode_continuation_token(
        tool_name="fetch_quran",
        next_page=2,
        page_size=80,
        request_state={
            "ayahs": ["2:255"],
            "editions": "ar-simple-clean",
        },
    )

    with pytest.raises(ToolError, match=r"^\[continuation_conflict\]"):
        resolve_fetch_request(
            tool_name="fetch_quran",
            host=None,
            continuation=token,
            ayahs="2:256",
            editions=None,
            default_editions="ar-simple-clean",
            missing_inputs_message=MISSING_AYAHS_MESSAGE,
        )


def test_paginate_fetch_results_builds_continuation_meta() -> None:
    request = ResolvedFetchRequest(
        requested_page=1,
        page_size=1,
        state=FetchAyahsEditionsRequestState(
            ayahs=["2:1", "2:2"],
            editions="ar-simple-clean",
        ),
    )
    results = {
        "ar-simple-clean": [
            _Entry(ayah="2:1", text="a"),
            _Entry(ayah="2:2", text="b"),
        ]
    }

    page_results, meta = paginate_fetch_results(
        tool_name="fetch_quran",
        continuation=None,
        request=request,
        results=results,
        bundle_key_fn=lambda entry: entry.ayah,
    )

    assert [entry.ayah for entry in page_results["ar-simple-clean"]] == ["2:1"]
    assert meta.has_more is True
    assert meta.total_items == 2
    assert meta.continuation is not None


def test_recompute_page_ayahs_supports_scalar_and_range_entries() -> None:
    scalar_results = {"ed": [SimpleNamespace(ayah="2:1"), SimpleNamespace(ayah="2:3")]}
    scalar = recompute_page_ayahs(
        ["2:1", "2:2", "2:3"],
        scalar_results,
        entry_ayahs=lambda entry: entry.ayah,
    )
    assert scalar == ["2:1", "2:3"]

    grouped_results = {"ed": [SimpleNamespace(ayahs=["2:2", "2:3"])]}
    grouped = recompute_page_ayahs(
        ["2:1", "2:2", "2:3"],
        grouped_results,
        entry_ayahs=lambda entry: entry.ayahs,
    )
    assert grouped == ["2:2", "2:3"]


def test_build_fetch_warnings_maps_gap_and_unresolved_contracts() -> None:
    warnings = build_fetch_warnings(
        gaps=[SimpleNamespace(edition_id="en-abdel-haleem", missing_ayahs=["2:255"])],
        unresolved=[SimpleNamespace(selector="bad-edition", suggestion="Call list_editions")],
    )

    assert warnings is not None
    assert any(isinstance(w, DataGapWarning) for w in warnings)
    assert any(isinstance(w, UnresolvedEditionWarning) for w in warnings)


async def test_execute_fetch_tool_reuses_full_wrapper_flow() -> None:
    app_ctx = SimpleNamespace()
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=app_ctx),
    )

    class _FetchResult:
        def __init__(self) -> None:
            self.data = {
                "en-abdel-haleem": [
                    SimpleNamespace(ayah="2:255", text="a"),
                    SimpleNamespace(ayah="2:256", text="b"),
                ]
            }
            self.gaps = [SimpleNamespace(edition_id="en-abdel-haleem", missing_ayahs=["2:257"])]
            self.unresolved = [SimpleNamespace(selector="bad", suggestion="Call list_editions")]

    async def _fetch_entries(
        passed_ctx: Any,
        ayahs: list[str],
        editions: str | list[str],
    ) -> Any:
        assert passed_ctx is app_ctx
        assert ayahs == ["2:255", "2:256"]
        assert editions == "en-abdel-haleem"
        return _FetchResult()

    page = await execute_fetch_tool(
        ctx=cast(Any, ctx),
        tool_name="fetch_translation",
        continuation=None,
        ayahs="2:255-256",
        editions=None,
        default_editions="en-abdel-haleem",
        missing_inputs_message=MISSING_AYAHS_MESSAGE,
        fetch_entries=_fetch_entries,
        build_results=lambda raw_results: {
            edition_id: [_Entry(ayah=entry.ayah, text=entry.text) for entry in entries]
            for edition_id, entries in raw_results.items()
        },
        entry_ayahs=lambda entry: entry.ayah,
        bundle_key_fn=lambda entry: entry.ayah,
    )

    assert page.ayahs == ["2:255", "2:256"]
    assert [entry.ayah for entry in page.results["en-abdel-haleem"]] == ["2:255", "2:256"]
    assert page.pagination.total_items == 2
    assert page.pagination.has_more is False
    assert page.pagination.continuation is None
    assert [entry.page for entry in page.pagination.pages] == [1, 1]
    assert page.warnings is not None
    assert any(isinstance(warning, DataGapWarning) for warning in page.warnings)
    assert any(isinstance(warning, UnresolvedEditionWarning) for warning in page.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc", "pattern"),
    [
        (
            DataNotFoundError(
                edition_id="en-ibn-kathir",
                edition_type="tafsir",
                missing_ayahs=["2:255"],
            ),
            r"^\[not_found\] tafsir data not found for en-ibn-kathir: missing 1 ayah\(s\): \['2:255'\]$",
        ),
        (
            DataStoreError(operation="fetch", cause=RuntimeError("boom")),
            r"^\[service_unavailable\] Database not available$",
        ),
    ],
)
async def test_execute_fetch_tool_translates_domain_errors(
    exc: Exception,
    pattern: str,
) -> None:
    app_ctx = SimpleNamespace()
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=app_ctx),
    )

    async def _fetch_entries(
        passed_ctx: Any,
        ayahs: list[str],
        editions: str | list[str],
    ) -> Any:
        assert passed_ctx is app_ctx
        assert ayahs == ["2:255"]
        assert editions == "en-ibn-kathir"
        raise exc

    with pytest.raises(ToolError, match=pattern):
        await execute_fetch_tool(
            ctx=cast(Any, ctx),
            tool_name="fetch_tafsir",
            continuation=None,
            ayahs="2:255",
            editions="en-ibn-kathir",
            default_editions=None,
            missing_inputs_message=MISSING_AYAHS_AND_EDITIONS_MESSAGE,
            fetch_entries=_fetch_entries,
            build_results=lambda raw_results: {
                edition_id: [_Entry(ayah=entry.ayah, text=entry.text) for entry in entries]
                for edition_id, entries in raw_results.items()
            },
            entry_ayahs=lambda entry: entry.ayah,
        )


def test_normalize_ayah_key_preserves_canonical_field_name() -> None:
    assert normalize_ayah_key("2:255") == "2:255"
    assert normalize_ayah_key(ayah="2:255") == "2:255"
    assert normalize_ayah_key("2:255", "2:255") == "2:255"


def test_fetch_entries_expose_ayah_key_and_legacy_alias() -> None:
    entries = [
        QuranEntry(ayah_key="1:1", text="quran"),
        TranslationEntry(ayah="1:2", text="translation"),
        TafsirEntry(ayah_key="1:3", text="tafsir", citation_url="url"),
    ]

    for entry, expected in zip(entries, ["1:1", "1:2", "1:3"], strict=True):
        assert entry.ayah_key == expected
        assert entry.ayah == expected

        entry.ayah = "9:9"
        assert entry.ayah_key == "9:9"
