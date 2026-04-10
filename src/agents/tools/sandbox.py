"""Sandboxed execution helpers — safe builtins and blocked token enforcement."""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import pandas as pd

# Builtins permitted inside execute_code sandbox.
# Deliberately minimal — no I/O, no import, no introspection.
_SAFE_BUILTINS: Final[dict[str, Any]] = {
    "len": len,
    "range": range,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "None": None,
    "True": True,
    "False": False,
    "isinstance": isinstance,
    "type": type,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "print": print,
}

_BLOCKED_TOKENS: Final[frozenset[str]] = frozenset(
    {"import", "open", "eval", "exec", "__import__", "compile", "globals", "locals", "getattr", "setattr", "delattr"}
)


def build_sandbox(df: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build globals and locals namespaces for sandboxed execution."""
    local_ns: dict[str, Any] = {"df": df.copy(), "pd": pd, "np": np}
    globals_ns: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
    return globals_ns, local_ns


def check_blocked_tokens(code: str) -> str | None:
    """Return an error string if any blocked token is found in the code."""
    for token in _BLOCKED_TOKENS:
        if token in code:
            return f"BLOCKED: '{token}' is not permitted in sandboxed execution."
    return None
