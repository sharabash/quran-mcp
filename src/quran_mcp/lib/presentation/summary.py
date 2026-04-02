"""
Generic summary builders for edition text (tafsir, translation, etc.).

This module provides domain-agnostic functions for formatting edition segments
and building LLM prompts for summarization. It supports both sampling (with system role)
and MCP prompts (user/assistant roles only).

Usage:
    from quran_mcp.lib.presentation.summary import (
        format_segments,
        infer_summary_lang,
        build_summary_messages_for_sampling,
        build_summary_messages_for_prompt,
    )
    from quran_mcp.lib.editions import SummaryPromptConfig

    config = SummaryPromptConfig(
        sampling_system_template="...",
        sampling_user_template="...",
        prompt_assistant_template="...",
        prompt_user_template="...",
    )
    messages = build_summary_messages_for_sampling(
        ayah_key="2:255",
        segments={"en-ibn-kathir": [{"ayah": "2:255", "text": "..."}]},
        config=config,
        mode="aggregate",
        lang="en",
        length="medium",
    )
"""
from __future__ import annotations

from typing import Mapping, Sequence

from quran_mcp.lib.editions.types import SummaryPromptConfig


def format_segments(
    segments: Mapping[str, Sequence[object]],
    header_template: str = "--- SOURCE: edition_id={edition_id} ---",
    source_names: Mapping[str, str] | None = None,
) -> str:
    """Serialize structured edition segments into a canonical text block.

    Accept Mapping[str, Sequence[object]] so callers can pass either Pydantic models
    (from the tool response) or plain dicts (from the prompt setup) without copying.
    The helper normalizes to strings to keep both call sites in sync.

    Args:
        segments: Dict mapping edition_id -> list of entries with 'ayah' and 'text' attributes.
        header_template: Template for section headers. Must contain '{edition_id}' placeholder.
            Also supports optional '{name}' placeholder when source_names is provided.
        source_names: Optional mapping of edition_id -> human-readable display name.
            When provided and header_template contains '{name}', the display name is
            interpolated into SOURCE headers.

    Returns:
        Formatted text block with section headers and ayah entries.

    Example:
        >>> segments = {
        ...     "en-ibn-kathir": [
        ...         {"ayah": "2:255", "text": "Allah - there is no deity..."}
        ...     ]
        ... }
        >>> text = format_segments(segments)
        >>> print(text)

        --- SOURCE: edition_id=en-ibn-kathir ---

        [2:255]
        Allah - there is no deity...
    """

    def _extract(entry: object, attr: str) -> str:
        if isinstance(entry, dict):
            value = entry.get(attr)
        else:
            value = getattr(entry, attr, None)
        return str(value) if value is not None else ""

    combined: list[str] = []
    for edition_id, entries in segments.items():
        name = (source_names or {}).get(edition_id, edition_id)
        header = header_template.format(edition_id=edition_id, name=name)
        combined.append(f"\n{header}\n")
        for entry in entries:
            ayah = _extract(entry, "ayah")
            text = _extract(entry, "text")
            combined.append(f"\n[{ayah}]\n{text}\n")
    return "".join(combined)


def infer_summary_lang(edition_ids: list[str]) -> str:
    """Infer summary language from edition IDs.

    Args:
        edition_ids: List of edition IDs (e.g., ["en-ibn-kathir", "ar-tabari"])

    Returns:
        "ar" if all editions are Arabic, "en" otherwise
    """
    if not edition_ids:
        return "en"

    all_arabic = all(eid.startswith("ar-") for eid in edition_ids)
    return "ar" if all_arabic else "en"


def _build_options_lines(
    ayah_key: str,
    mode: str,
    lang: str,
    length: str,
    focus: str | None,
    sources: list[str] | None,
    source_names: Mapping[str, str] | None = None,
) -> list[str]:
    """Build the options lines for summary prompts."""
    opts_lines = [
        f"ayah_key: {ayah_key}",
        f"mode: {mode}",
        f"lang: {lang}",
        f"length: {length}",
    ]
    if sources:
        opts_lines.append(f"sources: {', '.join(sources)}")
    if focus:
        opts_lines.append(f"focus: {focus}")
    # Source legend: map edition_ids to human-readable names for citation
    if source_names:
        legend_parts = [f"{eid} = {name}" for eid, name in source_names.items()]
        opts_lines.append(f"source_legend: {'; '.join(legend_parts)}")
    return opts_lines


