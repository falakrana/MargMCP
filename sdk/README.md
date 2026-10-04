# AgentOps SDK

Python SDK for instrumenting AI agents for AgentOps MCP.

## Installation

```bash
pip install -e .
```

## Basic Usage

```python
from agentops_sdk import AgentOps

agentops = AgentOps.from_env()

with agentops.start_run(agent_name="my-agent") as run:
    # ... your agent logic here
    run.set_output_summary({"result": "Success"})
```
