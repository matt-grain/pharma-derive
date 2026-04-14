"""Auto-responder for simple_mock mailbox test — feeds canned responses for 4 derivations.

Matches TEST_MCP.md canned responses. Exits after 30 min of idle (no pending requests).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import cast

# Line-buffered stdout so `print` updates surface live under `uv run` in a background shell
# (Python block-buffers stdout on Windows when it's not a tty, which hid script progress
# during Phase 18.1 validation).
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

MAILBOX = "http://localhost:8650/mailbox"
IDLE_TIMEOUT_S = 1800  # 30 min — deliberate long window so HITL waits don't kill the responder


def get_pending() -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", json.loads(urllib.request.urlopen(MAILBOX).read()))  # noqa: S310


def get_request(rid: int) -> dict[str, object] | None:
    """Fetch a request by id. Returns None if the mailbox has already consumed it (404)."""
    try:
        return cast("dict[str, object]", json.loads(urllib.request.urlopen(f"{MAILBOX}/{rid}").read()))  # noqa: S310
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def respond(rid: int, args: dict[str, object]) -> bool:
    """POST a canned response. Returns True on success, False if the request was already consumed (404)."""
    body = json.dumps(
        {
            "content": "",
            "tool_calls": [
                {
                    "id": f"call_{rid}",
                    "type": "function",
                    "function": {"name": "final_result", "arguments": json.dumps(args)},
                }
            ],
        }
    ).encode()
    req = urllib.request.Request(f"{MAILBOX}/{rid}", data=body, method="POST")  # noqa: S310
    req.add_header("Content-Type", "application/json")
    try:
        urllib.request.urlopen(req)  # noqa: S310
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False  # request already consumed by a concurrent responder — not an error
        raise
    return True


def identify_role(sys_prompt: str) -> str:
    """Classify the agent from the unique first-sentence fingerprint of its system prompt.

    Keyed on the exact role declaration in each agent YAML under ``config/agents/``:
    ``coder`` → "senior statistical programmer"
    ``qc_programmer`` → "QC (quality control) programmer"
    ``debugger`` → "senior clinical programmer debugging"
    ``auditor`` → "regulatory compliance auditor"
    ``spec_interpreter`` → "clinical data specification analyst"

    The first-sentence check is robust against content that appears later in the
    prompt — including Phase 17.1's LTM tool descriptions, which mention
    "debugger" inside the coder's prompt and used to trip the old ``"debug" in
    sys_prompt`` heuristic.
    """
    head = sys_prompt[:300].lower()
    if "senior statistical programmer" in head:
        return "coder"
    if "qc (quality control) programmer" in head:
        return "qc"
    if "senior clinical programmer debugging" in head:
        return "debugger"
    if "regulatory compliance auditor" in head:
        return "auditor"
    if "clinical data specification analyst" in head:
        return "spec_interpreter"
    return "unknown"


def identify(rid: int) -> tuple[str, str] | None:
    """Identify (role, variable) from the mailbox request, or None if stale (404).

    Variable is matched on the user message prefix — not keywords — because 'age'
    appears in AGE_GROUP, IS_ELDERLY, and RISK_SCORE spec logic strings.
    """
    r = get_request(rid)
    if r is None:
        return None
    messages = cast("list[dict[str, str]]", r["messages"])
    sys_prompt = messages[0]["content"]
    user_msg = messages[1]["content"] if len(messages) > 1 else ""

    role = identify_role(sys_prompt)

    if user_msg.startswith("If age < 18") or user_msg.startswith("Age group"):
        var = "AGE_GROUP"
    elif user_msg.startswith("Number of days") or user_msg.startswith("Treatment duration"):
        var = "TREATMENT_DURATION"
    elif user_msg.startswith("True if AGE_GROUP"):
        var = "IS_ELDERLY"
    elif user_msg.startswith("If IS_ELDERLY"):
        var = "RISK_SCORE"
    elif role == "debugger":
        var = "DEBUG"
    elif role == "auditor":
        var = "AUDIT"
    else:
        var = "UNKNOWN"

    return role, var


RESPONSES: dict[tuple[str, str], dict[str, object]] = {
    ("coder", "AGE_GROUP"): {
        "variable_name": "AGE_GROUP",
        "python_code": "pd.cut(df['age'], bins=[0,18,65,200], labels=['minor','adult','senior'], right=False)",
        "approach": "pd.cut with bin edges",
        "null_handling": "NaN propagated by pd.cut",
    },
    ("qc", "AGE_GROUP"): {
        "variable_name": "AGE_GROUP",
        "python_code": (
            "pd.Series(np.select([df['age']<18, df['age']<65, df['age']>=65], "
            "['minor','adult','senior'], default=None), index=df.index).where(df['age'].notna())"
        ),
        "approach": "np.select with conditions",
        "null_handling": "where(notna()) mask",
    },
    ("coder", "TREATMENT_DURATION"): {
        "variable_name": "TREATMENT_DURATION",
        "python_code": "(pd.to_datetime(df['treatment_end']) - pd.to_datetime(df['treatment_start'])).dt.days + 1",
        "approach": "Vectorized datetime subtraction",
        "null_handling": "NaT propagates",
    },
    ("qc", "TREATMENT_DURATION"): {
        "variable_name": "TREATMENT_DURATION",
        "python_code": (
            "df.apply(lambda r: (pd.to_datetime(r['treatment_end']) - pd.to_datetime(r['treatment_start'])).days + 1 "
            "if pd.notna(r['treatment_end']) and pd.notna(r['treatment_start']) else None, axis=1).astype('Float64')"
        ),
        "approach": "Row-wise apply with null checks",
        "null_handling": "None if either date missing",
    },
    ("coder", "IS_ELDERLY"): {
        "variable_name": "IS_ELDERLY",
        "python_code": "(df['AGE_GROUP'] == 'senior').where(df['AGE_GROUP'].notna())",
        "approach": "Direct equality with null mask",
        "null_handling": "Null where AGE_GROUP is null",
    },
    ("qc", "IS_ELDERLY"): {
        "variable_name": "IS_ELDERLY",
        "python_code": "df['AGE_GROUP'].map({'senior': True, 'adult': False, 'minor': False})",
        "approach": "Dictionary mapping",
        "null_handling": "NaN keys map to NaN",
    },
    ("coder", "RISK_SCORE"): {
        "variable_name": "RISK_SCORE",
        "python_code": (
            "pd.Series(np.select("
            "[df['IS_ELDERLY'].eq(True) & df['TREATMENT_DURATION'].gt(120), "
            "df['IS_ELDERLY'].eq(True) & df['TREATMENT_DURATION'].le(120), "
            "df['IS_ELDERLY'].eq(False)], "
            "['high', 'medium', 'low'], default=None), index=df.index)"
            ".where(df['IS_ELDERLY'].notna() & df['TREATMENT_DURATION'].notna(), other=None)"
        ),
        "approach": "np.select with double mask",
        "null_handling": "Null if IS_ELDERLY or TREATMENT_DURATION is null",
    },
    ("qc", "RISK_SCORE"): {
        "variable_name": "RISK_SCORE",
        "python_code": (
            "df.apply(lambda r: ('high' if r['TREATMENT_DURATION'] > 120 else 'medium') "
            "if r['IS_ELDERLY'] == True else 'low' "
            "if pd.notna(r['IS_ELDERLY']) and pd.notna(r['TREATMENT_DURATION']) else None, axis=1)"
        ),
        "approach": "Row-wise apply with nested conditionals",
        "null_handling": "None if any source null",
    },
    ("debugger", "DEBUG"): {
        "variable_name": "RISK_SCORE",
        "root_cause": "Null handling difference between np.select and apply",
        "correct_implementation": "qc",
        "suggested_fix": "",
        "confidence": "high",
    },
    ("auditor", "AUDIT"): {
        "study": "simple_mock",
        "total_derivations": 4,
        "auto_approved": 3,
        "qc_mismatches": 1,
        "human_interventions": 0,
        "summary": (
            "All 4 derivations completed. AGE_GROUP, TREATMENT_DURATION, IS_ELDERLY passed QC. "
            "RISK_SCORE had a mismatch resolved by debugger."
        ),
        "recommendations": ["Review null handling in multi-source derivations"],
    },
}


def main() -> None:
    print(f"simple_mock auto-responder ({len(RESPONSES)} canned responses) — idle timeout 30min...")
    idle_start: float | None = None
    while True:
        pending = get_pending()
        if not pending:
            if idle_start is None:
                idle_start = time.monotonic()
            elif time.monotonic() - idle_start >= IDLE_TIMEOUT_S:
                break
            time.sleep(1)
            continue
        idle_start = None
        for p in pending:
            rid = cast("int", p["request_id"])
            ident = identify(rid)
            if ident is None:
                print(f"  #{rid}: stale (consumed) — skipping")
                continue
            role, var = ident
            key = (role, var)
            if key in RESPONSES:
                if respond(rid, RESPONSES[key]):
                    print(f"  #{rid}: {role}/{var} -> OK")
                else:
                    print(f"  #{rid}: {role}/{var} -> SKIPPED (already consumed)")
            else:
                print(f"  #{rid}: {role}/{var} -> UNKNOWN, skipping")
        time.sleep(2)
    print("Done — idle timeout reached.")


if __name__ == "__main__":
    main()
