from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from typing import Any

import pytest


def _load_module(module_name: str, module_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


REPO_ROOT = Path(__file__).resolve().parents[1]
MEMORY_RETRIEVE_PATH = REPO_ROOT / "scripts" / ".maintainer" / "goodmem" / "memory_retrieve.py"
MEMORY_CREATE_PATH = REPO_ROOT / "scripts" / ".maintainer" / "goodmem" / "memory_create.py"

memory_retrieve = _load_module("test_memory_retrieve", MEMORY_RETRIEVE_PATH)
memory_create = _load_module("test_memory_create", MEMORY_CREATE_PATH)


def test_retrieve_memories_filter_only_defaults_limit_and_query(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeConfig:
        @classmethod
        def from_env(cls) -> "FakeConfig":
            return cls()

    class FakeClient:
        def __init__(self, _config: FakeConfig) -> None:
            self.default_reranker_id = "reranker"

        async def initialize(self) -> None:
            captured["initialized"] = True

        async def search_memories(
            self,
            *,
            query: str,
            space_names: list[str],
            limit: int,
            filter_expr: str | None,
            reranker_id: str,
        ) -> list[dict[str, str]]:
            captured.update(
                {
                    "query": query,
                    "space_names": space_names,
                    "limit": limit,
                    "filter_expr": filter_expr,
                    "reranker_id": reranker_id,
                }
            )
            return [{"memory_id": "m1"}]

    def _parse_filter_string(value: str) -> dict[str, str]:
        return {"raw": value}

    def _build_filter_expression(terms: list[dict[str, str]]) -> str:
        return f"cast({len(terms)})"

    def _combine_filter_expressions(cast_expr: str | None, raw_exprs: list[str] | None) -> str:
        return f"{cast_expr}|{','.join(raw_exprs or [])}"

    monkeypatch.setattr(
        memory_retrieve,
        "_goodmem_bindings",
        lambda: {
            "GoodMemClient": FakeClient,
            "GoodMemConfig": FakeConfig,
            "parse_filter_string": _parse_filter_string,
            "build_filter_expression": _build_filter_expression,
            "combine_filter_expressions": _combine_filter_expressions,
        },
    )

    result = asyncio.run(
        memory_retrieve.retrieve_memories(
            space_names=["tafsir"],
            query=None,
            filter_strings=["surah=2"],
            filter_exprs=["exists('$.surahs')"],
            limit=None,
        )
    )

    assert result == [{"memory_id": "m1"}]
    assert captured["initialized"] is True
    assert captured["query"] == "*"
    assert captured["limit"] == 25
    assert captured["space_names"] == ["tafsir"]
    assert captured["filter_expr"] == "cast(1)|exists('$.surahs')"


def test_retrieve_main_rejects_invalid_limit(capsys: pytest.CaptureFixture[str]) -> None:
    rc = memory_retrieve.main(["--space-name", "tafsir", "--query", "x", "--limit", "0"])
    out = capsys.readouterr()
    assert rc == 2
    assert "--limit must be at least 1" in out.err


def test_memory_create_list_memories_handles_subprocess_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise OSError("subprocess unavailable")

    monkeypatch.setattr(memory_create.subprocess, "run", _boom)
    client = memory_create.GoodMemClient()
    memories, next_token = client.list_memories("space-id")
    assert memories == []
    assert next_token is None


def test_memory_create_main_rejects_missing_input_file(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.ndjson"
    rc = memory_create.main(["--space-id", "space-id", "--input", str(missing_file)])
    assert rc == 1
