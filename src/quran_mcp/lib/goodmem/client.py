"""GoodMem client adapter: space-aware async CRUD and semantic search."""

from __future__ import annotations

import asyncio
import functools
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar

import anyio
from goodmem_client import (
    MemoryCreationRequest,
    EmbeddersApi,
    MemoriesApi,
    RerankersApi,
    SpaceCreationRequest,
    SpacesApi,
)
from goodmem_client.exceptions import ApiException
from goodmem_client.models import Space, SpaceEmbedderConfig, SpaceKey
from goodmem_client.streaming import MemoryStreamClient
from pydantic import BaseModel, Field
from quran_mcp.lib.goodmem.filters import (
    build_metadata_filter_expression,
)
from quran_mcp.lib.goodmem.sdk import GoodMemSDKClients, build_sdk_clients
from quran_mcp.lib.goodmem.streaming import normalize_sdk_content, stream_search_memories

logger = logging.getLogger(__name__)


__all__ = [
    "GoodMemConfig",
    "GoodMemMemory",
    "GoodMemClient",
    "with_retry",
]


def _log_goodmem_operation(
    operation: str,
    *,
    spaces: list[str] | None = None,
    space_ids: list[str] | None = None,
    limit: int | None = None,
    query: str | None = None,
    filter_expr: str | None = None,
    reranker_id: str | None = None,
) -> None:
    """Log a GoodMem operation."""
    parts = [f"GoodMem {operation}: spaces={spaces} -> IDs={space_ids}, limit={limit}"]
    if query:
        parts.append(f"query={query[:80]}{'...' if len(query) > 80 else ''}")
    if filter_expr:
        parts.append(f"filter={filter_expr}")
    if reranker_id:
        parts.append(f"reranker={reranker_id[:12]}...")
    logger.info(", ".join(parts))


P = ParamSpec("P")
T = TypeVar("T")


def with_retry(
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Retry with exponential backoff; skips retries for ValueError and 4xx ApiException."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except ValueError:
                    logger.debug(f"{func.__name__} failed with ValueError, not retrying")
                    raise
                except ApiException as e:
                    if 400 <= e.status < 500:
                        logger.debug(f"{func.__name__} failed with client error {e.status}, not retrying")
                        raise
                    last_exception = e
                except OSError as e:
                    last_exception = e

                # Transient failure — retry with backoff
                if attempt == max_attempts:
                    break
                logger.warning(
                    f"{func.__name__} failed (attempt {attempt}/{max_attempts}): "
                    f"{last_exception}. Retrying in {delay:.2f}s..."
                )
                await anyio.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)

            # All retries exhausted
            logger.error(
                f"{func.__name__} failed after {max_attempts} attempts: {last_exception}"
            )
            raise last_exception

        return wrapper

    return decorator


@dataclass
class GoodMemConfig:
    """Configuration for GoodMem client."""

    api_key: str
    api_host: str = "https://localhost:8080"
    embedder: str = ""
    reranker: str = ""

    @classmethod
    def from_env(cls) -> "GoodMemConfig":
        """Load configuration from centralized Settings system."""
        from quran_mcp.lib.config.settings import get_settings

        gm = get_settings().goodmem

        return cls(
            api_key=gm.api_key.get_secret_value(),
            api_host=gm.api_host,
            embedder=gm.embedder or "",
            reranker=gm.reranker or "",
        )


class GoodMemMemory(BaseModel):
    """A GoodMem memory with content, metadata, and optional retrieval scores."""

    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    memory_id: str | None = None
    space_id: str | None = None
    relevance_score: float | None = Field(
        default=None,
        description="Relevance score from GoodMem retrieval (higher = more relevant)"
    )
    source_space_name: str | None = Field(
        default=None,
        description="Human-readable space name (resolved from space_id)"
    )


