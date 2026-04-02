"""Tests for quran_mcp.lib.config.sentry — event scrubbing.

Covers:
  - _is_sensitive: key matching against sensitive key set
  - _scrub_dict: redaction of sensitive values in dicts
  - before_send: Sentry event transformation (headers + data scrubbing)
"""

from __future__ import annotations

from quran_mcp.lib.config.sentry import _is_sensitive, _scrub_dict, before_send


class TestIsSensitive:
    def test_authorization(self):
        assert _is_sensitive("authorization") is True

    def test_api_key_variants(self):
        assert _is_sensitive("api_key") is True
        assert _is_sensitive("api-key") is True
        assert _is_sensitive("apikey") is True

    def test_case_insensitive(self):
        assert _is_sensitive("Authorization") is True
        assert _is_sensitive("API_KEY") is True

    def test_non_sensitive(self):
        assert _is_sensitive("content-type") is False
        assert _is_sensitive("user-agent") is False

    def test_password_and_token(self):
        assert _is_sensitive("password") is True
        assert _is_sensitive("token") is True
        assert _is_sensitive("cookie") is True


class TestScrubDict:
    def test_sensitive_values_redacted(self):
        d = {"authorization": "Bearer sk-secret", "content-type": "application/json"}
        result = _scrub_dict(d)
        assert result["authorization"] == "[Filtered]"
        assert result["content-type"] == "application/json"

    def test_multiple_sensitive_keys(self):
        d = {"token": "abc", "password": "xyz", "host": "localhost"}
        result = _scrub_dict(d)
        assert result["token"] == "[Filtered]"
        assert result["password"] == "[Filtered]"
        assert result["host"] == "localhost"

    def test_empty_dict(self):
        assert _scrub_dict({}) == {}


class TestBeforeSend:
    def test_scrubs_request_headers(self):
        event = {
            "request": {
                "headers": {"authorization": "Bearer secret", "accept": "text/html"},
            }
        }
        result = before_send(event, {})
        assert result["request"]["headers"]["authorization"] == "[Filtered]"
        assert result["request"]["headers"]["accept"] == "text/html"

    def test_scrubs_request_data(self):
        event = {
            "request": {
                "data": {"api_key": "sk-secret", "query": "hello"},
            }
        }
        result = before_send(event, {})
        assert result["request"]["data"]["api_key"] == "[Filtered]"
        assert result["request"]["data"]["query"] == "hello"

    def test_event_without_request_passes_through(self):
        event = {"message": "test error", "level": "error"}
        result = before_send(event, {})
        assert result == event

    def test_returns_event(self):
        event = {"request": {"headers": {}}}
        assert before_send(event, {}) is not None
