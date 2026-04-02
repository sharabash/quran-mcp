from __future__ import annotations

from quran_mcp.lib.tafsir.search import clean_tafsir_html


def test_empty_input():
    assert clean_tafsir_html("") == ""


def test_whitespace_only():
    assert clean_tafsir_html("   \n\n  ") == ""


def test_plain_text_unchanged():
    assert clean_tafsir_html("This is plain text.") == "This is plain text."


def test_h2_tags_removed_content_preserved():
    result = clean_tafsir_html("<h2>Chapter Title</h2>Some text")
    assert "Chapter Title" in result
    assert "<h2>" not in result
    assert "</h2>" not in result


def test_p_tags_become_newlines():
    result = clean_tafsir_html("<p>First paragraph</p><p>Second paragraph</p>")
    assert "First paragraph" in result
    assert "Second paragraph" in result
    assert "<p>" not in result
    assert "\n\n" in result


def test_br_tags_become_newlines():
    result = clean_tafsir_html("line one<br>line two<br/>line three")
    assert "line one\nline two\nline three" == result


def test_div_tags_removed_content_preserved():
    result = clean_tafsir_html("<div class='wrapper'>inner content</div>")
    assert "inner content" in result
    assert "<div" not in result
    assert "</div>" not in result


def test_span_with_attributes_removed():
    result = clean_tafsir_html('<span class="arabic rtl">some text</span>')
    assert "some text" in result
    assert "<span" not in result


def test_sup_footnote_markers_become_bracketed():
    result = clean_tafsir_html("reference<sup>1</sup> here")
    assert "[1]" in result
    assert "<sup>" not in result


def test_sup_with_attributes():
    result = clean_tafsir_html('note<sup class="fn">42</sup> text')
    assert "[42]" in result


def test_html_entities_decoded():
    result = clean_tafsir_html("A &amp; B &lt; C &gt; D &quot;E&quot;")
    assert "A & B < C > D" in result


def test_nested_tags():
    result = clean_tafsir_html('<p><span class="x">nested text</span></p>')
    assert "nested text" in result
    assert "<p>" not in result
    assert "<span" not in result


def test_multiple_consecutive_newlines_collapsed():
    result = clean_tafsir_html("<p>a</p>\n\n\n\n<p>b</p>")
    assert "\n\n\n" not in result
    assert "a" in result
    assert "b" in result


def test_multiple_spaces_collapsed():
    result = clean_tafsir_html("word1     word2      word3")
    assert result == "word1 word2 word3"


def test_arabic_text_with_html_preserved():
    html = '<p><span class="arabic">بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ</span></p>'
    result = clean_tafsir_html(html)
    assert "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ" in result
    assert "<span" not in result
    assert "<p>" not in result


def test_complex_tafsir_structure():
    html = (
        "<h2>Tafsir of Ayat al-Kursi</h2>"
        "<p>Ibn Kathir said:</p>"
        "<p><span class='arabic'>اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ</span></p>"
        "<div>This verse<sup>1</sup> is the greatest.</div>"
    )
    result = clean_tafsir_html(html)
    assert "Tafsir of Ayat al-Kursi" in result
    assert "Ibn Kathir said:" in result
    assert "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ" in result
    assert "[1]" in result
    assert "<" not in result


def test_nbsp_entity_decoded():
    result = clean_tafsir_html("word&nbsp;another")
    assert "\xa0" not in result
    assert "word" in result
    assert "another" in result


def test_adjacent_closing_opening_p_tags():
    result = clean_tafsir_html("</p><p>next")
    assert "<p>" not in result
    assert "</p>" not in result


def test_bold_italic_stripped():
    result = clean_tafsir_html("<b>bold</b> and <i>italic</i> and <em>em</em> and <strong>strong</strong>")
    assert "bold" in result
    assert "italic" in result
    assert "em" in result
    assert "strong" in result
    assert "<b>" not in result
    assert "<i>" not in result


def test_anchor_tags_stripped():
    result = clean_tafsir_html('<a href="http://example.com">link text</a>')
    assert "link text" in result
    assert "<a" not in result
    assert "href" not in result
