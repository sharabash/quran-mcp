from __future__ import annotations

import hashlib
import hmac
import time
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ConfigDict

from quran_mcp.lib.config.settings import Settings
from quran_mcp.lib.presentation.continuation import (
    _ContinuationToken,
    _b64url_decode,
    _b64url_encode,
    _canonical_json,
    _derive_continuation_secret,
)
from quran_mcp.lib.presentation.pagination import (
    ContinuationError,
    ContinuationPaginationMeta,
    PaginationMeta,
    build_checked_continuation_meta,
    build_continuation_meta,
    choose_auto_page_size,
    decode_continuation_request_model,
    decode_continuation_token,
    encode_continuation_token,
    enforce_token_cap,
    enforce_token_cap_dict,
    ensure_not_exhausted,
    estimate_tokens,
    hash_continuation_request,
    paginate,
)


# ---------------------------------------------------------------------------
# Fixtures — real Settings instance instead of MagicMock
# ---------------------------------------------------------------------------


def _make_test_settings(*, secret: str = "test-secret-key", ttl: int = 3600) -> Settings:
    return Settings(
        continuation={"token_secret": secret, "ttl_seconds": ttl},
        health={"token": ""},
    )


@pytest.fixture(autouse=True)
def _patch_settings():
    settings = _make_test_settings()
    with patch(
        "quran_mcp.lib.presentation.continuation.get_settings",
        return_value=settings,
        create=True,
    ):
        yield settings


def _simple_meta(page: int = 1, page_size: int = 10, total: int = 0) -> PaginationMeta:
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginationMeta(
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=total_pages,
        has_more=page < total_pages,
    )


class _SearchState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    surah: int | None = None


# ---------------------------------------------------------------------------
# paginate
# ---------------------------------------------------------------------------


def test_paginate_first_page():
    items = list(range(25))
    page_items, meta = paginate(items, page=1, page_size=10)
    assert page_items == list(range(10))
    assert meta.page == 1
    assert meta.total_items == 25
    assert meta.total_pages == 3
    assert meta.has_more is True


def test_paginate_middle_page():
    items = list(range(25))
    page_items, meta = paginate(items, page=2, page_size=10)
    assert page_items == list(range(10, 20))
    assert meta.page == 2
    assert meta.has_more is True


def test_paginate_last_page():
    items = list(range(25))
    page_items, meta = paginate(items, page=3, page_size=10)
    assert page_items == list(range(20, 25))
    assert meta.page == 3
    assert meta.has_more is False


def test_paginate_empty_list():
    page_items, meta = paginate([], page=1, page_size=10)
    assert page_items == []
    assert meta.total_items == 0
    assert meta.total_pages == 1
    assert meta.has_more is False


def test_paginate_beyond_total_pages():
    items = list(range(5))
    page_items, meta = paginate(items, page=99, page_size=10)
    assert page_items == []
    assert meta.page == 99
    assert meta.total_items == 5
    assert meta.has_more is False


def test_paginate_single_item():
    page_items, meta = paginate(["only"], page=1, page_size=10)
    assert page_items == ["only"]
    assert meta.total_items == 1
    assert meta.total_pages == 1
    assert meta.has_more is False


def test_paginate_page_size_larger_than_total():
    items = list(range(3))
    page_items, meta = paginate(items, page=1, page_size=100)
    assert page_items == [0, 1, 2]
    assert meta.total_pages == 1
    assert meta.has_more is False


def test_paginate_exact_fit():
    items = list(range(10))
    page_items, meta = paginate(items, page=1, page_size=10)
    assert page_items == list(range(10))
    assert meta.total_pages == 1
    assert meta.has_more is False


# ---------------------------------------------------------------------------
# encode / decode continuation token — round-trip
# ---------------------------------------------------------------------------


def test_continuation_round_trip():
    state = {"surah": 2, "ayah": 255}
    token = encode_continuation_token(
        tool_name="fetch_quran",
        next_page=3,
        page_size=10,
        request_state=state,
    )
    page, size, decoded_state = decode_continuation_token(
        token, tool_name="fetch_quran"
    )
    assert page == 3
    assert size == 10
    assert decoded_state == {"ayah": 255, "surah": 2}


def test_continuation_round_trip_with_explicit_state():
    state = {"edition": "ar-uthmani", "range": "2:1-5"}
    token = encode_continuation_token(
        tool_name="search_quran",
        next_page=2,
        page_size=18,
        request_state=state,
    )
    page, size, decoded_state = decode_continuation_token(
        token,
        tool_name="search_quran",
        request_state=state,
    )
    assert page == 2
    assert size == 18
    assert decoded_state["edition"] == "ar-uthmani"


