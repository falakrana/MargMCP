# Marg MCP SDK

Python SDK for instrumenting AI agents for Marg MCP.

## Installation

```bash
pip install -e .
```

## Basic Usage

```python
from marg_sdk import Marg

marg = Marg.from_env()

with marg.start_run(agent_id="my-agent") as run:
    # ... your agent logic here
    run.set_output_summary({"result": "Success"})
```
