from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from quran_mcp.lib.config.settings import Settings
from quran_mcp.middleware.stack import create_middleware_stack

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _settings(
    *,
    bucket_size: int,
    refill_seconds: float,
    daily_per_client: int,
    daily_global: int,
    health_token: str,
) -> Settings:
    return Settings(
        logging={"debug": False, "log_level": "normal", "format": "pretty"},
        rate_limit={
            "enabled": True,
            "metered_tools": ["metered_tool"],
            "bucket_size": bucket_size,
            "refill_seconds": refill_seconds,
            "daily_per_client": daily_per_client,
            "daily_global": daily_global,
        },
        relay={
            "enabled": False,
            "turn_gap_seconds": 12,
            "max_turn_minutes": 5,
        },
        health={"token": health_token},
        grounding={"authority_a_enabled": False},
    )


def _server(
    *,
    bucket_size: int,
    refill_seconds: float,
    daily_per_client: int,
    daily_global: int,
    health_token: str,
) -> FastMCP:
    server = FastMCP(
        "rate-limit-e2e",
        middleware=create_middleware_stack(
            _settings(
                bucket_size=bucket_size,
                refill_seconds=refill_seconds,
                daily_per_client=daily_per_client,
                daily_global=daily_global,
                health_token=health_token,
            ),
            relay_enabled=False,
        ),
    )

    @server.tool
    async def metered_tool() -> str:
        return "ok"

    return server


@asynccontextmanager
async def _client(
    server: FastMCP,
    *,
    headers: dict[str, str] | None = None,
) -> AsyncIterator[Client]:
    app = server.http_app()

    def _httpx_client_factory(
        *,
        headers: dict[str, str] | None,
        auth: httpx.Auth | str | None,
        follow_redirects: bool,
        timeout: httpx.Timeout | None = None,
        **_: object,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers=headers,
            auth=auth,
            follow_redirects=follow_redirects,
            timeout=timeout,
        )

    transport = StreamableHttpTransport(
        "http://testserver/mcp",
        headers=headers,
        httpx_client_factory=_httpx_client_factory,
    )
    async with app.lifespan(app):
        async with Client(transport) as client:
            yield client


async def test_rate_limit_throttles_repeated_tool_calls_at_request_boundary() -> None:
    server = _server(
        bucket_size=1,
        refill_seconds=9999,
        daily_per_client=100,
        daily_global=100,
        health_token="health-secret",
    )

    async with _client(server, headers={"x-openai-session": "sess-throttle"}) as client:
        first = await client.call_tool("metered_tool", {})
        assert first.content[0].text == "ok"

        with pytest.raises(ToolError, match="Rate limited"):
            await client.call_tool("metered_tool", {})


async def test_rate_limit_rejects_after_daily_cap_at_request_boundary() -> None:
    server = _server(
        bucket_size=10,
        refill_seconds=1,
        daily_per_client=1,
        daily_global=100,
        health_token="health-secret",
    )

    async with _client(server, headers={"x-openai-session": "sess-daily"}) as client:
        first = await client.call_tool("metered_tool", {})
        assert first.content[0].text == "ok"

        with pytest.raises(ToolError, match="Client daily limit"):
            await client.call_tool("metered_tool", {})


async def test_rate_limit_health_token_bypasses_real_request_limits() -> None:
    server = _server(
        bucket_size=1,
        refill_seconds=9999,
        daily_per_client=1,
        daily_global=1,
        health_token="health-secret",
    )

    identity_headers = {"x-openai-session": "sess-health"}
    async with _client(server, headers=identity_headers) as normal_client:
        first = await normal_client.call_tool("metered_tool", {})
        assert first.content[0].text == "ok"

    health_headers = {
        "x-openai-session": "sess-health",
        "x-health-token": "health-secret",
    }
    async with _client(server, headers=health_headers) as health_client:
        bypass = await health_client.call_tool("metered_tool", {})
        assert bypass.content[0].text == "ok"
