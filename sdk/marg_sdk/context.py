import contextvars
from typing import Optional

# Store current run instance
_current_run = contextvars.ContextVar("marg_current_run", default=None)
# Store current trace context (trace_id, span_id)
_current_span_context = contextvars.ContextVar("marg_current_span", default=None)

def get_current_run():
    return _current_run.get()

def set_current_run(run):
    return _current_run.set(run)

def reset_current_run(token):
    _current_run.reset(token)

def get_current_span_context():
    return _current_span_context.get()

def set_current_span_context(span_context):
    return _current_span_context.set(span_context)

def reset_current_span_context(token):
    _current_span_context.reset(token)
