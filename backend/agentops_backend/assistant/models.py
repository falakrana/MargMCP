"""Public schema of a diagnostic report (documented in docs/diagnostic-assistant.md)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from agentops_backend.schemas import SAFE_ID_PATTERN

READ_ONLY_NOTICE = (
    "This report is read-only analysis. The assistant has no write or execution "
    "capability and has not changed any monitored system."
)


class DiagnoseRunRequest(BaseModel):
    run_id: str = Field(pattern=SAFE_ID_PATTERN)
    question: Optional[str] = Field(default=None, max_length=500)


class DiagnoseAgentRequest(BaseModel):
    agent_id: str = Field(pattern=SAFE_ID_PATTERN)
    # ISO-8601; default window is the last 24h (max 30 days), as for MCP tools.
    started_after: Optional[datetime] = None
    started_before: Optional[datetime] = None
    question: Optional[str] = Field(default=None, max_length=500)


class Scope(BaseModel):
    kind: Literal["run", "agent"]
    project_id: str
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    started_after: Optional[str] = None
    started_before: Optional[str] = None
    question: Optional[str] = None


class Finding(BaseModel):
    """A directly observed fact. Always cites retrieved evidence."""

    statement: str
    evidence: list[str]


class Hypothesis(BaseModel):
    """A diagnostic hypothesis - NOT a fact."""

    explanation: str
    confidence: Literal["high", "medium", "low"]
    evidence: list[str]
    uncertainty: str = ""


class EvidenceRef(BaseModel):
    """A cited record, described from data actually retrieved this session."""

    ref: str
    type: Literal["run", "span", "metric", "errors", "comparison"]
    summary: str


class DiagnosticMeta(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    tool_calls: int = 0
    llm_calls: int = 0
    duration_ms: int = 0
    generated_at: str
    evidence_items: int = 0
    llm_skipped: bool = False
    dropped_uncited_statements: int = 0
    rejected_citations: int = 0
    blocked_action_claims: int = 0
    suspicious_content_detected: int = 0


class DiagnosticReport(BaseModel):
    scope: Scope
    findings: list[Finding] = Field(default_factory=list)
    likely_explanations: list[Hypothesis] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)
    next_checks: list[str] = Field(default_factory=list)
    read_only_notice: str = READ_ONLY_NOTICE
    meta: DiagnosticMeta
