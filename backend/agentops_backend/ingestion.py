"""Ingestion service: validation, idempotent persistence, run state machine.

Semantics
---------
* Batch-level problems (bad schema version, malformed envelope, too many
  events, project mismatch) fail the whole request.
* Event-level problems (out-of-range timestamp, forbidden attribute, invalid
  status transition, ...) reject only that event; the rest are persisted.
  Rejections are reported in the response and never silently dropped.
* ``(project_id, event_id)`` is the idempotency key. A retried event is
  counted as a duplicate and changes nothing (including run counters).
* Events may arrive out of order. A run created by a non-``run_started``
  event is a placeholder (``status='unknown'``, ``start_confirmed=False``)
  that is completed when ``run_started`` arrives.
* A run's terminal status is set once. A *different* terminal event for an
  already-terminal run is rejected (``invalid_status_transition``); a
  repeat of the same terminal status is accepted without changes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from agentops_backend.config import Settings
from agentops_backend.errors import ApiError
from agentops_backend.models import Agent, Event, Run, utcnow
from agentops_backend.observability import EventObservation, Observability
from agentops_backend.redact import scrub_obj, scrub_text
from agentops_backend.schemas import IngestBatch, IngestEvent, IngestResult, RejectedEvent

logger = logging.getLogger(__name__)

TERMINAL_STATUS = {
    "run_completed": "success",
    "run_failed": "error",
    "run_cancelled": "cancelled",
}
TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")

ALLOWED_DATA_KEYS = {
    "trace_id", "root_span_id", "span_id", "parent_span_id",
    "error_type", "error_summary", "metadata", "summary", "sdk_version",
    "provider", "model", "prompt_tokens", "completion_tokens", "total_tokens",
    "tool_name", "tool_type", "operation_name", "duration_ms", "status_code",
    "attributes", "deployment_version",
}
# Raw user content / secrets must never be ingested by default (schema §5.1).
FORBIDDEN_KEYS = {
    "prompt", "response", "completion", "messages", "input", "output",
    "llm.prompt", "llm.response", "tool.input", "tool.output",
    "tool_input", "tool_output", "api_key", "apikey", "secret", "password",
    "authorization", "token", "access_token",
}
MAX_METADATA_KEYS = 10
MAX_ATTRIBUTE_KEYS = 20
MAX_VALUE_LEN = 256
MAX_TOKEN_VALUE = 10**9


class EventRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _scalar_map(name: str, value: Any, max_keys: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EventRejected(f"invalid_{name}", f"'{name}' must be an object.")
    if len(value) > max_keys:
        raise EventRejected(f"invalid_{name}", f"'{name}' has more than {max_keys} keys.")
    for k, v in value.items():
        if k.lower() in FORBIDDEN_KEYS:
            raise EventRejected("forbidden_attribute", f"Attribute key '{k}' is not allowed.")
        if isinstance(v, (dict, list)) or v is None:
            raise EventRejected(f"invalid_{name}", f"'{name}' values must be scalars.")
        if len(str(v)) > MAX_VALUE_LEN:
            raise EventRejected(
                f"invalid_{name}", f"'{name}' value exceeds {MAX_VALUE_LEN} characters."
            )
    return value


def _token(data: dict[str, Any], key: str) -> Optional[int]:
    if key not in data:
        return None
    v = data[key]
    if isinstance(v, bool) or not isinstance(v, int) or v < 0 or v > MAX_TOKEN_VALUE:
        raise EventRejected("invalid_token_count", f"'{key}' must be a non-negative integer.")
    return v


def sanitize_data(data: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Validate and reduce ``data`` to the allowed attribute set."""
    for key in data:
        if key.lower() in FORBIDDEN_KEYS:
            raise EventRejected("forbidden_attribute", f"Attribute key '{key}' is not allowed.")
    if len(json.dumps(data, default=str)) > settings.max_event_data_bytes:
        raise EventRejected(
            "data_too_large", f"Event data exceeds {settings.max_event_data_bytes} bytes."
        )
    clean = {k: v for k, v in data.items() if k in ALLOWED_DATA_KEYS}

    if "trace_id" in clean and not (
        isinstance(clean["trace_id"], str) and TRACE_ID_RE.match(clean["trace_id"])
    ):
        raise EventRejected("invalid_trace_id", "trace_id must be 32 lowercase hex characters.")
    for key in ("root_span_id", "span_id", "parent_span_id"):
        if key in clean and not (
            isinstance(clean[key], str) and SPAN_ID_RE.match(clean[key])
        ):
            raise EventRejected("invalid_span_id", f"{key} must be 16 lowercase hex characters.")
    if "metadata" in clean:
        clean["metadata"] = scrub_obj(_scalar_map("metadata", clean["metadata"], MAX_METADATA_KEYS))
    if "attributes" in clean:
        clean["attributes"] = scrub_obj(_scalar_map("attributes", clean["attributes"], MAX_ATTRIBUTE_KEYS))
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        _token(clean, key)
    if "error_type" in clean:
        clean["error_type"] = scrub_text(str(clean["error_type"])[:128])
    if "error_summary" in clean:
        clean["error_summary"] = scrub_text(str(clean["error_summary"])[:1024])
    for key in ("sdk_version",):
        if key in clean:
            clean[key] = str(clean[key])[:32]
    return clean


