"""Tests for quran_mcp.lib.config.settings — internal helpers.

Covers:
  - _deep_merge: recursive dict merge
  - FlatEnvSettingsSource: env var → nested settings mapping
"""

from __future__ import annotations

import os
from unittest.mock import patch

from quran_mcp.lib.config.settings import FlatEnvSettingsSource, Settings, _deep_merge


class TestDeepMerge:
    def test_non_overlapping_keys(self):
        assert _deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_scalar_override(self):
        assert _deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 3, "z": 4}}
        assert _deep_merge(base, override) == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_scalar_replaces_dict(self):
        assert _deep_merge({"a": {"x": 1}}, {"a": "flat"}) == {"a": "flat"}

    def test_empty_override(self):
        base = {"a": 1, "b": {"c": 2}}
        assert _deep_merge(base, {}) == base

    def test_does_not_mutate_base(self):
        base = {"a": {"x": 1}}
        _deep_merge(base, {"a": {"x": 2}})
        assert base["a"]["x"] == 1


class TestFlatEnvSettingsSource:
    def test_maps_goodmem_api_key(self):
        with patch.dict(os.environ, {"GOODMEM_API_KEY": "test-key"}, clear=False):
            source = FlatEnvSettingsSource(Settings)
            result = source()
        assert result["goodmem"]["api_key"] == "test-key"

    def test_maps_db_password(self):
        with patch.dict(os.environ, {"QURAN_MCP_DB_PASSWORD": "dbpass"}, clear=False):
            source = FlatEnvSettingsSource(Settings)
            result = source()
        assert result["database"]["password"] == "dbpass"

    def test_missing_env_var_not_in_result(self):
        with patch.dict(os.environ, {}, clear=False):
            # Remove the key if it exists
            env = dict(os.environ)
            env.pop("GOODMEM_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                source = FlatEnvSettingsSource(Settings)
                result = source()
        assert "goodmem" not in result or "api_key" not in result.get("goodmem", {})

    def test_multiple_vars_same_section(self):
        env = {
            "QURAN_MCP_DB_HOST": "remotehost",
            "QURAN_MCP_DB_PORT": "5432",
        }
        with patch.dict(os.environ, env, clear=False):
            source = FlatEnvSettingsSource(Settings)
            result = source()
        assert result["database"]["host"] == "remotehost"
        assert result["database"]["port"] == "5432"
