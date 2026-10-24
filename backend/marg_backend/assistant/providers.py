"""LLM provider abstraction.

One real implementation: any OpenAI-compatible ``/chat/completions`` endpoint
(Groq, OpenAI, Ollama, vLLM, ...). Errors are reduced to a small set of kinds;
response bodies, headers and API keys are never put into exception text.
"""
from __future__ import annotations

import logging
from typing import Optional, Protocol
from urllib.parse import urlparse

import httpx

from marg_backend.config import Settings

logger = logging.getLogger("marg_backend.assistant")

PRESET_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
}
_PLACEHOLDER_KEYS = {"", "change-me", "changeme"}


class ProviderError(Exception):
    """Controlled provider failure. ``kind`` is one of: timeout, rate_limited,
    unavailable, auth, invalid_response."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, *, max_tokens: int, timeout: float) -> str:
        """Return the model's text reply or raise :class:`ProviderError`."""
        ...


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.name = name
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._transport = transport

    def complete(self, system: str, user: str, *, max_tokens: int, timeout: float) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            with httpx.Client(timeout=timeout, transport=self._transport) as client:
                resp = client.post(self._url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise ProviderError("timeout") from None
        except httpx.HTTPError:
            raise ProviderError("unavailable") from None

        status = resp.status_code
        if status == 429:
            raise ProviderError("rate_limited")
        if status in (401, 403):
            raise ProviderError("auth")
        if status >= 400:
            raise ProviderError("unavailable")
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("invalid_response") from None
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("invalid_response")
        return content


def build_provider(
    settings: Settings, transport: Optional[httpx.BaseTransport] = None
) -> Optional[LLMProvider]:
    """Return a provider, or ``None`` when the assistant is not configured."""
    name = (settings.diagnostic_llm_provider or "none").strip().lower()
    if name in ("", "none"):
        return None
    api_key = (settings.diagnostic_llm_api_key or "").strip()
    if api_key.lower() in _PLACEHOLDER_KEYS or not settings.diagnostic_llm_model:
        logger.warning("Diagnostic assistant disabled: provider needs a real API key and model.")
        return None
    base_url = settings.diagnostic_llm_base_url or PRESET_BASE_URLS.get(name)
    if not base_url:
        logger.warning("Diagnostic assistant disabled: no base URL for provider '%s'.", name)
        return None
    if urlparse(base_url).scheme not in ("http", "https"):
        logger.warning("Diagnostic assistant disabled: base URL must be http(s).")
        return None
    return OpenAICompatibleProvider(
        name, base_url, api_key, settings.diagnostic_llm_model, transport=transport
    )
