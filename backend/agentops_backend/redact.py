"""Secret scrubbing shared by logging, ingestion and error handling (Phase 9).

This is *defence in depth*: components are not supposed to put secrets into
logs or telemetry in the first place, but exception messages, URLs and
user-supplied metadata are outside our control. Everything that could reach a
log line, a stored error summary or a stored attribute passes through here.

Scrubbing is pattern based and therefore best-effort; it never replaces not
capturing sensitive data at all (see ``docs/threat-model.md``).
"""
from __future__ import annotations

import re
from typing import Any, Iterable

REDACTED = "[REDACTED]"

# Order matters: ``Bearer <token>`` must be scrubbed before the generic
# ``key=value`` rule, otherwise ``Authorization: Bearer abc`` would only lose
# the word "Bearer".
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"aop_[0-9a-f]{8}_[A-Za-z0-9_\-]{16,}"), "aop_[REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{8,}"), "Bearer [REDACTED]"),
    (
        re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
        "[REDACTED_JWT]",
    ),
    (re.compile(r"\b(?:sk|gsk|rk|pk)[-_][A-Za-z0-9_\-]{16,}"), "[REDACTED_KEY]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "[REDACTED_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_KEY]"),
    # Credentials embedded in URLs: scheme://user:password@host
    (re.compile(r"(://)[^/\s:@]+:[^/\s@]+@"), r"\1[REDACTED]@"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|apikey|secret|client[_-]?secret|password|passwd|"
            r"access[_-]?token|auth[_-]?token|token|authorization)"
            r"(\"?\s*[:=]\s*\"?)(?!(?:bearer\s+)?\[REDACTED)[^\s\"',;&]+"
        ),
        r"\1\2[REDACTED]",
    ),
)

# Mapping keys whose *values* are never kept, regardless of content.
SENSITIVE_KEYS = frozenset(
    {
        "api_key", "apikey", "secret", "client_secret", "password", "passwd",
        "authorization", "token", "access_token", "auth_token", "refresh_token",
        "private_key", "cookie", "set-cookie",
    }
)
# Raw user content: dropped unless payload capture is explicitly enabled.
PAYLOAD_KEYS = frozenset(
    {
        "prompt", "response", "completion", "messages", "input", "output",
        "llm.prompt", "llm.response", "tool.input", "tool.output",
        "tool_input", "tool_output",
    }
)

MAX_DEPTH = 6
MAX_ITEMS = 50


def scrub_text(text: str, max_len: int | None = None) -> str:
    """Replace secret-looking substrings; optionally truncate afterwards."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    if max_len is not None and len(text) > max_len:
        text = text[:max_len]
    return text


def scrub_obj(
    value: Any,
    *,
    redact_keys: Iterable[str] = SENSITIVE_KEYS,
    _depth: int = 0,
) -> Any:
    """Recursively scrub a JSON-like structure.

    * values under ``redact_keys`` (case-insensitive) become ``[REDACTED]``;
    * every string passes through :func:`scrub_text`;
    * depth and fan-out are bounded so hostile input cannot cause unbounded work.
    """
    keys = redact_keys if isinstance(redact_keys, (set, frozenset)) else frozenset(redact_keys)
    if _depth > MAX_DEPTH:
        return REDACTED
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= MAX_ITEMS:
                break
            key = str(k)
            if key.lower() in keys:
                out[key] = REDACTED
            else:
                out[key] = scrub_obj(v, redact_keys=keys, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [scrub_obj(v, redact_keys=keys, _depth=_depth + 1) for v in list(value)[:MAX_ITEMS]]
    return value
