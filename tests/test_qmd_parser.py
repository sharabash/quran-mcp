"""Tests for quran_mcp.lib.documentation.qmd_parser.

Covers:
  - _split_frontmatter: YAML frontmatter extraction
  - _convert_body: block-level markdown → HTML (directives, headings, tables, etc.)
  - _render_verse: verse directive rendering
  - _render_table: pipe table → HTML table
  - _inline_text: inline markdown → HTML with typography
  - _smart_typography: ASCII quote / ellipsis conversion
  - parse_qmd: end-to-end with a real QMD file from the manifest
"""

from __future__ import annotations

from quran_mcp.lib.documentation.qmd_parser import (
    _convert_body,
    _inline_text,
    _render_table,
    _render_verse,
    _smart_typography,
    _split_frontmatter,
    parse_qmd,
)


# ---------------------------------------------------------------------------
# _split_frontmatter — YAML frontmatter extraction
# ---------------------------------------------------------------------------


class TestSplitFrontmatter:
    def test_valid_frontmatter(self):
        text = '---\ntitle: "Hello"\ncategory: test\n---\nBody text here.'
        fm, body = _split_frontmatter(text)
        assert fm["title"] == "Hello"
        assert fm["category"] == "test"
        assert body == "Body text here."

    def test_no_frontmatter(self):
        text = "Just some plain text."
        fm, body = _split_frontmatter(text)
        assert fm == {}
        assert body == text

    def test_not_starting_with_dashes(self):
        text = "Hello\n---\ntitle: oops\n---\nBody"
        fm, body = _split_frontmatter(text)
        assert fm == {}
        assert body == text

    def test_frontmatter_with_list(self):
        text = "---\nitems:\n  - one\n  - two\n---\nBody"
        fm, body = _split_frontmatter(text)
        assert fm["items"] == ["one", "two"]
        assert body == "Body"


# ---------------------------------------------------------------------------
# _convert_body — block-level markdown → HTML
# ---------------------------------------------------------------------------


class TestConvertBody:
    def test_verse_directive(self):
        body = ":::verse\nref: 2:255\n\nSome arabic text\n:::"
        result = _convert_body(body)
        assert 'class="vb"' in result
        assert 'class="vref"' in result
        assert "2:255" in result

    def test_h2_heading(self):
        result = _convert_body("## My Heading")
        assert "<h2>" in result
        assert "My Heading" in result
        assert "</h2>" in result

    def test_h3_heading(self):
        result = _convert_body("### Sub Heading")
        assert "<h3>" in result
        assert "Sub Heading" in result
        assert "</h3>" in result

    def test_heading_strips_anchor_id(self):
        result = _convert_body("## Title {#my-anchor}")
        assert "<h2>Title</h2>" in result
        assert "{#my-anchor}" not in result

    def test_horizontal_rule(self):
        result = _convert_body("---")
        assert "<hr>" in result

    def test_pipe_table(self):
        body = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = _convert_body(body)
        assert "<table>" in result
        assert "<th>" in result
        assert "<td>" in result

    def test_ordered_list(self):
        body = "1. First item\n2. Second item\n3. Third item"
        result = _convert_body(body)
        assert "<ol>" in result
        assert "<li>" in result
        assert "First item" in result
        assert "Third item" in result

    def test_image(self):
        body = "![Alt text](image.png)"
        result = _convert_body(body)
        assert "<figure" in result
        assert 'alt="Alt text"' in result
        assert "/documentation/assets/image.png" in result
        assert "<figcaption>" in result

    def test_paragraph(self):
        result = _convert_body("Some plain text here.")
        assert "<p>" in result
        assert "Some plain text here." in result

    def test_empty_lines_skipped(self):
        result = _convert_body("\n\n\n")
        assert result == ""


# ---------------------------------------------------------------------------
# _render_verse — verse directive rendering
# ---------------------------------------------------------------------------


class TestRenderVerse:
    def test_arabic_and_translation(self):
        fields = {"ref": "2:255", "link": "https://quran.com/2/255"}
        body = ["Arabic text here", "---", "Translation text here"]
        result = _render_verse(fields, body)
        assert 'class="vb"' in result
        assert 'class="ar"' in result
        assert "Arabic text here" in result
        assert 'class="tr"' in result
        assert "Translation text here" in result

    def test_ref_with_link(self):
        fields = {"ref": "1:1", "link": "https://quran.com/1/1"}
        body = ["Arabic"]
        result = _render_verse(fields, body)
        assert '<a href="https://quran.com/1/1">1:1</a>' in result

    def test_ref_without_link(self):
        fields = {"ref": "1:1"}
        body = ["Arabic"]
        result = _render_verse(fields, body)
        assert '<span class="vref">1:1</span>' in result
        assert "<a " not in result

    def test_with_attribution(self):
        fields = {"ref": "2:7", "attribution": "Abdel Haleem"}
        body = ["Arabic", "---", "Translation"]
        result = _render_verse(fields, body)
        assert 'class="at"' in result
        assert "Abdel Haleem" in result

    def test_arabic_only_no_separator(self):
        fields = {"ref": "112:1"}
        body = ["Arabic only text"]
        result = _render_verse(fields, body)
        assert 'class="ar"' in result
        assert "Arabic only text" in result
        assert 'class="tr"' not in result


