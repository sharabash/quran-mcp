"""Canonical types and typed adapters for editions."""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, Self, TypeAlias, TypedDict, TypeVar, cast, overload

from quran_mcp.lib.editions.errors import DataGap, UnresolvedEdition

if TYPE_CHECKING:
    from quran_mcp.lib.context.types import AppContext
    from quran_mcp.lib.editions.fetcher import EditionFetcherConfig


TEntry = TypeVar("TEntry")
EditionType: TypeAlias = Literal["quran", "tafsir", "translation"]
EDITION_TYPES: tuple[EditionType, ...] = ("quran", "tafsir", "translation")


_EDITION_RECORD_FIELDS = (
    "edition_id",
    "edition_type",
    "lang",
    "code",
    "name",
    "author",
    "description",
    "choose_when",
    "avg_entry_tokens",
    "qf_resource_id",
)


@dataclass(frozen=True, slots=True)
class EditionRecord(Mapping[str, Any]):
    """Immutable edition record projected from editions.json.

    Required fields:
        edition_id, edition_type, lang, code, name

    Optional fields:
        author, description, choose_when, avg_entry_tokens, qf_resource_id
    """

    edition_id: str
    edition_type: EditionType
    lang: str
    code: str
    name: str
    author: str | None = None
    description: str | None = None
    choose_when: str | None = None
    avg_entry_tokens: int | None = None
    qf_resource_id: int | None = None

    @overload
    def __getitem__(self, key: Literal["edition_id"]) -> str: ...

    @overload
    def __getitem__(self, key: Literal["edition_type"]) -> EditionType: ...

    @overload
    def __getitem__(self, key: Literal["lang"]) -> str: ...

    @overload
    def __getitem__(self, key: Literal["code"]) -> str: ...

    @overload
    def __getitem__(self, key: Literal["name"]) -> str: ...

    @overload
    def __getitem__(self, key: Literal["author"]) -> str | None: ...

    @overload
    def __getitem__(self, key: Literal["description"]) -> str | None: ...

    @overload
    def __getitem__(self, key: Literal["choose_when"]) -> str | None: ...

    @overload
    def __getitem__(self, key: Literal["avg_entry_tokens"]) -> int | None: ...

    @overload
    def __getitem__(self, key: Literal["qf_resource_id"]) -> int | None: ...

    @overload
    def __getitem__(self, key: str) -> Any: ...

    def __getitem__(self, key: str) -> Any:
        if key not in _EDITION_RECORD_FIELDS:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(_EDITION_RECORD_FIELDS)

    def __len__(self) -> int:
        return len(_EDITION_RECORD_FIELDS)

    def as_dict(self) -> dict[str, Any]:
        """Return the full record as a plain dict for JSON-style consumers."""
        return {field: self[field] for field in _EDITION_RECORD_FIELDS}

    def as_public_dict(self) -> EditionInfoRecord:
        """Return the public summary shape used by list_editions responses."""
        return {
            "edition_id": self.edition_id,
            "edition_type": self.edition_type,
            "lang": self.lang,
            "code": self.code,
            "name": self.name,
            "author": self.author,
            "description": self.description,
            "choose_when": self.choose_when,
            "avg_entry_tokens": self.avg_entry_tokens,
        }


class EditionInfoRecord(TypedDict):
    """Public edition summary shape used by list_editions responses."""

    edition_id: str
    edition_type: EditionType
    lang: str
    code: str
    name: str
    author: str | None
    description: str | None
    choose_when: str | None
    avg_entry_tokens: int | None


class EditionListRecord(TypedDict):
    """Public grouped list_editions payload returned by registry helpers."""

    filters: dict[str, str]
    results: list[EditionInfoRecord]
    count: int


def project_edition_info(record: EditionRecord) -> EditionInfoRecord:
    """Project a loaded edition record into the public summary shape."""
    return record.as_public_dict()


@dataclass(slots=True)
class EditionFetchResult(Generic[TEntry]):
    """Typed wrapper around EditionFetcher results."""

    data: dict[str, list[TEntry]]
    gaps: list[DataGap] | None = None
    unresolved: list[UnresolvedEdition] | None = None

    @classmethod
    def from_result(cls, result: "EditionFetchResult[TEntry]") -> Self:
        """Rewrap a generic fetch result under a domain-specific subclass."""
        return cls(
            data=result.data,
            gaps=result.gaps,
            unresolved=result.unresolved,
        )


async def fetch_with_config(
    ctx: "AppContext",
    ayahs: str | list[str],
    editions: str | list[str],
    *,
    config: "EditionFetcherConfig",
) -> EditionFetchResult[TEntry]:
    """Run an EditionFetcher config through the common typed fetch path."""
    from quran_mcp.lib.editions.fetcher import EditionFetcher

    fetch_result = await EditionFetcher(config).fetch(ctx, ayahs, editions)
    return EditionFetchResult(
        data=cast(dict[str, list[TEntry]], fetch_result.data),
        gaps=fetch_result.gaps,
        unresolved=fetch_result.unresolved,
    )


@dataclass
class SummaryPromptConfig:
    """Domain-specific wording for summary prompts.

    Contains full prompt templates for both sampling and prompt-based
    summarization modes.

    Template Placeholders:
        - sampling_system_template: No placeholders (used as-is)
        - sampling_user_template: {options}, {text}
        - prompt_assistant_template: No placeholders (used as-is)
        - prompt_user_template: {options}, {text}

    Where:
        - {options}: Formatted options string (ayah_key, mode, lang, length, sources, focus)
        - {text}: Formatted segments text from format_segments()

    Example:
        >>> config = SummaryPromptConfig(
        ...     sampling_system_template="You are a tafsir summarizer...",
        ...     sampling_user_template="Summarize the following:\\n\\nOptions:\\n{options}\\n\\nText:\\n{text}",
        ...     prompt_assistant_template="I'm ready to summarize...",
        ...     prompt_user_template="Summarize:\\n\\nOptions:\\n{options}\\n\\nText:\\n{text}",
        ... )
    """

    sampling_system_template: str
    sampling_user_template: str
    prompt_assistant_template: str
    prompt_user_template: str
