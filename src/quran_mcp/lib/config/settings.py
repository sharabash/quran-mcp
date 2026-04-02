"""Centralized settings: env vars > .env > config.yml > defaults."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

import yaml
from dotenv import load_dotenv
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

VALID_LIFECYCLE_TAGS = frozenset({"ga", "preview", "internal", "deprecated"})

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------


def _parse_env_list(v: str | list[str] | None) -> list[str]:
    """Parse env-provided list values from JSON arrays or comma-separated strings."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        stripped = v.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                # Intentional: fall through to comma-split parsing below
                logger.debug("Failed to parse tag list as JSON: %s", stripped, exc_info=True)
            else:
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
        return [s.strip() for s in v.split(",") if s.strip()]
    return []


class DatabaseSettings(BaseModel):
    """PostgreSQL database configuration.

    Env vars use QURAN_MCP_DB_ prefix (e.g., QURAN_MCP_DB_PASSWORD).
    """

    model_config = ConfigDict(extra="ignore")

    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=2345, description="Database port (2345 maps to container 5432)")
    user: str = Field(default="quran_mcp_user", description="Database user")
    password: str = Field(default="", description="Database password (from .env via QURAN_MCP_DB_PASSWORD)")
    database: str = Field(default="quran_mcp_db", description="Database name")
    schema_name: str = Field(default="quran_mcp", description="PostgreSQL schema (hardcoded, not configurable)")
    min_pool_size: int = Field(default=2, description="Min asyncpg pool connections")
    max_pool_size: int = Field(default=20, description="Max asyncpg pool connections")


class ServerSettings(BaseModel):
    """Server profile and component visibility configuration."""

    model_config = ConfigDict(extra="ignore")

    port: int = Field(description="HTTP listen port (source of truth: config.yml)")
    profile: Literal["public", "dev", "full"] = Field(
        default="full",
        description="Named profile: public (ga only), dev (ga+preview+internal), full (all)",
    )
    expose_tags: Annotated[list[str] | None, NoDecode] = Field(
        default=None,
        description="Explicit lifecycle tag list, overrides profile when set",
    )

    @field_validator("expose_tags", mode="before")
    @classmethod
    def _parse_expose_tags(cls, v: str | list[str] | None) -> list[str] | None:
        """Support JSON-array or comma-separated env values."""
        if v is None:
            return None
        return _parse_env_list(v)

    @field_validator("expose_tags", mode="after")
    @classmethod
    def _validate_lifecycle_only(cls, v: list[str] | None) -> list[str] | None:
        """Ensure expose_tags contains only valid lifecycle tags."""
        if v is not None:
            invalid = set(v) - VALID_LIFECYCLE_TAGS
            if invalid:
                raise ValueError(
                    f"expose_tags contains non-lifecycle tags: {invalid}. "
                    f"Valid: {sorted(VALID_LIFECYCLE_TAGS)}"
                )
        return v


class RateLimitSettings(BaseModel):
    """Rate limiting configuration for cost-amplification protection."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(default=False, description="Enable rate limiting middleware")
    metered_tools: Annotated[list[str], NoDecode] = Field(
        default=[],
        description="Tool names subject to rate limiting and quota metering",
    )
    bucket_size: int = Field(default=2, description="Leaky bucket token capacity")
    refill_seconds: float = Field(default=10.0, description="Seconds per token refill")
    daily_per_client: int = Field(default=50, description="Max metered calls per client per day")
    daily_global: int = Field(default=200, description="Max metered calls globally per day")

    @field_validator("metered_tools", mode="before")
    @classmethod
    def _parse_tools_list(cls, v: str | list[str] | None) -> list[str]:
        """Support JSON-array or comma-separated env values."""
        return _parse_env_list(v)


class RelaySettings(BaseModel):
    """Relay system configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool | None = Field(
        default=None,
        description="Relay on/off. None = derive from profile (public=off, dev/full=on)",
    )
    write_token: SecretStr = Field(
        default=SecretStr(""),
        description=(
            "Shared secret for relay write tools (X-Relay-Token). "
            "GA-only relay surfaces reject writes when this token is unset."
        ),
    )
    turn_gap_seconds: int = Field(default=60, description="Seconds of inactivity before new turn")
    max_turn_minutes: int = Field(default=30, description="Max turn duration before auto-close")
    retention_days: int = Field(default=90, description="Days to retain relay data")
    log_turn_identity_event: bool = Field(default=False, description="Log turn correlation diagnostic to .logs/turn_identity_diagnostic.jsonl (opt-in)")


