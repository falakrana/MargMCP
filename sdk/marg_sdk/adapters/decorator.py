from functools import wraps
from typing import Any, Callable

from marg_sdk.client import Marg, AgentOps
from marg_sdk.context import get_current_run

def observe_agent(client: Marg, agent_id: str = None):
    """
    Decorator to wrap an agent execution function.
    Automatically starts a run, records success/failure, and handles context.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if get_current_run() is not None:
                return func(*args, **kwargs)
                
            with client.start_run(agent_id=agent_id):
                return func(*args, **kwargs)
        return wrapper
    return decorator
