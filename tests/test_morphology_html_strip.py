from __future__ import annotations

from quran_mcp.lib.morphology.html_strip import strip_html


def test_strip_bold_tag():
    assert strip_html("<b>bold</b>") == "bold"


def test_strip_italic_tag():
    assert strip_html("<i>italic</i>") == "italic"


def test_strip_em_tag():
    assert strip_html("<em>emphasis</em>") == "emphasis"


def test_strip_strong_tag():
    assert strip_html("<strong>strong</strong>") == "strong"


def test_strip_span_tag():
    assert strip_html("<span>text</span>") == "text"


def test_nested_tags():
    assert strip_html("<b><i>nested</i></b>") == "nested"


def test_deeply_nested_tags():
    assert strip_html("<span><b><i>deep</i></b></span>") == "deep"


def test_html_entity_amp():
    assert strip_html("A &amp; B") == "A &amp; B"


def test_html_entities_preserved():
    assert strip_html("&lt;tag&gt;") == "&lt;tag&gt;"


def test_none_input():
    assert strip_html(None) is None


def test_empty_string():
    assert strip_html("") == ""


def test_plain_text_passthrough():
    assert strip_html("no html here") == "no html here"


def test_plain_text_with_special_chars():
    assert strip_html("word (root: k-t-b)") == "word (root: k-t-b)"


def test_arabic_text_with_tags():
    assert strip_html("<b>كَتَبَ</b>") == "كَتَبَ"


def test_arabic_text_with_span():
    assert strip_html('<span class="ar">بِسْمِ اللَّهِ</span>') == "بِسْمِ اللَّهِ"


def test_self_closing_br():
    assert strip_html("line<br/>break") == "linebreak"


def test_self_closing_hr():
    assert strip_html("above<hr/>below") == "abovebelow"


def test_br_without_slash():
    assert strip_html("line<br>break") == "linebreak"


def test_span_with_class_attribute():
    assert strip_html('<span class="at">annotated</span>') == "annotated"


def test_span_with_multiple_attributes():
    assert strip_html('<span class="x" id="y">text</span>') == "text"


def test_multiple_consecutive_tags():
    assert strip_html("<b>one</b><i>two</i><em>three</em>") == "onetwothree"


def test_multiple_tags_with_spaces():
    assert strip_html("<b>one</b> <i>two</i> <em>three</em>") == "one two three"


def test_whitespace_only_after_strip():
    assert strip_html("<b>  </b>") == ""


def test_leading_trailing_whitespace_stripped():
    assert strip_html("  <b>text</b>  ") == "text"


def test_inner_whitespace_preserved():
    assert strip_html("<b>two words</b>") == "two words"
