"""Tool tracing — adds structured logging and timing to PydanticAI tools."""

from __future__ import annotations

import functools
import time
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

from loguru import logger

P = ParamSpec("P")
R = TypeVar("R")


def traced_tool(
    name: str,
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    """Decorator that logs tool entry, exit, timing, and errors."""

    def decorator(fn: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            logger.info("Tool {name} started", name=name)
            start = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                logger.info("Tool {name} completed in {ms:.1f}ms", name=name, ms=elapsed)
                return result
            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000
                logger.error("Tool {name} failed after {ms:.1f}ms: {err}", name=name, ms=elapsed, err=exc)
                raise

        return wrapper

    return decorator
