"""API-key generation, hashing, and FastAPI auth dependencies.

Key format: ``aop_<8 hex prefix>_<urlsafe secret>``. Only the prefix (lookup)
and an HMAC-SHA256 of the full key (verification) are stored. Keys are never
logged.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentops_backend.errors import ApiError, forbidden, unauthorized
from agentops_backend.models import ApiKey

KEY_PREFIX_MARK = "aop_"
VALID_SCOPES = {"ingest", "read"}

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Bearer token authentication (API key or admin token)",
)


@dataclass(frozen=True)
class Principal:
    project_id: str
    scopes: frozenset[str]
    key_id: int


def generate_api_key() -> tuple[str, str]:
    """Return ``(full_key, prefix)``. The full key is shown to the user once."""
    prefix = secrets.token_hex(4)
    key = f"{KEY_PREFIX_MARK}{prefix}_{secrets.token_urlsafe(32)}"
    return key, prefix


def hash_key(key: str, secret_key: str) -> str:
    return hmac.new(secret_key.encode(), key.encode(), hashlib.sha256).hexdigest()


def _parse_prefix(key: str) -> Optional[str]:
    if not key.startswith(KEY_PREFIX_MARK):
        return None
    rest = key[len(KEY_PREFIX_MARK):]
    prefix, sep, secret = rest.partition("_")
    if not sep or len(prefix) != 8 or not secret:
        return None
    return prefix


def _bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def authenticate(
    request: Request,
    session: Session,
    token: Optional[str] = None,
) -> Principal:
    if token is None:
        token = _bearer_token(request)
    if token is None:
        raise unauthorized()
    secret_key = request.app.state.settings.secret_key
    presented_hash = hash_key(token, secret_key)  # constant work for all paths
    prefix = _parse_prefix(token)
    row = None
    if prefix is not None:
        row = session.execute(
            select(ApiKey).where(ApiKey.key_prefix == prefix)
        ).scalar_one_or_none()
    stored = row.key_hash if row is not None else "0" * 64
    ok = hmac.compare_digest(presented_hash, stored)
    if row is None or not ok or row.revoked_at is not None:
        raise unauthorized()
    return Principal(
        project_id=row.project_id,
        scopes=frozenset(s for s in row.scopes.split(",") if s),
        key_id=row.id,
    )


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def require_scope(scope: str) -> Callable[..., Principal]:
    def dependency(
        request: Request,
        session: Session = Depends(get_session),
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    ) -> Principal:
        token = credentials.credentials if credentials is not None else _bearer_token(request)
        principal = authenticate(request, session, token=token)
        if scope not in principal.scopes:
            raise forbidden("insufficient_scope", f"API key lacks the '{scope}' scope.")
        return principal

    return dependency


def require_project_access(principal: Principal, project_id: str) -> None:
    """Service-layer tenant check: a key only ever reaches its own project."""
    if principal.project_id != project_id:
        raise forbidden("project_access_denied", "Credential is not valid for this project.")


def require_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> None:
    configured = request.app.state.settings.admin_token
    if not configured:
        raise ApiError(503, "admin_disabled", "Admin API is not enabled on this server.")
    token = credentials.credentials if credentials is not None else _bearer_token(request)
    if token is None or not hmac.compare_digest(token, configured):
        raise unauthorized("Missing or invalid admin credentials.")
