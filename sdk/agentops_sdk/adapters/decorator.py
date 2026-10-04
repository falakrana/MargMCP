from functools import wraps
from typing import Any, Callable

from agentops_sdk.client import AgentOps
from agentops_sdk.context import get_current_run

def observe_agent(agentops: AgentOps, agent_id: str = None):
    """
    Decorator to wrap an agent execution function.
    Automatically starts a run, records success/failure, and handles context.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # If we're already inside a run, just call the function.
            # In a more advanced implementation, this might start a child span.
            if get_current_run() is not None:
                return func(*args, **kwargs)
                
            with agentops.start_run(agent_id=agent_id):
                return func(*args, **kwargs)
        return wrapper
    return decorator
