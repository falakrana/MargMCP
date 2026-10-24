"""Request-level protections (Phase 9): rate limiting, body-size cap, headers.

Everything here is in-process and dependency free by design (see
``docs/assumptions-and-decisions.md``: no Redis/queue by default). The
trade-off is documented: counters are per worker process.

Components
----------
``RateLimiter``           bounded fixed-window counters
``BodyLimitMiddleware``   enforces ``max_payload_bytes`` on *every* request body,
                          including chunked bodies that declare no length
``install_http_protections`` per-IP flood guard, failed-auth throttle, security
                          headers and a server-generated request id
``enforce_rate``          per-project limit used by auth dependencies/routes
"""
from __future__ import annotations

import json
import math
import threading
import time
import uuid
from collections import OrderedDict
from typing import Callable, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from marg_backend.config import Settings
from marg_backend.errors import ApiError
from marg_backend.logging_config import request_id_var

# Fixed set => bounded Prometheus label values for rate_limited_total.
RATE_SCOPES = frozenset({"ip", "auth_failure", "ingest", "read", "diagnose"})
_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")
_UNLIMITED_PREFIXES = ("/health/", "/metrics")


class RateLimiter:
    """Thread-safe fixed-window counters with a hard cap on tracked keys."""

    def __init__(
        self,
        max_keys: int = 10_000,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_keys = max_keys
        self._window = window_seconds
        self._clock = clock
        self._data: "OrderedDict[tuple[str, str], list[float]]" = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._data)

    def hit(self, bucket: str, key: str, limit: int) -> tuple[bool, float]:
        """Count one event. Returns ``(allowed, retry_after_seconds)``."""
        now = self._clock()
        with self._lock:
            entry = self._data.get((bucket, key))
            if entry is None or now - entry[0] >= self._window:
                entry = [now, 0.0]
            entry[1] += 1
            self._data[(bucket, key)] = entry
            self._data.move_to_end((bucket, key))
            while len(self._data) > self._max_keys:
                self._data.popitem(last=False)  # evict least-recently-used
            allowed = entry[1] <= limit
            return allowed, max(0.0, self._window - (now - entry[0]))

    def count(self, bucket: str, key: str) -> int:
        now = self._clock()
        with self._lock:
            entry = self._data.get((bucket, key))
            if entry is None or now - entry[0] >= self._window:
                return 0
            return int(entry[1])

    def retry_after(self, bucket: str, key: str) -> float:
        now = self._clock()
        with self._lock:
            entry = self._data.get((bucket, key))
            if entry is None:
                return 0.0
            return max(0.0, self._window - (now - entry[0]))


def client_ip(request: Request, trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.split(",")[-1].strip()
        if last:
            return last[:64]
    return request.client.host if request.client else "unknown"


def _rate_limited(scope: str, retry_after: float, request: Request) -> ApiError:
    try:
        metrics = request.app.state.observability.metrics
        if scope in RATE_SCOPES:
            metrics.rate_limited_total.labels(scope=scope).inc()
    except Exception:  # noqa: BLE001 - metrics must never mask the 429
        pass
    return ApiError(
        429,
        "rate_limited",
        "Rate limit exceeded. Retry later.",
        headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
    )


def enforce_rate(request: Request, scope: str, key: str, limit: int) -> None:
    """Per-key limit used after authentication (key = project id)."""
    settings: Settings = request.app.state.settings
    if not settings.rate_limit_enabled:
        return
    allowed, retry_after = request.app.state.limiter.hit(scope, key, limit)
    if not allowed:
        raise _rate_limited(scope, retry_after, request)


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Reject request bodies larger than ``max_bytes`` (pure ASGI).

    Checks the declared ``Content-Length`` up front and also counts bytes as
    they are received, so a chunked upload without a length cannot be used to
    make the server buffer an arbitrarily large body.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send)
            return

        total = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    raise _BodyTooLarge()
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not started:
                await self._reject(send)

    async def _reject(self, send: Send) -> None:
        body = json.dumps(
            {
                "error": {
                    "code": "payload_too_large",
                    "message": f"Request body exceeds {self.max_bytes} bytes.",
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def install_http_protections(app: FastAPI, settings: Settings) -> None:
    """Register the HTTP middleware that guards every route."""
    limiter = RateLimiter(max_keys=settings.rate_limit_max_tracked_keys)
    app.state.limiter = limiter

    @app.middleware("http")
    async def _protect(request: Request, call_next):
        request_id = uuid.uuid4().hex
        token = request_id_var.set(request_id)
        try:
            path = request.url.path
            ip = client_ip(request, settings.trust_proxy_headers)
            limited = settings.rate_limit_enabled and not path.startswith(_UNLIMITED_PREFIXES)
            if limited:
                if limiter.count("auth_failure", ip) >= settings.rate_limit_auth_failures_per_minute:
                    response = _rejection(
                        _rate_limited("auth_failure", limiter.retry_after("auth_failure", ip), request)
                    )
                    return _decorate(response, request_id, path, settings)
                allowed, retry_after = limiter.hit("ip", ip, settings.rate_limit_ip_per_minute)
                if not allowed:
                    return _decorate(
                        _rejection(_rate_limited("ip", retry_after, request)),
                        request_id, path, settings,
                    )
            response = await call_next(request)
            if limited and response.status_code in (401, 403):
                limiter.hit("auth_failure", ip, settings.rate_limit_auth_failures_per_minute)
            return _decorate(response, request_id, path, settings)
        finally:
            request_id_var.reset(token)


def _rejection(err: ApiError) -> JSONResponse:
    return JSONResponse(err.body(), status_code=err.status_code, headers=err.headers)


def _decorate(response, request_id: str, path: str, settings: Settings):
    h = response.headers
    h["X-Request-ID"] = request_id
    h["X-Content-Type-Options"] = "nosniff"
    h["Referrer-Policy"] = "no-referrer"
    h["Cache-Control"] = "no-store"
    if not path.startswith(_DOC_PATHS):
        # Pure JSON API: nothing may be framed, scripted or loaded from it.
        h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        h["X-Frame-Options"] = "DENY"
    if settings.env != "development":
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def optional_ip(request: Request, settings: Optional[Settings] = None) -> str:
    settings = settings or request.app.state.settings
    return client_ip(request, settings.trust_proxy_headers)
