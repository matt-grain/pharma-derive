# MCP + Mailbox Functional Test

## Prerequisites

```bash
# Terminal 1: AgentLens mailbox
cd C:\Projects\AgentLens
uv run agentlens serve --mode mailbox --port 8650

# Terminal 2: Backend API
cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

# Terminal 3: Frontend
cd frontend && npm run dev

# Terminal 4: Auto-responder (this script)
```

## MCP Client Test

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://localhost:8000/mcp/mcp") as client:
        tools = await client.list_tools()
        print(f"{len(tools)} MCP tools: {[t.name for t in tools]}")

        result = await client.call_tool("run_workflow", {"spec_path": "specs/simple_mock.yaml"})
        wf_id = result.data["workflow_id"]
        print(f"Started: {wf_id}")

        # Poll until done (run auto-responder in another terminal)
        import time
        for _ in range(60):
            status = await client.call_tool("get_workflow_status", {"workflow_id": wf_id})
            state = status.data["status"]
            print(f"  Status: {state}")
            if state in ("completed", "failed"):
                break
            time.sleep(2)

        result = await client.call_tool("get_workflow_result", {"workflow_id": wf_id})
        print(f"Result: {result.data}")

asyncio.run(main())
```

## Auto-Responder (simple_mock spec)

The key to correct identification: match the FULL user message (the spec's logic field)
against known prefixes. Do NOT guess by keywords — "age" appears in both AGE_GROUP and IS_ELDERLY.

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
    """Identify (role, variable) from the mailbox request.
    
    Uses the FULL user message to match against known spec logic prefixes.
    Do NOT match by keyword — 'age' appears in AGE_GROUP, IS_ELDERLY, and RISK_SCORE.
    """
    r = get_request(rid)
    sys_prompt = r["messages"][0]["content"]
    user_msg = r["messages"][1]["content"] if len(r["messages"]) > 1 else ""

    # Role detection — "debugging" contains "debug" but NOT "debugger"
    if "debug" in sys_prompt.lower():
        role = "debugger"
    elif "audit" in sys_prompt.lower():
        role = "auditor"
    elif "QC" in sys_prompt and "INDEPENDENT" in sys_prompt:
        role = "qc"
    else:
        role = "coder"

    # Variable detection — match by spec logic prefix (unique per variable)
    if user_msg.startswith("If age < 18") or user_msg.startswith("Age group"):
        var = "AGE_GROUP"
    elif user_msg.startswith("Number of days") or user_msg.startswith("Treatment duration"):
        var = "TREATMENT_DURATION"
    elif user_msg.startswith("True if AGE_GROUP"):
        var = "IS_ELDERLY"
    elif user_msg.startswith("If IS_ELDERLY"):
        var = "RISK_SCORE"
    elif "debug" in user_msg.lower() or "mismatch" in user_msg.lower():
        var = "DEBUG"
    elif role == "auditor":
        var = "AUDIT"
    else:
        var = "UNKNOWN"

    return role, var

# --- Canned responses per (role, variable) ---
RESPONSES = {
    ("coder", "AGE_GROUP"): {
        "variable_name": "AGE_GROUP",
        "python_code": "pd.cut(df['age'], bins=[0,18,65,200], labels=['minor','adult','senior'], right=False)",
        "approach": "pd.cut with bin edges",
        "null_handling": "NaN propagated by pd.cut"
    },
    ("qc", "AGE_GROUP"): {
        "variable_name": "AGE_GROUP",
        "python_code": "pd.Series(np.select([df['age']<18, df['age']<65, df['age']>=65], ['minor','adult','senior'], default=None), index=df.index).where(df['age'].notna())",
        "approach": "np.select with conditions",
        "null_handling": "where(notna()) mask"
    },
    ("coder", "TREATMENT_DURATION"): {
        "variable_name": "TREATMENT_DURATION",
        "python_code": "(pd.to_datetime(df['treatment_end']) - pd.to_datetime(df['treatment_start'])).dt.days + 1",
        "approach": "Vectorized datetime subtraction",
        "null_handling": "NaT propagates"
    },
    ("qc", "TREATMENT_DURATION"): {
        "variable_name": "TREATMENT_DURATION",
        "python_code": "df.apply(lambda r: (pd.to_datetime(r['treatment_end']) - pd.to_datetime(r['treatment_start'])).days + 1 if pd.notna(r['treatment_end']) and pd.notna(r['treatment_start']) else None, axis=1).astype('Float64')",
        "approach": "Row-wise apply with null checks",
        "null_handling": "None if either date missing"
    },
    ("coder", "IS_ELDERLY"): {
        "variable_name": "IS_ELDERLY",
        "python_code": "(df['AGE_GROUP'] == 'senior').where(df['AGE_GROUP'].notna())",
        "approach": "Direct equality with null mask",
        "null_handling": "Null where AGE_GROUP is null"
    },
    ("qc", "IS_ELDERLY"): {
        "variable_name": "IS_ELDERLY",
        "python_code": "df['AGE_GROUP'].map({'senior': True, 'adult': False, 'minor': False})",
        "approach": "Dictionary mapping",
        "null_handling": "NaN keys map to NaN"
    },
    ("coder", "RISK_SCORE"): {
        "variable_name": "RISK_SCORE",
        "python_code": "pd.Series(np.select([df['IS_ELDERLY'].eq(True) & df['TREATMENT_DURATION'].gt(120), df['IS_ELDERLY'].eq(True) & df['TREATMENT_DURATION'].le(120), df['IS_ELDERLY'].eq(False)], ['high', 'medium', 'low'], default=None), index=df.index).where(df['IS_ELDERLY'].notna() & df['TREATMENT_DURATION'].notna(), other=None)",
        "approach": "np.select with double mask",
        "null_handling": "Null if IS_ELDERLY or TREATMENT_DURATION is null"
    },
    ("qc", "RISK_SCORE"): {
        "variable_name": "RISK_SCORE",
        "python_code": "df.apply(lambda r: ('high' if r['TREATMENT_DURATION'] > 120 else 'medium') if r['IS_ELDERLY'] == True else 'low' if pd.notna(r['IS_ELDERLY']) and pd.notna(r['TREATMENT_DURATION']) else None, axis=1)",
        "approach": "Row-wise apply with nested conditionals",
        "null_handling": "None if any source null"
    },
    ("debugger", "DEBUG"): {
        "variable_name": "RISK_SCORE",
        "root_cause": "Null handling difference between np.select and apply",
        "correct_implementation": "qc",
        "suggested_fix": "",
        "confidence": "high"
    },
    ("auditor", "AUDIT"): {
        "study": "simple_mock",
        "total_derivations": 4,
        "auto_approved": 3,
        "qc_mismatches": 1,
        "human_interventions": 0,
        "summary": "All 4 derivations completed. AGE_GROUP, TREATMENT_DURATION, IS_ELDERLY passed QC. RISK_SCORE had a mismatch resolved by debugger.",
        "recommendations": ["Review null handling in multi-source derivations"]
    },
}

print("Auto-responder running (simple_mock)...")
print("Matching variables by spec logic prefix — not by keyword.")
empty = 0
while empty < 30:
    pending = get_pending()
    if not pending:
        time.sleep(1)
        empty += 1
        continue
    empty = 0
    for p in pending:
        rid = p["request_id"]
        role, var = identify(rid)
        key = (role, var)
        if key in RESPONSES:
            respond(rid, RESPONSES[key])
            print(f"  #{rid}: {role}/{var} -> OK")
        else:
            print(f"  #{rid}: {role}/{var} -> UNKNOWN, skipping")
    time.sleep(2)
print("Done — no requests for 30s.")
```

## Expected Result

```
Status: completed
Derived: ['AGE_GROUP', 'TREATMENT_DURATION', 'IS_ELDERLY', 'RISK_SCORE']
QC: AGE_GROUP=match, TREATMENT_DURATION=match, IS_ELDERLY=match, RISK_SCORE=match (or mismatch if null edge case triggers)
Errors: []
```

## Verifying Persistence

After the workflow completes, restart the backend (`Ctrl+C` + re-run uvicorn).
The workflow should still appear in the dashboard with study name, DAG, code, and audit trail.

```bash
curl -s http://localhost:8000/api/v1/workflows/ | python -m json.tool
curl -s http://localhost:8000/api/v1/workflows/{ID}/dag | python -m json.tool
curl -s http://localhost:8000/api/v1/workflows/{ID}/audit | python -m json.tool
```
