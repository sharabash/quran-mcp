"""
Application context and lifespan management.

This module is the composition root for the application. It owns the lifespan
and composes all shared dependencies (GoodMem client, DB pool, etc.).

Architectural Note:
    This is NOT middleware. Middleware intercepts requests (runs on every request).
    This is a composition root / application bootstrap that runs once at startup/shutdown.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from inspect import isawaitable
from typing import TYPE_CHECKING, Any, AsyncContextManager

from quran_mcp.lib.goodmem import GoodMemClient, GoodMemConfig
from quran_mcp.lib.context.types import AppContext
from quran_mcp.lib.db.pool import create_pool, close_pool

if TYPE_CHECKING:
    from quran_mcp.lib.config.settings import Settings

logger = logging.getLogger(__name__)
RuntimeSamplingOverridesApplier = Callable[[Mapping[str, Any]], bool | Awaitable[bool]]


async def create_app_context(
    *,
    with_goodmem: bool = False,
    settings: "Settings | None" = None,
) -> "AppContext":
    """Create an AppContext for REPL or testing usage (without FastMCP server).

    Does NOT auto-close resources; use create_app_context_managed() for that.
    Pass with_goodmem=True to initialize the GoodMem client from environment.
    """
    goodmem_cli: GoodMemClient | None = None
    if with_goodmem:
        try:
            config = GoodMemConfig.from_env()
            goodmem_cli = GoodMemClient(config)
            await goodmem_cli.initialize()
            logger.info("GoodMem client initialized (standalone)")
        except Exception as e:
            logger.warning(f"GoodMem init failed: {e}. Semantic search disabled.")
            goodmem_cli = None

    return AppContext(goodmem_cli=goodmem_cli, settings=settings)


@asynccontextmanager
async def create_app_context_managed(
    *,
    with_goodmem: bool = False,
    settings: "Settings | None" = None,
) -> AsyncIterator["AppContext"]:
    """Create an AppContext as an async context manager with cleanup."""
    ctx = await create_app_context(with_goodmem=with_goodmem, settings=settings)
    yield ctx


def build_lifespan_context_manager(
    *,
    settings: "Settings | None" = None,
    apply_runtime_sampling_overrides: RuntimeSamplingOverridesApplier | None = None,
) -> Callable[[Any], AsyncContextManager[AppContext]]:
    """Build an application lifespan manager with explicit runtime hooks.

    The returned callable matches FastMCP's lifespan signature and keeps runtime
    ownership explicit by injecting optional startup behavior (such as sampling
    override application) from the composition root.
    """

    @asynccontextmanager
    async def _lifespan_context_manager(server) -> AsyncIterator[AppContext]:
        """Application lifecycle manager. Composes all shared dependencies.

        This lifespan function:
        - Initializes GoodMem client (optional, graceful degradation on failure)
        - Creates database pool
        - Applies optional runtime DB overrides (via injected callback)
        - Attaches owner-scoped turn-manager and relay runtime state
        - Yields the composed AppContext
        - Cleans up resources on shutdown

        Args:
            server: FastMCP server instance (unused, required by FastMCP signature)

        Yields:
            AppContext with all initialized dependencies

        Usage:
            In server.py:
                from quran_mcp.lib.context.lifespan import build_lifespan_context_manager
                mcp = FastMCP(..., lifespan=build_lifespan_context_manager(...))

            In tools/resources:
                goodmem_cli = ctx.request_context.lifespan_context.goodmem_cli
        """
        # GoodMem client (optional - graceful degradation)
        # Failures: connection errors, missing credentials, timeouts → log warning, continue
        goodmem_cli: GoodMemClient | None = None
        try:
            config = GoodMemConfig.from_env()
            goodmem_cli = GoodMemClient(config)
            await goodmem_cli.initialize()
            logger.info("GoodMem client initialized successfully")
        except Exception as e:
            # Graceful degradation: log but don't fail server startup
            logger.warning(f"GoodMem init failed: {e}. Semantic search disabled.")
            goodmem_cli = None

        # Database pool — always created when DB password is configured.
        # The relay_settings parameter controls retention cleanup only.
        from quran_mcp.lib.config.profiles import resolve_relay_enabled
        from quran_mcp.lib.config.settings import get_settings

        runtime_settings = settings or get_settings()
        relay_enabled = resolve_relay_enabled(runtime_settings)

        db_pool = await create_pool(
            runtime_settings.database,
            runtime_settings.relay if relay_enabled else None,
        )

        # Apply runtime config overrides (DB takes precedence over config.yml)
        if db_pool and apply_runtime_sampling_overrides is not None:
            from quran_mcp.lib.db.runtime_config import load_runtime_config

            runtime_sampling = await load_runtime_config(db_pool, "sampling")
            if runtime_sampling:
                apply_result = apply_runtime_sampling_overrides(runtime_sampling)
                applied = await apply_result if isawaitable(apply_result) else apply_result
                if applied:
                    logger.info("Applied runtime_config sampling overrides: %s", runtime_sampling)

        app_ctx = AppContext(
            goodmem_cli=goodmem_cli,
            db_pool=db_pool,
            settings=runtime_settings,
        )

        from quran_mcp.lib.db.turn_manager import reset_turn_manager
        from quran_mcp.lib.relay.runtime import drain_pending, reset_relay_runtime_state

        reset_turn_manager(app_ctx)
        reset_relay_runtime_state(app_ctx)

        try:
            yield app_ctx
        finally:
            if relay_enabled:
                await drain_pending(app_ctx)
            await close_pool(db_pool)

    return _lifespan_context_manager
