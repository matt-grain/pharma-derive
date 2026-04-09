# Step 6 — Detailed Mailbox Protocol for Manual Functional Test

## Overview

This documents the exact protocol for running the CDDE orchestrator against AgentLens in **mailbox mode** (no real LLM). You act as the LLM by responding to each mailbox request manually or via script.

## Prerequisites

```bash
# Terminal 1: Start AgentLens mailbox
cd C:\Projects\AgentLens
uv run agentlens serve --mode mailbox --port 8650

# Terminal 2: Run orchestrator
cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework
uv run python -c "
import asyncio
from pathlib import Path
from src.engine.orchestrator import DerivationOrchestrator

async def main():
    orchestrator = DerivationOrchestrator(
        spec_path='specs/simple_mock.yaml',
        llm_base_url='http://localhost:8650/v1',
        output_dir=Path('output'),
    )
    result = await orchestrator.run()
    print(f'Status: {result.status}')
    print(f'Derived: {result.derived_variables}')
    print(f'QC: {result.qc_summary}')
    print(f'Errors: {result.errors}')
    print(f'Audit records: {len(result.audit_records)}')

asyncio.run(main())
"

# Terminal 3: Respond to mailbox (this protocol)
```

## Respond Helper

Save this as `respond.py` or paste into terminal:

```python
import json, urllib.request

def respond(rid, args):
    """Send a final_result response to a mailbox request."""
    body = json.dumps({
        "content": "",
        "tool_calls": [{
            "id": f"call_{rid}",
            "type": "function",
            "function": {
                "name": "final_result",
                "arguments": json.dumps(args)
            }
        }]
    }).encode()
    req = urllib.request.Request(
        f"http://localhost:8650/mailbox/{rid}",
        data=body, method="POST"
    )
    req.add_header("Content-Type", "application/json")
    print(f"  #{rid}:", urllib.request.urlopen(req).read().decode())
```

## Monitoring Commands

```bash
# List pending requests
curl -s http://localhost:8650/mailbox | python -m json.tool

# Inspect a specific request (see system prompt + user message)
curl -s http://localhost:8650/mailbox/{ID} | python -m json.tool

# Identify role (first 40 chars of system prompt)
curl -s http://localhost:8650/mailbox/{ID} | python -c "
import sys,json
d=json.load(sys.stdin)
print('Role:', d['messages'][0]['content'][:60])
print('Task:', d['messages'][1]['content'][:80])
"
```

## Expected Flow

The orchestrator sends requests in DAG order. Each layer waits for the previous to complete.

### Phase A — Spec Interpreter (optional, may be skipped)

The orchestrator may or may not call the spec interpreter depending on implementation.
If present: 1 request, respond with parsed rules.

### Phase B — Layer 0: AGE_GROUP + TREATMENT_DURATION (4 requests)

4 requests arrive simultaneously (2 variables x Coder+QC each):

| Request | Role | Variable | How to Identify |
|---------|------|----------|-----------------|
| N | QC | TREATMENT_DURATION | System: "QC...INDEPENDENT", User: "Number of days..." |
| N+1 | Coder | TREATMENT_DURATION | System: "senior statistical", User: "Number of days..." |
| N+2 | QC | AGE_GROUP | System: "QC...INDEPENDENT", User: "If age < 18..." |
| N+3 | Coder | AGE_GROUP | System: "senior statistical", User: "If age < 18..." |

**Note:** Request IDs and ordering may vary. Always check the system prompt to identify Coder vs QC.

**Responses:**

