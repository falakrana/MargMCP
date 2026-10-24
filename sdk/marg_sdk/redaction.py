import re
from typing import Any, Dict

REDACTED = "[REDACTED]"

# Credentials and secrets that must NEVER be captured under any circumstances
CREDENTIAL_KEYS = frozenset({
    "api_key", "apikey", "secret", "client_secret", "password", "passwd",
    "authorization", "token", "access_token", "auth_token", "refresh_token",
    "private_key", "cookie", "set-cookie",
})

# Payload fields that are stripped unless capture_payloads=True
PAYLOAD_KEYS = frozenset({
    "prompt", "response", "completion", "messages", "input", "output",
    "llm.prompt", "llm.response", "tool.input", "tool.output",
    "tool_input", "tool_output",
})

_SECRET_PATTERNS = (
    (re.compile(r"aop_[0-9a-f]{8}_[A-Za-z0-9_\-]{16,}"), "aop_[REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"\b(?:sk|gsk|rk|pk)[-_][A-Za-z0-9_\-]{16,}"), "[REDACTED_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_KEY]"),
    (re.compile(r"(://)[^/\s:@]+:[^/\s@]+@"), r"\1[REDACTED]@"),
)


def _scrub_text(text: str) -> str:
    for pat, repl in _SECRET_PATTERNS:
        text = pat.sub(repl, text)
    return text


def _scrub_value(val: Any, capture_payloads: bool, depth: int = 0) -> Any:
    if depth > 5:
        return REDACTED
    if isinstance(val, str):
        return _scrub_text(val)
    if isinstance(val, dict):
        out = {}
        for k, v in val.items():
            key_str = str(k).lower()
            if key_str in CREDENTIAL_KEYS:
                out[k] = REDACTED
            elif not capture_payloads and key_str in PAYLOAD_KEYS:
                out[k] = REDACTED
            else:
                out[k] = _scrub_value(v, capture_payloads, depth + 1)
        return out
    if isinstance(val, (list, tuple)):
        return [_scrub_value(item, capture_payloads, depth + 1) for item in val[:50]]
    return val


def redact_sensitive_data(data: Dict[str, Any], capture_payloads: bool = False) -> Dict[str, Any]:
    """
    Redact sensitive fields from the data dictionary.
    - Credentials/API keys are ALWAYS redacted, regardless of capture_payloads.
    - Raw prompts/responses are redacted if capture_payloads is False (default).
    - Recursively processes nested dictionaries and sequences.
    """
    if not isinstance(data, dict):
        return data
    return _scrub_value(data, capture_payloads=capture_payloads)
