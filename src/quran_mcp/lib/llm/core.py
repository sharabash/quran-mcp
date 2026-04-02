"""Core LLM exception types."""

from __future__ import annotations



class ProviderError(Exception):
    """Base exception for LLM provider errors."""

    def __init__(self, message: str, provider: str, cause: Exception | None = None):
        super().__init__(message)
        self.provider = provider
        self.cause = cause

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(provider={self.provider!r}, message={str(self)!r})"


class RateLimitError(ProviderError):
    """Rate limit exceeded. Caller should retry with backoff."""

    def __init__(
        self, provider: str, retry_after: float | None = None, cause: Exception | None = None
    ):
        super().__init__(f"Rate limit exceeded for {provider}", provider, cause)
        self.retry_after = retry_after

    def __repr__(self) -> str:
        return f"RateLimitError(provider={self.provider!r}, retry_after={self.retry_after})"


class InvalidResponseError(ProviderError):
    """Response failed to parse as expected model."""

    def __init__(
        self,
        provider: str,
        model_name: str,
        raw_response: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(f"Failed to parse response as {model_name}", provider, cause)
        self.model_name = model_name
        self.raw_response = (
            raw_response[:1000] if raw_response and len(raw_response) > 1000 else raw_response
        )

    def __repr__(self) -> str:
        return f"InvalidResponseError(provider={self.provider!r}, model_name={self.model_name!r})"


class AuthenticationError(ProviderError):
    """Invalid or missing API key."""

    def __init__(self, provider: str, cause: Exception | None = None):
        super().__init__(f"Authentication failed for {provider}", provider, cause)

    def __repr__(self) -> str:
        return f"AuthenticationError(provider={self.provider!r})"


class NetworkError(ProviderError):
    """Network connection failed or timed out."""

    def __init__(self, provider: str, cause: Exception | None = None):
        super().__init__(f"Connection failed for {provider}", provider, cause)

    def __repr__(self) -> str:
        return f"NetworkError(provider={self.provider!r})"


class ContentFilteredError(ProviderError):
    """Content blocked by safety filters or model refused to respond."""

    def __init__(self, provider: str, reason: str | None = None, cause: Exception | None = None):
        msg = f"Content filtered by {provider}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg, provider, cause)
        self.reason = reason

    def __repr__(self) -> str:
        return f"ContentFilteredError(provider={self.provider!r}, reason={self.reason!r})"


class ContextWindowExceededError(ProviderError):
    """Input too long for model's context window."""

    def __init__(
        self, provider: str, max_tokens: int | None = None, cause: Exception | None = None
    ):
        msg = f"Context window exceeded for {provider}"
        if max_tokens:
            msg += f" (max: {max_tokens})"
        super().__init__(msg, provider, cause)
        self.max_tokens = max_tokens

    def __repr__(self) -> str:
        return f"ContextWindowExceededError(provider={self.provider!r}, max_tokens={self.max_tokens})"


__all__ = [
    "ProviderError",
    "RateLimitError",
    "InvalidResponseError",
    "AuthenticationError",
    "NetworkError",
    "ContentFilteredError",
    "ContextWindowExceededError",
]