```python
# Identify which ID is which first!
# curl -s http://localhost:8650/mailbox | python -m json.tool

# --- TREATMENT_DURATION ---
# Coder (vectorized):
respond(CODER_DUR_ID, {
    "variable_name": "TREATMENT_DURATION",
    "python_code": "(pd.to_datetime(df['treatment_end']) - pd.to_datetime(df['treatment_start'])).dt.days + 1",
    "approach": "Vectorized datetime subtraction with +1 inclusive",
    "null_handling": "NaT propagates naturally through datetime ops"
})

# QC (row-wise apply):
respond(QC_DUR_ID, {
    "variable_name": "TREATMENT_DURATION",
    "python_code": "df.apply(lambda r: (pd.to_datetime(r['treatment_end']) - pd.to_datetime(r['treatment_start'])).days + 1 if pd.notna(r['treatment_end']) and pd.notna(r['treatment_start']) else None, axis=1).astype('Float64')",
    "approach": "Row-wise apply with explicit null check per row",
    "null_handling": "Returns None if either date is missing"
})

# --- AGE_GROUP ---
# Coder (pd.cut):
respond(CODER_AGE_ID, {
    "variable_name": "AGE_GROUP",
    "python_code": "pd.cut(df['age'], bins=[0,18,65,200], labels=['minor','adult','senior'], right=False)",
    "approach": "pd.cut with bin edges",
    "null_handling": "NaN propagated by pd.cut automatically"
})

# QC (np.select):
respond(QC_AGE_ID, {
    "variable_name": "AGE_GROUP",
    "python_code": "pd.Series(np.select([df['age']<18, df['age']<65, df['age']>=65], ['minor','adult','senior'], default=None), index=df.index).where(df['age'].notna())",
    "approach": "np.select with conditions array and .where() null mask",
    "null_handling": "Null via .where(notna()) mask"
})
```

### Phase C — Layer 1: IS_ELDERLY (2 requests)

2 requests arrive after Layer 0 completes:

```python
# Coder (direct comparison):
respond(CODER_ELDERLY_ID, {
    "variable_name": "IS_ELDERLY",
    "python_code": "(df['AGE_GROUP'] == 'senior').where(df['AGE_GROUP'].notna())",
    "approach": "Direct equality comparison with .where() null mask",
    "null_handling": "Null where AGE_GROUP is null via .where(notna())"
})

# QC (map):
respond(QC_ELDERLY_ID, {
    "variable_name": "IS_ELDERLY",
    "python_code": "df['AGE_GROUP'].map({'senior': True, 'adult': False, 'minor': False})",
    "approach": "Dictionary mapping — explicit True/False per category",
    "null_handling": "NaN keys map to NaN automatically"
})
```

### Phase D — Layer 2: RISK_SCORE (2 requests)

2 requests arrive after Layer 1 completes:

```python
# Coder (np.select):
respond(CODER_RISK_ID, {
    "variable_name": "RISK_SCORE",
    "python_code": "np.select([df['IS_ELDERLY'].eq(True) & df['TREATMENT_DURATION'].gt(120), df['IS_ELDERLY'].eq(True) & df['TREATMENT_DURATION'].le(120), df['IS_ELDERLY'].eq(False)], ['high', 'medium', 'low'], default=None).where(df['IS_ELDERLY'].notna() & df['TREATMENT_DURATION'].notna(), other=None)",
    "approach": "np.select with boolean conditions and .where() null mask",
    "null_handling": "Null if IS_ELDERLY or TREATMENT_DURATION is null"
})

# QC (apply lambda):
respond(QC_RISK_ID, {
    "variable_name": "RISK_SCORE",
    "python_code": "df.apply(lambda r: ('high' if r['TREATMENT_DURATION'] > 120 else 'medium') if r['IS_ELDERLY'] == True else 'low' if pd.notna(r['IS_ELDERLY']) and pd.notna(r['TREATMENT_DURATION']) else None, axis=1)",
    "approach": "Row-wise apply with nested conditionals",
    "null_handling": "Returns None if any source is null"
})
```

**Note:** RISK_SCORE may trigger a QC mismatch (the np.select and apply approaches handle null edge cases differently). If so, a **debugger** request will appear.

### Phase E — Debugger (conditional, 1 request)

If a QC mismatch occurs, the debugger agent is called:

