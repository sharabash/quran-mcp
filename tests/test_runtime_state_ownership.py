"""Runtime ownership regression tests for context/server/sampling seams."""

from __future__ import annotations

import contextvars
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import importlib
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastmcp import FastMCP

import quran_mcp.lib.context.lifespan as lifespan_mod
import quran_mcp.lib.relay.runtime as relay_runtime_mod
import quran_mcp.lib.relay.turns as relay_turns_mod
import quran_mcp.lib.sampling.handler as sampling_mod
import quran_mcp.lib.sampling.runtime as sampling_runtime_mod
from quran_mcp.lib.config.settings import SamplingSettings
from quran_mcp.lib.context.request import get_active_relay_turn_id
from quran_mcp.lib.documentation.runtime import get_or_create_documentation_runtime_state
from quran_mcp.lib.site.health import get_or_create_health_runtime_state


class _NoopSamplingHandler:
    async def __call__(self, *_args, **_kwargs):  # pragma: no cover - never invoked
        raise AssertionError("should not be called in unit test")


class _TrackedRelayMiddleware:
    def __init__(self) -> None:
        self.drained = 0

    async def _drain_pending_local(self, timeout: float = 5.0) -> None:
        assert timeout == 1.5
        self.drained += 1


class _StubFastMCPContext:
    def __init__(self, *, session_id: str = "session-1") -> None:
        self.session_id = session_id
        self._state: dict[str, str] = {}

    async def get_state(self, key: str) -> str | None:
        return self._state.get(key)

    async def set_state(self, key: str, value: str) -> None:
        self._state[key] = value


class _StubTurnManager:
    def __init__(self, state: object) -> None:
        self._state = state
        self.calls: list[dict[str, object]] = []

    def find_state_by_turn_id(self, turn_id):
        if str(turn_id) == str(self._state.turn_id):
            return self._state
        return None

    async def get_or_create_turn(self, _pool, **kwargs):
        self.calls.append(kwargs)
        return self._state


def test_context_types_module_stays_leaf() -> None:
    original_context_types = sys.modules.pop("quran_mcp.lib.context.types", None)
    original_goodmem = sys.modules.pop("quran_mcp.lib.goodmem", None)

    try:
        importlib.import_module("quran_mcp.lib.context.types")
        assert "quran_mcp.lib.goodmem" not in sys.modules
    finally:
        sys.modules.pop("quran_mcp.lib.context.types", None)
        sys.modules.pop("quran_mcp.lib.goodmem", None)
        if original_context_types is not None:
            sys.modules["quran_mcp.lib.context.types"] = original_context_types
        if original_goodmem is not None:
            sys.modules["quran_mcp.lib.goodmem"] = original_goodmem


def test_server_module_import_is_lazy() -> None:
    sys.modules.pop("quran_mcp.server", None)
    module = importlib.import_module("quran_mcp.server")

    assert "mcp" not in module.__dict__
    assert callable(module.get_or_create_mcp)
    assert module.peek_mcp() is None


