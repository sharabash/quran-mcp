"""Tests for quran_mcp.lib.goodmem — client helpers and bootstrap seams.

These tests cover the pure/testable helpers on the client class plus the
bootstrap path that wires and initializes the SDK-backed adapter.

Covers:
  - normalize_sdk_content: str/bytes/tuple/None/base64 normalization
  - with_retry: async retry decorator behavior
  - _ensure_initialized: guard check
"""

from __future__ import annotations

import inspect
import logging
from types import SimpleNamespace
from typing import Any, cast, get_type_hints

import pytest
from goodmem_client.exceptions import ApiException
from pydantic import SecretStr

from quran_mcp.lib.goodmem import GoodMemClient, with_retry
import quran_mcp.lib.goodmem.sdk as goodmem_sdk
from quran_mcp.lib.goodmem.streaming import normalize_sdk_content, stream_search_memories


# ---------------------------------------------------------------------------
# normalize_sdk_content — free function in streaming module
# ---------------------------------------------------------------------------


class TestNormalizeSdkContent:
    def test_none_returns_empty(self):
        assert normalize_sdk_content(None) == ""

    def test_plain_string(self):
        assert normalize_sdk_content("hello world") == "hello world"

    def test_bytes(self):
        assert normalize_sdk_content(b"hello") == "hello"

    def test_tuple_extracts_second_element(self):
        result = normalize_sdk_content(("filename", b"content", "mime"))
        assert result == "content"

    def test_base64_string_decoded(self):
        import base64
        encoded = base64.b64encode(b"Test content").decode()
        result = normalize_sdk_content(encoded)
        assert result == "Test content"

    def test_non_base64_string_returned_as_is(self):
        # Strings that aren't valid base64 should pass through
        result = normalize_sdk_content("not base64 at all!!!")
        assert result == "not base64 at all!!!"


# ---------------------------------------------------------------------------
# with_retry — async decorator
# ---------------------------------------------------------------------------


class TestWithRetry:
    def test_preserves_async_callable_shape(self):
        @with_retry(max_attempts=3)
        async def sample(a: int, b: str = "x") -> str:
            return f"{a}:{b}"

        assert inspect.iscoroutinefunction(sample)
        assert tuple(inspect.signature(sample).parameters) == ("a", "b")
        assert inspect.signature(sample).parameters["b"].default == "x"

    async def test_success_on_first_try(self):
        call_count = 0

        @with_retry(max_attempts=3)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    async def test_retries_on_transient_error(self):
        call_count = 0

        @with_retry(max_attempts=3, initial_delay=0.01)
        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "ok"

        result = await fail_then_succeed()
        assert result == "ok"
        assert call_count == 3

    async def test_no_retry_on_value_error(self):
        call_count = 0

        @with_retry(max_attempts=3, initial_delay=0.01)
        async def fail_with_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            await fail_with_value_error()
        assert call_count == 1  # no retry

    async def test_no_retry_on_4xx_api_exception(self):
        call_count = 0

        @with_retry(max_attempts=3, initial_delay=0.01)
        async def fail_with_client_error():
            nonlocal call_count
            call_count += 1
            raise ApiException(status=400, reason="Bad Request")

        with pytest.raises(ApiException):
            await fail_with_client_error()
        assert call_count == 1  # no retry on 4xx

    async def test_max_attempts_exhausted(self):
        call_count = 0

        @with_retry(max_attempts=2, initial_delay=0.01)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise OSError("persistent failure")

        with pytest.raises(OSError, match="persistent failure"):
            await always_fail()
        assert call_count == 2

    async def test_no_retry_on_programming_error(self):
        call_count = 0

        @with_retry(max_attempts=3, initial_delay=0.01)
        async def fail_with_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("bad program state")

        with pytest.raises(TypeError, match="bad program state"):
            await fail_with_type_error()
        assert call_count == 1


# ---------------------------------------------------------------------------
# _ensure_initialized
# ---------------------------------------------------------------------------


class TestEnsureInitialized:
    def test_raises_when_not_initialized(self):
        from quran_mcp.lib.goodmem import GoodMemConfig

        config = GoodMemConfig(api_key="test", api_host="http://localhost:9999")
        client = GoodMemClient(config)
        # _initialized is False by default
        with pytest.raises(RuntimeError, match="initialize"):
            client._ensure_initialized()


