"""GoodMem SDK client construction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from goodmem_client import (
    ApiClient,
    Configuration,
    EmbeddersApi,
    MemoriesApi,
    RerankersApi,
    SpacesApi,
)
from goodmem_client.streaming import MemoryStreamClient

if TYPE_CHECKING:
    from quran_mcp.lib.goodmem.client import GoodMemConfig


@dataclass(slots=True)
class GoodMemSDKClients:
    """Constructed GoodMem SDK clients."""

    spaces_api: SpacesApi
    memories_api: MemoriesApi
    rerankers_api: RerankersApi
    embedders_api: EmbeddersApi
    stream_client: MemoryStreamClient


__all__ = ["GoodMemSDKClients", "build_sdk_clients"]


def build_sdk_clients(config: GoodMemConfig) -> GoodMemSDKClients:
    """Build all SDK clients from a GoodMem configuration."""
    sdk_config = Configuration(
        host=config.api_host,
        api_key={"ApiKeyAuth": config.api_key},
    )
    api_client = ApiClient(configuration=sdk_config)
    return GoodMemSDKClients(
        spaces_api=SpacesApi(api_client),
        memories_api=MemoriesApi(api_client),
        rerankers_api=RerankersApi(api_client),
        embedders_api=EmbeddersApi(api_client),
        stream_client=MemoryStreamClient(api_client),
    )