def test_server_factory_dynamic_access(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("quran_mcp.server")
    builds: list[FastMCP] = []

    def _build_stub() -> FastMCP:
        instance = FastMCP(name="test-server")
        builds.append(instance)
        return instance

    monkeypatch.setattr(module, "build_mcp", _build_stub)
    monkeypatch.setattr(module, "_mcp_singleton", None)

    # Trigger build via dynamic __getattr__ property "mcp"
    first = getattr(module, "mcp")
    second = getattr(module, "mcp")
    third = module.peek_mcp()

    assert isinstance(first, FastMCP)
    assert first is second
    assert second is third
    assert builds == [first]


def test_build_mcp_threads_injected_settings_into_lifespan_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("quran_mcp.server")
    seen: dict[str, object] = {}
    injected_settings = SimpleNamespace(
        sentry=object(),
        sampling=SamplingSettings(),
        server=SimpleNamespace(profile="full"),
        logging=SimpleNamespace(wire_dump=False),
        relay=SimpleNamespace(),
        database=SimpleNamespace(),
    )

    def _fail_get_settings():
        raise AssertionError("build_mcp should not re-read global settings when injected")

    def _build_lifespan_context_manager(*, settings=None, apply_runtime_sampling_overrides=None):
        seen["lifespan_settings"] = settings
        seen["lifespan_applier"] = apply_runtime_sampling_overrides

        @asynccontextmanager
        async def _lifespan(_server):
            yield SimpleNamespace()

        return _lifespan

    monkeypatch.setattr("quran_mcp.lib.config.logging.setup_logging", lambda: None)
    monkeypatch.setattr("quran_mcp.lib.config.profiles.resolve_active_tags", lambda _settings: None)
    monkeypatch.setattr("quran_mcp.lib.config.profiles.resolve_relay_enabled", lambda _settings: False)
    monkeypatch.setattr("quran_mcp.lib.config.sentry.init_sentry", lambda _sentry: None)
    monkeypatch.setattr("quran_mcp.lib.config.settings.get_settings", _fail_get_settings)
    monkeypatch.setattr(
        "quran_mcp.lib.context.lifespan.build_lifespan_context_manager",
        _build_lifespan_context_manager,
    )
    monkeypatch.setattr(
        "quran_mcp.lib.sampling.runtime.apply_runtime_sampling_overrides",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "quran_mcp.lib.sampling.runtime.sampling_handler",
        lambda _sampling: _NoopSamplingHandler(),
    )
    monkeypatch.setattr(
        "quran_mcp.lib.site.mount_public_routes",
        lambda *, mcp, settings, logger: seen.setdefault("mounted_settings", settings),
    )
    monkeypatch.setattr("quran_mcp.mcp.prompts.register_all_core_prompts", lambda _mcp: None)
    monkeypatch.setattr("quran_mcp.mcp.resources.register_all_core_resources", lambda _mcp: None)
    monkeypatch.setattr("quran_mcp.mcp.tools.register_all_core_tools", lambda _mcp: None)
    monkeypatch.setattr("quran_mcp.mcp.tools.relay.register", lambda _mcp: None)
    monkeypatch.setattr(
        "quran_mcp.middleware.stack.create_middleware_stack",
        lambda settings, *, relay_enabled: (
            seen.setdefault("middleware_settings", settings),
            seen.setdefault("middleware_relay_enabled", relay_enabled),
            [],
        )[2],
    )

    module.build_mcp(settings=injected_settings)

    assert seen["lifespan_settings"] is injected_settings
    assert seen["middleware_settings"] is injected_settings
    assert seen["middleware_relay_enabled"] is False
    assert seen["mounted_settings"] is injected_settings
    assert callable(seen["lifespan_applier"])


def test_package_root_does_not_conjure_mcp_namespace() -> None:
    original_package = sys.modules.get("quran_mcp")
    original_subpackage = sys.modules.get("quran_mcp.mcp")
    try:
        sys.modules.pop("quran_mcp", None)
        sys.modules.pop("quran_mcp.mcp", None)
        fresh_package = importlib.import_module("quran_mcp")
        assert "mcp" not in fresh_package.__dict__
        with pytest.raises(AttributeError):
            getattr(fresh_package, "mcp")
    finally:
        if original_package is not None:
            sys.modules["quran_mcp"] = original_package
        if original_subpackage is not None:
            sys.modules["quran_mcp.mcp"] = original_subpackage


def test_lifespan_module_does_not_expose_legacy_default_manager() -> None:
    assert "lifespan_context_manager" not in lifespan_mod.__dict__
    with pytest.raises(AttributeError):
        getattr(lifespan_mod, "lifespan_context_manager")


def test_sampling_handler_respects_explicit_ownership() -> None:
    previous = sampling_mod.get_dynamic_handler()

    handler = sampling_mod.sampling_handler(
        SamplingSettings(provider="unsupported-provider"),
        register_active=False,
    )

    assert isinstance(handler, sampling_mod.DynamicSamplingHandler)
    assert sampling_mod.get_dynamic_handler() is previous


def test_sampling_handler_is_pure_by_default() -> None:
    previous = sampling_mod.get_dynamic_handler()

    handler = sampling_mod.sampling_handler(
        SamplingSettings(provider="unsupported-provider"),
    )

    assert isinstance(handler, sampling_mod.DynamicSamplingHandler)
    assert sampling_mod.get_dynamic_handler() is previous


def test_activate_dynamic_handler_is_context_local() -> None:
    handler = sampling_mod.sampling_handler(
        SamplingSettings(provider="unsupported-provider"),
    )

    sampling_runtime_mod.activate_dynamic_handler(handler)

    assert sampling_runtime_mod.get_dynamic_handler() is handler
    assert contextvars.Context().run(sampling_runtime_mod.get_dynamic_handler) is None


def test_build_mcp_threads_sampling_handler_without_ambient_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("quran_mcp.server")
    seen: dict[str, object] = {}
    dynamic_handler = _NoopSamplingHandler()
    injected_settings = SimpleNamespace(
        sentry=object(),
        sampling=SamplingSettings(),
        server=SimpleNamespace(profile="full"),
        logging=SimpleNamespace(wire_dump=False),
        relay=SimpleNamespace(),
        database=SimpleNamespace(),
    )

    class _StubFastMCP:
        def __init__(self, *args, **kwargs) -> None:
            seen["sampling_handler"] = kwargs["sampling_handler"]
            self.http_app = lambda **_kwargs: SimpleNamespace(state=None)

        def enable(self, *args, **kwargs) -> None:
            return None

    monkeypatch.setattr("quran_mcp.lib.config.logging.setup_logging", lambda: None)
    monkeypatch.setattr("quran_mcp.lib.config.profiles.resolve_active_tags", lambda _settings: None)
    monkeypatch.setattr("quran_mcp.lib.config.profiles.resolve_relay_enabled", lambda _settings: False)
    monkeypatch.setattr("quran_mcp.lib.config.sentry.init_sentry", lambda _sentry: None)

    @asynccontextmanager
    async def _lifespan(_server):
        yield SimpleNamespace()

    monkeypatch.setattr(
        "quran_mcp.lib.context.lifespan.build_lifespan_context_manager",
        lambda **_kwargs: _lifespan,
    )
    monkeypatch.setattr(
        "quran_mcp.lib.sampling.runtime.sampling_handler",
        lambda _sampling: dynamic_handler,
    )
    monkeypatch.setattr(
        "quran_mcp.lib.sampling.runtime.activate_dynamic_handler",
        lambda _handler: (_ for _ in ()).throw(
            AssertionError("build_mcp should thread the handler explicitly, not activate ambient state")
        ),
    )
    monkeypatch.setattr(
        "quran_mcp.lib.sampling.runtime.apply_runtime_sampling_overrides",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "quran_mcp.lib.site.mount_public_routes",
        lambda *, mcp, settings, logger: None,
    )
    monkeypatch.setattr("quran_mcp.mcp.prompts.register_all_core_prompts", lambda _mcp: None)
    monkeypatch.setattr("quran_mcp.mcp.resources.register_all_core_resources", lambda _mcp: None)
    monkeypatch.setattr("quran_mcp.mcp.tools.register_all_core_tools", lambda _mcp: None)
    monkeypatch.setattr("quran_mcp.mcp.tools.relay.register", lambda _mcp: None)
    monkeypatch.setattr("quran_mcp.middleware.stack.create_middleware_stack", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(module, "FastMCP", _StubFastMCP)

    module.build_mcp(settings=injected_settings)

    assert seen["sampling_handler"] is dynamic_handler


def test_documentation_runtime_state_is_per_owner() -> None:
    first_owner = SimpleNamespace()
    second_owner = SimpleNamespace()

    first_state = get_or_create_documentation_runtime_state(first_owner)
    second_state = get_or_create_documentation_runtime_state(second_owner)
    first_state.json_cache = (("fetch_quran",), '{"tool_count": 1}')

    assert first_state is not second_state
    assert second_state.json_cache is None


def test_health_runtime_state_is_per_owner() -> None:
    first_owner = SimpleNamespace()
    second_owner = SimpleNamespace()

    first_state = get_or_create_health_runtime_state(first_owner)
    second_state = get_or_create_health_runtime_state(second_owner)
    first_state.last_request_time = 42.0
    first_state.cache["default"] = (100.0, {"status": "healthy"})

    assert first_state is not second_state
    assert second_state.last_request_time == 0.0
    assert second_state.cache == {}


def test_relay_runtime_state_lives_in_lib_seam() -> None:
    first_owner = SimpleNamespace()
    second_owner = SimpleNamespace()

    first = _TrackedRelayMiddleware()
    second = _TrackedRelayMiddleware()
    relay_runtime_mod.register_relay_middleware(first_owner, first)
    relay_runtime_mod.register_relay_middleware(second_owner, second)

    first_state = relay_runtime_mod.peek_relay_runtime_state(first_owner)
    second_state = relay_runtime_mod.peek_relay_runtime_state(second_owner)

    assert first_state is not second_state
    assert first_state is not None
    assert second_state is not None
    assert len(list(first_state.middleware_instances)) == 1
    assert len(list(second_state.middleware_instances)) == 1


@pytest.mark.asyncio
async def test_relay_runtime_drain_and_reset_are_lib_owned() -> None:
    owner = SimpleNamespace()
    relay_runtime_mod.reset_relay_runtime_state(owner)

    first = _TrackedRelayMiddleware()
    second = _TrackedRelayMiddleware()
    relay_runtime_mod.register_relay_middleware(owner, first)
    relay_runtime_mod.register_relay_middleware(owner, second)

    await relay_runtime_mod.drain_pending(owner, timeout=1.5)

    assert first.drained == 1
    assert second.drained == 1

    relay_runtime_mod.reset_relay_runtime_state(owner)
    state = relay_runtime_mod.peek_relay_runtime_state(owner)
    assert state is not None
    assert len(list(state.middleware_instances)) == 0


def test_build_relay_turn_context_centralizes_shared_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = {
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        "x-openai-session": "openai-session-1",
    }
    ctx = _StubFastMCPContext(session_id="relay-session")

    monkeypatch.setattr(relay_turns_mod, "extract_client_info", lambda _ctx: {"name": "chatgpt", "version": "1"})

    turn_context = relay_turns_mod.build_relay_turn_context(ctx, headers=headers)

    assert turn_context.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert turn_context.provider_continuity_token == "openai-session-1"
    assert turn_context.context_id == "relay-session"
    assert turn_context.client_info == {"name": "chatgpt", "version": "1"}


def test_build_relay_turn_context_uses_provider_aware_identity_without_traceparent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = {"x-openai-session": "openai-session-2"}
    ctx = _StubFastMCPContext(session_id="relay-session")

    monkeypatch.setattr(relay_turns_mod, "extract_client_info", lambda _ctx: None)

    turn_context = relay_turns_mod.build_relay_turn_context(ctx, headers=headers)

    assert turn_context.trace_id is None
    assert turn_context.provider_continuity_token == "openai-session-2"
    assert turn_context.context_id == "openai-conv:openai-session-2"


def test_get_relay_db_pool_reads_from_request_lifespan_boundary() -> None:
    app_ctx = SimpleNamespace(db_pool=object())
    fastmcp_ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app_ctx))

    assert relay_turns_mod.get_relay_db_pool(fastmcp_ctx) is app_ctx.db_pool
    assert relay_turns_mod.get_relay_db_pool(SimpleNamespace()) is None


