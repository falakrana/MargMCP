"""AI diagnostic assistant (Phase 8).

A read-only investigator: it retrieves *real* telemetry through the same
authorised tool layer the MCP server uses, asks an LLM to reason over that
bounded evidence, then verifies every citation before returning a report.
See ``docs/diagnostic-assistant.md``.
"""
from marg_backend.assistant.engine import DiagnosticEngine
from marg_backend.assistant.models import DiagnosticReport
from marg_backend.assistant.providers import (
    LLMProvider,
    OpenAICompatibleProvider,
    ProviderError,
    build_provider,
)

__all__ = [
    "DiagnosticEngine",
    "DiagnosticReport",
    "LLMProvider",
    "OpenAICompatibleProvider",
    "ProviderError",
    "build_provider",
]
