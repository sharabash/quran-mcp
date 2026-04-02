from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from quran_mcp.lib.morphology.voyage_reranker import (
    VOYAGE_RERANK_URL,
    VoyageRerankerError,
    rerank_verses,
)


def _mock_response(status_code: int = 200, json_data: dict | None = None, text: str = ""):
    resp = AsyncMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


@pytest.mark.asyncio
async def test_rerank_call_construction():
    response = _mock_response(json_data={"data": [
        {"index": 0, "relevance_score": 0.9},
        {"index": 1, "relevance_score": 0.5},
    ]})
    mock_client = AsyncMock()
    mock_client.post.return_value = response

    with patch("quran_mcp.lib.morphology.voyage_reranker.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        await rerank_verses("test query", ["doc1", "doc2"], api_key="sk-test")

    mock_client.post.assert_called_once_with(
        VOYAGE_RERANK_URL,
        json={
            "query": "test query",
            "documents": ["doc1", "doc2"],
            "model": "rerank-2",
        },
        headers={
            "Authorization": "Bearer sk-test",
            "Content-Type": "application/json",
        },
    )


@pytest.mark.asyncio
async def test_custom_model():
    response = _mock_response(json_data={"data": []})
    mock_client = AsyncMock()
    mock_client.post.return_value = response

    with patch("quran_mcp.lib.morphology.voyage_reranker.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        await rerank_verses("q", ["d"], api_key="sk-test", model="rerank-3")

    call_kwargs = mock_client.post.call_args[1]
    assert call_kwargs["json"]["model"] == "rerank-3"


@pytest.mark.asyncio
async def test_results_sorted_by_relevance_descending():
    response = _mock_response(json_data={"data": [
        {"index": 0, "relevance_score": 0.3},
        {"index": 1, "relevance_score": 0.9},
        {"index": 2, "relevance_score": 0.6},
    ]})
    mock_client = AsyncMock()
    mock_client.post.return_value = response

    with patch("quran_mcp.lib.morphology.voyage_reranker.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        results = await rerank_verses("q", ["a", "b", "c"], api_key="sk-test")

    assert results[0]["relevance_score"] == 0.9
    assert results[1]["relevance_score"] == 0.6
    assert results[2]["relevance_score"] == 0.3
    assert results[0]["index"] == 1
    assert results[1]["index"] == 2
    assert results[2]["index"] == 0


@pytest.mark.asyncio
async def test_empty_documents_returns_empty():
    result = await rerank_verses("query", [], api_key="sk-test")
    assert result == []


@pytest.mark.asyncio
async def test_no_api_key_raises():
    with pytest.raises(VoyageRerankerError, match="not configured"):
        await rerank_verses("query", ["doc"], api_key="")


@pytest.mark.asyncio
async def test_none_api_key_raises():
    with pytest.raises(VoyageRerankerError, match="not configured"):
        await rerank_verses("query", ["doc"], api_key=None)


@pytest.mark.asyncio
async def test_non_200_raises():
    response = _mock_response(status_code=429, text="rate limited")
    mock_client = AsyncMock()
    mock_client.post.return_value = response

    with patch("quran_mcp.lib.morphology.voyage_reranker.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(VoyageRerankerError, match="429"):
            await rerank_verses("q", ["d"], api_key="sk-test")


@pytest.mark.asyncio
async def test_500_error_includes_response_text():
    response = _mock_response(status_code=500, text="internal server error")
    mock_client = AsyncMock()
    mock_client.post.return_value = response

    with patch("quran_mcp.lib.morphology.voyage_reranker.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(VoyageRerankerError, match="internal server error"):
            await rerank_verses("q", ["d"], api_key="sk-test")


@pytest.mark.asyncio
async def test_network_error_propagates():
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("connection refused")

    with patch("quran_mcp.lib.morphology.voyage_reranker.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(httpx.ConnectError):
            await rerank_verses("q", ["d"], api_key="sk-test")


@pytest.mark.asyncio
async def test_empty_data_field_returns_empty():
    response = _mock_response(json_data={"data": []})
    mock_client = AsyncMock()
    mock_client.post.return_value = response

    with patch("quran_mcp.lib.morphology.voyage_reranker.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        results = await rerank_verses("q", ["d"], api_key="sk-test")

    assert results == []


@pytest.mark.asyncio
async def test_missing_data_field_returns_empty():
    response = _mock_response(json_data={"usage": {"tokens": 10}})
    mock_client = AsyncMock()
    mock_client.post.return_value = response

    with patch("quran_mcp.lib.morphology.voyage_reranker.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        results = await rerank_verses("q", ["d"], api_key="sk-test")

    assert results == []