@pytest.mark.asyncio
async def test_activate_relay_turn_bridges_mounted_state_boundary() -> None:
    state = SimpleNamespace(
        turn_id=uuid4(),
        call_index=0,
        last_completed_at=None,
        started_at=datetime.now(timezone.utc),
        origin="inferred",
        ended=False,
    )
    mgr = _StubTurnManager(state)
    parent_ctx = _StubFastMCPContext(session_id="parent-session")
    mounted_ctx = _StubFastMCPContext(session_id="mounted-session")

    async with relay_turns_mod.activate_relay_turn(parent_ctx, state.turn_id):
        assert await parent_ctx.get_state("relay.turn_id") == str(state.turn_id)
        resolved = await relay_turns_mod.get_bound_relay_turn_state(mounted_ctx, mgr=mgr)
        assert resolved is state
        assert get_active_relay_turn_id() == str(state.turn_id)

    assert get_active_relay_turn_id() is None


@pytest.mark.asyncio
async def test_resolve_relay_turn_state_uses_shared_manager_contract() -> None:
    state = SimpleNamespace(
        turn_id=uuid4(),
        call_index=0,
        last_completed_at=None,
        started_at=datetime.now(timezone.utc),
        origin="explicit",
        ended=False,
    )
    mgr = _StubTurnManager(state)
    ctx = _StubFastMCPContext(session_id="relay-session")
    headers = {
        "traceparent": "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
        "x-openai-session": "provider-token-1",
    }

    resolved = await relay_turns_mod.resolve_relay_turn_state(
        ctx,
        pool=object(),
        turn_gap_seconds=12,
        max_turn_seconds=34,
        origin_hint="explicit",
        prefer_bound_state=False,
        headers=headers,
        mgr=mgr,
    )

    assert resolved is state
    assert mgr.calls == [{
        "trace_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "context_id": "relay-session",
        "provider_continuity_token": "provider-token-1",
        "client_info": None,
        "turn_gap_seconds": 12,
        "max_turn_seconds": 34,
        "origin_hint": "explicit",
    }]


