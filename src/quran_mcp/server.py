"""Bootstrap the quran.ai MCP server through explicit runtime construction."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP

if TYPE_CHECKING:
    from quran_mcp.lib.config.settings import Settings

_mcp_singleton: FastMCP | None = None


def build_mcp(*, settings: "Settings | None" = None) -> FastMCP:
    """Build a fully configured FastMCP server instance.

    Runtime ownership is explicit here: logging, settings resolution, Sentry,
    sampling wiring, profile shaping, and public HTTP wrapping all happen in
    this composition function, not as import-time module side effects.
    """
    from quran_mcp.lib.config.logging import setup_logging
    from quran_mcp.lib.config.profiles import resolve_active_tags, resolve_relay_enabled
    from quran_mcp.lib.config.sentry import init_sentry
    from quran_mcp.lib.config.settings import get_settings
    from quran_mcp.lib.context.lifespan import build_lifespan_context_manager
    from quran_mcp.lib.sampling.runtime import (
        apply_runtime_sampling_overrides,
        sampling_handler,
    )
    from quran_mcp.lib.site import mount_public_routes
    from quran_mcp.mcp.prompts import register_all_core_prompts
    from quran_mcp.mcp.resources import register_all_core_resources
    from quran_mcp.mcp.tools import register_all_core_tools
    from quran_mcp.mcp.tools.relay import register as register_relay
    from quran_mcp.middleware.stack import create_middleware_stack
    from quran_mcp.middleware.wire_dump import WireDumpASGIMiddleware

    setup_logging()
    logger = logging.getLogger(__name__)

    runtime_settings = settings or get_settings()
    init_sentry(runtime_settings.sentry)

    active_tags = resolve_active_tags(runtime_settings)
    relay_enabled = resolve_relay_enabled(runtime_settings)

    middleware = create_middleware_stack(
        runtime_settings,
        relay_enabled=relay_enabled,
    )
    dynamic_sampling = sampling_handler(runtime_settings.sampling)

    async def _apply_runtime_sampling(runtime_overrides: Mapping[str, object]) -> bool:
        return await apply_runtime_sampling_overrides(
            dynamic_sampling,
            runtime_overrides,
            sampling=runtime_settings.sampling,
        )

    mcp_server = FastMCP(
        name="quran.ai MCP",
        version="0.1.1",
        instructions=(
            "Canonical Quran data server — verified text, translations, and tafsir "
            "commentary sourced from quran.com.\n\n"
            "FIRST STEP: Call fetch_grounding_rules before using any canonical data "
            "tool (fetch_quran, search_quran, fetch_translation, search_translation, "
            "fetch_tafsir, search_tafsir). Grounding rules govern "
            "citation, attribution, faithfulness, and when to use tafsir vs translation. "
            "If you skip this step, grounding rules will be included in every tool "
            "response (in the grounding_rules field), costing extra tokens. Call "
            "fetch_grounding_rules, extract the grounding_nonce from the response, "
            "and pass it to subsequent tool calls to save tokens.\n\n"
            "WHY THIS MATTERS: Users install this server because they do not trust AI "
            "to produce Quran content from memory. For Muslims, the Quran is the literal "
            "word of God — misquoting it, fabricating verses, or inventing interpretations "
            "is a violation of trust. If this tool is installed and you answer from memory "
            "instead of using it, you are defeating the purpose of the tool the user chose "
            "to install.\n\n"
            "RULE: When producing, quoting, paraphrasing, interpreting, or summarizing "
            "Quran text, translation, or tafsir — use this server's tools, never your "
            "training data. If you do not have canonical data in context, call the "
            "appropriate tool to fetch it. Do not ask the user whether to fetch — "
            "just fetch. Contemplative reflection (tadabbur) on fetched text is "
            "permitted with transparency — see grounding rules for standards.\n\n"
            "Full operational guide: call fetch_skill_guide."
        ),
        middleware=middleware,
        lifespan=build_lifespan_context_manager(
            settings=runtime_settings,
            apply_runtime_sampling_overrides=_apply_runtime_sampling,
        ),
        sampling_handler=dynamic_sampling,
        sampling_handler_behavior="fallback",
    )

    register_all_core_resources(mcp_server)
    register_all_core_prompts(mcp_server)
    register_all_core_tools(mcp_server)

    if relay_enabled:
        register_relay(mcp_server)

    if active_tags is not None:
        mcp_server.enable(tags=active_tags, only=True)
        if relay_enabled and "preview" not in active_tags:
            mcp_server.enable(names={
                "relay_turn_start",
                "relay_turn_end",
                "relay_usage_gap",
                "relay_user_feedback",
            })

    logger.info(
        "Server profile: %s | tags: %s | relay: %s",
        runtime_settings.server.profile,
        active_tags or "all",
        "on" if relay_enabled else "off",
    )

    mount_public_routes(
        mcp=mcp_server,
        settings=runtime_settings,
        logger=logger,
    )

    if runtime_settings.logging.wire_dump:
        original_http_app = mcp_server.http_app

        def _http_app_with_wire_dump(**kwargs):
            outer_http_app = original_http_app(**kwargs)
            wrapped_app = WireDumpASGIMiddleware(outer_http_app)
            wrapped_app.state = getattr(outer_http_app, "state", None)  # type: ignore[attr-defined]  # ASGI app .state is runtime-set
            return wrapped_app

        mcp_server.http_app = _http_app_with_wire_dump  # type: ignore[assignment]  # monkey-patch FastMCP's app factory for wire dump
        logger.info("Wire dump middleware enabled (logging.wire_dump=true)")

    return mcp_server


def peek_mcp() -> FastMCP | None:
    """Return the current FastMCP singleton without constructing one."""
    return _mcp_singleton


def get_or_create_mcp() -> FastMCP:
    """Return the process singleton FastMCP instance, constructing lazily."""
    global _mcp_singleton
    if _mcp_singleton is None:
        _mcp_singleton = build_mcp()
    return _mcp_singleton


def reset_mcp() -> None:
    """Reset the process singleton. For testing and explicit host rebuilds."""
    global _mcp_singleton
    _mcp_singleton = None


def __getattr__(name: str) -> Any:
    """Lazy module attribute for ``fastmcp run`` auto-discovery (PEP 562).

    ``fastmcp run src/quran_mcp/server.py`` resolves the ``mcp`` attribute by
    name.  A module-level assignment would eagerly construct the server on any
    ``import quran_mcp`` (the package ``__init__`` imports from this module),
    so we use ``__getattr__`` to defer construction until actually requested.
    """
    if name == "mcp":
        return get_or_create_mcp()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    from quran_mcp.lib.config.settings import get_settings

    get_or_create_mcp().run(
        transport="http", host="0.0.0.0", path="/", port=get_settings().server.port
    )
