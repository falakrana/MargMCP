"""
AgentOps MCP — Real Pilot Agent Demonstration.

Implements a multi-step customer support & troubleshooting pilot agent:
- Emits telemetry for intent detection, knowledge retrieval, and tool execution.
- Emits custom events with structured metadata.
- Demonstrates resilient telemetry export, credential redaction, and error reporting.

Usage:
    python examples/pilot_agent.py [--scenario success|refund|failure]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

# Ensure SDK is in path
sdk_path = Path(__file__).resolve().parents[1] / "sdk"
if str(sdk_path) not in sys.path:
    sys.path.insert(0, str(sdk_path))

from marg_sdk import Marg, MargConfig, AgentOps, AgentOpsConfig


def create_pilot_client() -> Marg:
    """Initialize Marg SDK from environment variables (.env)."""
    config = MargConfig.from_env()
    if not config.project_id:
        config.project_id = os.environ.get("MARG_PROJECT_ID") or os.environ.get("AGENTOPS_PROJECT_ID", "synthetic-demo")
    if not config.api_key:
        config.api_key = (
            os.environ.get("MARG_API_KEY")
            or os.environ.get("AGENTOPS_API_KEY")
            or os.environ.get("MARG_MCP_API_KEY")
            or os.environ.get("AGENTOPS_MCP_API_KEY")
        )
    config.flush_interval_seconds = 0.5
    config.capture_payloads = True
    return Marg(config=config)


class SupportTools:
    """Mock domain tools representing real external systems."""

    @staticmethod
    def search_knowledge_base(query: str) -> list[str]:
        time.sleep(0.08)  # Simulate search latency
        return [
            f"KB-101: Instructions for billing dispute regarding '{query}'",
            "KB-204: Standard 30-day refund policy documentation",
        ]

    @staticmethod
    def get_account_profile(account_id: str) -> dict:
        time.sleep(0.05)
        return {
            "account_id": account_id,
            "tier": "enterprise",
            "credit_balance": 150.00,
            "status": "active",
        }

    @staticmethod
    def process_refund(account_id: str, amount: float, reason: str) -> dict:
        time.sleep(0.1)
        if amount > 500.0:
            raise ValueError(f"Refund amount ${amount:.2f} exceeds automatic approval ceiling ($500.00)")
        return {
            "transaction_id": f"tx_ref_{int(time.time())}",
            "account_id": account_id,
            "amount": amount,
            "status": "settled",
        }


def run_customer_support_workflow(client: AgentOps, query: str, user_id: str, amount: float = 0.0) -> dict:
    """Execute a realistic multi-step autonomous agent workflow."""
    print(f"\n[PILOT AGENT] Starting run for user '{user_id}': '{query}'")

    with client.start_run(agent_id="support-copilot-v1") as run:
        root_span = run.root_span_id
        s1_id = uuid.uuid4().hex[:16]
        s2_id = uuid.uuid4().hex[:16]

        # Step 1: Retrieval & Classification Span
        print("  -> Searching knowledge base...")
        t0 = time.time()
        kb_articles = SupportTools.search_knowledge_base(query)
        run.record_event("llm_call_completed", {
            "span_id": s1_id,
            "parent_span_id": root_span,
            "duration_ms": int((time.time() - t0) * 1000),
            "prompt_tokens": 120,
            "completion_tokens": 45,
            "total_tokens": 165,
        })

        # Step 2: Account Lookup Span
        print("  -> Fetching customer profile...")
        t1 = time.time()
        profile = SupportTools.get_account_profile(user_id)
        run.record_event("tool_call_completed", {
            "span_id": s2_id,
            "parent_span_id": root_span,
            "tool_name": "account_lookup",
            "duration_ms": int((time.time() - t1) * 1000),
        })

        # Step 3: Action Execution (e.g. Refund)
        if amount > 0:
            print(f"  -> Processing requested refund of ${amount:.2f}...")
            s3_id = uuid.uuid4().hex[:16]
            t2 = time.time()
            try:
                refund_res = SupportTools.process_refund(user_id, amount, reason=query)
                run.record_event("tool_call_completed", {
                    "span_id": s3_id,
                    "parent_span_id": root_span,
                    "tool_name": "process_refund",
                    "duration_ms": int((time.time() - t2) * 1000),
                })
                run.set_output_summary({"refund": refund_res, "user_id": user_id})
                return {
                    "status": "success",
                    "user_id": user_id,
                    "resolution": f"Refund of ${amount:.2f} approved and settled.",
                    "tx": refund_res["transaction_id"],
                }
            except Exception as e:
                run.record_event("tool_call_failed", {
                    "span_id": s3_id,
                    "parent_span_id": root_span,
                    "tool_name": "process_refund",
                    "error_type": type(e).__name__,
                    "error_summary": str(e),
                })
                raise

        # Step 4: General Inquiry Resolution
        run.set_output_summary({"inquiry_resolved": True, "articles_count": len(kb_articles)})
        print("  -> Inquiry resolved successfully.")
        return {
            "status": "success",
            "user_id": user_id,
            "resolution": f"Provided {len(kb_articles)} KB articles.",
        }


def main():
    parser = argparse.ArgumentParser(description="AgentOps Pilot Agent Runner")
    parser.add_argument(
        "--scenario",
        choices=["success", "refund", "failure"],
        default="success",
        help="Scenario to execute",
    )
    args = parser.parse_args()

    client = create_pilot_client()
    try:
        if args.scenario == "success":
            res = run_customer_support_workflow(
                client,
                query="How do I change my organization billing address?",
                user_id="user_acct_4821",
            )
            print(f"[RESULT] {res}")

        elif args.scenario == "refund":
            res = run_customer_support_workflow(
                client,
                query="Requesting prorated refund for cancelled seat",
                user_id="user_acct_9912",
                amount=75.50,
            )
            print(f"[RESULT] {res}")

        elif args.scenario == "failure":
            print("[PILOT AGENT] Executing failure scenario (refund exceeding threshold)...")
            try:
                run_customer_support_workflow(
                    client,
                    query="Requesting maximum compensation refund",
                    user_id="user_acct_1033",
                    amount=1250.00,  # Will trigger ValueError exception
                )
            except Exception as e:
                print(f"[EXPECTED FAILURE HANDLED] {type(e).__name__}: {e}")

    finally:
        print("[PILOT AGENT] Flushing telemetry to AgentOps...")
        client.shutdown()
        print("[PILOT AGENT] Telemetry flush completed.")


if __name__ == "__main__":
    main()