```python
respond(DEBUGGER_ID, {
    "variable_name": "RISK_SCORE",
    "root_cause": "The coder np.select defaults non-elderly to low even when sources are null. The QC apply correctly returns None when sources are null.",
    "correct_implementation": "qc",
    "suggested_fix": "np.select([df['IS_ELDERLY'].eq(True) & df['TREATMENT_DURATION'].gt(120), df['IS_ELDERLY'].eq(True) & df['TREATMENT_DURATION'].le(120), df['IS_ELDERLY'].eq(False)], ['high', 'medium', 'low'], default=None).where(df['IS_ELDERLY'].notna() & df['TREATMENT_DURATION'].notna(), other=None)",
    "confidence": "high"
})
```

### Phase F — Auditor (1 request)

Final step — the auditor summarizes the workflow:

```python
respond(AUDITOR_ID, {
    "study": "simple_mock",
    "total_derivations": 4,
    "auto_approved": 3,
    "qc_mismatches": 1,
    "human_interventions": 0,
    "summary": "All 4 derivations completed. AGE_GROUP, TREATMENT_DURATION, and IS_ELDERLY passed QC on first attempt. RISK_SCORE had a QC mismatch due to null handling differences, resolved by debugger.",
    "recommendations": [
        "Review RISK_SCORE null handling edge case for production robustness",
        "Consider adding explicit null-propagation unit tests for multi-source derivations"
    ]
})
```

## Expected Final Output (Terminal 2)

```
Status: completed
Derived: ['AGE_GROUP', 'TREATMENT_DURATION', 'IS_ELDERLY', 'RISK_SCORE']
QC: {'AGE_GROUP': 'match', 'TREATMENT_DURATION': 'match', 'IS_ELDERLY': 'match', 'RISK_SCORE': 'mismatch'}
Errors: []
Audit records: ~15-25
```

## Quick One-Shot Script

For fast replay without manual identification, save all responses in a single script that polls and auto-responds:

```python
import json, time, urllib.request

MAILBOX = "http://localhost:8650/mailbox"

def get_pending():
    return json.loads(urllib.request.urlopen(MAILBOX).read())

def get_request(rid):
    return json.loads(urllib.request.urlopen(f"{MAILBOX}/{rid}").read())

def respond(rid, args):
    body = json.dumps({
        "content": "",
        "tool_calls": [{"id": f"call_{rid}", "type": "function",
                        "function": {"name": "final_result", "arguments": json.dumps(args)}}]
    }).encode()
    req = urllib.request.Request(f"{MAILBOX}/{rid}", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    urllib.request.urlopen(req)

def identify(rid):
    """Returns (role, variable) tuple."""
    r = get_request(rid)
    role = "qc" if "QC" in r["messages"][0]["content"] else "coder"
    if "debugger" in r["messages"][0]["content"].lower():
        role = "debugger"
    if "audit" in r["messages"][0]["content"].lower():
        role = "auditor"
    preview = r.get("preview", r["messages"][1]["content"][:50]) if len(r["messages"]) > 1 else ""
    if "age" in preview.lower() and "elderly" not in preview.lower():
        var = "AGE_GROUP"
    elif "treatment" in preview.lower() or "days" in preview.lower():
        var = "TREATMENT_DURATION"
    elif "elderly" in preview.lower():
        var = "IS_ELDERLY"
    elif "risk" in preview.lower():
        var = "RISK_SCORE"
    elif "debug" in preview.lower():
        var = "DEBUG"
    elif "audit" in preview.lower():
        var = "AUDIT"
    else:
        var = "UNKNOWN"
    return role, var

# --- Canned responses ---
RESPONSES = {
    ("coder", "TREATMENT_DURATION"): {
        "variable_name": "TREATMENT_DURATION",
        "python_code": "(pd.to_datetime(df['treatment_end']) - pd.to_datetime(df['treatment_start'])).dt.days + 1",
        "approach": "Vectorized datetime subtraction", "null_handling": "NaT propagates"
    },
    ("qc", "TREATMENT_DURATION"): {
        "variable_name": "TREATMENT_DURATION",
        "python_code": "df.apply(lambda r: (pd.to_datetime(r['treatment_end']) - pd.to_datetime(r['treatment_start'])).days + 1 if pd.notna(r['treatment_end']) and pd.notna(r['treatment_start']) else None, axis=1).astype('Float64')",
        "approach": "Row-wise apply", "null_handling": "Explicit null check"
    },
    ("coder", "AGE_GROUP"): {
        "variable_name": "AGE_GROUP",
        "python_code": "pd.cut(df['age'], bins=[0,18,65,200], labels=['minor','adult','senior'], right=False)",
        "approach": "pd.cut", "null_handling": "NaN propagated"
    },
    ("qc", "AGE_GROUP"): {
        "variable_name": "AGE_GROUP",
        "python_code": "pd.Series(np.select([df['age']<18, df['age']<65, df['age']>=65], ['minor','adult','senior'], default=None), index=df.index).where(df['age'].notna())",
        "approach": "np.select", "null_handling": "where() mask"
    },
    ("coder", "IS_ELDERLY"): {
        "variable_name": "IS_ELDERLY",
        "python_code": "(df['AGE_GROUP'] == 'senior').where(df['AGE_GROUP'].notna())",
        "approach": "Direct comparison", "null_handling": "where(notna())"
    },
    ("qc", "IS_ELDERLY"): {
        "variable_name": "IS_ELDERLY",
        "python_code": "df['AGE_GROUP'].map({'senior': True, 'adult': False, 'minor': False})",
        "approach": "Dict mapping", "null_handling": "NaN maps to NaN"
    },
    ("coder", "RISK_SCORE"): {
        "variable_name": "RISK_SCORE",
        "python_code": "pd.Series(np.select([df['IS_ELDERLY'].eq(True) & df['TREATMENT_DURATION'].gt(120), df['IS_ELDERLY'].eq(True) & df['TREATMENT_DURATION'].le(120), df['IS_ELDERLY'].eq(False)], ['high', 'medium', 'low'], default=None), index=df.index).where(df['IS_ELDERLY'].notna() & df['TREATMENT_DURATION'].notna(), other=None)",
        "approach": "np.select", "null_handling": "where() double mask"
    },
    ("qc", "RISK_SCORE"): {
        "variable_name": "RISK_SCORE",
        "python_code": "df.apply(lambda r: ('high' if r['TREATMENT_DURATION'] > 120 else 'medium') if r['IS_ELDERLY'] == True else 'low' if pd.notna(r['IS_ELDERLY']) and pd.notna(r['TREATMENT_DURATION']) else None, axis=1)",
        "approach": "Row-wise apply", "null_handling": "None if any null"
    },
    ("debugger", "DEBUG"): {
        "variable_name": "RISK_SCORE",
        "root_cause": "Null handling difference between np.select default and apply None return",
        "correct_implementation": "qc", "suggested_fix": "Add .where() null mask",
        "confidence": "high"
    },
    ("auditor", "AUDIT"): {
        "study": "simple_mock", "total_derivations": 4, "auto_approved": 3,
        "qc_mismatches": 1, "human_interventions": 0,
        "summary": "All 4 derivations completed successfully.",
        "recommendations": ["Review null handling in multi-source derivations"]
    },
}

print("Auto-responder started. Polling mailbox...")
while True:
    pending = get_pending()
    if not pending:
        time.sleep(1)
        continue
    for p in pending:
        rid = p["request_id"]
        role, var = identify(rid)
        key = (role, var)
        if key in RESPONSES:
            respond(rid, RESPONSES[key])
            print(f"  Responded #{rid}: {role} / {var}")
        else:
            print(f"  Unknown #{rid}: {role} / {var} — skipping")
    time.sleep(1)
```

Run this auto-responder in Terminal 3 before starting the orchestrator in Terminal 2 for a fully automated test.

## Timeout Configuration

The default AgentLens mailbox timeout is ~60s. If responses are slow, requests will 408. To increase:

```bash
# Start AgentLens with longer timeout
agentlens serve --mode mailbox --port 8650 --timeout 300
```

Or configure PydanticAI timeout in the orchestrator (future: add to config YAML).