class TestGoodMemConfig:
    def test_from_env_copies_reranker(self, monkeypatch: pytest.MonkeyPatch):
        from quran_mcp.lib.goodmem import GoodMemConfig

        stub_settings = SimpleNamespace(
            goodmem=SimpleNamespace(
                api_key=SecretStr("env-key"),
                api_host="https://example.invalid",
                embedder="embedder-name",
                reranker="reranker-name",
            )
        )

        monkeypatch.setattr(
            "quran_mcp.lib.config.settings.get_settings",
            lambda: stub_settings,
        )

        config = GoodMemConfig.from_env()
        assert config.api_key == "env-key"
        assert config.api_host == "https://example.invalid"
        assert config.embedder == "embedder-name"
        assert config.reranker == "reranker-name"

    def test_default_reranker_id_comes_from_config(self):
        from quran_mcp.lib.goodmem import GoodMemConfig

        config = GoodMemConfig(
            api_key="test",
            api_host="http://localhost:9999",
            reranker="voyage",
        )
        client = GoodMemClient(config)
        client._reranker_name_to_id = {"voyage": "reranker-id"}

        assert client.default_reranker_id == "reranker-id"


class _FakeStreamClient:
    def __init__(self, events):
        self._events = events
        self.calls: list[dict] = []

    def retrieve_memory_stream_chat(self, **kwargs):
        self.calls.append(kwargs)
        yield from self._events


class TestStreamSearchMemories:
    def test_backfills_relevance_scores_when_item_arrives_late(self):
        memory_definition_event = SimpleNamespace(
            retrieved_item=None,
            memory_definition={
                "memoryId": "mem-1",
                "spaceId": "space-1",
                "originalContent": "hello world",
                "metadata": {"k": "v"},
            },
        )
        retrieved_item_event = SimpleNamespace(
            retrieved_item=SimpleNamespace(
                chunk=SimpleNamespace(
                    relevance_score=0.91,
                    chunk={"memoryId": "mem-1"},
                )
            ),
            memory_definition=None,
        )
        stream_client = _FakeStreamClient([memory_definition_event, retrieved_item_event])

        rows = stream_search_memories(
            stream_client=cast(Any, stream_client),
            query="hello",
            space_keys=cast(Any, []),
            limit=5,
            reranker_id=None,
            rerank_threshold=None,
            rerank_max_results=None,
            space_id_to_name={"space-1": "tafsir"},
            logger=logging.getLogger(__name__),
        )

        assert len(rows) == 1
        assert rows[0]["memory_id"] == "mem-1"
        assert rows[0]["relevance_score"] == pytest.approx(0.91)
        assert rows[0]["source_space_name"] == "tafsir"

    def test_deduplicates_memory_definitions(self):
        duplicate_definition_a = SimpleNamespace(
            retrieved_item=None,
            memory_definition={
                "memoryId": "mem-1",
                "spaceId": "space-1",
                "originalContent": "first",
                "metadata": {},
            },
        )
        duplicate_definition_b = SimpleNamespace(
            retrieved_item=None,
            memory_definition={
                "memoryId": "mem-1",
                "spaceId": "space-1",
                "originalContent": "second",
                "metadata": {},
            },
        )
        stream_client = _FakeStreamClient([duplicate_definition_a, duplicate_definition_b])

        rows = stream_search_memories(
            stream_client=cast(Any, stream_client),
            query="hello",
            space_keys=cast(Any, []),
            limit=5,
            reranker_id=None,
            rerank_threshold=None,
            rerank_max_results=None,
            space_id_to_name={},
            logger=logging.getLogger(__name__),
        )

        assert len(rows) == 1
        assert rows[0]["content"] == "first"

    def test_forwards_stream_request_shape(self):
        memory_definition_event = SimpleNamespace(
            retrieved_item=None,
            memory_definition={
                "memoryId": "mem-1",
                "spaceId": "space-1",
                "originalContent": "hello world",
                "metadata": {"k": "v"},
            },
        )
        stream_client = _FakeStreamClient([memory_definition_event])

        rows = stream_search_memories(
            stream_client=cast(Any, stream_client),
            query="mercy",
            space_keys=cast(
                Any,
                [
                SimpleNamespace(
                    space_id="space-1",
                    filter="CAST(val('$.edition_id') AS TEXT) = 'en-ibn-kathir'",
                )
            ],
            ),
            limit=17,
            reranker_id="rerank-1",
            rerank_threshold=0.25,
            rerank_max_results=4,
            space_id_to_name={"space-1": "tafsir"},
            logger=logging.getLogger(__name__),
        )

        assert len(rows) == 1
        assert len(stream_client.calls) == 1
        call = stream_client.calls[0]
        assert call["message"] == "mercy"
        assert call["requested_size"] == 17
        assert call["fetch_memory"] is True
        assert call["fetch_memory_content"] is True
        assert call["pp_reranker_id"] == "rerank-1"
        assert call["pp_relevance_threshold"] == 0.25
        assert call["pp_max_results"] == 4
        assert len(call["space_keys"]) == 1
        assert call["space_keys"][0].space_id == "space-1"
        assert call["space_keys"][0].filter == "CAST(val('$.edition_id') AS TEXT) = 'en-ibn-kathir'"


