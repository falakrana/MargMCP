"""Admin/registration service: projects, agents, API keys."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agentops_backend.auth import generate_api_key, hash_key
from agentops_backend.errors import ApiError, not_found
from agentops_backend.models import Agent, ApiKey, Project
from agentops_backend.schemas import (
    AgentCreate,
    ApiKeyCreate,
    ApiKeyCreated,
    ProjectCreate,
)


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
    return ApiKeyCreated(
        id=row.id,
        project_id=project_id,
        name=row.name,
        scopes=row.scopes.split(","),
        api_key=key,
    )