class GoodMemSpaceSettings(BaseModel):
    """GoodMem space name mappings."""

    model_config = ConfigDict(extra="ignore")

    quran: str = Field(default="quran", description="Quran editions space name")
    tafsir: str = Field(default="tafsir", description="Tafsir space name")
    translation: str = Field(default="translation", description="Translation space name")
    post: Annotated[list[str], NoDecode] = Field(default=["post"], description="Posts space name(s)")

    @field_validator("post", mode="before")
    @classmethod
    def _parse_post_list(cls, v: str | list[str] | None) -> list[str]:
        """Support JSON-array or comma-separated env values."""
        return _parse_env_list(v) if v is not None else ["post"]


class GoodMemSettings(BaseModel):
    """GoodMem configuration."""

    model_config = ConfigDict(extra="ignore")

    api_key: SecretStr = Field(default=SecretStr(""), description="GoodMem API key")
    api_host: str = Field(default="https://localhost:8080", description="API host")
    embedder: str | None = Field(default=None, description="Default embedder name (e.g., text-embedding-3-large)")
    space: GoodMemSpaceSettings = Field(default_factory=GoodMemSpaceSettings)
    reranker: str | None = Field(default=None, description="Reranker display name (resolved to ID at init)")


class PostsSettings(BaseModel):
    """Posts search configuration."""

    model_config = ConfigDict(extra="ignore")


class SamplingSettings(BaseModel):
    """LLM sampling fallback configuration."""

    model_config = ConfigDict(extra="ignore")

    # Generic MCP sampling settings
    provider: str = Field(default="openai", description="Sampling provider (openai/anthropic/gemini/openrouter)")
    model: str | None = Field(default=None, description="Model override")
    api_key: SecretStr = Field(default=SecretStr(""), description="Fallback API key")
    base_url: str | None = Field(default=None, description="Fallback base URL")
    max_output_tokens: int | None = Field(default=None, description="Max output tokens")

    # OpenAI-specific
    openai_api_key: SecretStr = Field(default=SecretStr(""), description="OpenAI API key")
    openai_base_url: str | None = Field(default=None, description="OpenAI base URL")
    openai_org: str | None = Field(default=None, description="OpenAI organization")
    openai_model: str | None = Field(default=None, description="OpenAI model override")

    # Anthropic-specific
    anthropic_api_key: SecretStr = Field(default=SecretStr(""), description="Anthropic API key")
    anthropic_base_url: str | None = Field(default=None, description="Anthropic base URL")
    anthropic_model: str | None = Field(default=None, description="Anthropic model override")

    # Gemini-specific
    google_api_key: SecretStr = Field(default=SecretStr(""), description="Google API key")
    gemini_api_key: SecretStr = Field(default=SecretStr(""), description="Gemini API key (alias)")
    gemini_model: str | None = Field(default=None, description="Gemini model override")

    # OpenRouter-specific
    openrouter_api_key: SecretStr = Field(default=SecretStr(""), description="OpenRouter API key")
    openrouter_base_url: str | None = Field(default=None, description="OpenRouter base URL")
    openrouter_model: str | None = Field(default=None, description="OpenRouter model override")


class VoyageSettings(BaseModel):
    """Voyage AI reranking configuration for concordance."""

    model_config = ConfigDict(extra="ignore")

    api_key: SecretStr = Field(default=SecretStr(""), description="Voyage AI API key")
    model: str = Field(default="rerank-2", description="Voyage reranking model")
    top_k: int = Field(default=50, description="Size of candidate pool to rerank")
    timeout_seconds: float = Field(default=10.0, description="HTTP timeout for Voyage API")


class HealthSettings(BaseModel):
    """Health check endpoint configuration."""

    model_config = ConfigDict(extra="ignore")

    url: str | None = Field(default=None, description="Recursive MCP client URL for self-test (default: built from server.port)")
    token: SecretStr = Field(default=SecretStr(""), description="Shared secret for rate limit exemption (X-Health-Token header)")
    connection_timeout_s: float = Field(default=5.0, description="MCP handshake + list_tools timeout in seconds")
    tool_timeout_s: float = Field(default=10.0, description="Per-tool invocation timeout in seconds")
    max_timeout_s: float = Field(default=60.0, description="Overall endpoint timeout cap in seconds")
    tier0_cache_ttl_s: float = Field(default=10.0, description="Tier 0 result cache TTL in seconds")
    tier1_cache_ttl_s: float = Field(default=30.0, description="Tier 1 result cache TTL in seconds")


class SentrySettings(BaseModel):
    """Sentry error tracking and performance tracing configuration."""

    model_config = ConfigDict(extra="ignore")

    dsn: SecretStr = Field(default=SecretStr(""), description="Sentry DSN (empty = disabled)")
    enabled: bool = Field(default=True, description="Enable Sentry when DSN is set")
    traces_sample_rate: float = Field(default=0.2, description="Fraction of requests to trace (0.0-1.0)")
    environment: str = Field(default="production", description="Sentry environment tag")
    release: str | None = Field(default=None, description="Release identifier (version or git SHA)")
    send_default_pii: bool = Field(default=False, description="Send PII (default: off, defense-in-depth)")


