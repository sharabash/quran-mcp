"""QMD (Quran Markdown) parser — converts .qmd files to HTML for documentation showcases.

Reads .qmd files listed in the manifest and converts each to a showcase dict
with generated HTML that the Svelte SPA renders on the /documentation page.

Manifest:  lib/documentation/data/usage-examples/manifest.json
QMD files: lib/documentation/data/usage-examples/*.qmd
Format:    .skills/quran-mcp-new-usage-example/references/export-format.md
Caller:    documentation.generator._build_usage_examples_context()
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

_QMD_DIR = Path(__file__).resolve().parent / "data" / "usage-examples"
_MANIFEST_PATH = _QMD_DIR / "manifest.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_generated_showcases() -> list[dict[str, Any]]:
    """Load manifest and parse all listed QMD files into showcase dicts."""
    return [parse_qmd(f) for f in _load_manifest()]


def parse_qmd(filename: str) -> dict[str, Any]:
    """Parse a single QMD file and return a showcase dict with generated HTML."""
    path = _QMD_DIR / filename
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    html = _convert_body(body)
    tools = _extract_tool_names(frontmatter.get("tools_used", []))
    slug = path.stem

    prompt = frontmatter["prompt"]
    prompt_escaped = _inline_text(prompt)

    return {
        "id": f"usage-showcase-{slug}-generated",
        "category": frontmatter.get("category", ""),
        "title": frontmatter["title"],
        "prompt_html": f"&ldquo;{prompt_escaped}&rdquo;",
        "model": frontmatter.get("model"),
        "date": frontmatter.get("date"),
        "prerequisite_tools": ["fetch_grounding_rules", "list_editions"],
        "tools": tools,
        "response_html": html,
        "generated": True,
    }


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


def _load_manifest() -> list[str]:
    if not _MANIFEST_PATH.is_file():
        return []
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.index("\n---\n", 4)
    return yaml.safe_load(text[4:end]), text[end + 5:]


def _extract_tool_names(tools_used: list[str]) -> list[str]:
    """Extract unique tool names from entries like 'fetch_quran(2:7, ...)'."""
    names: list[str] = []
    for entry in tools_used:
        name = entry.split("(")[0].strip()
        if name and name not in names:
            names.append(name)
    return names


# ---------------------------------------------------------------------------
# Body → HTML conversion
# ---------------------------------------------------------------------------


def _convert_body(body: str) -> str:
    lines = body.split("\n")
    blocks: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # ── Directive block ──
        if stripped.startswith(":::") and len(stripped) > 3:
            block_type = stripped[3:].strip()
            i += 1
            block_lines: list[str] = []
            while i < len(lines) and lines[i].strip() != ":::":
                block_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1
            blocks.append(_render_directive(block_type, block_lines))
            continue

        # ── Headings ──
        if stripped.startswith("### "):
            title = re.sub(r"\s*\{#[\w-]+\}$", "", stripped[4:])
            blocks.append(f"<h3>{_inline_text(title)}</h3>")
            i += 1
            continue
        if stripped.startswith("## "):
            title = re.sub(r"\s*\{#[\w-]+\}$", "", stripped[3:])
            blocks.append(f"<h2>{_inline_text(title)}</h2>")
            i += 1
            continue

        # ── Horizontal rule ──
        if stripped == "---":
            blocks.append("<hr>")
            i += 1
            continue

        # ── Table ──
        if stripped.startswith("|"):
            table_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            blocks.append(_render_table(table_lines))
            continue

        # ── Ordered list ──
        if re.match(r"^\d+\.\s", stripped):
            items: list[str] = []
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s*", "", lines[i].strip()))
                i += 1
            blocks.append(_render_ordered_list(items))
            continue

        # ── Markdown image ──
        img_m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if img_m:
            alt, src = img_m.group(1), img_m.group(2)
            alt_html = _inline_text(alt)
            blocks.append(
                f'<figure class="artifact-figure">\n'
                f'  <img src="/documentation/assets/{src}" alt="{alt_html}">\n'
                f"  <figcaption>{alt_html}</figcaption>\n"
                f"</figure>"
            )
            i += 1
            continue

        # ── Empty line ──
        if not stripped:
            i += 1
            continue

        # ── Paragraph ──
        para_lines: list[str] = []
        while i < len(lines):
            s = lines[i].strip()
            if (
                not s
                or s.startswith(":::")
                or s.startswith("## ")
                or s.startswith("### ")
                or s.startswith("|")
                or s == "---"
                or re.match(r"^\d+\.\s", s)
                or re.match(r"^!\[", s)
            ):
                break
            para_lines.append(s)
            i += 1
        if para_lines:
            blocks.append(f"<p>{_inline_text(' '.join(para_lines))}</p>")

    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Directive rendering
# ---------------------------------------------------------------------------


def _parse_fields(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    """Split directive lines into key:value fields and body."""
    fields: dict[str, str] = {}
    body_start = 0
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            body_start = idx + 1
            break
        m = re.match(r"^(\w+):\s*(.+)", stripped)
        if m:
            fields[m.group(1)] = m.group(2).strip()
            body_start = idx + 1
        else:
            body_start = idx
            break
    body = lines[body_start:]
    while body and not body[0].strip():
        body = body[1:]
    while body and not body[-1].strip():
        body = body[:-1]
    return fields, body


def _split_at_separator(lines: list[str]) -> tuple[list[str], list[str]]:
    for i, line in enumerate(lines):
        if line.strip() == "---":
            return lines[:i], lines[i + 1 :]
    return lines, []


def _render_directive(block_type: str, lines: list[str]) -> str:
    fields, body = _parse_fields(lines)
    if block_type == "verse":
        return _render_verse(fields, body)
    if block_type == "quote":
        return _render_quote(fields, body)
    if block_type == "insight":
        return _render_insight(fields, body)
    if block_type == "commentary":
        return _render_commentary(body)
    if block_type == "grounding":
        return _render_grounding(body)
    if block_type == "artifact":
        return _render_artifact(fields)
    if block_type == "sources":
        return _render_sources(body)
    return f"<!-- unknown block: {block_type} -->"


def _render_verse(fields: dict[str, str], body: list[str]) -> str:
    ref = fields.get("ref", "")
    link = fields.get("link", "")
    attr = fields.get("attribution", "")

    arabic_lines, translation_lines = _split_at_separator(body)
    arabic = " ".join(line.strip() for line in arabic_lines if line.strip())
    translation = _inline_text(
        " ".join(line.strip() for line in translation_lines if line.strip())
    )

    parts = ['<div class="vb">']
    if ref:
        if link:
            parts.append(
                f'  <span class="vref"><a href="{link}">{ref}</a></span>'
            )
        else:
            parts.append(f'  <span class="vref">{ref}</span>')
    parts.append(f'  <div class="ar">{arabic}</div>')
    if translation:
        parts.append(f'  <div class="tr">{translation}</div>')
    if attr:
        parts.append(f'  <span class="at">{_inline_text(attr)}</span>')
    parts.append("</div>")
    return "\n".join(parts)


def _render_quote(fields: dict[str, str], body: list[str]) -> str:
    attr = fields.get("attribution", "")

    has_separator = any(line.strip() == "---" for line in body)
    if has_separator:
        arabic_lines, english_lines = _split_at_separator(body)
    else:
        arabic_lines, english_lines = [], body

    arabic = " ".join(line.strip() for line in arabic_lines if line.strip())
    english = _inline_text(
        " ".join(line.strip() for line in english_lines if line.strip())
    )

    parts = ['<div class="sq">']
    if arabic:
        parts.append(f'  <div class="ar">{arabic}</div>')
    if english:
        parts.append(f"  <p>{english}</p>")
    if attr:
        parts.append(f'  <span class="at">{_inline_text(attr)}</span>')
    parts.append("</div>")
    return "\n".join(parts)


def _render_insight(fields: dict[str, str], body: list[str]) -> str:
    title = fields.get("title", "Insight")
    body_text = _inline_text(" ".join(line.strip() for line in body if line.strip()))
    title_html = _inline_text(title)

    return (
        '<div class="insight">\n'
        '  <div class="insight-head">'
        '<em style="color: var(--text-heading);">* </em>'
        f"<em>Insight &mdash; </em>{title_html}</div>\n"
        f"  <p>{body_text}</p>\n"
        "</div>"
    )


def _render_commentary(body: list[str]) -> str:
    text = _inline_text(" ".join(line.strip() for line in body if line.strip()))
    return f'<p class="commentary">{text}</p>'


def _render_grounding(body: list[str]) -> str:
    raw = " ".join(line.strip() for line in body if line.strip())
    formatted = re.sub(r"(\w+)\s*\(([^)]*)\)", r"<code>\1(\2)</code>", raw)
    return f'<p class="grounding"><span class="grounding-label">Grounded in quran.ai:</span> {formatted}</p>'


def _render_artifact(fields: dict[str, str]) -> str:
    ref = fields.get("ref", "")
    caption = fields.get("caption", "")
    parts = ['<figure class="artifact-figure">']
    parts.append(f'  <img src="/documentation/assets/{ref}" alt="{caption}">')
    if caption:
        parts.append(f"  <figcaption>{caption}</figcaption>")
    parts.append("</figure>")
    return "\n".join(parts)


def _render_sources(body: list[str]) -> str:
    items: list[str] = []
    for line in body:
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(f"  <li>{_inline_text(stripped[2:])}</li>")
    if not items:
        return ""
    parts = ['<div class="sources">', '  <p class="sources-head">Sources</p>', "  <ul>"]
    parts.extend(items)
    parts.append("  </ul>")
    parts.append("</div>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Table / list rendering
# ---------------------------------------------------------------------------


def _render_table(lines: list[str]) -> str:
    if len(lines) < 2:
        return ""

    def _parse_row(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    headers = _parse_row(lines[0])
    rows = [_parse_row(line) for line in lines[2:]]  # skip separator

    parts = ["<table>"]
    parts.append(
        "  <thead><tr>"
        + "".join(f"<th>{_inline_text(h)}</th>" for h in headers)
        + "</tr></thead>"
    )
    parts.append("  <tbody>")
    for row in rows:
        parts.append(
            "    <tr>"
            + "".join(f"<td>{_inline_text(c)}</td>" for c in row)
            + "</tr>"
        )
    parts.append("  </tbody>")
    parts.append("</table>")
    return "\n".join(parts)


def _render_ordered_list(items: list[str]) -> str:
    parts = ["<ol>"]
    for item in items:
        parts.append(f"  <li>{_inline_text(item)}</li>")
    parts.append("</ol>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------


def _smart_typography(html: str) -> str:
    """Apply smart quotes and ellipsis to text nodes, skipping HTML tags and <code>."""
    parts = re.split(r"(<[^>]+>)", html)
    in_code = False
    for i, part in enumerate(parts):
        if part.startswith("<code"):
            in_code = True
            continue
        if part == "</code>":
            in_code = False
            continue
        if part.startswith("<") or in_code:
            continue
        # Text node — apply typography
        part = part.replace("...", "&hellip;")
        part = re.sub(r'(^|[\s(])"', r"\1&ldquo;", part)
        part = part.replace('"', "&rdquo;")
        part = re.sub(r"(^|[\s(])'", r"\1&lsquo;", part)
        part = part.replace("'", "&rsquo;")
        parts[i] = part
    return "".join(parts)


# ---------------------------------------------------------------------------
# Inline markdown → HTML
# ---------------------------------------------------------------------------


def _inline_text(text: str) -> str:
    """Convert inline markdown to HTML with typographic entities."""
    # Escape HTML-significant characters
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")

    # Markdown → HTML (order: links, bold+italic combo, bold, italic, code)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Unicode typographic characters (after markdown so patterns still match)
    text = text.replace("\u2019", "&rsquo;")
    text = text.replace("\u2018", "&lsquo;")
    text = text.replace("\u201c", "&ldquo;")
    text = text.replace("\u201d", "&rdquo;")
    text = text.replace("\u2014", "&mdash;")
    text = text.replace("\u2013", "&ndash;")
    text = text.replace("\u2192", "&rarr;")
    text = text.replace("\uFDFA", "&#xFDFA;")

    # Smart ASCII quotes and ellipsis — only in text nodes, not in HTML tags/code
    text = _smart_typography(text)

    return text
