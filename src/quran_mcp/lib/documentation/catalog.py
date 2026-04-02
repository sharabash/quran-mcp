"""Catalog and static configuration for the documentation site generator."""

from __future__ import annotations

from typing import Any

PUBLIC_DOC_TAGS = {"ga", "preview"}
PUBLIC_DOC_EXCLUDED_TAGS = {"deprecated", "internal", "in-development"}
PUBLIC_DOC_EXCLUDED_PREFIXES = ("relay_",)

TOOL_GROUPS: list[dict[str, Any]] = [
    {
        "id": "grounding-setup",
        "label": "Grounding and setup",
        "blurb": (
            "Session initialization and edition discovery. Call "
            "fetch_grounding_rules once per session before using any other tool."
        ),
        "subgroups": [
            {"label": "Session startup", "tools": ("fetch_grounding_rules", "list_editions")},
        ],
    },
    {
        "id": "search-and-retrieval",
        "label": "Search and retrieval",
        "blurb": (
            "Fetch exact Quran text, translations, and tafsir commentary by verse "
            "reference, or search semantically across the corpus."
        ),
        "subgroups": [
            {"label": "Quran", "tools": ("fetch_quran", "search_quran")},
            {"label": "Tafsir", "tools": ("fetch_tafsir", "search_tafsir")},
            {"label": "Translation", "tools": ("fetch_translation", "search_translation")},
        ],
    },
    {
        "id": "word-study",
        "label": "Word study",
        "blurb": (
            "Inspect Quranic words at the morphology, lemma, root, and concordance "
            "level without leaving canonical data."
        ),
        "subgroups": [
            {"label": None, "tools": ("fetch_word_morphology", "fetch_word_paradigm", "fetch_word_concordance")},
        ],
    },
    {
        "id": "apps",
        "label": "Apps",
        "blurb": (
            "Open the mushaf app or expose the page payload behind it. "
            "show_mushaf is the human-facing entry point; fetch_mushaf is the host-facing rendering payload it depends on."
        ),
        "subgroups": [
            {"label": "Mushaf reader", "tools": ("show_mushaf", "fetch_mushaf")},
        ],
    },
    {
        "id": "utilities",
        "label": "Utilities",
        "blurb": "Structural metadata and server configuration tools.",
        "subgroups": [
            {"label": None, "tools": ("fetch_quran_metadata", "fetch_skill_guide")},
        ],
    },
]

_TOOL_ORDER: list[str] = []
for _group in TOOL_GROUPS:
    for _subgroup in _group["subgroups"]:
        _TOOL_ORDER.extend(_subgroup["tools"])
TOOL_ORDER_INDEX = {name: i for i, name in enumerate(_TOOL_ORDER)}

TOOL_LEADS = {
    "fetch_grounding_rules": (
        "Start a session here when Quranic content will be quoted, paraphrased, interpreted, or summarized. "
        "It returns the canonical grounding contract that suppresses repeated grounding payloads on later canonical-tool calls."
    ),
    "fetch_skill_guide": (
        "Use this when you want the full operating manual rather than the short grounding contract. "
        "It is the authoritative guide for fetch vs search decisions, tafsir discipline, and dynamic-context reuse."
    ),
    "list_editions": (
        "This is the discovery tool for edition ids. It lets the caller choose a tafsir or translation by language, "
        "author, or methodology instead of guessing a selector string."
    ),
    "fetch_quran": (
        "Fetch exact Quran text for known ayah references. This is the safest path when the user asks for "
        "precise Arabic wording and the verse reference is already known."
    ),
    "fetch_translation": (
        "Fetch literal translation text for known ayah references. Use it when the user wants a translation "
        "rendering, not interpretive commentary."
    ),
    "fetch_tafsir": (
        "Fetch full tafsir blocks for known ayah references. Use it when the question is interpretive and the "
        "verse is already known, especially when scholar selection matters."
    ),
    "search_quran": (
        "Search semantically across Quran text with optional translations attached. It is the fastest route from "
        "a theme, transliteration, or partial phrase to the right ayah."
    ),
    "search_translation": (
        "Search translation text directly when edition filtering matters. This is narrower than search_quran, "
        "but it gives tighter control over which translation corpus is searched."
    ),
    "search_tafsir": (
        "Search commentary content when the user knows the topic but not the ayah. It is useful for thematic "
        "tafsir discovery, but the returned passage still needs source-aware reading."
    ),
    "fetch_word_morphology": (
        "Inspect a Quranic word at the segment and grammar level. The response includes root, lemma, stem, "
        "feature tags, frequencies, and a plain-language morphological description."
    ),
    "fetch_word_paradigm": (
        "Move from one Quranic word to its derivational family. This is the tool for seeing how a lemma "
        "appears across perfect, imperfect, and imperative stems."
    ),
    "fetch_word_concordance": (
        "Find related occurrences by exact stem, lemma, or root. It is the right tool when you want a ranked "
        "concordance rather than a semantic theme search."
    ),
    "show_mushaf": (
        "Open the traditional mushaf view at a page, juz, or surah location. The response is app-oriented "
        "structured content meant to anchor follow-up questions in page context."
    ),
    "fetch_mushaf": (
        "Fetch the page rendering payload that powers show_mushaf. This is primarily for MCP hosts that need the "
        "underlying page model behind the app surface."
    ),
    "fetch_quran_metadata": (
        "Fetch fixed-shape structural metadata for ayah, surah, juz, page, hizb, ruku, or manzil lookups. "
        "It is the navigation tool for structure, not wording."
    ),
}