class LoggingSettings(BaseModel):
    """Logging and debug configuration."""

    model_config = ConfigDict(extra="ignore")

    log_level: str = Field(default="normal", description="MCP log level (minimal/normal/verbose/debug)")
    format: Literal["pretty", "json"] = Field(default="pretty", description='Log output format: "pretty" (human-friendly) or "json" (structured)')
    debug: bool = Field(
        default=False,
        description=(
            "Enable HTTP debug middleware "
            "(config.yml logging.debug or nested env LOGGING__DEBUG)"
        ),
    )
    wire_dump: bool = Field(default=False, description="Enable ASGI wire dump middleware (logs full HTTP request/response to /tmp/mcp-wire-dump.jsonl)")


class ContinuationSettings(BaseModel):
    """Opaque continuation token configuration."""

    model_config = ConfigDict(extra="ignore")

    ttl_seconds: int = Field(
        default=3600,
        description="Continuation token validity window in seconds",
    )
    token_secret: SecretStr = Field(
        default=SecretStr(""),
        description="Optional secret for signing opaque continuation tokens",
    )


class GroundingSettings(BaseModel):
    """Grounding gate configuration."""

    model_config = ConfigDict(extra="ignore")

    authority_a_enabled: bool = Field(
        default=False,
        description=(
            "Enable Authority A (identity-based retained acknowledgment). "
            "Disabled by default during nonce mechanism testing."
        ),
    )


class ShowMushafSettings(BaseModel):
    """show_mushaf MCP App configuration."""

    model_config = ConfigDict(extra="ignore")

    interactive: bool = Field(
        default=True,
        description="Enable word selection and interaction UI in the mushaf app.",
    )


class McpAppsSettings(BaseModel):
    """MCP Apps configuration."""

    model_config = ConfigDict(extra="ignore")

    show_mushaf: ShowMushafSettings = Field(default_factory=ShowMushafSettings)


_FLAT_ENV_MAPPING: dict[str, tuple[str, str]] = {
    # Server
    "PORT": ("server", "port"),
    # Database
    "QURAN_MCP_DB_HOST": ("database", "host"),
    "QURAN_MCP_DB_PORT": ("database", "port"),
    "QURAN_MCP_DB_USER": ("database", "user"),
    "QURAN_MCP_DB_PASSWORD": ("database", "password"),
    "QURAN_MCP_DB_DATABASE": ("database", "database"),
    "QURAN_MCP_DB_MIN_POOL_SIZE": ("database", "min_pool_size"),
    "QURAN_MCP_DB_MAX_POOL_SIZE": ("database", "max_pool_size"),
    # GoodMem
    "GOODMEM_API_KEY": ("goodmem", "api_key"),
    # Sampling (secrets only)
    "MCP_SAMPLING_API_KEY": ("sampling", "api_key"),
    "OPENAI_API_KEY": ("sampling", "openai_api_key"),
    "ANTHROPIC_API_KEY": ("sampling", "anthropic_api_key"),
    "GOOGLE_API_KEY": ("sampling", "google_api_key"),
    "GEMINI_API_KEY": ("sampling", "gemini_api_key"),
    "OPENROUTER_API_KEY": ("sampling", "openrouter_api_key"),
    # Voyage
    "VOYAGE_API_KEY": ("voyage", "api_key"),
    "VOYAGE_MODEL": ("voyage", "model"),
    "VOYAGE_TOP_K": ("voyage", "top_k"),
    "VOYAGE_TIMEOUT_SECONDS": ("voyage", "timeout_seconds"),
    # Sentry
    "SENTRY_DSN": ("sentry", "dsn"),
    "SENTRY_ENVIRONMENT": ("sentry", "environment"),
    "SENTRY_TRACES_SAMPLE_RATE": ("sentry", "traces_sample_rate"),
    "SENTRY_RELEASE": ("sentry", "release"),
    # Logging (config.yml only — no env var overrides)
    # Health
    "HEALTH_URL": ("health", "url"),
    "HEALTH_TOKEN": ("health", "token"),
    # Relay
    "RELAY_WRITE_TOKEN": ("relay", "write_token"),
    "CONTINUATION_TTL_SECONDS": ("continuation", "ttl_seconds"),
    "CONTINUATION_TOKEN_SECRET": ("continuation", "token_secret"),
    # Grounding
    "GROUNDING_AUTHORITY_A_ENABLED": ("grounding", "authority_a_enabled"),
}