class TestGoodMemSdkWiring:
    def test_goodmem_facade_reexports_support_modules(self):
        import quran_mcp.lib.goodmem as goodmem

        assert "GoodMemSDKClients" in goodmem.__all__
        assert "build_sdk_clients" in goodmem.__all__
        assert "normalize_sdk_content" in goodmem.__all__
        assert "stream_search_memories" in goodmem.__all__
        assert "_cast_clause" not in goodmem.__all__
        assert "_format_literal" not in goodmem.__all__
        assert "_infer_value_type" not in goodmem.__all__

    def test_sdk_client_annotations_are_concrete(self):
        hints = get_type_hints(goodmem_sdk.GoodMemSDKClients)

        assert hints["spaces_api"] is goodmem_sdk.SpacesApi
        assert hints["memories_api"] is goodmem_sdk.MemoriesApi
        assert hints["rerankers_api"] is goodmem_sdk.RerankersApi
        assert hints["embedders_api"] is goodmem_sdk.EmbeddersApi
        assert hints["stream_client"] is goodmem_sdk.MemoryStreamClient

    def test_build_sdk_clients_uses_one_api_client(self, monkeypatch: pytest.MonkeyPatch):
        created: dict[str, object] = {}

        class _FakeConfiguration:
            def __init__(self, *, host: str, api_key: dict[str, str]):
                self.host = host
                self.api_key = api_key

        class _FakeApiClient:
            def __init__(self, *, configuration):
                self.configuration = configuration

        def _wrap(name: str):
            def _ctor(api_client):
                created[name] = api_client
                return SimpleNamespace(name=name, api_client=api_client)

            return _ctor

        monkeypatch.setattr(goodmem_sdk, "Configuration", _FakeConfiguration)
        monkeypatch.setattr(goodmem_sdk, "ApiClient", _FakeApiClient)
        monkeypatch.setattr(goodmem_sdk, "SpacesApi", _wrap("spaces"))
        monkeypatch.setattr(goodmem_sdk, "MemoriesApi", _wrap("memories"))
        monkeypatch.setattr(goodmem_sdk, "RerankersApi", _wrap("rerankers"))
        monkeypatch.setattr(goodmem_sdk, "EmbeddersApi", _wrap("embedders"))
        monkeypatch.setattr(goodmem_sdk, "MemoryStreamClient", _wrap("stream"))

        from quran_mcp.lib.goodmem import GoodMemConfig

        clients = goodmem_sdk.build_sdk_clients(
            GoodMemConfig(
                api_key="secret-key",
                api_host="https://goodmem.invalid",
                embedder="embedder-a",
                reranker="reranker-b",
            )
        )

        assert clients.spaces_api.api_client is clients.memories_api.api_client
        assert clients.memories_api.api_client is clients.rerankers_api.api_client
        assert clients.rerankers_api.api_client is clients.embedders_api.api_client
        assert clients.embedders_api.api_client is clients.stream_client.api_client
        assert created["spaces"] is clients.spaces_api.api_client
        assert clients.spaces_api.api_client.configuration.host == "https://goodmem.invalid"
        assert clients.spaces_api.api_client.configuration.api_key == {
            "ApiKeyAuth": "secret-key"
        }


class TestGoodMemClientAdapter:
    def test_constructor_wires_concrete_sdk_clients(self, monkeypatch: pytest.MonkeyPatch):
        sentinels = SimpleNamespace(
            spaces=SimpleNamespace(name="spaces"),
            memories=SimpleNamespace(name="memories"),
            rerankers=SimpleNamespace(name="rerankers"),
            embedders=SimpleNamespace(name="embedders"),
            stream=SimpleNamespace(name="stream"),
        )

        def _fake_build_sdk_clients(_config):
            return SimpleNamespace(
                spaces_api=sentinels.spaces,
                memories_api=sentinels.memories,
                rerankers_api=sentinels.rerankers,
                embedders_api=sentinels.embedders,
                stream_client=sentinels.stream,
            )

        monkeypatch.setattr("quran_mcp.lib.goodmem.client.build_sdk_clients", _fake_build_sdk_clients)

        from quran_mcp.lib.goodmem import GoodMemConfig

        client = GoodMemClient(
            GoodMemConfig(api_key="key", api_host="https://goodmem.invalid")
        )

        assert client.spaces_api is sentinels.spaces
        assert client.memories_api is sentinels.memories
        assert client.rerankers_api is sentinels.rerankers
        assert client.embedders_api is sentinels.embedders
        assert client.stream_client is sentinels.stream