def test_decode_continuation_request_model_round_trip():
    state = {"query": "mercy", "surah": 2}
    token = encode_continuation_token(
        tool_name="search_quran",
        next_page=3,
        page_size=18,
        request_state=state,
    )
    page, size, request_state = decode_continuation_request_model(
        token,
        tool_name="search_quran",
        state_model=_SearchState,
    )
    assert page == 3
    assert size == 18
    assert request_state.query == "mercy"
    assert request_state.surah == 2


def test_decode_continuation_request_model_validates_shape():
    state = {"query": "mercy", "surah": 2}
    token = encode_continuation_token(
        tool_name="search_quran",
        next_page=3,
        page_size=18,
        request_state=state,
    )
    with pytest.raises(ContinuationError) as exc_info:
        decode_continuation_request_model(
            token,
            tool_name="search_quran",
            state_model=_SearchState,
            explicit_state={"surah": 3},
        )
    assert exc_info.value.reason == "conflict"


def test_continuation_empty_request_state_round_trips():
    token = encode_continuation_token(
        tool_name="fetch_quran",
        next_page=2,
        page_size=5,
        request_state={},
    )
    page, page_size, request_state = decode_continuation_token(
        token,
        tool_name="fetch_quran",
    )
    assert page == 2
    assert page_size == 5
    assert request_state == {}

    page, page_size, request_state = decode_continuation_token(
        token,
        tool_name="fetch_quran",
        request_state={},
    )
    assert page == 2
    assert page_size == 5
    assert request_state == {}


def test_continuation_empty_request_state_is_explicit_modern_shape():
    token = encode_continuation_token(
        tool_name="fetch_quran",
        next_page=2,
        page_size=5,
        request_state={},
    )
    payload_part, _ = token.split(".", 1)
    payload = _ContinuationToken.model_validate_json(_b64url_decode(payload_part))
    assert payload.v == 1
    assert "r" in payload.model_fields_set
    assert payload.r == {}


# ---------------------------------------------------------------------------
# decode — tampered token
# ---------------------------------------------------------------------------


def test_continuation_tampered_raises():
    token = encode_continuation_token(
        tool_name="fetch_quran",
        next_page=2,
        page_size=10,
        request_state={"x": 1},
    )
    payload, sig = token.split(".", 1)
    tampered = payload + "XX." + sig
    with pytest.raises(ContinuationError) as exc_info:
        decode_continuation_token(tampered, tool_name="fetch_quran")
    assert exc_info.value.reason in ("tampered", "invalid")


def test_continuation_tampered_signature_raises():
    token = encode_continuation_token(
        tool_name="fetch_quran",
        next_page=2,
        page_size=10,
        request_state={"x": 1},
    )
    payload, sig = token.split(".", 1)
    bad_sig = sig[:-4] + "XXXX"
    with pytest.raises(ContinuationError) as exc_info:
        decode_continuation_token(f"{payload}.{bad_sig}", tool_name="fetch_quran")
    assert exc_info.value.reason == "tampered"


# ---------------------------------------------------------------------------
# decode — expired token
# ---------------------------------------------------------------------------


def test_continuation_expired_raises():
    past = int(time.time()) - 10
    token = encode_continuation_token(
        tool_name="fetch_quran",
        next_page=2,
        page_size=10,
        request_state={"x": 1},
        expires_at=past,
    )
    with pytest.raises(ContinuationError) as exc_info:
        decode_continuation_token(token, tool_name="fetch_quran")
    assert exc_info.value.reason == "expired"


# ---------------------------------------------------------------------------
# decode — wrong tool_name
# ---------------------------------------------------------------------------


def test_continuation_wrong_tool_raises():
    token = encode_continuation_token(
        tool_name="fetch_quran",
        next_page=2,
        page_size=10,
        request_state={"x": 1},
    )
    with pytest.raises(ContinuationError) as exc_info:
        decode_continuation_token(token, tool_name="search_tafsir")
    assert exc_info.value.reason == "conflict"
    assert "fetch_quran" in str(exc_info.value)


# ---------------------------------------------------------------------------
# decode — request state mismatch
# ---------------------------------------------------------------------------