# ---------------------------------------------------------------------------
# _render_table — pipe table → HTML table
# ---------------------------------------------------------------------------


class TestRenderTable:
    def test_standard_table(self):
        lines = [
            "| Name | Value |",
            "|------|-------|",
            "| foo  | 42    |",
        ]
        result = _render_table(lines)
        assert "<table>" in result
        assert "<th>Name</th>" in result
        assert "<th>Value</th>" in result
        assert "<td>foo</td>" in result
        assert "<td>42</td>" in result
        assert "</table>" in result

    def test_single_row_returns_empty(self):
        lines = ["| only header |"]
        assert _render_table(lines) == ""

    def test_multiple_data_rows(self):
        lines = [
            "| Col |",
            "|-----|",
            "| a   |",
            "| b   |",
            "| c   |",
        ]
        result = _render_table(lines)
        assert result.count("<td>") == 3
        assert "<td>a</td>" in result
        assert "<td>b</td>" in result
        assert "<td>c</td>" in result


# ---------------------------------------------------------------------------
# _inline_text — inline markdown → HTML with typography
# ---------------------------------------------------------------------------


class TestInlineText:
    def test_link(self):
        result = _inline_text("[Quran](https://quran.com)")
        assert '<a href="https://quran.com">Quran</a>' in result

    def test_bold(self):
        result = _inline_text("**important**")
        assert "<strong>important</strong>" in result

    def test_italic(self):
        result = _inline_text("*emphasis*")
        assert "<em>emphasis</em>" in result

    def test_code(self):
        result = _inline_text("`some_code`")
        assert "<code>some_code</code>" in result

    def test_bold_italic(self):
        result = _inline_text("***both***")
        assert "<strong><em>both</em></strong>" in result

    def test_html_escaping_ampersand(self):
        result = _inline_text("A & B")
        assert "&amp;" in result
        assert "A &amp; B" in result

    def test_html_escaping_angle_brackets(self):
        result = _inline_text("<script>")
        assert "&lt;script&gt;" in result

    def test_unicode_right_single_quote(self):
        result = _inline_text("it\u2019s")
        assert "&rsquo;" in result

    def test_unicode_em_dash(self):
        result = _inline_text("word\u2014word")
        assert "&mdash;" in result

    def test_unicode_left_double_quote(self):
        result = _inline_text("\u201chello\u201d")
        assert "&ldquo;" in result
        assert "&rdquo;" in result


# ---------------------------------------------------------------------------
# _smart_typography — ASCII quote / ellipsis conversion
# ---------------------------------------------------------------------------


class TestSmartTypography:
    def test_double_quotes(self):
        result = _smart_typography('"hello"')
        assert "&ldquo;" in result
        assert "&rdquo;" in result

    def test_single_quotes(self):
        result = _smart_typography("'world'")
        assert "&lsquo;" in result
        assert "&rsquo;" in result

    def test_ellipsis(self):
        result = _smart_typography("wait...")
        assert "&hellip;" in result
        assert "..." not in result

    def test_code_not_transformed(self):
        result = _smart_typography('<code>"quoted"</code>')
        assert "&ldquo;" not in result
        assert "&rdquo;" not in result
        assert '"quoted"' in result

    def test_text_outside_code_transformed(self):
        result = _smart_typography('"before" <code>inside</code> "after"')
        assert "&ldquo;" in result
        assert "&rdquo;" in result


# ---------------------------------------------------------------------------
# parse_qmd — end-to-end with a real QMD file from the manifest
# ---------------------------------------------------------------------------


class TestParseQmd:
    def test_real_qmd_file(self):
        result = parse_qmd("sealing-of-hearts.qmd")

        assert "id" in result
        assert "title" in result
        assert "prompt_html" in result
        assert "tools" in result
        assert "response_html" in result
        assert "generated" in result

        assert result["generated"] is True
        assert isinstance(result["id"], str)
        assert result["id"].startswith("usage-showcase-")
        assert isinstance(result["title"], str)
        assert len(result["title"]) > 0
        assert isinstance(result["tools"], list)
        assert len(result["tools"]) > 0

        html = result["response_html"]
        assert isinstance(html, str)
        assert len(html) > 0
        assert "<" in html  # contains HTML tags

    def test_real_qmd_file_has_expected_fields(self):
        result = parse_qmd("sealing-of-hearts.qmd")
        assert result["category"] == "Thematic exploration"
        assert "model" in result
        assert "date" in result
        assert result["prerequisite_tools"] == ["fetch_grounding_rules", "list_editions"]

    def test_prompt_html_has_smart_quotes(self):
        result = parse_qmd("sealing-of-hearts.qmd")
        assert "&ldquo;" in result["prompt_html"]
        assert "&rdquo;" in result["prompt_html"]
