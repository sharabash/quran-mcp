from __future__ import annotations

import logging
from textwrap import dedent

import pytest

from quran_mcp.lib.config.settings import clear_settings_cache, get_settings


def _write_config(tmp_path, base: str, local: str | None = None) -> str:
    config_path = tmp_path / "config.yml"
    config_path.write_text(dedent(base).strip() + "\n", encoding="utf-8")
    if local is not None:
        (tmp_path / "config.local.yml").write_text(
            dedent(local).strip() + "\n",
            encoding="utf-8",
        )
    return str(config_path)


@pytest.fixture(autouse=True)
def _clear_settings(monkeypatch: pytest.MonkeyPatch):
    clear_settings_cache()
    monkeypatch.delenv("MCP_CONFIG_YAML", raising=False)
    monkeypatch.delenv("GOODMEM__SPACE__QURAN", raising=False)
    monkeypatch.delenv("GOODMEM__SPACE__POST", raising=False)
    monkeypatch.delenv("RATE_LIMIT__METERED_TOOLS", raising=False)
    monkeypatch.delenv("SERVER__EXPOSE_TAGS", raising=False)
    yield
    clear_settings_cache()


def test_get_settings_applies_local_override_without_false_nested_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        goodmem:
          space:
            quran: base-quran
        """,
        """
        goodmem:
          space:
            quran: local-quran
        """,
    )
    monkeypatch.setenv("MCP_CONFIG_YAML", config_path)
    caplog.set_level(logging.WARNING)

    settings = get_settings()

    assert settings.goodmem.space.quran == "local-quran"
    override_messages = [record.getMessage() for record in caplog.records]
    assert override_messages == []


def test_get_settings_logs_leaf_override_for_nested_env_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        goodmem:
          space:
            quran: yaml-quran
        """,
    )
    monkeypatch.setenv("MCP_CONFIG_YAML", config_path)
    monkeypatch.setenv("GOODMEM__SPACE__QURAN", "env-quran")
    caplog.set_level(logging.WARNING)

    settings = get_settings()

    assert settings.goodmem.space.quran == "env-quran"
    override_messages = [record.getMessage() for record in caplog.records]
    assert "Environment variable overrides config.yml value for goodmem.space.quran" in override_messages
    assert all(not message.endswith("goodmem.space") for message in override_messages)


def test_get_settings_parses_metered_tools_from_comma_separated_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        rate_limit:
          enabled: true
          metered_tools: []
        """,
    )
    monkeypatch.setenv("MCP_CONFIG_YAML", config_path)
    monkeypatch.setenv(
        "RATE_LIMIT__METERED_TOOLS",
        "fetch_translation, search_translation",
    )

    settings = get_settings()

    assert settings.rate_limit.enabled is True
    assert settings.rate_limit.metered_tools == [
        "fetch_translation",
        "search_translation",
    ]


def test_get_settings_parses_expose_tags_from_comma_separated_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        server:
          profile: public
          expose_tags: null
        """,
    )
    monkeypatch.setenv("MCP_CONFIG_YAML", config_path)
    monkeypatch.setenv("SERVER__EXPOSE_TAGS", "ga, preview")

    settings = get_settings()

    assert settings.server.profile == "public"
    assert settings.server.expose_tags == ["ga", "preview"]


def test_get_settings_parses_goodmem_post_spaces_from_comma_separated_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        goodmem:
          space:
            post:
              - post
        """,
    )
    monkeypatch.setenv("MCP_CONFIG_YAML", config_path)
    monkeypatch.setenv("GOODMEM__SPACE__POST", "post, post-archive")

    settings = get_settings()

    assert settings.goodmem.space.post == ["post", "post-archive"]


def test_get_settings_parses_expose_tags_from_json_array_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        server:
          profile: public
          expose_tags: null
        """,
    )
    monkeypatch.setenv("MCP_CONFIG_YAML", config_path)
    monkeypatch.setenv("SERVER__EXPOSE_TAGS", '["ga", "preview"]')

    settings = get_settings()

    assert settings.server.expose_tags == ["ga", "preview"]


def test_get_settings_parses_metered_tools_from_json_array_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        rate_limit:
          enabled: true
          metered_tools: []
        """,
    )
    monkeypatch.setenv("MCP_CONFIG_YAML", config_path)
    monkeypatch.setenv(
        "RATE_LIMIT__METERED_TOOLS",
        '["fetch_translation", "search_translation"]',
    )

    settings = get_settings()

    assert settings.rate_limit.metered_tools == [
        "fetch_translation",
        "search_translation",
    ]


def test_get_settings_parses_goodmem_post_spaces_from_json_array_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        goodmem:
          space:
            post:
              - post
        """,
    )
    monkeypatch.setenv("MCP_CONFIG_YAML", config_path)
    monkeypatch.setenv("GOODMEM__SPACE__POST", '["post", "post-archive"]')

    settings = get_settings()

    assert settings.goodmem.space.post == ["post", "post-archive"]