class GoodMemClient:
    """Async client for GoodMem semantic memory operations.

    All public APIs use space names (not UUIDs). Blocking SDK calls are
    offloaded to threads via anyio.to_thread.
    """

    def __init__(self, config: GoodMemConfig):
        """Initialize client. Call ``await client.initialize()`` before use."""
        self.config = config
        self._space_name_to_id: dict[str, str] = {}
        self._space_id_to_name: dict[str, str] = {}
        self._reranker_name_to_id: dict[str, str] = {}
        self._embedder_name_to_id: dict[str, str] = {}
        self._initialized: bool = False
        self._space_creation_lock = asyncio.Lock()

        # SDK clients are constructed eagerly and never optional after init.
        self.spaces_api: SpacesApi
        self.memories_api: MemoriesApi
        self.rerankers_api: RerankersApi
        self.embedders_api: EmbeddersApi
        self.stream_client: MemoryStreamClient

        sdk_clients: GoodMemSDKClients = build_sdk_clients(config)
        self.spaces_api = sdk_clients.spaces_api
        self.memories_api = sdk_clients.memories_api
        self.rerankers_api = sdk_clients.rerankers_api
        self.embedders_api = sdk_clients.embedders_api
        self.stream_client = sdk_clients.stream_client

        logger.info(
            f"GoodMem client initialized (host={config.api_host})"
        )

    async def initialize(self) -> None:
        """Discover spaces, rerankers, and embedders. Fail-fast on space discovery errors."""
        await self._discover_spaces()
        await self._discover_rerankers()
        await self._discover_embedders()
        self._initialized = True
        logger.info(
            f"GoodMem client ready "
            f"({len(self._space_name_to_id)} spaces, "
            f"{len(self._reranker_name_to_id)} rerankers discovered)"
        )

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError(
                "GoodMemClient.initialize() must be called before using the client. "
                "Call 'await client.initialize()' after construction."
            )

    @with_retry(max_attempts=3, initial_delay=0.5)
    async def _discover_spaces(self) -> None:
        """Discover all spaces and populate bidirectional lookup dicts."""
        try:
            def _list_spaces_sync() -> list[Space]:
                all_spaces = []
                next_token = None

                while True:
                    response = self.spaces_api.list_spaces(
                        max_results=100,
                        next_token=next_token,
                    )

                    spaces = response.spaces if response.spaces else []
                    all_spaces.extend(spaces)

                    next_token = response.next_token
                    if not next_token:
                        break

                return all_spaces

            spaces = await anyio.to_thread.run_sync(_list_spaces_sync)

            for space in spaces:
                space_id = space.space_id
                space_name = space.name

                self._space_name_to_id[space_name] = space_id
                self._space_id_to_name[space_id] = space_name

            logger.debug(f"Discovered {len(spaces)} spaces: {list(self._space_name_to_id.keys())}")

        except Exception as e:
            # Fail-fast: Raise exception to prevent client from operating with broken state
            raise RuntimeError(
                f"Failed to discover GoodMem spaces: {e}. "
                "Client cannot operate without space discovery."
            ) from e

    async def _discover_rerankers(self) -> None:
        """Discover rerankers (best-effort, non-fatal on failure)."""
        try:
            def _list_rerankers_sync() -> dict[str, str]:
                response = self.rerankers_api.list_rerankers()
                rerankers = response.rerankers if response.rerankers else []
                return {r.display_name: r.reranker_id for r in rerankers}

            self._reranker_name_to_id = await anyio.to_thread.run_sync(_list_rerankers_sync)
            logger.debug(
                f"Discovered {len(self._reranker_name_to_id)} rerankers: "
                f"{list(self._reranker_name_to_id.keys())}"
            )

        except Exception as e:
            # Intentional: reranking is optional — search works without it
            logger.warning(f"Reranker discovery failed (reranking may be unavailable): {e}")

    async def _discover_embedders(self) -> None:
        """Discover all embedders and populate name→ID lookup."""
        try:
            def _list_embedders_sync() -> dict[str, str]:
                response = self.embedders_api.list_embedders()
                embedders = response.embedders if response.embedders else []
                return {e.display_name: e.embedder_id for e in embedders}

            self._embedder_name_to_id = await anyio.to_thread.run_sync(_list_embedders_sync)
            logger.debug(
                f"Discovered {len(self._embedder_name_to_id)} embedders: "
                f"{list(self._embedder_name_to_id.keys())}"
            )
        except Exception as e:
            # Intentional: embedder discovery failure doesn't block GoodMem init
            logger.warning(f"Embedder discovery failed: {e}")

    @property
    def default_embedder_id(self) -> str | None:
        """Resolve the configured embedder name to its UUID."""
        name = self.config.embedder
        if not name:
            return None
        embedder_id = self._embedder_name_to_id.get(name)
        if not embedder_id:
            logger.warning(
                f"Configured embedder '{name}' not found in discovered embedders: "
                f"{list(self._embedder_name_to_id.keys())}"
            )
        return embedder_id

    @property
    def default_reranker_id(self) -> str | None:
        """Resolve the configured reranker name to its UUID."""
        name = self.config.reranker
        if not name:
            return None
        reranker_id = self._reranker_name_to_id.get(name)
        if not reranker_id:
            logger.warning(
                f"Configured reranker '{name}' not found in discovered rerankers: "
                f"{list(self._reranker_name_to_id.keys())}"
            )
        return reranker_id

    async def _resolve_space_name(
        self, space_name: str, embedder_id: str | None = None
    ) -> str:
        """Resolve space name to ID, creating the space on first encounter."""
        if space_name in self._space_name_to_id:
            return self._space_name_to_id[space_name]

        async with self._space_creation_lock:
            # Double-check: another task may have created it while we waited for the lock
            if space_name in self._space_name_to_id:
                return self._space_name_to_id[space_name]

            return await self._ensure_space_exists_locked(space_name, embedder_id)

    async def _ensure_space_exists_locked(
        self, space_name: str, embedder_id: str | None = None
    ) -> str:
        """Create space if missing. Caller must hold _space_creation_lock."""

        resolved_embedder_id = embedder_id or self.default_embedder_id

        if not resolved_embedder_id:
            raise ValueError(
                f"Space '{space_name}' does not exist and no embedder configured. "
                f"Set goodmem.embedder in config.yml. "
                f"Known spaces: {list(self._space_name_to_id.keys())}"
            )

        logger.info(f"Creating space '{space_name}' with embedder_id={resolved_embedder_id}")

        def _create_space_sync() -> str:
            # Configure chunking for large content (tafsir is ~53KB HTML = 19,315 tokens)
            # Embedder text-embedding-3-small has 8,192 token limit
            # Use RecursiveChunking with 6000 token chunks + 600 token overlap
            from goodmem_client.models.chunking_configuration import ChunkingConfiguration
            from goodmem_client.models.recursive_chunking_configuration import RecursiveChunkingConfiguration
            from goodmem_client.models.separator_keep_strategy import SeparatorKeepStrategy
            from goodmem_client.models.length_measurement import LengthMeasurement

            chunking_config = ChunkingConfiguration(
                recursive=RecursiveChunkingConfiguration(
                    chunk_size=6000,  # Conservative to stay under 8192 token limit
                    chunk_overlap=600,  # 10% overlap for context continuity
                    keep_strategy=SeparatorKeepStrategy.KEEP_END,
                    length_measurement=LengthMeasurement.TOKEN_COUNT,
                )
            )

            request = SpaceCreationRequest(
                name=space_name,
                space_embedders=[
                    SpaceEmbedderConfig(
                        embedder_id=resolved_embedder_id,
                        default_retrieval_weight=1.0,
                    )
                ],
                default_chunking_config=chunking_config,
            )

            response = self.spaces_api.create_space(space_creation_request=request)
            return response.space_id

        try:
            space_id = await anyio.to_thread.run_sync(_create_space_sync)

            self._space_name_to_id[space_name] = space_id
            self._space_id_to_name[space_id] = space_name

            logger.info(f"Created space '{space_name}' with ID {space_id}")
            return space_id

        except ApiException as e:
            # Handle HTTP 409 Conflict (concurrent creation race condition)
            if e.status == 409:
                logger.debug(
                    f"Space '{space_name}' already exists (HTTP 409 Conflict), re-discovering spaces"
                )

                # Re-discover all spaces to get the newly created one
                await self._discover_spaces()

                # Try to resolve again
                if space_name in self._space_name_to_id:
                    return self._space_name_to_id[space_name]
                else:
                    raise RuntimeError(
                        f"Space '{space_name}' conflict detected but not found after re-discovery"
                    ) from e

            raise RuntimeError(
                f"Failed to create space '{space_name}': HTTP {e.status} - {e}"
            ) from e

        except Exception as e:
            raise RuntimeError(
                f"Failed to create space '{space_name}': {e}"
            ) from e

    async def delete_space(self, space_name: str) -> None:
        """Delete a space by name."""
        self._ensure_initialized()

        if space_name not in self._space_name_to_id:
            raise ValueError(
                f"Space '{space_name}' does not exist. "
                f"Known spaces: {list(self._space_name_to_id.keys())}"
            )

        space_id = self._space_name_to_id[space_name]

        logger.info(f"Deleting space '{space_name}' (ID: {space_id})")

        def _delete_space_sync() -> None:
            self.spaces_api.delete_space(id=space_id)

        try:
            await anyio.to_thread.run_sync(_delete_space_sync)

            del self._space_name_to_id[space_name]
            del self._space_id_to_name[space_id]

            logger.info(f"Deleted space '{space_name}'")

        except ApiException as e:
            raise RuntimeError(
                f"Failed to delete space '{space_name}': HTTP {e.status} - {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Failed to delete space '{space_name}': {e}"
            ) from e

    @with_retry(max_attempts=3, initial_delay=0.5)
    async def create_memory(
        self,
        content: str,
        metadata: dict[str, Any],
        space_name: str,
        embedder_id: str | None = None,
    ) -> GoodMemMemory:
        """Create a memory in the named space, auto-creating the space if needed."""
        self._ensure_initialized()

        space_id = await self._resolve_space_name(space_name, embedder_id)

        def _create_memory_sync() -> tuple[str, str]:
            request = MemoryCreationRequest(
                space_id=space_id,
                content_type="text/plain",
                original_content=content,
                metadata=metadata,
            )

            response = self.memories_api.create_memory(memory_creation_request=request)
            return response.memory_id, response.space_id

        try:
            memory_id, space_id = await anyio.to_thread.run_sync(_create_memory_sync)

            logger.debug(f"Created memory {memory_id} in space '{space_name}'")

            return GoodMemMemory(
                content=content,
                metadata=metadata,
                memory_id=memory_id,
                space_id=space_id,
            )

        except Exception as e:
            raise RuntimeError(
                f"Failed to create memory in space '{space_name}': {e}"
            ) from e

    @with_retry(max_attempts=3, initial_delay=1.0)
    async def get_memory(self, memory_id: str) -> GoodMemMemory:
        """Fetch a memory by ID."""
        self._ensure_initialized()

        def _get_memory_sync() -> tuple[str, dict, str]:
            response = self.memories_api.get_memory(id=memory_id, include_content=True)
            content = normalize_sdk_content(response.original_content)
            return content, response.metadata or {}, response.space_id

        try:
            content, metadata, space_id = await anyio.to_thread.run_sync(_get_memory_sync)

            return GoodMemMemory(
                content=content,
                metadata=metadata,
                memory_id=memory_id,
                space_id=space_id,
            )

        except Exception as e:
            raise RuntimeError(f"Failed to fetch memory {memory_id}: {e}") from e

    @with_retry(max_attempts=3, initial_delay=1.0)
    async def update_memory(
        self, memory_id: str, content: str, metadata: dict[str, Any]
    ) -> GoodMemMemory:
        """Delete-then-recreate a memory. Returns a NEW memory_id.

        Not atomic: if create fails after delete, the original is lost.
        """
        self._ensure_initialized()

        try:
            existing = await self.get_memory(memory_id)
            await self.delete_memory(memory_id)

            space_name = self._space_id_to_name.get(existing.space_id)
            if not space_name:
                raise RuntimeError(
                    f"Cannot resolve space_id {existing.space_id} to space_name"
                )

            new_memory = await self.create_memory(
                content=content,
                metadata=metadata,
                space_name=space_name,
            )

            logger.info(
                f"Updated memory {memory_id} → {new_memory.memory_id} "
                f"(new ID due to delete+recreate pattern)"
            )

            return new_memory

        except Exception as e:
            raise RuntimeError(f"Failed to update memory {memory_id}: {e}") from e

    @with_retry(max_attempts=3, initial_delay=1.0)
    async def delete_memory(self, memory_id: str) -> None:
        """Delete a memory by ID."""
        self._ensure_initialized()

        def _delete_memory_sync() -> None:
            self.memories_api.delete_memory(id=memory_id)

        try:
            await anyio.to_thread.run_sync(_delete_memory_sync)
            logger.debug(f"Deleted memory {memory_id}")

        except Exception as e:
            raise RuntimeError(f"Failed to delete memory {memory_id}: {e}") from e

    async def delete_memories_batch(
        self, memory_ids: list[str]
    ) -> tuple[list[str], dict[str, Exception]]:
        """Delete multiple memories, continuing past individual failures."""
        self._ensure_initialized()

        successfully_deleted: list[str] = []
        failed: dict[str, Exception] = {}

        for memory_id in memory_ids:
            try:
                await self.delete_memory(memory_id)
                successfully_deleted.append(memory_id)
            except Exception as e:
                logger.warning(f"Failed to delete memory {memory_id}: {e}")
                failed[memory_id] = e

        logger.info(
            f"Batch delete complete: {len(successfully_deleted)} succeeded, "
            f"{len(failed)} failed"
        )

        return successfully_deleted, failed

    @with_retry(max_attempts=3, initial_delay=0.5)
    async def search_memories(
        self,
        query: str,
        space_names: list[str],
        limit: int = 10,
        filter_expr: str | None = None,
        reranker_id: str | None = None,
        rerank_threshold: float | None = None,
        rerank_max_results: int | None = None,
    ) -> list[GoodMemMemory]:
        """Semantic search across spaces with optional reranking and metadata filtering."""
        self._ensure_initialized()

        space_ids = []
        for space_name in space_names:
            space_id = await self._resolve_space_name(space_name)
            space_ids.append(space_id)

        _log_goodmem_operation(
            "memory_retrieve",
            spaces=space_names,
            space_ids=space_ids,
            limit=limit,
            query=query,
            filter_expr=filter_expr,
            reranker_id=reranker_id,
        )

        def _search_memories_sync() -> list[GoodMemMemory]:
            # Use space_keys (not space_ids) to support per-space filter expressions
            space_keys = [
                SpaceKey(space_id=sid, filter=filter_expr)
                for sid in space_ids
            ]
            rows = stream_search_memories(
                stream_client=self.stream_client,
                query=query,
                space_keys=space_keys,
                limit=limit,
                reranker_id=reranker_id,
                rerank_threshold=rerank_threshold,
                rerank_max_results=rerank_max_results,
                space_id_to_name=self._space_id_to_name,
                logger=logger,
            )
            return [GoodMemMemory(**row) for row in rows]

        try:
            results = await anyio.to_thread.run_sync(_search_memories_sync)
            logger.debug(f"Search returned {len(results)} results")
            return results

        except Exception as e:
            raise RuntimeError(
                f"Failed to search memories in spaces {space_names}: {e}"
            ) from e

    async def get_by_domain_id(
        self, space_name: str, metadata_filters: dict[str, Any]
    ) -> GoodMemMemory | None:
        """Metadata-only lookup for uniqueness checks (TOCTOU — not atomic)."""
        self._ensure_initialized()

        filter_expr = build_metadata_filter_expression(metadata_filters)

        logger.debug(
            f"Looking up memory in '{space_name}' with filters: {metadata_filters}"
        )

        # GoodMem requires a non-empty query; the metadata filters do the real work
        query_placeholder = "content"

        results = await self.search_memories(
            query=query_placeholder,
            space_names=[space_name],
            limit=1,
            filter_expr=filter_expr,
        )

        if results:
            logger.debug(f"Found memory {results[0].memory_id} matching filters")
            return results[0]

        logger.debug("No memory found matching filters")
        return None
