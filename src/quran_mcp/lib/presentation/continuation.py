"""Opaque continuation-token transport for paginated tool responses."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from quran_mcp.lib.config.settings import get_settings
from quran_mcp.lib.presentation.page_planning import PageEntry, PaginationMeta

ContinuationRequestT = TypeVar("ContinuationRequestT", bound=BaseModel)


class ContinuationPaginationMeta(BaseModel):
    """Continuation metadata included in opaque-continuation tool responses."""

    model_config = ConfigDict(extra="forbid")

    total_items: int = Field(
        description="Total items represented by this continuation-planned response set"
    )
    has_more: bool = Field(description="Whether more results are available via continuation")
    continuation: str | None = Field(
        default=None,
        description=(
            "Opaque same-tool continuation token. Null when no further results remain. "
            "When provided, call the same tool again with this token. You may omit "
            "the original request-shaping inputs, or repeat them unchanged for "
            "verification. If you change those inputs, the tool will reject the "
            "continuation as a different request."
        ),
    )
    pages: list[PageEntry] = Field(
        default_factory=list,
        description=(
            "Deterministic manifest of entries across the continuation-planned response set. "
            "Each record identifies the page number plus the edition and ayah key "
            "represented on that page."
        ),
    )


class ContinuationError(ValueError):
    """Raised when an opaque continuation token is invalid or unusable."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


class _ContinuationToken(BaseModel):
    """Compact signed continuation payload."""

    model_config = ConfigDict(extra="forbid")

    v: int = 1
    t: str
    n: int = Field(ge=1)
    s: int = Field(ge=1)
    r: dict[str, Any] = Field(default_factory=dict)
    q: str
    e: int = Field(ge=0)


def _has_modern_request_state(payload_data: dict[str, Any]) -> bool:
    """Return whether a raw payload uses the current request-state shape."""
    return payload_data.get("v") == 1 and "r" in payload_data


def _b64url_encode(raw: bytes) -> str:
    """Encode bytes as URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    """Decode URL-safe base64 with optional missing padding."""
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _canonical_json(data: Any) -> str:
    """Canonical JSON representation for deterministic request hashing."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonicalize_continuation_request(data: Any) -> Any:
    """Return a JSON-safe canonical copy of request-shaping inputs."""
    return json.loads(_canonical_json(data))


def hash_continuation_request(data: Any) -> str:
    """Hash normalized continuation request state for conflict detection."""
    canonical = canonicalize_continuation_request(data)
    return hashlib.sha256(_canonical_json(canonical).encode("utf-8")).hexdigest()


def _derive_continuation_secret() -> bytes:
    """Return a stable signing secret for opaque continuation tokens."""
    settings = get_settings()
    explicit = settings.continuation.token_secret.get_secret_value()
    if explicit:
        return explicit.encode("utf-8")

    health_token = settings.health.token.get_secret_value()
    if health_token:
        return hmac.new(
            health_token.encode("utf-8"),
            b"quran-mcp:continuation:v1",
            hashlib.sha256,
        ).digest()

    project_root = str(Path(__file__).resolve().parents[2])
    return hashlib.sha256(f"quran-mcp:continuation:v1|{project_root}".encode("utf-8")).digest()


def continuation_ttl_seconds() -> int:
    """Return the configured continuation-token validity window."""
    return max(1, get_settings().continuation.ttl_seconds)