def build_summary_messages_for_sampling(
    ayah_key: str,
    segments: Mapping[str, Sequence[object]],
    config: SummaryPromptConfig,
    mode: str = "aggregate",
    focus: str | None = None,
    lang: str = "en",
    length: str = "medium",
    sources: list[str] | None = None,
    source_names: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """Build messages for tool sampling (ctx.sample) — CAN include 'system' role.

    This function builds a list of messages suitable for LLM sampling APIs that
    support the 'system' role. The prompts are customized via SummaryPromptConfig.

    Summary options:
      - mode: 'aggregate' | 'separate' | 'compare' (default 'aggregate')
      - focus: optional string to spotlight specific aspects
      - lang: 'ar' | 'en' (tools may infer if omitted)
      - length: 'short' | 'medium' | 'detailed' (default 'medium')

    Args:
        ayah_key: The ayah reference being summarized (e.g., "2:255").
        segments: Dict mapping edition_id -> list of entries with 'ayah' and 'text'.
        config: SummaryPromptConfig with domain-specific prompt templates.
        mode: Summary mode - aggregate, separate, or compare.
        focus: Optional focus string to emphasize specific aspects.
        lang: Output language for the summary.
        length: Summary length - short, medium, or detailed.
        sources: Optional list of source edition IDs to mention.
        source_names: Optional mapping of edition_id -> human-readable display name.
            When provided, SOURCE headers and citation instructions use display names
            instead of raw edition_ids.

    Returns:
        List of dicts with 'role' and 'content' keys suitable for ctx.sample().

    Note:
        The config.sampling_system_template and config.sampling_user_template
        are used directly as the system and user message content. They should
        be complete templates that include all necessary instructions.
    """
    header_tpl = "--- SOURCE: {name} [{edition_id}] ---" if source_names else "--- SOURCE: edition_id={edition_id} ---"
    text = format_segments(segments, header_template=header_tpl, source_names=source_names)
    opts_lines = _build_options_lines(ayah_key, mode, lang, length, focus, sources, source_names=source_names)
    opts_str = "\n".join(f"- {line}" for line in opts_lines)

    return [
        {
            "role": "system",
            "content": config.sampling_system_template,
        },
        {
            "role": "user",
            "content": config.sampling_user_template.format(
                options=opts_str,
                text=text,
            ),
        },
    ]


def build_summary_messages_for_prompt(
    ayah_key: str,
    segments: Mapping[str, Sequence[object]],
    config: SummaryPromptConfig,
    mode: str = "aggregate",
    focus: str | None = None,
    lang: str = "en",
    length: str = "medium",
    sources: list[str] | None = None,
    source_names: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """Build messages for MCP prompts — MUST use only 'user'/'assistant' roles.

    This function builds a list of messages suitable for MCP prompt handlers
    which cannot use the 'system' role. Instructions are embedded in the
    assistant and user messages instead.

    Summary options:
      - mode: 'aggregate' | 'separate' | 'compare' (default 'aggregate')
      - focus: optional string to spotlight specific aspects
      - lang: 'ar' | 'en' (prompts typically default to 'en' unless provided)
      - length: 'short' | 'medium' | 'detailed' (default 'medium')

    Args:
        ayah_key: The ayah reference being summarized (e.g., "2:255").
        segments: Dict mapping edition_id -> list of entries with 'ayah' and 'text'.
        config: SummaryPromptConfig with domain-specific prompt templates.
        mode: Summary mode - aggregate, separate, or compare.
        focus: Optional focus string to emphasize specific aspects.
        lang: Output language for the summary.
        length: Summary length - short, medium, or detailed.
        sources: Optional list of source edition IDs to mention.
        source_names: Optional mapping of edition_id -> human-readable display name.

    Returns:
        List of dicts with 'role' and 'content' keys suitable for PromptMessage.

    Note:
        MCP prompts cannot use 'system' role, so we use assistant/user pattern.
        The config.prompt_assistant_template and config.prompt_user_template
        are used directly as the message content.
    """
    header_tpl = "--- SOURCE: {name} [{edition_id}] ---" if source_names else "--- SOURCE: edition_id={edition_id} ---"
    text = format_segments(segments, header_template=header_tpl, source_names=source_names)
    opts_lines = _build_options_lines(ayah_key, mode, lang, length, focus, sources, source_names=source_names)
    opts_str = "\n".join(f"- {line}" for line in opts_lines)

    return [
        {
            "role": "assistant",
            "content": config.prompt_assistant_template,
        },
        {
            "role": "user",
            "content": config.prompt_user_template.format(
                options=opts_str,
                text=text,
            ),
        },
    ]
