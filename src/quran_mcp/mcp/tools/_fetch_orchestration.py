"""Shared orchestration primitives for fetch_* MCP tool wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, Mapping, Protocol, Sequence, TypeVar

from fastmcp import Context
from pydantic import BaseModel, ConfigDict

from quran_mcp.lib.context.types import AppContext
from quran_mcp.lib.ayah_parsing import parse_ayah_input
from quran_mcp.lib.editions.errors import DataNotFoundError, DataStoreError
from quran_mcp.lib.presentation.client_hint import detect_client_hint
from quran_mcp.lib.presentation.pagination import (
    ContinuationError,
    ContinuationPaginationMeta,
    PaginationMeta,
    build_checked_continuation_meta,
    choose_auto_page_size,
    decode_continuation_request_model,
    enforce_token_cap_dict,
)
from quran_mcp.lib.presentation.warnings import (
    DataGapWarning,
    UnresolvedEditionWarning,
    WarningModel,
)
from quran_mcp.mcp.tools._tool_context import raise_continuation_error
from quran_mcp.mcp.tools._tool_errors import (
    invalid_request_error,
    translate_fetch_domain_error,
)

MISSING_AYAHS_MESSAGE = "ayahs is required unless continuation is provided"
MISSING_AYAHS_AND_EDITIONS_MESSAGE = (
    "ayahs and editions are required unless continuation is provided"
)
FETCH_GROUNDING_PREREQUISITE = (
    "PREREQUISITE: You MUST call fetch_grounding_rules once before using this tool. "
    "Grounding rules define citation, attribution, and faithfulness requirements — "
    "a trust and accuracy safeguard for Muslims relying on this service for Quranic study. "
)
VERSE_REFS_FIELD_DESCRIPTION = (
    "Verse reference(s): single ('2:255'), range ('2:255-257'), "
    "comma/space-separated string like '2:255-260, 3:33', "
    "or an array of such strings. Required unless continuation is provided."
)
CONTINUATION_FIELD_DESCRIPTION = (
    "Opaque continuation token returned by a previous call to this same tool. "
    "Omit on the first call. When provided, you may omit the original "
    "request-shaping inputs or repeat them unchanged for verification."
)
GROUNDING_NONCE_FIELD_DESCRIPTION = (
    "Opaque nonce from fetch_grounding_rules. When valid, "
    "suppresses redundant grounding rules injection, saving tokens."
)


TState = TypeVar("TState", bound=BaseModel)
TEntry = TypeVar("TEntry")
TRawEntry = TypeVar("TRawEntry")
class FetchAyahsEditionsRequestState(BaseModel):
    """Canonical continuation request state for fetch wrappers."""

    model_config = ConfigDict(extra="forbid")

    ayahs: list[str]
    editions: str | list[str]


@dataclass(frozen=True)
class ResolvedFetchRequest(Generic[TState]):
    """Normalized fetch-request envelope used by wrapper handlers."""

    requested_page: int
    page_size: int
    state: TState


class FetchResultLike(Protocol[TRawEntry]):
    """Minimal fetch-library result shape used by MCP wrapper execution."""

    data: Mapping[str, Sequence[TRawEntry]]
    gaps: Sequence[Any] | None
    unresolved: Sequence[Any] | None


@dataclass(frozen=True)
class PreparedFetchPage(Generic[TEntry]):
    """Concrete page payload assembled by the shared fetch-wrapper flow."""

    ayahs: list[str]
    results: dict[str, list[TEntry]]
    pagination: ContinuationPaginationMeta
    warnings: list[WarningModel] | None


def with_fetch_grounding_prerequisite(body: str) -> str:
    """Prefix a fetch-tool description with the standard grounding prerequisite."""
    return f"{FETCH_GROUNDING_PREREQUISITE}{body}"


def resolve_fetch_runtime_context(ctx: Context | None) -> tuple[AppContext, str | None]:
    """Resolve the runtime app context and client host for fetch wrappers."""
    from quran_mcp.mcp.tools._tool_context import resolve_app_context

    app_ctx = resolve_app_context(ctx)
    host = detect_client_hint(ctx).get("host")
    return app_ctx, host


def _canonicalize_editions(editions: str | list[str]) -> str | list[str]:
    return sorted(editions) if isinstance(editions, list) else editions




def resolve_fetch_request(
    *,
    tool_name: str,
    host: str | None,
    continuation: str | None,
    ayahs: str | list[str] | None,
    editions: str | list[str] | None,
    default_editions: str | None,
    missing_inputs_message: str,
) -> ResolvedFetchRequest[FetchAyahsEditionsRequestState]:
    """Resolve raw fetch tool inputs into a typed continuation state."""
    page_size = choose_auto_page_size(tool_name, host)
    try:
        parsed_ayahs = parse_ayah_input(ayahs) if ayahs is not None else None
    except ValueError as exc:
        raise invalid_request_error(str(exc)) from exc

    explicit_state: dict[str, object] = {}
    if parsed_ayahs is not None:
        explicit_state["ayahs"] = parsed_ayahs
    if editions is not None:
        explicit_state["editions"] = _canonicalize_editions(editions)

    if continuation:
        try:
            requested_page, page_size, request_state = decode_continuation_request_model(
                continuation,
                tool_name=tool_name,
                state_model=FetchAyahsEditionsRequestState,
                explicit_state=dict(explicit_state) if explicit_state else None,
            )
        except ContinuationError as exc:
            raise_continuation_error(exc)
        return ResolvedFetchRequest(
            requested_page=requested_page,
            page_size=page_size,
            state=request_state,
        )

    if parsed_ayahs is None:
        raise invalid_request_error(missing_inputs_message)

    normalized_editions = editions if editions is not None else default_editions
    if normalized_editions is None:
        raise invalid_request_error(missing_inputs_message)

    return ResolvedFetchRequest(
        requested_page=1,
        page_size=page_size,
        state=FetchAyahsEditionsRequestState(
            ayahs=parsed_ayahs,
            editions=_canonicalize_editions(normalized_editions),
        ),
    )


def paginate_fetch_results(
    *,
    tool_name: str,
    continuation: str | None,
    request: ResolvedFetchRequest[TState],
    results: dict[str, list[TEntry]],
    bundle_key_fn: Callable[[TEntry], str] | None = None,
) -> tuple[dict[str, list[TEntry]], ContinuationPaginationMeta]:
    """Apply token-aware pagination and continuation metadata shaping."""
    internal_meta = PaginationMeta(
        page=request.requested_page,
        page_size=request.page_size,
        total_items=0,
        total_pages=1,
        has_more=False,
    )
    paged_results, internal_meta = enforce_token_cap_dict(
        results,
        internal_meta,
        bundle_key_fn=bundle_key_fn,
    )
    try:
        meta = build_checked_continuation_meta(
            continuation=continuation,
            requested_page=request.requested_page,
            tool_name=tool_name,
            request_state=request.state,
            internal_meta=internal_meta,
            page_size=request.page_size,
        )
    except ContinuationError as exc:
        raise_continuation_error(exc)
    return paged_results, meta


def build_fetch_results(
    raw_results: Mapping[str, Sequence[TRawEntry]],
    *,
    entry_factory: Callable[[TRawEntry], TEntry],
) -> dict[str, list[TEntry]]:
    """Map fetch-library results into output-model entries keyed by edition id."""
    return {
        edition_id: [entry_factory(entry) for entry in entries]
        for edition_id, entries in raw_results.items()
    }


def recompute_page_ayahs(
    all_ayahs: list[str],
    results: Mapping[str, Sequence[TEntry]],
    *,
    entry_ayahs: Callable[[TEntry], str | list[str]],
) -> list[str]:
    """Recompute page ayah order from entries that survived pagination."""
    survived: set[str] = set()
    for entries in results.values():
        for entry in entries:
            ayah_or_ayahs = entry_ayahs(entry)
            if isinstance(ayah_or_ayahs, list):
                survived.update(ayah_or_ayahs)
            else:
                survived.add(ayah_or_ayahs)
    return [ayah for ayah in all_ayahs if ayah in survived]


def build_fetch_warnings(
    *,
    gaps: list[Any] | None,
    unresolved: list[Any] | None,
) -> list[WarningModel] | None:
    """Build the stable warning contract used by fetch wrappers."""
    warnings: list[WarningModel] = []

    for gap in gaps or []:
        warnings.append(
            DataGapWarning(
                edition_id=gap.edition_id,
                missing_ayahs=gap.missing_ayahs,
            )
        )

    for unresolved_edition in unresolved or []:
        warnings.append(
            UnresolvedEditionWarning(
                selector=unresolved_edition.selector,
                suggestion=unresolved_edition.suggestion,
            )
        )

    return warnings or None


async def execute_fetch_tool(
    *,
    ctx: Context | None,
    tool_name: str,
    continuation: str | None,
    ayahs: str | list[str] | None,
    editions: str | list[str] | None,
    default_editions: str | None,
    missing_inputs_message: str,
    fetch_entries: Callable[[AppContext, list[str], str | list[str]], Awaitable[FetchResultLike[TRawEntry]]],
    build_results: Callable[[Mapping[str, Sequence[TRawEntry]]], dict[str, list[TEntry]]],
    entry_ayahs: Callable[[TEntry], str | list[str]],
    bundle_key_fn: Callable[[TEntry], str] | None = None,
) -> PreparedFetchPage[TEntry]:
    """Execute the common fetch-wrapper flow for one tool."""
    app_ctx, host = resolve_fetch_runtime_context(ctx)
    request = resolve_fetch_request(
        tool_name=tool_name,
        host=host,
        continuation=continuation,
        ayahs=ayahs,
        editions=editions,
        default_editions=default_editions,
        missing_inputs_message=missing_inputs_message,
    )
    try:
        fetch_result = await fetch_entries(
            app_ctx,
            request.state.ayahs,
            request.state.editions,
        )
    except (DataNotFoundError, DataStoreError) as exc:
        raise translate_fetch_domain_error(exc) from exc
    results = build_results(fetch_result.data)
    results, meta = paginate_fetch_results(
        tool_name=tool_name,
        continuation=continuation,
        request=request,
        results=results,
        bundle_key_fn=bundle_key_fn,
    )
    return PreparedFetchPage(
        ayahs=recompute_page_ayahs(
            request.state.ayahs,
            results,
            entry_ayahs=entry_ayahs,
        ),
        results=results,
        pagination=meta,
        warnings=build_fetch_warnings(
            gaps=list(fetch_result.gaps) if fetch_result.gaps else None,
            unresolved=list(fetch_result.unresolved) if fetch_result.unresolved else None,
        ),
    )
