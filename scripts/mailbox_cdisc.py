"""Auto-responder for CDISC ADSL mailbox test — feeds canned responses for 7 derivations."""

from __future__ import annotations

import json
import time
import urllib.request

MAILBOX = "http://localhost:8650/mailbox"


def get_pending() -> list[dict[str, object]]:
    return json.loads(urllib.request.urlopen(MAILBOX).read())  # noqa: S310


def get_request(rid: int) -> dict[str, object]:
    return json.loads(urllib.request.urlopen(f"{MAILBOX}/{rid}").read())  # noqa: S310


def respond(rid: int, args: dict[str, object]) -> None:
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
    req = urllib.request.Request(f"{MAILBOX}/{rid}", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    urllib.request.urlopen(req)  # noqa: S310


def identify(rid: int) -> tuple[str, str]:
    r = get_request(rid)
    msgs = r["messages"]
    sys_prompt = str(msgs[0]["content"]) if msgs else ""
    user_msg = str(msgs[1]["content"]) if len(msgs) > 1 else ""

    if "debug" in sys_prompt.lower():
        role = "debugger"
    elif "audit" in sys_prompt.lower():
        role = "auditor"
    elif "QC" in sys_prompt and "INDEPENDENT" in sys_prompt:
        role = "qc"
    else:
        role = "coder"

    if user_msg.startswith("Age group"):
        var = "AGEGR1"
    elif user_msg.startswith("Treatment duration") or user_msg.startswith("Number of treatment"):
        var = "TRTDUR"
    elif user_msg.startswith("Safety population"):
        var = "SAFFL"
    elif user_msg.startswith("Intent-to-treat"):
        var = "ITTFL"
    elif user_msg.startswith("Efficacy population"):
        var = "EFFFL"
    elif user_msg.startswith("Discontinuation flag"):
        var = "DISCONFL"
    elif user_msg.startswith("Duration of disease"):
        var = "DURDIS"
    elif "mismatch" in user_msg.lower() or "debug" in user_msg.lower():
        var = "DEBUG"
    elif role == "auditor":
        var = "AUDIT"
    else:
        var = "UNKNOWN"
    return role, var


RESPONSES: dict[tuple[str, str], dict[str, object]] = {
    ("coder", "AGEGR1"): {
        "variable_name": "AGEGR1",
        "python_code": "pd.cut(df['AGE'], bins=[0, 65, 81, 200], labels=['<65', '65-80', '>80'], right=False)",
        "approach": "pd.cut with right=False",
        "null_handling": "NaN propagated",
    },
    ("qc", "AGEGR1"): {
        "variable_name": "AGEGR1",
        "python_code": "pd.Series(np.select([df['AGE'] < 65, (df['AGE'] >= 65) & (df['AGE'] <= 80), df['AGE'] > 80], ['<65', '65-80', '>80'], default=None), index=df.index).where(df['AGE'].notna())",
        "approach": "np.select",
        "null_handling": "where(notna())",
    },
    ("coder", "TRTDUR"): {
        "variable_name": "TRTDUR",
        "python_code": "(pd.to_datetime(df['RFXENDTC']) - pd.to_datetime(df['RFXSTDTC'])).dt.days + 1",
        "approach": "Vectorized datetime subtraction + 1",
        "null_handling": "NaT propagates",
    },
    ("qc", "TRTDUR"): {
        "variable_name": "TRTDUR",
        "python_code": "df.apply(lambda r: (pd.to_datetime(r['RFXENDTC']) - pd.to_datetime(r['RFXSTDTC'])).days + 1 if pd.notna(r.get('RFXENDTC')) and r.get('RFXENDTC','') != '' and pd.notna(r.get('RFXSTDTC')) and r.get('RFXSTDTC','') != '' else None, axis=1).astype('Float64')",
        "approach": "Row-wise with null checks",
        "null_handling": "None if either date missing",
    },
    ("coder", "SAFFL"): {
        "variable_name": "SAFFL",
        "python_code": "pd.Series(np.where((df['ARM'].notna() & (df['ARM'] != '')) & (df['RFXSTDTC'].notna() & (df['RFXSTDTC'] != '')), 'Y', 'N'), index=df.index)",
        "approach": "np.where on ARM + RFXSTDTC",
        "null_handling": "N if missing",
    },
    ("qc", "SAFFL"): {
        "variable_name": "SAFFL",
        "python_code": "df.apply(lambda r: 'Y' if (pd.notna(r.get('ARM')) and r.get('ARM','') != '' and pd.notna(r.get('RFXSTDTC')) and r.get('RFXSTDTC','') != '') else 'N', axis=1)",
        "approach": "Row-wise apply",
        "null_handling": "N for missing",
    },
    ("coder", "ITTFL"): {
        "variable_name": "ITTFL",
        "python_code": "pd.Series(np.where(df['ARMCD'].notna() & (df['ARMCD'] != ''), 'Y', 'N'), index=df.index)",
        "approach": "np.where on ARMCD",
        "null_handling": "N if empty",
    },
    ("qc", "ITTFL"): {
        "variable_name": "ITTFL",
        "python_code": "df['ARMCD'].apply(lambda x: 'Y' if pd.notna(x) and x != '' else 'N')",
        "approach": "Apply lambda",
        "null_handling": "N for missing",
    },
    ("coder", "EFFFL"): {
        "variable_name": "EFFFL",
        "python_code": "pd.Series(np.where((df['ARMCD'].notna() & (df['ARMCD'] != '')) & (df['ARM'] != 'Screen Failure'), 'Y', 'N'), index=df.index)",
        "approach": "ARMCD non-empty AND not screen failure",
        "null_handling": "N if not randomized",
    },
    ("qc", "EFFFL"): {
        "variable_name": "EFFFL",
        "python_code": "df.apply(lambda r: 'Y' if pd.notna(r.get('ARMCD')) and r.get('ARMCD','') != '' and r.get('ARM','') != 'Screen Failure' else 'N', axis=1)",
        "approach": "Row-wise apply",
        "null_handling": "N for screen failures",
    },
    ("coder", "DISCONFL"): {
        "variable_name": "DISCONFL",
        "python_code": "pd.Series(np.where(df['DSDECOD'].notna() & (df['DSDECOD'] != '') & (df['DSCAT'] == 'DISPOSITION EVENT'), 'Y', ''), index=df.index)",
        "approach": "np.where on DSCAT + DSDECOD",
        "null_handling": "Empty if no discontinuation",
    },
    ("qc", "DISCONFL"): {
        "variable_name": "DISCONFL",
        "python_code": "df.apply(lambda r: 'Y' if pd.notna(r.get('DSDECOD')) and r.get('DSDECOD','') != '' and r.get('DSCAT','') == 'DISPOSITION EVENT' else '', axis=1)",
        "approach": "Row-wise apply",
        "null_handling": "Empty default",
    },
    ("coder", "DURDIS"): {
        "variable_name": "DURDIS",
        "python_code": "pd.Series(np.nan, index=df.index, dtype='Float64')",
        "approach": "Not derivable from SDTM — all NaN",
        "null_handling": "All NaN",
    },
    ("qc", "DURDIS"): {
        "variable_name": "DURDIS",
        "python_code": "pd.Series(np.nan, index=df.index, dtype='Float64')",
        "approach": "Not derivable — all NaN",
        "null_handling": "All NaN",
    },
    ("debugger", "DEBUG"): {
        "variable_name": "UNKNOWN",
        "root_cause": "Boundary or null handling difference between vectorized and row-wise approaches",
        "correct_implementation": "qc",
        "suggested_fix": "",
        "confidence": "high",
    },
    ("auditor", "AUDIT"): {
        "study": "cdiscpilot01",
        "total_derivations": 7,
        "auto_approved": 5,
        "qc_mismatches": 2,
        "human_interventions": 0,
        "summary": "7 ADSL derivations completed for CDISC Pilot Study.",
        "recommendations": ["Validate DURDIS derivability", "Review TRTDUR null handling"],
    },
}


if __name__ == "__main__":
    print(f"CDISC ADSL auto-responder ({len(RESPONSES)} canned responses)...")
    empty = 0
    while empty < 35:
        pending = get_pending()
        if not pending:
            time.sleep(1)
            empty += 1
            continue
        empty = 0
        for p in pending:
            rid = int(p["request_id"])
            role, var = identify(rid)
            key = (role, var)
            if key in RESPONSES:
                respond(rid, RESPONSES[key])
                print(f"  #{rid}: {role:8s} / {var:10s} OK")
            else:
                print(f"  #{rid}: {role:8s} / {var:10s} UNKNOWN")
        time.sleep(2)
    print("Done.")