def _derived_ids(project_id: str, run_id: str) -> tuple[str, str]:
    digest = hashlib.sha256(f"{project_id}:{run_id}".encode()).hexdigest()
    return digest[:32], digest[32:48]


def _recompute_duration(run: Run) -> None:
    if run.start_confirmed and run.ended_at is not None:
        delta = run.ended_at - run.started_at
        run.duration_ms = max(0, int(delta.total_seconds() * 1000))


def _apply_to_run(run: Run, event_type: str, ts: datetime, data: dict[str, Any]) -> None:
    now = utcnow()
    run.updated_at = now

    if event_type == "run_started":
        if not run.start_confirmed:
            run.start_confirmed = True
            run.started_at = ts
            if "trace_id" in data:
                run.trace_id = data["trace_id"]
            if "root_span_id" in data:
                run.root_span_id = data["root_span_id"]
            if run.status == "unknown":
                run.status = "running"
            _recompute_duration(run)
        if data.get("metadata") and run.run_metadata is None:
            run.run_metadata = data["metadata"]
        if "sdk_version" in data:
            run.sdk_version = data["sdk_version"]
    elif event_type in TERMINAL_STATUS:
        if run.status in TERMINAL_STATUS.values():
            pass  # same-status repeat: accepted, no change
        else:
            run.status = TERMINAL_STATUS[event_type]
            run.ended_at = ts
            if event_type == "run_failed":
                run.error_type = data.get("error_type", "UnknownError")
                run.error_summary = data.get("error_summary")
            _recompute_duration(run)
    elif not run.start_confirmed and ts < run.started_at:
        run.started_at = ts  # best estimate until run_started arrives

    if event_type in ("llm_call_completed", "llm_call_failed"):
        run.llm_call_count += 1
    elif event_type in ("tool_call_completed", "tool_call_failed"):
        run.tool_call_count += 1

    if event_type == "llm_call_completed":
        prompt = data.get("prompt_tokens", 0)
        completion = data.get("completion_tokens", 0)
        run.total_prompt_tokens += prompt
        run.total_completion_tokens += completion
        run.total_tokens += data.get("total_tokens", prompt + completion)

    if data.get("deployment_version") and not run.deployment_version:
        run.deployment_version = data["deployment_version"][:64]


def _get_or_create_agent(
    session: Session, settings: Settings, project_id: str, agent_id: str
) -> None:
    if session.get(Agent, (project_id, agent_id)) is not None:
        return
    if not settings.auto_register_agents:
        raise EventRejected("unknown_agent", "Agent is not registered for this project.")
    try:
        with session.begin_nested():
            session.add(
                Agent(project_id=project_id, id=agent_id, name=agent_id, auto_registered=True)
            )
            session.flush()
    except IntegrityError:
        pass  # concurrent registration won the race


def _get_or_create_run(
    session: Session, project_id: str, ev: IngestEvent
) -> Run:
    run = session.get(Run, (project_id, ev.run_id))
    if run is not None:
        return run
    trace_id, root_span_id = _derived_ids(project_id, ev.run_id)
    now = utcnow()
    try:
        with session.begin_nested():
            run = Run(
                project_id=project_id,
                run_id=ev.run_id,
                agent_id=ev.agent_id,
                trace_id=trace_id,
                root_span_id=root_span_id,
                environment=ev.environment,
                status="unknown",
                started_at=ev.timestamp,
                sdk_version="unknown",
                start_confirmed=False,
                created_at=now,
                updated_at=now,
            )
            session.add(run)
            session.flush()
    except IntegrityError:
        run = session.get(Run, (project_id, ev.run_id))
        if run is None:  # pragma: no cover - would indicate a different integrity bug
            raise
    return run


