"""Shared fixtures for integration tests.

A single Client(mcp) session is shared across the entire integration test
suite. This prevents the server lifespan from tearing down the DB pool
between test files.
"""

import pytest_asyncio
from fastmcp import Client

from quran_mcp.server import get_or_create_mcp


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def mcp_client():
    async with Client(get_or_create_mcp()) as client:
        yield client