def test_continuation_state_mismatch_raises():
    token = encode_continuation_token(
        tool_name="fetch_quran",
        next_page=2,
        page_size=10,
        request_state={"edition": "ar-uthmani"},
    )
    with pytest.raises(ContinuationError) as exc_info:
        decode_continuation_token(
            token,
            tool_name="fetch_quran",
            request_state={"edition": "en-hilali"},
        )
    assert exc_info.value.reason == "conflict"


# ---------------------------------------------------------------------------
# decode — malformed token
# ---------------------------------------------------------------------------


def test_continuation_no_dot_raises():
    with pytest.raises(ContinuationError) as exc_info:
        decode_continuation_token("nodothere", tool_name="fetch_quran")
    assert exc_info.value.reason == "invalid"


def test_continuation_garbage_raises():
    with pytest.raises(ContinuationError):
        decode_continuation_token("!!!.!!!", tool_name="fetch_quran")


# ---------------------------------------------------------------------------
# enforce_token_cap — flat list
# ---------------------------------------------------------------------------


def test_enforce_token_cap_under_cap():
    items = ["short"] * 5
    meta = _simple_meta(page=1, page_size=10, total=5)
    result_items, result_meta = enforce_token_cap(items, meta, cap=25_000)
    assert result_items == items
    assert result_meta.has_more is False
    assert result_meta.total_pages == 1


def test_enforce_token_cap_over_cap_truncates():
    big_text = "x" * 5000
    items = [big_text] * 20
    meta = _simple_meta(page=1, page_size=20, total=20)
    result_items, result_meta = enforce_token_cap(items, meta, cap=6000)
    assert len(result_items) < 20
    assert result_meta.has_more is True
    assert result_meta.total_pages > 1


def test_enforce_token_cap_empty_items():
    meta = _simple_meta(page=1, page_size=10, total=0)
    result_items, result_meta = enforce_token_cap([], meta, cap=25_000)
    assert result_items == []
    assert result_meta.has_more is False
    assert result_meta.total_items == 0


def test_enforce_token_cap_arabic_uses_lower_ratio():
    arabic_text = "\u0628\u0633\u0645 \u0627\u0644\u0644\u0647 \u0627\u0644\u0631\u062d\u0645\u0646 \u0627\u0644\u0631\u062d\u064a\u0645" * 200
    english_text = "In the name of God the Most Gracious the Most Merciful " * 200
    arabic_tokens = estimate_tokens(arabic_text)
    english_tokens = estimate_tokens(english_text)
    arabic_ratio = len(arabic_text) / arabic_tokens
    english_ratio = len(english_text) / english_tokens
    assert arabic_ratio < english_ratio


def test_enforce_token_cap_with_page_entry_fn():
    items = ["item_a", "item_b", "item_c"]
    meta = _simple_meta(page=1, page_size=10, total=3)
    def entry_fn(item: str) -> tuple[None, str]:
        return (None, item)
    result_items, result_meta = enforce_token_cap(
        items, meta, cap=25_000, page_entry_fn=entry_fn
    )
    assert result_items == items
    assert len(result_meta.pages) == 3
    assert result_meta.pages[0].ayah_key == "item_a"


def test_enforce_token_cap_page_2():
    big_text = "y" * 4000
    items = [big_text] * 10
    meta = _simple_meta(page=2, page_size=10, total=10)
    result_items, result_meta = enforce_token_cap(items, meta, cap=5000)
    assert result_meta.page == 2
    assert result_meta.total_pages > 1


# ---------------------------------------------------------------------------
# enforce_token_cap_dict
# ---------------------------------------------------------------------------


def test_enforce_token_cap_dict_under_cap():
    results = {"ed-a": ["text1", "text2"], "ed-b": ["text3"]}
    meta = _simple_meta(page=1, page_size=10, total=3)
    result_dict, result_meta = enforce_token_cap_dict(results, meta, cap=25_000)
    assert "ed-a" in result_dict
    assert "ed-b" in result_dict
    assert result_meta.has_more is False


def test_enforce_token_cap_dict_over_cap():
    big = "z" * 5000
    results = {"ed-a": [big] * 10}
    meta = _simple_meta(page=1, page_size=10, total=10)
    result_dict, result_meta = enforce_token_cap_dict(results, meta, cap=6000)
    total_returned = sum(len(v) for v in result_dict.values())
    assert total_returned < 10
    assert result_meta.has_more is True


def test_enforce_token_cap_dict_empty():
    meta = _simple_meta(page=1, page_size=10, total=0)
    result_dict, result_meta = enforce_token_cap_dict({}, meta, cap=25_000)
    assert result_dict == {}