@pytest.mark.asyncio
async def test_apply_runtime_sampling_overrides_swaps_owned_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = _NoopSamplingHandler()
    replacement = _NoopSamplingHandler()
    dynamic = sampling_mod.DynamicSamplingHandler(initial)

    def _build_from_runtime(_overrides, *, sampling):
        assert isinstance(sampling, SamplingSettings)
        return replacement

    monkeypatch.setattr(sampling_runtime_mod, "build_handler_from_runtime_overrides", _build_from_runtime)

    applied = await sampling_mod.apply_runtime_sampling_overrides(
        dynamic,
        {"active_provider": "openai", "active_model": "gpt-5"},
        sampling=SamplingSettings(),
    )

    assert applied is True
    assert dynamic.current_handler is replacement


@pytest.mark.asyncio
async def test_lifespan_uses_injected_runtime_sampling_applier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_pool = object()
    seen: dict[str, object] = {}
    injected_settings = SimpleNamespace(database=object(), relay=object())

    class _StubGoodMemConfig:
        @classmethod
        def from_env(cls):
            return cls()

    class _StubGoodMemClient:
        def __init__(self, _config):
            pass

        async def initialize(self):
            return None

    async def _create_pool(database, relay):
        assert database is injected_settings.database
        assert relay is None
        return created_pool

    async def _close_pool(pool):
        seen["closed_pool"] = pool

    async def _load_runtime_config(pool, key):
        assert pool is created_pool
        assert key == "sampling"
        return {"active_provider": "openai", "active_model": "gpt-5"}

    async def _apply_runtime_sampling(overrides):
        seen["runtime_sampling"] = dict(overrides)
        return True

    monkeypatch.setattr(lifespan_mod, "GoodMemConfig", _StubGoodMemConfig)
    monkeypatch.setattr(lifespan_mod, "GoodMemClient", _StubGoodMemClient)
    monkeypatch.setattr(lifespan_mod, "create_pool", _create_pool)
    monkeypatch.setattr(lifespan_mod, "close_pool", _close_pool)

    from quran_mcp.lib.config import profiles as profiles_mod
    from quran_mcp.lib.config import settings as settings_mod
    from quran_mcp.lib.db import runtime_config as runtime_config_mod
    from quran_mcp.lib.db import turn_manager as turn_manager_mod

    def _reset_turn_manager(owner):
        owner.turn_manager = object()

    monkeypatch.setattr(turn_manager_mod, "reset_turn_manager", _reset_turn_manager)
    monkeypatch.setattr(
        settings_mod,
        "get_settings",
        lambda: (_ for _ in ()).throw(
            AssertionError("lifespan should not re-read global settings when injected")
        ),
    )
    def _resolve_relay_enabled(settings):
        assert settings is injected_settings
        return False

    monkeypatch.setattr(profiles_mod, "resolve_relay_enabled", _resolve_relay_enabled)
    monkeypatch.setattr(runtime_config_mod, "load_runtime_config", _load_runtime_config)

    lifespan = lifespan_mod.build_lifespan_context_manager(
        settings=injected_settings,
        apply_runtime_sampling_overrides=_apply_runtime_sampling,
    )

    async with lifespan(object()) as app_ctx:
        assert app_ctx.db_pool is created_pool
        assert app_ctx.turn_manager is not None
        assert app_ctx.relay_runtime_state is not None
        assert app_ctx.settings is injected_settings

    assert seen["runtime_sampling"] == {"active_provider": "openai", "active_model": "gpt-5"}
    assert seen["closed_pool"] is created_pool


