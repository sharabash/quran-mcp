"""Streaming-event normalization helpers for GoodMem retrieval."""

from __future__ import annotations

import base64
import logging
from typing import Any, Mapping

from goodmem_client.models import SpaceKey
from goodmem_client.streaming import MemoryStreamClient

__all__ = ["normalize_sdk_content", "stream_search_memories"]


def normalize_sdk_content(content: str | bytes | tuple | None) -> str:
    """Normalize the SDK's original_content field to a string."""
    if content is None:
        return ""
    if isinstance(content, bytes):
        return content.decode("utf-8")
    if isinstance(content, tuple):
        item = content[1] if len(content) > 1 else content[0]
        return item.decode("utf-8") if isinstance(item, bytes) else str(item)
    if isinstance(content, str):
        try:
            decoded_bytes = base64.b64decode(content, validate=True)
            return decoded_bytes.decode("utf-8")
        except Exception:
            return content
    return str(content)


def stream_search_memories(
    *,
    stream_client: MemoryStreamClient,
    query: str,
    space_keys: list[SpaceKey],
    limit: int,
    reranker_id: str | None,
    rerank_threshold: float | None,
    rerank_max_results: int | None,
    space_id_to_name: Mapping[str, str],
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    """Collect memory records from GoodMem stream events."""
    rows: list[dict[str, Any]] = []
    seen_memory_ids: set[str] = set()
    memory_scores: dict[str, float] = {}

    for event in stream_client.retrieve_memory_stream_chat(
        message=query,
        space_keys=space_keys,
        requested_size=limit,
        fetch_memory=True,
        fetch_memory_content=True,
        pp_reranker_id=reranker_id,
        pp_relevance_threshold=rerank_threshold,
        pp_max_results=rerank_max_results,
    ):
        if hasattr(event, "retrieved_item") and event.retrieved_item:
            retrieved_item = event.retrieved_item
            if hasattr(retrieved_item, "chunk") and retrieved_item.chunk:
                chunk_ref = retrieved_item.chunk
                score = getattr(chunk_ref, "relevance_score", None)
                inner_chunk = getattr(chunk_ref, "chunk", None)
                if inner_chunk and isinstance(inner_chunk, dict):
                    memory_id = inner_chunk.get("memoryId") or inner_chunk.get("memory_id")
                    if memory_id and score is not None:
                        if memory_id not in memory_scores or score > memory_scores[memory_id]:
                            memory_scores[memory_id] = float(score)

        if not (hasattr(event, "memory_definition") and event.memory_definition):
            continue
        memory_definition = event.memory_definition
        if not isinstance(memory_definition, dict):
            logger.warning(
                "Skipping non-dict memory_definition: %s",
                type(memory_definition),
            )
            continue

        memory_id = memory_definition.get("memoryId")
        if not memory_id:
            logger.warning(
                "Skipping memory_definition without memoryId: %s",
                memory_definition.keys(),
            )
            continue
        if memory_id in seen_memory_ids:
            continue
        seen_memory_ids.add(memory_id)

        space_id = memory_definition.get("spaceId")
        rows.append(
            {
                "content": normalize_sdk_content(memory_definition.get("originalContent")),
                "metadata": memory_definition.get("metadata") or {},
                "memory_id": memory_id,
                "space_id": space_id,
                "relevance_score": memory_scores.get(memory_id),
                "source_space_name": (
                    space_id_to_name.get(space_id) if space_id else None
                ),
            }
        )

    for row in rows:
        if row["relevance_score"] is None and row["memory_id"] in memory_scores:
            row["relevance_score"] = memory_scores[row["memory_id"]]

    logger.info(
        "GoodMem retrieve complete: %s results, %s scores",
        len(rows),
        len(memory_scores),
    )
    return rows[:limit]