# ---------------------------------------------------------------------------
# choose_auto_page_size
# ---------------------------------------------------------------------------


def test_choose_auto_page_size_known_tool():
    size = choose_auto_page_size("search_quran")
    assert size == 18


def test_choose_auto_page_size_claude_host():
    size = choose_auto_page_size("search_quran", host="claude")
    assert size == 10


def test_choose_auto_page_size_unknown_tool():
    size = choose_auto_page_size("nonexistent_tool")
    assert size == 10


def test_choose_auto_page_size_fetch_tools():
    assert choose_auto_page_size("fetch_quran") == 80
    assert choose_auto_page_size("fetch_quran", host="claude") == 50
    assert choose_auto_page_size("fetch_tafsir") == 28
    assert choose_auto_page_size("fetch_tafsir", host="claude") == 20


# ---------------------------------------------------------------------------
# build_continuation_meta
# ---------------------------------------------------------------------------


def test_build_continuation_meta_has_more():
    internal_meta = PaginationMeta(
        page=1,
        page_size=10,
        total_items=25,
        total_pages=3,
        has_more=True,
    )
    result = build_continuation_meta(
        tool_name="fetch_quran",
        request_state={"range": "2:1-10"},
        internal_meta=internal_meta,
        page_size=10,
    )
    assert isinstance(result, ContinuationPaginationMeta)
    assert result.has_more is True
    assert result.continuation is not None
    assert result.total_items == 25


def test_build_continuation_meta_no_more():
    internal_meta = PaginationMeta(
        page=3,
        page_size=10,
        total_items=25,
        total_pages=3,
        has_more=False,
    )
    result = build_continuation_meta(
        tool_name="fetch_quran",
        request_state={"range": "2:1-10"},
        internal_meta=internal_meta,
        page_size=10,
    )
    assert result.has_more is False
    assert result.continuation is None


def test_build_continuation_meta_token_decodes():
    internal_meta = PaginationMeta(
        page=1,
        page_size=5,
        total_items=15,
        total_pages=3,
        has_more=True,
    )
    state = {"edition": "ar-uthmani"}
    result = build_continuation_meta(
        tool_name="fetch_quran",
        request_state=state,
        internal_meta=internal_meta,
        page_size=5,
    )
    page, size, decoded_state = decode_continuation_token(
        result.continuation, tool_name="fetch_quran"
    )
    assert page == 2
    assert size == 5
    assert decoded_state == {"edition": "ar-uthmani"}


def test_build_checked_continuation_meta_validates_exhaustion():
    internal_meta = PaginationMeta(
        page=3,
        page_size=10,
        total_items=25,
        total_pages=3,
        has_more=False,
    )
    with pytest.raises(ContinuationError) as exc_info:
        build_checked_continuation_meta(
            continuation="opaque-token",
            requested_page=4,
            tool_name="fetch_quran",
            request_state={"query": "mercy"},
            internal_meta=internal_meta,
            page_size=10,
        )
    assert exc_info.value.reason == "exhausted"


def test_build_checked_continuation_meta_accepts_model_request_state():
    internal_meta = PaginationMeta(
        page=1,
        page_size=18,
        total_items=25,
        total_pages=2,
        has_more=True,
    )
    result = build_checked_continuation_meta(
        continuation=None,
        requested_page=1,
        tool_name="search_quran",
        request_state=_SearchState(query="mercy", surah=2),
        internal_meta=internal_meta,
        page_size=18,
    )
    assert result.continuation is not None
    page, size, decoded_state = decode_continuation_token(
        result.continuation,
        tool_name="search_quran",
    )
    assert page == 2
    assert size == 18
    assert decoded_state == {"query": "mercy", "surah": 2}


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------


def test_estimate_tokens_arabic_higher_density():
    arabic = "\u0628\u0633\u0645 \u0627\u0644\u0644\u0647" * 100
    english = "bismillah " * 100
    assert estimate_tokens(arabic) > estimate_tokens(english)


def test_estimate_tokens_empty_string():
    assert estimate_tokens("") == 0


def test_estimate_tokens_list():
    items = ["hello", "world", "test"]
    result = estimate_tokens(items)
    assert result > 0


# ---------------------------------------------------------------------------
# ContinuationError attributes
# ---------------------------------------------------------------------------


