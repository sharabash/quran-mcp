"""Shared orchestration primitives for search_* MCP tool wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Generic, Mapping, NoReturn, Protocol, Sequence, TypeVar, cast

from fastmcp import Context
from fastmcp.exceptions import ToolError
from pydantic import BaseModel

from quran_mcp.lib.context.types import AppContext
from quran_mcp.lib.goodmem import GoodMemClient
from quran_mcp.lib.presentation.client_hint import detect_client_hint
from quran_mcp.lib.presentation.pagination import (
    MAX_SEARCH_DEPTH,
    ContinuationError,
    ContinuationPaginationMeta,
    PaginationMeta,
    build_checked_continuation_meta,
    choose_auto_page_size,
    decode_continuation_request_model,
    enforce_token_cap,
)
from quran_mcp.lib.search.common import SearchPipelineError
from quran_mcp.mcp.tools._tool_context import raise_continuation_error
from quran_mcp.mcp.tools._tool_errors import invalid_request_error

QUERY_REQUIRED_MESSAGE = "query is required unless continuation is provided"
SEARCH_TOOL_ERROR_CONTRACT = (
    "Failure contract: `[invalid_request]` for malformed inputs, "
    "`[continuation_invalid|tampered|expired|conflict|exhausted|legacy]` for bad continuation "
    "tokens, `[search_backend_failure]` for retrieval failures, and "
    "`[search_enrichment_failure]` for post-retrieval enrichment failures."
)

class SearchRequestState(Protocol):
    """Minimal state shape shared by search continuation models."""

    query: str


TState = TypeVar("TState", bound=BaseModel)
TEntry = TypeVar("TEntry")
TLibResult = TypeVar("TLibResult")
TWarning = TypeVar("TWarning")


@dataclass(frozen=True)
class ResolvedSearchRequest(Generic[TState]):
    """Normalized search-request envelope used by wrapper handlers."""

    requested_page: int
    page_size: int
    state: TState


@dataclass(frozen=True)
class SearchExecution(Generic[TEntry, TWarning]):
    """Shared pagination and warning result for search tool wrappers."""

    query: str
    results: list[TEntry]
    total_found: int
    pagination: ContinuationPaginationMeta
    warnings: list[TWarning] | None


@dataclass(frozen=True)
class SearchRequestInputs(Generic[TState]):
    """Normalized explicit and initial state inputs for search tools."""

    explicit_state: dict[str, object]
    initial_state: TState | None


@dataclass(frozen=True)
class SearchExecutionPlan(Generic[TState, TEntry, TLibResult, TWarning]):
    """Typed plan for one search tool execution."""

    tool_name: str
    state_model: type[TState]
    run_search: Callable[[GoodMemClient, TState, int], Awaitable[TLibResult]]
    results_getter: Callable[[TLibResult], Sequence[TEntry]]
    warnings_builder: Callable[[TLibResult], Sequence[TWarning]]
    page_ref: Callable[[TEntry], tuple[str | None, str]]



def _raise_backend_unavailable(message: str) -> NoReturn:
    raise ToolError(f"[search_backend_failure] {message}")


def _decode_search_continuation(
    *,
    continuation: str,
    tool_name: str,
    state_model: type[BaseModel],
    explicit_state: Mapping[str, object],
) -> ResolvedSearchRequest[BaseModel]:
    try:
        decoded = decode_continuation_request_model(
            continuation,
            tool_name=tool_name,
            state_model=state_model,
            explicit_state=dict(explicit_state) if explicit_state else None,
        )
    except ContinuationError as exc:
        raise_continuation_error(exc)

    return ResolvedSearchRequest(
        requested_page=cast(int, decoded[0]),
        page_size=cast(int, decoded[1]),
        state=cast(BaseModel, decoded[2]),
    )


def _build_search_pagination(
    *,
    continuation: str | None,
    requested_page: int,
    tool_name: str,
    request_state: BaseModel,
    internal_meta: PaginationMeta,
    page_size: int,
) -> ContinuationPaginationMeta:
    try:
        return build_checked_continuation_meta(
            continuation=continuation,
            requested_page=requested_page,
            tool_name=tool_name,
            request_state=request_state,
            internal_meta=internal_meta,
            page_size=page_size,
        )
    except ContinuationError as exc:
        raise_continuation_error(exc)


def _canonicalize_request_value(value: object) -> object:
    if isinstance(value, list):
        return sorted(value)
    return value


def build_search_request_inputs(
    state_model: type[TState],
    *,
    continuation: str | None,
    query: str | None,
    defaults: Mapping[str, object] | None = None,
    **fields: object,
) -> SearchRequestInputs[TState]:
    """Build explicit continuation state and initial request state consistently."""
    explicit_state: dict[str, object] = {}
    if query is not None:
        explicit_state["query"] = query

    initial_state_fields: dict[str, object] = {}
    for key, value in fields.items():
        normalized_value = _canonicalize_request_value(value)
        if value is not None:
            explicit_state[key] = normalized_value
            initial_state_fields[key] = normalized_value
            continue
        if defaults and key in defaults:
            initial_state_fields[key] = _canonicalize_request_value(defaults[key])

    initial_state = None
    if continuation is None and query is not None:
        initial_state = state_model(query=query, **initial_state_fields)

    return SearchRequestInputs(
        explicit_state=explicit_state,
        initial_state=initial_state,
    )


def resolve_search_request(
    *,
    ctx: Context | None,
    tool_name: str,
    continuation: str | None,
    state_model: type[TState],
    explicit_state: Mapping[str, object],
    initial_state: TState | None,
) -> ResolvedSearchRequest[TState]:
    """Resolve raw search tool inputs into a typed continuation state."""
    host = detect_client_hint(ctx).get("host")
    page_size = choose_auto_page_size(tool_name, host)

    if continuation is not None:
        return cast(
            ResolvedSearchRequest[TState],
            _decode_search_continuation(
                continuation=continuation,
                tool_name=tool_name,
                state_model=state_model,
                explicit_state=explicit_state,
            ),
        )

    if initial_state is None:
        raise invalid_request_error(QUERY_REQUIRED_MESSAGE)

    return ResolvedSearchRequest(
        requested_page=1,
        page_size=page_size,
        state=initial_state,
    )


def resolve_search_runtime_context(ctx: Context | None) -> tuple[AppContext, GoodMemClient]:
    """Resolve the runtime app context and GoodMem client for search tools."""
    from quran_mcp.mcp.tools._tool_context import resolve_app_context

    app_ctx = resolve_app_context(ctx)
    goodmem_client = app_ctx.goodmem_cli
    if goodmem_client is None:
        _raise_backend_unavailable("Search backend unavailable: GoodMem client not initialized")
    return app_ctx, goodmem_client


async def execute_search_tool(
    *,
    ctx: Context | None,
    continuation: str | None,
    explicit_state: Mapping[str, object],
    initial_state: TState | None,
    plan: SearchExecutionPlan[TState, TEntry, TLibResult, TWarning],
    goodmem_client: GoodMemClient | None = None,
) -> SearchExecution[TEntry, TWarning]:
    """Run a search tool through one shared continuation/pagination pipeline."""
    request = resolve_search_request(
        ctx=ctx,
        tool_name=plan.tool_name,
        continuation=continuation,
        state_model=plan.state_model,
        explicit_state=explicit_state,
        initial_state=initial_state,
    )
    _, runtime_client = resolve_search_runtime_context(ctx)
    client = goodmem_client if goodmem_client is not None else runtime_client
    request_state = request.state

    try:
        lib_result = await plan.run_search(client, request_state, MAX_SEARCH_DEPTH)
    except ValueError as exc:
        raise invalid_request_error(str(exc)) from exc
    except SearchPipelineError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc

    internal_meta = PaginationMeta(
        page=request.requested_page,
        page_size=request.page_size,
        total_items=0,
        total_pages=1,
        has_more=False,
    )
    page_entries, internal_meta = enforce_token_cap(
        list(plan.results_getter(lib_result)),
        internal_meta,
        page_entry_fn=plan.page_ref,
    )
    pagination = _build_search_pagination(
        continuation=continuation,
        requested_page=request.requested_page,
        tool_name=plan.tool_name,
        request_state=request_state,
        internal_meta=internal_meta,
        page_size=request.page_size,
    )

    return SearchExecution(
        query=cast(SearchRequestState, request_state).query,
        results=page_entries,
        total_found=internal_meta.total_items,
        pagination=pagination,
        warnings=list(plan.warnings_builder(lib_result)) or None,
    )
