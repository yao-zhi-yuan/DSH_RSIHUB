"""Validation helpers for the local Ollama model route."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def validate_ollama_base_url(value: str) -> str:
    """Return a normalized loopback OpenAI-compatible Ollama URL."""
    parsed = urlsplit(value.strip())
    if parsed.scheme != "http" or parsed.hostname not in _LOOPBACK_HOSTS:
        raise ValueError("OLLAMA_BASE_URL must use HTTP on a loopback host")
    if parsed.path.rstrip("/") != "/v1" or parsed.query or parsed.fragment:
        raise ValueError("OLLAMA_BASE_URL must end with /v1 and have no query or fragment")
    return urlunsplit((parsed.scheme, parsed.netloc, "/v1", "", ""))


def model_matches(configured: str, returned: object) -> bool:
    """Require Ollama to report the exact configured model tag."""
    return isinstance(returned, str) and returned == configured
