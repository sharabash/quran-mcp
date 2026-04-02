"""Strip HTML tags from morphological description fields.

The quran.com corpus stores descriptions with inline HTML markup
(e.g., <span class="at">, <i class="ab">, <b>) that we need to
strip before returning to MCP clients.
"""

import re

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str | None) -> str | None:
    """Remove HTML tags from text, preserving inner content.

    Returns None unchanged if input is None or empty.
    """
    if not text:
        return text
    return _TAG_RE.sub("", text).strip()
