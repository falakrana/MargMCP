"""Retention and deletion of run metadata/events (Phase 9).

What this does and does not delete
----------------------------------
* Deletes ``runs`` rows older than the cutoff (by ``started_at``) together with
  all of their ``events`` rows, in bounded batches, one transaction per batch
  (events first, then runs), so no batch ever leaves orphaned events or a run
  that is missing its events.
* Projects, agents and API keys are never touched.
* **Trace backend:** span data lives in Tempo, which has no per-trace delete
  API; it expires by block retention (``infra/tempo/tempo.yml``). After a purge
  a trace may therefore outlive its run record for up to the Tempo retention
  period. Keep ``AGENTOPS_TRACE_RETENTION_DAYS`` <= ``AGENTOPS_RUN_RETENTION_DAYS``
  so traces never outlive metadata under normal configuration.
* Prometheus series are aggregate numeric time series without run identifiers;
  they age out under Prometheus' own retention and are not deleted per run.

Destructive execution is opt-in everywhere: dry-run is the default for the API
and the CLI.

CLI::

    python -m agentops_backend.retention                # dry run, configured retention
    python -m agentops_backend.retention --older-than-days 30 --execute
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from agentops_backend.models import Event, Run

logger = logging.getLogger("agentops_backend.audit")

TRACE_BACKEND_NOTE = (
    "Trace spans in the trace backend (Tempo) are not deleted by this operation; "
    "they expire by the backend's own block retention."
)


@dataclass
class PurgeResult:
    dry_run: bool
    cutoff: Optional[datetime]
    project_id: Optional[str]
    runs: int
    events: int
    batches: int
    complete: bool
    trace_backend_note: str = TRACE_BACKEND_NOTE


def _conditions(cutoff: Optional[datetime], project_id: Optional[str]) -> list:
    conds: list = []
    if cutoff is not None:
        conds.append(Run.started_at < cutoff)
    if project_id is not None:
        conds.append(Run.project_id == project_id)
    return conds


def purge_runs(
    session: Session,
    *,
    cutoff: Optional[datetime],
    project_id: Optional[str] = None,
    dry_run: bool = True,
    batch_size: int = 500,
    max_batches: int = 100,
) -> PurgeResult:
    """Delete (or count) runs started before ``cutoff`` and their events.

    ``cutoff=None`` matches every run (use together with ``project_id`` to erase
    one project's telemetry). At least one of the two must be given.
    """
    if cutoff is None and project_id is None:
        raise ValueError("refusing to purge without a cutoff or a project_id")
    conds = _conditions(cutoff, project_id)

    if dry_run:
        runs = session.execute(select(func.count()).select_from(Run).where(*conds)).scalar_one()
        events = session.execute(
            select(func.count())
            .select_from(Event)
            .join(
                Run,
                (Event.project_id == Run.project_id) & (Event.run_id == Run.run_id),
            )
            .where(*conds)
        ).scalar_one()
        return PurgeResult(True, cutoff, project_id, runs, events, 0, True)

    runs_deleted = events_deleted = batches = 0
    complete = False
    while batches < max_batches:
        pairs = session.execute(
            select(Run.project_id, Run.run_id)
            .where(*conds)
            .order_by(Run.started_at, Run.project_id, Run.run_id)
            .limit(batch_size)
        ).all()
        if not pairs:
            complete = True
            break
        by_project: dict[str, list[str]] = {}
        for pid, rid in pairs:
            by_project.setdefault(pid, []).append(rid)
        for pid, run_ids in by_project.items():
            events_deleted += session.execute(
                delete(Event).where(Event.project_id == pid, Event.run_id.in_(run_ids))
            ).rowcount or 0
            runs_deleted += session.execute(
                delete(Run).where(Run.project_id == pid, Run.run_id.in_(run_ids))
            ).rowcount or 0
        session.commit()
        batches += 1
    else:
        # Loop ended on max_batches: check whether anything is left.
        complete = (
            session.execute(select(func.count()).select_from(Run).where(*conds)).scalar_one() == 0
        )
    return PurgeResult(False, cutoff, project_id, runs_deleted, events_deleted, batches, complete)


def purge_older_than(
    session: Session,
    *,
    days: int,
    project_id: Optional[str] = None,
    dry_run: bool = True,
    max_batches: int = 100,
    now: Optional[datetime] = None,
) -> PurgeResult:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    result = purge_runs(
        session, cutoff=cutoff, project_id=project_id, dry_run=dry_run, max_batches=max_batches
    )
    _audit(result)
    return result


def purge_project_telemetry(
    session: Session, project_id: str, *, dry_run: bool = True, max_batches: int = 100
) -> PurgeResult:
    result = purge_runs(
        session, cutoff=None, project_id=project_id, dry_run=dry_run, max_batches=max_batches
    )
    _audit(result)
    return result


def _audit(result: PurgeResult) -> None:
    # Counts only: never run ids or payload content.
    logger.info(
        "retention.purge dry_run=%s project=%s runs=%d events=%d batches=%d complete=%s",
        result.dry_run, result.project_id or "*", result.runs, result.events,
        result.batches, result.complete,
    )


def main(argv: Optional[list[str]] = None) -> int:
    from agentops_backend.config import get_settings
    from agentops_backend.db import make_engine, make_session_factory

    parser = argparse.ArgumentParser(description="Purge expired AgentOps run data.")
    parser.add_argument("--older-than-days", type=int, default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--max-batches", type=int, default=100)
    parser.add_argument(
        "--execute", action="store_true", help="actually delete (default: dry run)"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    days = args.older_than_days or settings.run_retention_days
    engine = make_engine(settings.resolved_database_url(), settings)
    try:
        with make_session_factory(engine)() as session:
            result = purge_older_than(
                session, days=days, project_id=args.project_id,
                dry_run=not args.execute, max_batches=args.max_batches,
            )
    finally:
        engine.dispose()
    out = asdict(result)
    out["cutoff"] = result.cutoff.isoformat() if result.cutoff else None
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
