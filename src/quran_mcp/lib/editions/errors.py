"""
Custom error types and data structures for edition content retrieval.

Provides clear error semantics for MCP error mapping:
- DataNotFoundError → MCP error with "not found" semantics (HTTP 404 equivalent)
- DataStoreError → MCP error with "internal error" semantics (HTTP 500 equivalent)
- DataGap → Structured representation of missing data for graceful degradation
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quran_mcp.lib.editions.types import EditionType


class DataNotFoundError(Exception):
    """Raised when ALL editions fail to return requested data.

    Partial results (some ayahs missing) are reported via DataGap, not this error.
    Maps to MCP error with "not found" semantics (HTTP 404 equivalent).
    """

    def __init__(
        self,
        edition_id: str,
        edition_type: EditionType,
        missing_ayahs: list[str],
    ) -> None:
        self.edition_id = edition_id
        self.edition_type = edition_type
        self.missing_ayahs = missing_ayahs

        ayah_preview = missing_ayahs[:5]
        suffix = "..." if len(missing_ayahs) > 5 else ""

        super().__init__(
            f"{edition_type} data not found for {edition_id}: "
            f"missing {len(missing_ayahs)} ayah(s): {ayah_preview}{suffix}"
        )


class DataStoreError(Exception):
    """Raised when a data backend fails (DB or GoodMem: timeouts, auth, malformed responses).

    Maps to MCP error with "internal error" semantics (HTTP 500 equivalent).
    """

    def __init__(self, operation: str, cause: Exception) -> None:
        self.operation = operation
        self.cause = cause
        super().__init__(f"Data store {operation} failed: {cause}")


@dataclass
class DataGap:
    """Missing data for a specific edition — used for graceful degradation."""

    edition_id: str
    missing_ayahs: list[str]


@dataclass
class UnresolvedEdition:
    """Edition selector that could not be resolved to a known edition."""

    selector: str
    edition_type: EditionType
    suggestion: str = "Use list_editions tool to see available editions"
