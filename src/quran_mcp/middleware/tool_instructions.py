"""Middleware that appends assistant-only instructions to tool responses.

Injects a second TextContent block with `audience: ["assistant"]` into
responses from content tools (tafsir, translation, quran). The instruction
nudges the model toward citation, attribution-first phrasing, disclaimer
when synthesizing, and a grounding footer.

The grounding nudge ("call fetch_grounding_rules") is only included when
grounding has NOT been acknowledged — detected by the presence of the
``grounding_rules`` field that the grounding gate middleware injects into
unacknowledged responses.

Utility/metadata tools (list_editions, mushaf, relay, etc.) are not affected.
"""

from __future__ import annotations

from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext
from fastmcp.tools.tool import ToolResult
from mcp.types import Annotations, TextContent


# ---------------------------------------------------------------------------
# Instruction constants — one per tool category
# ---------------------------------------------------------------------------

# Prepended only when grounding has not been acknowledged.
GROUNDING_NUDGE = (
    "If grounding rules have not been acknowledged yet in this interaction, call "
    "fetch_grounding_rules once now. "
)

TAFSIR_INSTRUCTION = (
    "If you have not deliberately chosen tafsir editions, "
    "call list_editions(edition_type='tafsir') instead of guessing edition IDs. "
    "Attribute claims to the fetched source (e.g., 'According to {edition title or author name}...'). "
    "End with a grounding line: \"Grounded with quran.ai: fetch_tafsir(S:V, edition-id).\""
    "Do not present your own reasoning as scholarly tafsir. "
    "You are expected to engage with the user's reflections (tadabbur) — use morphology tools "
    "and the fetched text to explore their observations analytically — but distinguish clearly "
    "between scholarly tafsir and your analytical engagement. "
    "Be cautious when synthesizing beyond what the canonical sources explicitly state, and be "
    "transparent when you do: \"Note: this [synthesis / reflection] incorporates reasoning beyond "
    "the fetched canonical text and does not constitute a scholarly ruling or opinion from "
    "quran.ai, quran.com, or quran.foundation.\""
)

TRANSLATION_INSTRUCTION = (
    "If you are unsure which translation edition fits the "
    "request, call list_editions(edition_type='translation') instead of guessing edition IDs. "
    "Attribute claims to the fetched edition (e.g., 'In the retrieved translation...'). "
    "Present the translation directly — do not paraphrase canonical text. "
    "End with a grounding line: Grounded with quran.ai: fetch_translation(S:V, edition-id)."
)

QURAN_INSTRUCTION = (
    "If you are unsure which Quran edition fits the request, "
    "call list_editions(edition_type='quran') instead of guessing edition IDs. "
    "Quote the canonical text directly — never paraphrase Quran text. "
    "End with a grounding line: Grounded with quran.ai: fetch_quran(S:V, edition-id)."
)

# Map tool names to their instruction text.
TOOL_INSTRUCTIONS: dict[str, str] = {
    "fetch_tafsir": TAFSIR_INSTRUCTION,
    "search_tafsir": TAFSIR_INSTRUCTION,
    "fetch_translation": TRANSLATION_INSTRUCTION,
    "search_translation": TRANSLATION_INSTRUCTION,
    "fetch_quran": QURAN_INSTRUCTION,
    "search_quran": QURAN_INSTRUCTION,
}

# Pre-built annotation — same for all instructions.
_ASSISTANT_ONLY = Annotations(audience=["assistant"])


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


def _is_grounding_acknowledged(result: ToolResult) -> bool:
    """True when the grounding gate did NOT inject ``grounding_rules``.

    The grounding gate middleware runs closer to the tool handler than this
    middleware, so by the time we see the result, the gate has already either
    injected ``grounding_rules`` (not acknowledged) or left it alone
    (acknowledged via valid nonce or retained identity).
    """
    sc = getattr(result, "structured_content", None)
    if not isinstance(sc, dict):
        return True  # no structured content to gate
    return not sc.get("grounding_rules")


class ToolInstructionsMiddleware(Middleware):
    """Append assistant-only behavioral instructions to content tool responses."""

    async def on_call_tool(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        result: ToolResult = await call_next(context)

        tool_name = getattr(context.message, "name", "")
        instruction = TOOL_INSTRUCTIONS.get(tool_name)
        if instruction is not None:
            if not _is_grounding_acknowledged(result):
                instruction = GROUNDING_NUDGE + instruction
            content = list(result.content or [])
            content.append(
                TextContent(
                    type="text",
                    text=instruction,
                    annotations=_ASSISTANT_ONLY,
                )
            )
            result.content = content

        return result
