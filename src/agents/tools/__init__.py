"""Agent tools for Coder and QC agents.

Error handling strategy (3 layers):

1. **Tool-level** — Each tool catches expected errors (SyntaxError, TypeError, etc.)
   and returns them as ``"ERROR: ..."`` strings. The LLM reads the error and adjusts
   its code on the next turn. This is the normal retry path.

2. **Tracing** — The ``@traced_tool`` decorator (``tracing.py``) logs every tool call
   with timing. On unexpected exceptions it logs at ERROR level with the full
   exception, then re-raises.

3. **PydanticAI** — When a tool raises any unhandled exception, PydanticAI wraps it
   as a ``ToolRetryError`` and sends the error text back to the LLM as a retry prompt,
   up to the agent's ``retries`` limit (default 3). If all retries are exhausted,
   the exception propagates to the orchestrator which handles it via the FSM
   ``fail()`` transition.

Raising ``ModelRetry("message")`` from a tool explicitly triggers the retry without
consuming the generic exception path — prefer this for known-recoverable failures.
"""

from __future__ import annotations

from src.agents.tools.execute_code import execute_code
from src.agents.tools.inspect_data import inspect_data

__all__ = ["execute_code", "inspect_data"]