class FlatEnvSettingsSource:
    """Maps flat env vars (e.g. GOODMEM_API_KEY) to nested settings paths."""

    def __init__(self, settings_cls: type["Settings"]):
        self.settings_cls = settings_cls

    def __call__(self) -> dict[str, Any]:
        result: dict[str, dict[str, Any]] = {}

        for env_var, (section, field) in _FLAT_ENV_MAPPING.items():
            value = os.environ.get(env_var)
            if value is not None:
                if section not in result:
                    result[section] = {}
                result[section][field] = value

        return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base, returning a new dict."""
    merged = base.copy()
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a single YAML file, returning empty dict on error or missing."""
    if not path.exists():
        return {}

    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        logger.debug(f"Loaded config from {path}")
        return data
    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse {path}: {e}")
        return {}
    except OSError as e:
        logger.warning(f"Failed to read {path}: {e}")
        return {}


class YamlConfigSettingsSource:
    """Loads config.yml and deep-merges a sibling config.local.yml on top."""

    def __init__(self, settings_cls: type["Settings"]):
        self.settings_cls = settings_cls

    def __call__(self) -> dict[str, Any]:
        config_path = Path(os.environ.get("MCP_CONFIG_YAML", "config.yml"))
        base = _load_yaml(config_path)

        local_path = config_path.parent / config_path.name.replace(".yml", ".local.yml")
        local = _load_yaml(local_path)

        if local:
            logger.debug(f"Applying local overrides from {local_path}")
            return _deep_merge(base, local)
        return base


class Settings(BaseSettings):
    """Centralized application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    server: ServerSettings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    relay: RelaySettings = Field(default_factory=RelaySettings)
    goodmem: GoodMemSettings = Field(default_factory=GoodMemSettings)
    posts: PostsSettings = Field(default_factory=PostsSettings)
    sampling: SamplingSettings = Field(default_factory=SamplingSettings)
    voyage: VoyageSettings = Field(default_factory=VoyageSettings)
    health: HealthSettings = Field(default_factory=HealthSettings)
    sentry: SentrySettings = Field(default_factory=SentrySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    continuation: ContinuationSettings = Field(default_factory=ContinuationSettings)
    grounding: GroundingSettings = Field(default_factory=GroundingSettings)
    mcp_apps: McpAppsSettings = Field(default_factory=McpAppsSettings)

    # Instance-level storage for YAML data (thread-safe)
    _yaml_source_data: dict[str, Any] | None = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        return (
            init_settings,
            FlatEnvSettingsSource(settings_cls),
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


def _log_overrides(settings: Settings, yaml_data: dict[str, Any]) -> None:
    """Log warnings when env vars override YAML values."""
    if not yaml_data:
        return

    def _unseal(value: Any) -> Any:
        if isinstance(value, SecretStr):
            return value.get_secret_value()
        return value

    def _compare_value(path: str, yaml_val: Any, final_val: Any) -> None:
        yaml_val = _unseal(yaml_val)
        final_val = _unseal(final_val)

        if isinstance(final_val, BaseModel) and isinstance(yaml_val, dict):
            for key, nested_yaml_val in yaml_val.items():
                if hasattr(final_val, key):
                    _compare_value(
                        f"{path}.{key}",
                        nested_yaml_val,
                        getattr(final_val, key),
                    )
            return

        if isinstance(final_val, dict) and isinstance(yaml_val, dict):
            for key, nested_yaml_val in yaml_val.items():
                if key in final_val:
                    _compare_value(
                        f"{path}.{key}",
                        nested_yaml_val,
                        final_val[key],
                    )
            return

        if final_val != yaml_val:
            logger.warning(
                "Environment variable overrides config.yml value for %s",
                path,
            )

    for section_name in (
        "server",
        "database",
        "rate_limit",
        "relay",
        "goodmem",
        "posts",
        "sampling",
        "voyage",
        "health",
        "sentry",
        "logging",
        "continuation",
        "grounding",
    ):
        if section_name in yaml_data and isinstance(yaml_data[section_name], dict):
            settings_section = getattr(settings, section_name, None)
            if settings_section:
                _compare_value(section_name, yaml_data[section_name], settings_section)


@lru_cache
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached)."""
    load_dotenv()
    yaml_source = YamlConfigSettingsSource(Settings)
    yaml_data = yaml_source()
    settings = Settings()
    settings._yaml_source_data = yaml_data

    # Log any overrides
    _log_overrides(settings, yaml_data)

    logger.info("Settings loaded successfully")
    return settings


def clear_settings_cache() -> None:
    """Clear the settings cache. Useful for testing."""
    get_settings.cache_clear()
