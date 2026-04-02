"""Tests for quran_mcp.lib.presentation.client_hint.

Covers:
  - _detect_host: header-based priority (openai-session → claude baggage →
    clientInfo name → fallback)
  - _detect_platform: mobile regex detection vs desktop fallback
"""

from __future__ import annotations

from quran_mcp.lib.presentation.client_hint import _detect_host, _detect_platform


# ---------------------------------------------------------------------------
# _detect_host — header-based priority
# ---------------------------------------------------------------------------


class TestDetectHost:
    def test_openai_session_header(self):
        headers = {"x-openai-session": "sess-abc123"}
        assert _detect_host(headers, None) == "chatgpt"

    def test_claude_baggage_header(self):
        headers = {"baggage": "sentry-trace_id=abc123"}
        assert _detect_host(headers, None) == "claude"

    def test_openai_takes_priority_over_claude(self):
        headers = {
            "x-openai-session": "sess-abc",
            "baggage": "sentry-trace_id=abc",
        }
        assert _detect_host(headers, None) == "chatgpt"

    def test_clientinfo_chatgpt(self):
        client_info = {"name": "ChatGPT-Desktop", "version": "1.0"}
        assert _detect_host(None, client_info) == "chatgpt"

    def test_clientinfo_openai(self):
        client_info = {"name": "openai-mcp-gateway", "version": "2.0"}
        assert _detect_host(None, client_info) == "chatgpt"

    def test_clientinfo_claude(self):
        client_info = {"name": "Claude-Desktop", "version": "1.0"}
        assert _detect_host(None, client_info) == "claude"

    def test_clientinfo_case_insensitive(self):
        client_info = {"name": "CLAUDE-CLI", "version": "1.0"}
        assert _detect_host(None, client_info) == "claude"

    def test_headers_take_priority_over_clientinfo(self):
        headers = {"x-openai-session": "sess-abc"}
        client_info = {"name": "Claude-Desktop", "version": "1.0"}
        assert _detect_host(headers, client_info) == "chatgpt"

    def test_unknown_when_no_signals(self):
        assert _detect_host(None, None) == "unknown"

    def test_unknown_with_empty_headers(self):
        assert _detect_host({}, None) == "unknown"

    def test_unknown_with_unrecognized_clientinfo(self):
        client_info = {"name": "custom-mcp-client", "version": "1.0"}
        assert _detect_host(None, client_info) == "unknown"

    def test_empty_openai_session_not_detected(self):
        headers = {"x-openai-session": ""}
        assert _detect_host(headers, None) == "unknown"

    def test_baggage_without_sentry_trace(self):
        headers = {"baggage": "other-key=value"}
        assert _detect_host(headers, None) == "unknown"


# ---------------------------------------------------------------------------
# _detect_platform — mobile vs desktop
# ---------------------------------------------------------------------------


class TestDetectPlatform:
    def test_mobile_android(self):
        headers = {"user-agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537"}
        assert _detect_platform(headers) == "mobile"

    def test_mobile_mobi(self):
        headers = {"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS) Mobile/15E148"}
        assert _detect_platform(headers) == "mobile"

    def test_desktop_chrome(self):
        headers = {"user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) Chrome/120"}
        assert _detect_platform(headers) == "desktop"

    def test_desktop_claude_code(self):
        headers = {"user-agent": "claude-code/1.0"}
        assert _detect_platform(headers) == "desktop"

    def test_unknown_no_headers(self):
        assert _detect_platform(None) == "unknown"

    def test_unknown_empty_ua(self):
        assert _detect_platform({"user-agent": ""}) == "unknown"

    def test_unknown_no_ua_header(self):
        assert _detect_platform({"content-type": "text/html"}) == "unknown"