def _process_event(
    session: Session, settings: Settings, project_id: str, ev: IngestEvent, now: datetime
) -> Optional[EventObservation]:
    """Persist one event.

    Returns an :class:`EventObservation` if the event was newly stored, or
    ``None`` if it was a duplicate (idempotent retry).
    """
    if ev.project_id is not None and ev.project_id != project_id:
        raise EventRejected("project_mismatch", "Event project_id differs from batch project_id.")
    if session.get(Event, (project_id, ev.event_id)) is not None:
        return None  # idempotent retry, regardless of current time/validation
    if abs(ev.timestamp - now) > timedelta(hours=settings.timestamp_tolerance_hours):
        raise EventRejected(
            "timestamp_out_of_range",
            f"Timestamp is more than {settings.timestamp_tolerance_hours}h from server time.",
        )
    data = sanitize_data(ev.data, settings)
    if ev.deployment_version and "deployment_version" not in data:
        data["deployment_version"] = ev.deployment_version

    _get_or_create_agent(session, settings, project_id, ev.agent_id)
    run = _get_or_create_run(session, project_id, ev)
    if run.agent_id != ev.agent_id:
        raise EventRejected("agent_mismatch", "run_id already belongs to a different agent.")
    new_status = TERMINAL_STATUS.get(ev.event_type)
    if new_status and run.status in TERMINAL_STATUS.values() and run.status != new_status:
        raise EventRejected(
            "invalid_status_transition",
            f"Run is already '{run.status}'; cannot transition to '{new_status}'.",
        )

    try:
        with session.begin_nested():
            session.add(
                Event(
                    project_id=project_id,
                    event_id=ev.event_id,
                    run_id=ev.run_id,
                    agent_id=ev.agent_id,
                    event_type=ev.event_type,
                    environment=ev.environment,
                    timestamp=ev.timestamp,
                    data=data,
                    received_at=utcnow(),
                )
            )
            session.flush()
    except IntegrityError:
        return None  # concurrent duplicate

    was_terminal = run.status in TERMINAL_STATUS.values()
    had_duration = run.duration_ms is not None
    _apply_to_run(run, ev.event_type, ev.timestamp, data)
    session.flush()
    is_terminal = run.status in TERMINAL_STATUS.values()
    return EventObservation(
        project_id=project_id,
        event_id=ev.event_id,
        run_id=ev.run_id,
        agent_id=ev.agent_id,
        event_type=ev.event_type,
        environment=ev.environment,
        timestamp=ev.timestamp,
        data=dict(data),
        trace_id=run.trace_id,
        root_span_id=run.root_span_id,
        run_status=run.status,
        run_started_at=run.started_at,
        run_ended_at=run.ended_at,
        run_duration_ms=run.duration_ms,
        run_error_type=run.error_type,
        terminal_transition=is_terminal and not was_terminal,
        duration_became_known=(not had_duration) and run.duration_ms is not None,
    )


def validate_envelope(raw_body: bytes, settings: Settings) -> IngestBatch:
    """Parse and validate the request body into an :class:`IngestBatch`."""
    if len(raw_body) > settings.max_payload_bytes:
        raise ApiError(
            413,
            "payload_too_large",
            f"Request body exceeds {settings.max_payload_bytes} bytes.",
        )
    try:
        parsed = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "invalid_json", "Request body is not valid JSON.")
    if not isinstance(parsed, dict):
        raise ApiError(422, "validation_error", "Request body must be a JSON object.")

    from agentops_backend.schemas import SUPPORTED_SCHEMA_VERSIONS

    version = parsed.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ApiError(
            422,
            "unsupported_schema_version",
            "Unsupported or missing schema_version.",
            details={"supported": sorted(SUPPORTED_SCHEMA_VERSIONS)},
        )
    batch = parsed.get("batch")
    if isinstance(batch, list) and len(batch) > settings.max_batch_size:
        raise ApiError(
            422,
            "batch_too_large",
            f"Batch exceeds the maximum of {settings.max_batch_size} events.",
        )
    return IngestBatch.model_validate(parsed)  # RequestValidationError-like handled upstream


def ingest_batch(
    session: Session,
    settings: Settings,
    project_id: str,
    batch: IngestBatch,
    observer: Optional[Observability] = None,
) -> IngestResult:
    if batch.project_id != project_id:
        raise ApiError(
            403, "project_access_denied", "Credential is not valid for this project."
        )
    now = datetime.now(timezone.utc)
    accepted = 0
    duplicates = 0
    rejected: list[RejectedEvent] = []
    observations: list[EventObservation] = []
    try:
        for index, ev in enumerate(batch.batch):
            try:
                observation = _process_event(session, settings, project_id, ev, now)
                if observation:
                    accepted += 1
                    observations.append(observation)
                else:
                    duplicates += 1
            except EventRejected as exc:
                rejected.append(
                    RejectedEvent(
                        index=index, event_id=ev.event_id, code=exc.code, message=exc.message
                    )
                )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.exception("Database error during ingestion")
        raise ApiError(
            503, "database_unavailable", "Storage is temporarily unavailable; retry later."
        )
    if observer is not None:
        # Post-commit and best-effort: never changes the response or stored data.
        observer.record_batch(observations, duplicates, [r.code for r in rejected])
    return IngestResult(accepted=accepted, duplicates=duplicates, rejected=rejected)