def encode_continuation_token(
    *,
    tool_name: str,
    next_page: int,
    page_size: int,
    request_state: dict[str, Any],
    expires_at: int | None = None,
) -> str:
    """Create an opaque, signed continuation token."""
    normalized_request = canonicalize_continuation_request(request_state)
    payload = _ContinuationToken(
        t=tool_name,
        n=next_page,
        s=page_size,
        r=normalized_request,
        q=hash_continuation_request(normalized_request),
        e=expires_at if expires_at is not None else int(time.time()) + continuation_ttl_seconds(),
    )
    payload_json = _canonical_json(payload.model_dump(exclude_none=True))
    payload_bytes = payload_json.encode("utf-8")
    signature = hmac.new(_derive_continuation_secret(), payload_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


def decode_continuation_token(
    token: str,
    *,
    tool_name: str,
    request_state: dict[str, Any] | None = None,
) -> tuple[int, int, dict[str, Any]]:
    """Validate and decode an opaque continuation token."""
    try:
        payload_part, sig_part = token.split(".", 1)
    except ValueError as exc:
        raise ContinuationError("invalid", "Invalid continuation token") from exc

    try:
        payload_bytes = _b64url_decode(payload_part)
        signature = _b64url_decode(sig_part)
    except Exception as exc:
        raise ContinuationError("invalid", "Invalid continuation token") from exc

    expected_sig = hmac.new(_derive_continuation_secret(), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_sig):
        raise ContinuationError("tampered", "Tampered continuation token")

    try:
        payload_data = json.loads(payload_bytes)
        payload = _ContinuationToken.model_validate(payload_data)
    except Exception as exc:
        raise ContinuationError("invalid", "Invalid continuation token") from exc

    if payload.t != tool_name:
        raise ContinuationError(
            "conflict",
            f"Continuation token belongs to {payload.t}, not {tool_name}",
        )
    normalized_request = canonicalize_continuation_request(request_state) if request_state is not None else None
    request_hash = hash_continuation_request(payload.r)
    if not _has_modern_request_state(payload_data):
        if normalized_request is None:
            raise ContinuationError(
                "legacy",
                "Legacy continuation token requires the original request parameters",
            )
        if payload.q != hash_continuation_request(normalized_request):
            raise ContinuationError(
                "conflict",
                "Continuation token does not match the supplied request parameters",
            )
        resolved_request_state = normalized_request
    else:
        if payload.q != request_hash:
            raise ContinuationError("invalid", "Invalid continuation token")
        if normalized_request is not None:
            for key, explicit_value in normalized_request.items():
                if payload.r.get(key) != explicit_value:
                    raise ContinuationError(
                        "conflict",
                        "Continuation token does not match the supplied request parameters",
                    )
        resolved_request_state = payload.r
    if payload.e < int(time.time()):
        raise ContinuationError("expired", "Expired continuation token")

    return payload.n, payload.s, resolved_request_state


def decode_continuation_request_model(
    token: str,
    *,
    tool_name: str,
    state_model: type[ContinuationRequestT],
    explicit_state: BaseModel | dict[str, Any] | None = None,
) -> tuple[int, int, ContinuationRequestT]:
    """Decode a continuation token and validate request state into a typed model."""
    explicit_request: dict[str, Any] | None
    if explicit_state is None:
        explicit_request = None
    elif isinstance(explicit_state, BaseModel):
        explicit_request = explicit_state.model_dump(exclude_none=True)
    else:
        explicit_request = explicit_state

    requested_page, page_size, request_state = decode_continuation_token(
        token,
        tool_name=tool_name,
        request_state=explicit_request,
    )
    try:
        typed_request = state_model.model_validate(request_state)
    except Exception as exc:
        raise ContinuationError("invalid", "Invalid continuation token") from exc
    return requested_page, page_size, typed_request


def build_continuation_meta(
    *,
    tool_name: str,
    request_state: dict[str, Any],
    internal_meta: PaginationMeta,
    page_size: int,
) -> ContinuationPaginationMeta:
    """Convert internal numeric pagination metadata into the public continuation shape."""
    continuation = None
    if internal_meta.has_more:
        continuation = encode_continuation_token(
            tool_name=tool_name,
            next_page=internal_meta.page + 1,
            page_size=page_size,
            request_state=request_state,
        )

    return ContinuationPaginationMeta(
        total_items=internal_meta.total_items,
        has_more=internal_meta.has_more,
        continuation=continuation,
        pages=internal_meta.pages,
    )


def build_checked_continuation_meta(
    *,
    continuation: str | None,
    requested_page: int,
    tool_name: str,
    request_state: BaseModel | dict[str, Any],
    internal_meta: PaginationMeta,
    page_size: int,
) -> ContinuationPaginationMeta:
    """Validate continuation depth and build public continuation metadata."""
    ensure_not_exhausted(
        continuation=continuation,
        requested_page=requested_page,
        total_pages=internal_meta.total_pages,
    )
    normalized_request_state = (
        request_state.model_dump(exclude_none=True)
        if isinstance(request_state, BaseModel)
        else request_state
    )
    return build_continuation_meta(
        tool_name=tool_name,
        request_state=normalized_request_state,
        internal_meta=internal_meta,
        page_size=page_size,
    )


def ensure_not_exhausted(
    *,
    continuation: str | None,
    requested_page: int,
    total_pages: int,
) -> None:
    """Raise a predictable error when a continuation points past the final page."""
    if continuation is not None and requested_page > total_pages:
        raise ContinuationError("exhausted", "Continuation token is exhausted")
