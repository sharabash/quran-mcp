"""Shared context types used across the application.

`AppContext` lives in this small leaf module on purpose.

Why it is separate:
- `lifespan.py` is the composition root that creates shared dependencies.
- Fetch/business-logic modules also need the `AppContext` type in their
  function signatures.
- If `AppContext` lived in `lifespan.py`, leaf modules would have to import
  the whole startup/shutdown module just to reference one dataclass.

Keeping the type here preserves a clean dependency direction:
- `lifespan.py` imports `AppContext` to construct it
- fetchers/helpers import `AppContext` to declare what they need
- neither side has to depend on the other's implementation details
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import asyncpg

if TYPE_CHECKING:
    from quran_mcp.lib.config.settings import Settings
    from quran_mcp.lib.goodmem import GoodMemClient
    from quran_mcp.lib.db.turn_manager import TurnManager
    from quran_mcp.lib.relay.runtime import RelayRuntimeState
else:
    # Keep this module as a runtime leaf: avoid importing the heavy GoodMem stack
    # just to resolve a type annotation.
    Settings = Any
    GoodMemClient = Any
    TurnManager = Any
    RelayRuntimeState = Any


@dataclass
class AppContext:
    """Global application context with all shared dependencies.

    Attributes:
        goodmem_cli: Optional GoodMem client for semantic memory caching.
                     None if GoodMem initialization failed (graceful degradation).
        db_pool: Database connection pool.
        settings: Runtime settings owned by the composition root, when available.
        turn_manager: Owner-scoped relay turn manager.
        relay_runtime_state: Owner-scoped relay middleware registry.
    """

    goodmem_cli: GoodMemClient | None = None
    db_pool: asyncpg.Pool | None = None
    settings: Settings | None = None
    turn_manager: TurnManager | None = None
    relay_runtime_state: RelayRuntimeState | None = None