QUICKSTART_CONFIG = """{
  "mcpServers": {
    "quran": { "url": "https://mcp.quran.ai" }
  }
}"""

QUICKSTART_CONFIG_HTML = (
    '<span class="hl-p">{ </span>'
    '<span class="hl-key">"mcpServers"</span>'
    '<span class="hl-p">: {</span>\n'
    '    <span class="hl-key">"quran"</span>'
    '<span class="hl-p">: { </span>'
    '<span class="hl-key">"url"</span>'
    '<span class="hl-p">: </span>'
    '<span class="hl-str">"https://mcp.quran.ai"</span>'
    '<span class="hl-p"> }</span>\n'
    '<span class="hl-p">} }</span>'
)

EDITION_SECTION_CONFIG: list[dict[str, Any]] = [
    {
        "id": "tafsir",
        "label": "Tafsir",
        "summary_suffix": "classical and modern commentary",
        "columns": (
            {"key": "edition_id", "label": "Edition ID", "class_name": "is-copy"},
            {"key": "name", "label": "Name", "class_name": "is-name"},
            {"key": "author", "label": "Author", "class_name": "is-author"},
            {"key": "lang", "label": "Lang", "class_name": "is-lang"},
        ),
    },
    {
        "id": "translation",
        "label": "Translation",
        "summary_suffix": "translations across supported languages",
        "columns": (
            {"key": "edition_id", "label": "Edition ID", "class_name": "is-copy"},
            {"key": "name", "label": "Name", "class_name": "is-name"},
            {"key": "author", "label": "Author", "class_name": "is-author"},
            {"key": "lang", "label": "Lang", "class_name": "is-lang"},
        ),
    },
]

TOOL_EXAMPLE_CONFIG: dict[str, dict[str, Any]] = {
    "show_mushaf": {
        "layout": "apps",
        "screenshot": {
            "src": "/screenshots/new/claude8.png",
            "alt": "Claude showing a grounded answer with the mushaf app inline",
            "caption": "A grounded answer can open the mushaf surface inline after the tool call resolves.",
        },
    },
    "fetch_mushaf": {
        "layout": "apps",
        "screenshot": {
            "src": "/screenshots/new/claude8.png",
            "alt": "Claude showing a grounded answer with the mushaf app inline",
            "caption": "Hosts use this payload to render the same mushaf surface that show_mushaf opens for the model.",
        },
    },
}


def tool_sort_key(tool: Any) -> tuple[int, str]:
    return TOOL_ORDER_INDEX.get(tool.name, len(_TOOL_ORDER)), tool.name


def is_public_docs_tool(tool: Any) -> bool:
    if any(str(getattr(tool, "name", "")).startswith(prefix) for prefix in PUBLIC_DOC_EXCLUDED_PREFIXES):
        return False
    tags = set(getattr(tool, "tags", set()) or set())
    return bool(tags & PUBLIC_DOC_TAGS) and not bool(tags & PUBLIC_DOC_EXCLUDED_TAGS)


def short_description(tool_name: str, tool: Any) -> str:
    lead = TOOL_LEADS.get(tool_name)
    if lead:
        return lead
    return " ".join(str(getattr(tool, "description", "")).split())


def card_summary(tool_name: str, tool: Any) -> str:
    description = short_description(tool_name, tool)
    if "." in description:
        return description.split(".", 1)[0].strip() + "."
    return description


__all__ = [
    "TOOL_GROUPS",
    "TOOL_EXAMPLE_CONFIG",
    "EDITION_SECTION_CONFIG",
    "QUICKSTART_CONFIG",
    "QUICKSTART_CONFIG_HTML",
    "tool_sort_key",
    "is_public_docs_tool",
    "short_description",
    "card_summary",
]
