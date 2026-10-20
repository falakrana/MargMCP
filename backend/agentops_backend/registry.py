"""Admin/registration service: projects, agents, API keys."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agentops_backend.auth import generate_api_key, hash_key
from agentops_backend.errors import ApiError, not_found
from agentops_backend.models import Agent, ApiKey, Project, utcnow
from agentops_backend.schemas import (
    AgentCreate,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    ApiKeyRotated,
    ProjectCreate,
)

audit = logging.getLogger("agentops_backend.audit")


def create_project(session: Session, body: ProjectCreate) -> Project:
    project = Project(
        id=body.project_id or str(uuid.uuid4()), tenant_id=body.tenant_id, name=body.name
    )
    session.add(project)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiError(409, "already_exists", "A project with this id already exists.")
    return project


def create_agent(session: Session, project_id: str, body: AgentCreate) -> Agent:
    if session.get(Project, project_id) is None:
        raise not_found("Project not found.")
    agent = Agent(
        project_id=project_id,
        id=body.agent_id or str(uuid.uuid4()),
        name=body.name,
        auto_registered=False,
    )
    session.add(agent)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiError(409, "already_exists", "An agent with this id already exists.")
    return agent


def create_api_key(
    session: Session, secret_key: str, project_id: str, body: ApiKeyCreate
) -> ApiKeyCreated:
    if session.get(Project, project_id) is None:
        raise not_found("Project not found.")
    for _ in range(5):  # retry on the (very unlikely) prefix collision
        key, prefix = generate_api_key()
        taken = session.execute(
            select(ApiKey.id).where(ApiKey.key_prefix == prefix)
        ).first()
        if not taken:
            break
    else:  # pragma: no cover
        raise ApiError(500, "key_generation_failed", "Could not generate a unique key.")
    row = ApiKey(
        project_id=project_id,
        name=body.name,
        key_prefix=prefix,
        key_hash=hash_key(key, secret_key),
        scopes=",".join(sorted(set(body.scopes))),
    )
    session.add(row)
    session.commit()
    audit.info("api_key.created key_id=%s project=%s scopes=%s", row.id, project_id, row.scopes)
    return ApiKeyCreated(
        id=row.id,
        project_id=project_id,
        name=row.name,
        scopes=row.scopes.split(","),
        api_key=key,
    )


def _key_out(row: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        key_prefix=row.key_prefix,
        scopes=[s for s in row.scopes.split(",") if s],
        created_at=row.created_at,
        revoked_at=row.revoked_at,
        active=row.revoked_at is None,
    )


def _get_key(session: Session, project_id: str, key_id: int) -> ApiKey:
    row = session.get(ApiKey, key_id)
    # Same 404 for "no such key" and "key of another project": no existence oracle.
    if row is None or row.project_id != project_id:
        raise not_found("API key not found.")
    return row


def list_api_keys(session: Session, project_id: str) -> list[ApiKeyOut]:
    if session.get(Project, project_id) is None:
        raise not_found("Project not found.")
    rows = session.execute(
        select(ApiKey).where(ApiKey.project_id == project_id).order_by(ApiKey.id)
    ).scalars()
    return [_key_out(r) for r in rows]


def revoke_api_key(session: Session, project_id: str, key_id: int) -> ApiKeyOut:
    """Idempotent: revoking an already revoked key keeps its original timestamp."""
    row = _get_key(session, project_id, key_id)
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        session.commit()
        audit.info("api_key.revoked key_id=%s project=%s", row.id, project_id)
    return _key_out(row)


def rotate_api_key(
    session: Session,
    secret_key: str,
    project_id: str,
    key_id: int,
    *,
    revoke_old: bool = True,
) -> ApiKeyRotated:
    """Issue a replacement key with the same name and scopes.

    With ``revoke_old=False`` both keys stay valid until the operator revokes the
    old one, allowing a zero-downtime rollout across running agents.
    """
    old = _get_key(session, project_id, key_id)
    if old.revoked_at is not None:
        raise ApiError(409, "key_revoked", "A revoked key cannot be rotated; create a new key.")
    created = create_api_key(
        session,
        secret_key,
        project_id,
        ApiKeyCreate(name=old.name, scopes=[s for s in old.scopes.split(",") if s]),
    )
    if revoke_old:
        revoke_api_key(session, project_id, key_id)
    session.refresh(old)
    audit.info(
        "api_key.rotated old_key_id=%s new_key_id=%s project=%s revoke_old=%s",
        key_id, created.id, project_id, revoke_old,
    )
    return ApiKeyRotated(new_key=created, old_key=_key_out(old))
