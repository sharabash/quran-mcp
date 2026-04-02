"""Relay runtime ownership shared by lifespan and middleware."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol
import weakref


class _DrainableRelayMiddleware(Protocol):
    async def _drain_pending_local(self, timeout: float = 5.0) -> None: ...


@dataclass
class RelayRuntimeState:
    """Owner-scoped relay runtime registry."""

    middleware_instances: weakref.WeakSet[Any] = field(default_factory=weakref.WeakSet)

    def register(self, middleware: Any) -> None:
        """Track a live relay middleware instance."""
        self.middleware_instances.add(middleware)

    async def drain_pending(self, timeout: float = 5.0) -> None:
        """Drain pending background writes from all tracked relay middleware."""
        instances = list(self.middleware_instances)
        if not instances:
            return
        await asyncio.gather(
            *(instance._drain_pending_local(timeout=timeout) for instance in instances),
        )

    def reset(self) -> None:
        """Clear the tracked middleware registry."""
        self.middleware_instances.clear()


def build_relay_runtime_state() -> RelayRuntimeState:
    """Create an isolated relay runtime registry."""
    return RelayRuntimeState()


def get_or_create_relay_runtime_state(owner: Any) -> RelayRuntimeState:
    """Return owner-scoped relay runtime state, creating it on first access."""
    if owner is None:
        raise ValueError("owner is required for relay runtime ownership")
    state = getattr(owner, "relay_runtime_state", None)
    if state is None:
        state = build_relay_runtime_state()
        setattr(owner, "relay_runtime_state", state)
    return state


def peek_relay_runtime_state(owner: Any) -> RelayRuntimeState | None:
    """Return owner-scoped relay runtime state without constructing one."""
    if owner is None:
        raise ValueError("owner is required for relay runtime ownership")
    return getattr(owner, "relay_runtime_state", None)


def register_relay_middleware(owner: Any, middleware: _DrainableRelayMiddleware) -> None:
    """Register a relay middleware instance for later draining."""
    get_or_create_relay_runtime_state(owner).register(middleware)


async def drain_pending(owner: Any, timeout: float = 5.0) -> None:
    """Drain pending relay middleware writes for one owner."""
    if owner is None:
        raise ValueError("owner is required for relay runtime ownership")
    state = getattr(owner, "relay_runtime_state", None)
    if state is None:
        return
    await state.drain_pending(timeout=timeout)


def reset_relay_runtime_state(owner: Any) -> None:
    """Reset relay runtime ownership state for one owner."""
    if owner is None:
        raise ValueError("owner is required for relay runtime ownership")
    setattr(owner, "relay_runtime_state", build_relay_runtime_state())
