# AgentOps SDK — Integration Guide

A practical, step-by-step developer guide on integrating AgentOps MCP observability into any Python AI Agent, LangChain workflow, or RAG application.

---

## 1. Quick Overview

The AgentOps SDK is designed with a **gradual adoption model**:
- **Level 1 (Zero-Code-Change Decorator):** Add 2 lines above your agent function. Automatically captures execution time, success/failure, stack traces, and environment.
- **Level 2 (Context Manager):** Wrap multi-step tasks or pipelines with `with agentops.start_run():`.
- **Level 3 (Fine-Grained Spans for RAG / Tools):** Track individual tool executions (e.g., Vector DB retrieval) and LLM token usage for waterfall visualization in the dashboard.

---

## 2. Installation & Configuration

### Step 1: Install the SDK
In your agent's virtual environment:
```bash
pip install agentops-sdk
# Or link directly from the local repository during development:
pip install -e /path/to/AgentOpsMCP/sdk
```

### Step 2: Configure Environment Variables
Add these variables to your project's `.env` file:
```env
AGENTOPS_ENDPOINT=http://localhost:8000
AGENTOPS_PROJECT_ID=my-project-id
AGENTOPS_API_KEY=aop_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxx
```

> **Note on Projects:** Each AI application should use its own dedicated `AGENTOPS_PROJECT_ID` (e.g., `ragnition`, `support-bot`, `sales-agent`) so that telemetry, token costs, and errors are cleanly segregated in the dashboard.

---

## 3. Integration Patterns

### Pattern 1: The 1-Line Decorator (Recommended for 90% of use cases)

If you have an agent function, script, or endpoint, you do **not** need to touch any internal logic. Just add the `@observe_agent` decorator:

```python
from agentops_sdk import AgentOps
from agentops_sdk.adapters.decorator import observe_agent

# Initialize the client from environment variables (.env)
agentops = AgentOps.from_env()

@observe_agent(agentops, agent_id="document-analysis-agent")
def run_agent(user_query: str):
    # Your existing agent code remains 100% untouched
    result = execute_complex_agent_pipeline(user_query)
    return result
```

#### What gets captured automatically:
- ✅ **Run Lifecycle:** When the agent starts and finishes.
- ✅ **Execution Duration:** Total elapsed time down to the millisecond.
- ✅ **Status:** Marked as `success` or `error`.
- ✅ **Exception Diagnostics:** If your function throws an error, the SDK automatically captures the exception type and safe error summary before propagating the error.

---

### Pattern 2: Context Manager (`with` block)

Ideal for classes, scripts, or async pipelines where you want explicit control over when a run starts and ends:

```python
from agentops_sdk import AgentOps

agentops = AgentOps.from_env()

def handle_user_request(request_data):
    with agentops.start_run(agent_id="customer-support-agent") as run:
        # Run your AI task
        output = process_request(request_data)
        
        # Optionally attach a safe summary
        run.set_output_summary({"status": "resolved", "items_processed": 5})
        return output
```

---

### Pattern 3: Fine-Grained Span Tracking (RAG & Multi-Tool Pipelines)

Use this pattern when you want the dashboard's **Waterfall Span Tree** to show separate breakdown bars for:
1. Vector Database / Document Retrieval duration.
2. Individual Tool executions.
3. LLM generation latency and token counts.

#### Real-World RAG Example:

```python
import time
from agentops_sdk import AgentOps

agentops = AgentOps.from_env()

async def run_rag_pipeline(document_id: str, query: str):
    # 1. Start the agent run
    with agentops.start_run(agent_id="ragnition-rag-agent") as run:
        
        # 2. Track Retrieval (Vector DB / Chroma / Pinecone)
        t0 = time.perf_counter()
        retrieved_docs = await retriever.ainvoke(query)
        retrieval_ms = (time.perf_counter() - t0) * 1000.0

        run.record_event("tool_call_completed", {
            "tool_name": "chroma_retriever",
            "duration_ms": retrieval_ms,
            "chunks_retrieved": len(retrieved_docs),
            "document_id": document_id
        })

        # 3. Track LLM Generation
        t0_llm = time.perf_counter()
        llm_response = await llm.ainvoke(messages)
        llm_ms = (time.perf_counter() - t0_llm) * 1000.0

        run.record_event("llm_call_completed", {
            "provider": "groq",
            "model": "qwen/qwen3.8-27b",
            "duration_ms": llm_ms,
            "prompt_tokens": 120,
            "completion_tokens": 45
        })

        return llm_response
```

---

## 4. Best Practices & Safety Guarantees

1. **Non-Blocking / Best-Effort Delivery:**
   - Telemetry is buffered in an in-memory queue and dispatched asynchronously by a background worker thread.
   - An observability backend outage or slow network connection will **never** slow down or crash your AI agent.
2. **Safe Fallback in Production:**
   - Wrap the SDK initialization in a `try...except` so your service starts smoothly even if observability is temporarily disabled:
     ```python
     try:
         from agentops_sdk import AgentOps
         agentops = AgentOps.from_env()
     except Exception:
         agentops = None
     ```
3. **Privacy by Default:**
   - Sensitive user prompts, raw completions, and secret tool arguments are redacted by default unless payload capture is explicitly enabled via `AGENTOPS_CAPTURE_PAYLOADS=true`.
   - Never log authorization headers or private API tokens into event payloads.

---

## 5. Troubleshooting & Common Pitfalls

| Issue | Cause | Fix |
|---|---|---|
| **`HTTP 404` when connecting dashboard** | Port collision (e.g. host application ran on port `8000`). | Run AgentOps backend on `8000` and your AI agent app on another port (e.g., `8001`). |
| **`ModuleNotFoundError: No module named 'agentops_sdk'`** | Running with system Python instead of the activated virtual environment. | Start your server using the virtual environment interpreter (e.g. `.\.venv\Scripts\python`). |
| **Runs not appearing on dashboard** | Background worker hasn't flushed yet, or process exited immediately. | The SDK flushes batches every 2 seconds. In one-off CLI scripts, call `agentops.shutdown()` before exit to flush the queue. |
