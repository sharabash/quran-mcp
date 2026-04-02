"""Validated request model for concordance lookups.

This module centralizes the selector matrix used by the concordance tool.
The MCP surface still accepts multiple input shapes, but the implementation
normalizes them into a single immutable request object before any query work
starts.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from quran_mcp.lib.morphology.types import (
    ConcordanceGroupBy,
    ConcordanceMatchBy,
    ConcordanceQueryEcho,
)

ConcordanceSelectorKind = Literal["ayah_key", "word", "root", "lemma", "stem"]


@dataclass(frozen=True, slots=True)
class ConcordanceSelection:
    """Normalized selector for a concordance lookup."""

    kind: ConcordanceSelectorKind
    ayah_key: str | None = None
    word_position: int | None = None
    word_text: str | None = None
    word: str | None = None
    root: str | None = None
    lemma: str | None = None
    stem: str | None = None

    @property
    def search_term(self) -> str | None:
        """Return the lexical term used for semantic reranking."""
        return self.word_text or self.word or self.root or self.lemma or self.stem

    def to_query_echo(self) -> ConcordanceQueryEcho:
        """Build the public concordance query echo for this selection."""
        if self.kind == "ayah_key":
            echo = ConcordanceQueryEcho()
            if self.ayah_key is not None:
                echo["ayah_key"] = self.ayah_key
            if self.word_position is not None:
                echo["word_position"] = self.word_position
            if self.word_text is not None:
                echo["text"] = self.word_text
            return echo
        if self.kind == "word":
            echo = ConcordanceQueryEcho()
            if self.word is not None:
                echo["word"] = self.word
            if self.ayah_key is not None:
                echo["resolved_verse"] = self.ayah_key
            return echo
        if self.kind == "root":
            return ConcordanceQueryEcho(root=self.root or "")
        if self.kind == "lemma":
            return ConcordanceQueryEcho(lemma=self.lemma or "")
        if self.kind == "stem":
            return ConcordanceQueryEcho(stem=self.stem or "")
        raise ValueError(f"Unsupported concordance selector kind: {self.kind!r}")


@dataclass(frozen=True, slots=True)
class ConcordanceRequest:
    """Full concordance request after selector validation."""

    selection: ConcordanceSelection
    match_by: ConcordanceMatchBy = "all"
    group_by: ConcordanceGroupBy = "verse"
    rerank_from: str | None = None
    page: int = 1
    page_size: int = 20

    def with_overrides(
        self,
        *,
        match_by: ConcordanceMatchBy | None = None,
        group_by: ConcordanceGroupBy | None = None,
        rerank_from: str | None | Literal[False] = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> "ConcordanceRequest":
        """Return a copy with a few fields overridden."""
        updates: dict[str, object] = {}
        if match_by is not None:
            updates["match_by"] = match_by
        if group_by is not None:
            updates["group_by"] = group_by
        if rerank_from is not None:
            updates["rerank_from"] = rerank_from
        if page is not None:
            updates["page"] = page
        if page_size is not None:
            updates["page_size"] = page_size
        return replace(self, **updates)


def build_concordance_request(
    *,
    ayah_key: str | None = None,
    word_position: int | None = None,
    word_text: str | None = None,
    word: str | None = None,
    root: str | None = None,
    lemma: str | None = None,
    stem: str | None = None,
    match_by: ConcordanceMatchBy = "all",
    group_by: ConcordanceGroupBy = "verse",
    rerank_from: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ConcordanceRequest:
    """Validate raw selector inputs and normalize them into one request object."""
    if word_position is not None and not ayah_key:
        raise ValueError("word_position requires ayah_key")
    if word_text is not None and not ayah_key:
        raise ValueError("word_text requires ayah_key")
    if word_position is not None and word_text is not None:
        raise ValueError("Provide either word_position or word_text, not both")

    input_types = sum(1 for item in (ayah_key, word, root, lemma, stem) if item is not None)
    if input_types > 1:
        non_ayah = sum(1 for item in (word, root, lemma, stem) if item is not None)
        if non_ayah > 1 or (ayah_key is not None and non_ayah > 0):
            raise ValueError("Provide only one of: ayah_key, word, root, lemma, or stem")
    if input_types == 0:
        raise ValueError("Provide one of: ayah_key, word, root, lemma, or stem")
    if match_by not in ("all", "root", "lemma", "stem"):
        raise ValueError(f"Invalid match_by: {match_by!r}")
    if group_by not in ("verse", "word"):
        raise ValueError(f"Invalid group_by: {group_by!r}")
    if page < 1:
        raise ValueError("page must be >= 1")
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between 1 and 100")

    if ayah_key is not None:
        selection = ConcordanceSelection(
            kind="ayah_key",
            ayah_key=ayah_key,
            word_position=word_position,
            word_text=word_text,
        )
    elif word is not None:
        selection = ConcordanceSelection(kind="word", word=word)
    elif root is not None:
        selection = ConcordanceSelection(kind="root", root=root)
    elif lemma is not None:
        selection = ConcordanceSelection(kind="lemma", lemma=lemma)
    else:
        selection = ConcordanceSelection(kind="stem", stem=stem)

    return ConcordanceRequest(
        selection=selection,
        match_by=match_by,
        group_by=group_by,
        rerank_from=rerank_from,
        page=page,
        page_size=page_size,
    )