def test_continuation_error_has_reason_and_message():
    err = ContinuationError("expired", "Token has expired")
    assert err.reason == "expired"
    assert err.message == "Token has expired"
    assert "Token has expired" in str(err)


# ---------------------------------------------------------------------------
# Legacy token helpers
# ---------------------------------------------------------------------------


def _encode_legacy_token(
    *,
    tool_name: str,
    next_page: int,
    page_size: int,
    request_state: dict,
    expires_at: int | None = None,
) -> str:
    from quran_mcp.lib.presentation.continuation import continuation_ttl_seconds

    payload = {
        "v": 1,
        "t": tool_name,
        "n": next_page,
        "s": page_size,
        "q": hash_continuation_request(request_state),
        "e": expires_at if expires_at is not None else int(time.time()) + continuation_ttl_seconds(),
    }
    payload_json = _canonical_json(payload)
    payload_bytes = payload_json.encode("utf-8")
    signature = hmac.new(
        _derive_continuation_secret(), payload_bytes, hashlib.sha256
    ).digest()
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


# ---------------------------------------------------------------------------
# Legacy token round-trip
# ---------------------------------------------------------------------------


def test_legacy_token_round_trip():
    original_state = {"surah": 2, "ayah": 255}
    token = _encode_legacy_token(
        tool_name="fetch_quran",
        next_page=3,
        page_size=10,
        request_state=original_state,
    )
    payload_part, _ = token.split(".", 1)
    payload = _ContinuationToken.model_validate_json(_b64url_decode(payload_part))
    assert "r" not in payload.model_fields_set
    page, size, decoded_state = decode_continuation_token(
        token,
        tool_name="fetch_quran",
        request_state=original_state,
    )
    assert page == 3
    assert size == 10
    assert decoded_state == {"ayah": 255, "surah": 2}


# ---------------------------------------------------------------------------
# Legacy token without caller state fails
# ---------------------------------------------------------------------------


def test_legacy_token_without_caller_state_fails():
    original_state = {"edition": "ar-uthmani", "range": "2:1-10"}
    token = _encode_legacy_token(
        tool_name="fetch_quran",
        next_page=2,
        page_size=5,
        request_state=original_state,
    )
    with pytest.raises(ContinuationError) as exc_info:
        decode_continuation_token(token, tool_name="fetch_quran")
    assert exc_info.value.reason == "legacy"


# ---------------------------------------------------------------------------
# Legacy token with wrong caller state fails
# ---------------------------------------------------------------------------


def test_legacy_token_with_wrong_caller_state_fails():
    original_state = {"edition": "ar-uthmani", "range": "2:1-10"}
    token = _encode_legacy_token(
        tool_name="fetch_quran",
        next_page=2,
        page_size=5,
        request_state=original_state,
    )
    wrong_state = {"edition": "en-hilali", "range": "3:1-5"}
    with pytest.raises(ContinuationError) as exc_info:
        decode_continuation_token(
            token,
            tool_name="fetch_quran",
            request_state=wrong_state,
        )
    assert exc_info.value.reason == "conflict"


# ---------------------------------------------------------------------------
# Token size bounds
# ---------------------------------------------------------------------------


def test_token_size_reasonable():
    state = {"edition": "ar-uthmani", "range": "2:255-260", "query": "mercy"}
    token = encode_continuation_token(
        tool_name="fetch_quran",
        next_page=5,
        page_size=20,
        request_state=state,
    )
    assert len(token.encode("utf-8")) < 512


def test_token_with_large_request_state():
    large_state = {f"ayah_{i}": f"{i // 10 + 1}:{i}" for i in range(200)}
    token = encode_continuation_token(
        tool_name="fetch_quran",
        next_page=2,
        page_size=10,
        request_state=large_state,
    )
    assert isinstance(token, str)
    assert "." in token
    page, size, decoded_state = decode_continuation_token(
        token, tool_name="fetch_quran"
    )
    assert page == 2
    assert size == 10
    assert len(decoded_state) == 200


# ---------------------------------------------------------------------------
# ensure_not_exhausted
# ---------------------------------------------------------------------------


def test_ensure_not_exhausted_raises_on_over_page():
    with pytest.raises(ContinuationError) as exc_info:
        ensure_not_exhausted(
            continuation="some-token-value",
            requested_page=6,
            total_pages=5,
        )
    assert exc_info.value.reason == "exhausted"


def test_ensure_not_exhausted_allows_valid_page():
    ensure_not_exhausted(
        continuation="some-token-value",
        requested_page=3,
        total_pages=5,
    )