@pytest.mark.asyncio
async def test_lifespan_uses_lib_relay_runtime_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _drain_pending(_owner):
        calls.append(f"drain:{_owner.__class__.__name__}")

    def _reset_relay_runtime_state(_owner):
        calls.append(f"reset:{_owner.__class__.__name__}")
        _owner.relay_runtime_state = object()

    class _StubGoodMemConfig:
        @classmethod
        def from_env(cls):
            return cls()

    class _StubGoodMemClient:
        def __init__(self, _config):
            pass

        async def initialize(self):
            return None

    async def _create_pool(_database, _relay):
        return object()

    async def _close_pool(_pool):
        return None

    monkeypatch.setattr(lifespan_mod, "GoodMemConfig", _StubGoodMemConfig)
    monkeypatch.setattr(lifespan_mod, "GoodMemClient", _StubGoodMemClient)
    monkeypatch.setattr(lifespan_mod, "create_pool", _create_pool)
    monkeypatch.setattr(lifespan_mod, "close_pool", _close_pool)

    from quran_mcp.lib.config import profiles as profiles_mod
    from quran_mcp.lib.config import settings as settings_mod
    from quran_mcp.lib.db import turn_manager as turn_manager_mod
    from quran_mcp.lib.relay import runtime as relay_runtime_mod2

    def _reset_turn_manager(owner):
        owner.turn_manager = object()

    monkeypatch.setattr(turn_manager_mod, "reset_turn_manager", _reset_turn_manager)
    monkeypatch.setattr(
        settings_mod,
        "get_settings",
        lambda: SimpleNamespace(database=object(), relay=object()),
    )
    monkeypatch.setattr(profiles_mod, "resolve_relay_enabled", lambda _settings: True)
    monkeypatch.setattr(relay_runtime_mod2, "reset_relay_runtime_state", _reset_relay_runtime_state)
    monkeypatch.setattr(relay_runtime_mod2, "drain_pending", _drain_pending)

    lifespan = lifespan_mod.build_lifespan_context_manager()
    async with lifespan(object()) as app_ctx:
        assert app_ctx.db_pool is not None
        assert app_ctx.turn_manager is not None
        assert app_ctx.relay_runtime_state is not None

    assert calls == ["reset:AppContext", "drain:AppContext"]