class TestGoodMemClientBootstrap:
    @pytest.mark.asyncio
    async def test_initialize_discovers_spaces_and_optional_lookups(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        space_pages = [
            SimpleNamespace(
                spaces=[
                    SimpleNamespace(space_id="space-1", name="tafsir"),
                ],
                next_token="page-2",
            ),
            SimpleNamespace(
                spaces=[
                    SimpleNamespace(space_id="space-2", name="translation"),
                ],
                next_token=None,
            ),
        ]
        spaces_calls: list[tuple[int, str | None]] = []

        def _list_spaces(*, max_results: int, next_token: str | None):
            spaces_calls.append((max_results, next_token))
            return space_pages[len(spaces_calls) - 1]

        def _list_rerankers():
            return SimpleNamespace(
                rerankers=[
                    SimpleNamespace(display_name="voyage", reranker_id="reranker-1"),
                ]
            )

        def _list_embedders():
            return SimpleNamespace(
                embedders=[
                    SimpleNamespace(display_name="embedder-a", embedder_id="embedder-1"),
                ]
            )

        sdk_clients = SimpleNamespace(
            spaces_api=SimpleNamespace(list_spaces=_list_spaces),
            memories_api=SimpleNamespace(),
            rerankers_api=SimpleNamespace(list_rerankers=_list_rerankers),
            embedders_api=SimpleNamespace(list_embedders=_list_embedders),
            stream_client=SimpleNamespace(),
        )
        monkeypatch.setattr("quran_mcp.lib.goodmem.client.build_sdk_clients", lambda _config: sdk_clients)

        from quran_mcp.lib.goodmem import GoodMemConfig

        client = GoodMemClient(
            GoodMemConfig(
                api_key="key",
                api_host="https://goodmem.invalid",
                embedder="embedder-a",
                reranker="voyage",
            )
        )

        await client.initialize()

        assert client._initialized is True
        assert client._space_name_to_id == {
            "tafsir": "space-1",
            "translation": "space-2",
        }
        assert client._space_id_to_name == {
            "space-1": "tafsir",
            "space-2": "translation",
        }
        assert client._reranker_name_to_id == {"voyage": "reranker-1"}
        assert client._embedder_name_to_id == {"embedder-a": "embedder-1"}
        assert client.default_reranker_id == "reranker-1"
        assert client.default_embedder_id == "embedder-1"
        assert spaces_calls == [(100, None), (100, "page-2")]

    @pytest.mark.asyncio
    async def test_initialize_fails_fast_when_space_discovery_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        rerankers_called = False
        embedders_called = False

        def _list_spaces(*, max_results: int, next_token: str | None):
            raise ApiException(status=503, reason="Service Unavailable")

        def _list_rerankers():
            nonlocal rerankers_called
            rerankers_called = True
            return SimpleNamespace(rerankers=[])

        def _list_embedders():
            nonlocal embedders_called
            embedders_called = True
            return SimpleNamespace(embedders=[])

        sdk_clients = SimpleNamespace(
            spaces_api=SimpleNamespace(list_spaces=_list_spaces),
            memories_api=SimpleNamespace(),
            rerankers_api=SimpleNamespace(list_rerankers=_list_rerankers),
            embedders_api=SimpleNamespace(list_embedders=_list_embedders),
            stream_client=SimpleNamespace(),
        )
        monkeypatch.setattr("quran_mcp.lib.goodmem.client.build_sdk_clients", lambda _config: sdk_clients)

        from quran_mcp.lib.goodmem import GoodMemConfig

        client = GoodMemClient(
            GoodMemConfig(api_key="key", api_host="https://goodmem.invalid")
        )

        with pytest.raises(RuntimeError, match="Failed to discover GoodMem spaces"):
            await client.initialize()

        assert client._initialized is False
        assert client._space_name_to_id == {}
        assert client._space_id_to_name == {}
        assert client._reranker_name_to_id == {}
        assert client._embedder_name_to_id == {}
        assert rerankers_called is False
        assert embedders_called is False

    @pytest.mark.asyncio
    async def test_create_memory_shapes_sdk_request(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        captured: dict[str, Any] = {}

        def _fake_build_sdk_clients(_config):
            def _create_memory(*, memory_creation_request):
                captured["request"] = memory_creation_request
                return SimpleNamespace(
                    memory_id="mem-9",
                    space_id=memory_creation_request.space_id,
                )

            return SimpleNamespace(
                spaces_api=SimpleNamespace(),
                memories_api=SimpleNamespace(create_memory=_create_memory),
                rerankers_api=SimpleNamespace(),
                embedders_api=SimpleNamespace(),
                stream_client=SimpleNamespace(),
            )

        monkeypatch.setattr("quran_mcp.lib.goodmem.client.build_sdk_clients", _fake_build_sdk_clients)

        from quran_mcp.lib.goodmem import GoodMemConfig

        client = GoodMemClient(
            GoodMemConfig(api_key="key", api_host="https://goodmem.invalid")
        )
        client._initialized = True
        client._space_name_to_id = {"tafsir": "space-1"}
        client._space_id_to_name = {"space-1": "tafsir"}

        result = await client.create_memory(
            content="commentary",
            metadata={"ayah_key": "2:255"},
            space_name="tafsir",
        )

        assert result.memory_id == "mem-9"
        assert result.space_id == "space-1"
        request = captured["request"]
        assert request.space_id == "space-1"
        assert request.content_type == "text/plain"
        assert request.original_content == "commentary"
        assert request.metadata == {"ayah_key": "2:255"}

    @pytest.mark.asyncio
    async def test_search_memories_shapes_stream_request_and_normalizes_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        captured: dict[str, Any] = {}

        def _fake_build_sdk_clients(_config):
            return SimpleNamespace(
                spaces_api=SimpleNamespace(),
                memories_api=SimpleNamespace(),
                rerankers_api=SimpleNamespace(),
                embedders_api=SimpleNamespace(),
                stream_client=SimpleNamespace(),
            )

        def _fake_stream_search_memories(**kwargs):
            captured.update(kwargs)
            return [
                {
                    "content": "normalized tafsir",
                    "metadata": {"ayah_key": "2:255"},
                    "memory_id": "mem-1",
                    "space_id": "space-1",
                    "relevance_score": 0.91,
                    "source_space_name": "tafsir",
                }
            ]

        monkeypatch.setattr("quran_mcp.lib.goodmem.client.build_sdk_clients", _fake_build_sdk_clients)
        monkeypatch.setattr("quran_mcp.lib.goodmem.client.stream_search_memories", _fake_stream_search_memories)

        from quran_mcp.lib.goodmem import GoodMemConfig

        client = GoodMemClient(
            GoodMemConfig(api_key="key", api_host="https://goodmem.invalid")
        )
        client._initialized = True
        client._space_name_to_id = {"tafsir": "space-1"}
        client._space_id_to_name = {"space-1": "tafsir"}

        result = await client.search_memories(
            query="throne verse",
            space_names=["tafsir"],
            limit=7,
            filter_expr="CAST(val('$.edition_id') AS TEXT) = 'en-ibn-kathir'",
            reranker_id="rerank-1",
            rerank_threshold=0.25,
            rerank_max_results=4,
        )

        assert len(result) == 1
        assert result[0].memory_id == "mem-1"
        assert result[0].source_space_name == "tafsir"
        assert captured["query"] == "throne verse"
        assert captured["limit"] == 7
        assert captured["reranker_id"] == "rerank-1"
        assert captured["rerank_threshold"] == 0.25
        assert captured["rerank_max_results"] == 4
        assert captured["space_id_to_name"] == {"space-1": "tafsir"}
        assert len(captured["space_keys"]) == 1
        space_key = captured["space_keys"][0]
        assert space_key.space_id == "space-1"
        assert space_key.filter == "CAST(val('$.edition_id') AS TEXT) = 'en-ibn-kathir'"

    @pytest.mark.asyncio
    async def test_get_by_domain_id_propagates_search_failures(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        def _fake_build_sdk_clients(_config):
            return SimpleNamespace(
                spaces_api=SimpleNamespace(),
                memories_api=SimpleNamespace(),
                rerankers_api=SimpleNamespace(),
                embedders_api=SimpleNamespace(),
                stream_client=SimpleNamespace(),
            )

        async def _fake_search_memories(**_kwargs):
            raise RuntimeError("search failed")

        monkeypatch.setattr("quran_mcp.lib.goodmem.client.build_sdk_clients", _fake_build_sdk_clients)

        from quran_mcp.lib.goodmem import GoodMemConfig

        client = GoodMemClient(
            GoodMemConfig(api_key="key", api_host="https://goodmem.invalid")
        )
        client._initialized = True
        monkeypatch.setattr(client, "search_memories", _fake_search_memories)

        with pytest.raises(RuntimeError, match="search failed"):
            await client.get_by_domain_id(
                space_name="tafsir",
                metadata_filters={"ayah_key": "2:255"},
            )
