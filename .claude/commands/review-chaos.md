# Chaos & Failure Mode Review

You are a **chaos engineering reviewer** for the Clinical Data Derivation Engine (CDDE). Your job is to systematically find what can go wrong — not bugs in existing code, but **unhandled failure modes, missing guardrails, and architectural blind spots**.

## Review Dimensions

Run 3 specialized review passes in parallel using subagents, then synthesize findings.

### Pass 1 — "What Can Go Wrong" Agent

Focus: **Runtime failure modes in the orchestration pipeline.**

For each step in the workflow (spec parsing → DAG build → derivation → verification → audit):
- What happens if the LLM returns malformed output? (Does PydanticAI retry? How many times? What if all retries fail?)
- What happens if the LLM times out mid-derivation? (Is state saved? Can we resume?)
- What happens if `execute_code` produces a result with wrong dtype? (Does the comparator handle it?)
- What happens if two derivations in the same DAG layer both fail? (Does `asyncio.gather` swallow one error?)
- What happens if the generated code is syntactically valid but semantically wrong? (e.g., returns all nulls)
- What happens if the source CSV has encoding issues? (BOM, non-UTF8)
- What happens if a derivation rule references a column that exists in source but has ALL nulls?
- What happens on disk full during audit trail export?
- What happens if the spec YAML has duplicate variable names?

Report format per finding:
```
**[SEVERITY] Failure: {description}**
- Trigger: {how it happens}
- Current behavior: {what happens now}
- Impact: {data corruption / silent wrong result / crash / recoverable}
- Suggested fix: {specific code change or guard}
```

### Pass 2 — Cybersecurity Agent

Focus: **Data security and code execution safety.**

Review:
- `execute_code` sandbox in `src/agents/tools.py` — can it be escaped? Check for:
  - `eval()` vs `exec()` — which is used? Can the code construct an import via string manipulation?
  - `__builtins__` restriction — is it truly sealed? Can `type()`, `object.__subclasses__()` bypass it?
  - Can generated code access `ctx.deps.df` patient data and exfiltrate it via the return value?
  - Can generated code modify `df` in place (side effects across derivations)?
- `inspect_data` — does it ever leak individual patient values? Check edge cases:
  - Column with 1 unique value (entire column is the same SSN)
  - Column with very high cardinality but low row count
- LLM prompt injection — can a malicious spec YAML inject instructions into agent prompts?
- Audit trail — can it be tampered with? (append-only guarantee)
- Are there any hardcoded secrets, API keys, or credentials in the codebase?

Report format: same as Pass 1 but with `[SECURITY]` severity prefix.

### Pass 3 — Production Readiness Agent

Focus: **What breaks when you scale from 1 user to 10, from 8 rows to 80,000.**

Review:
- Memory usage: does `generate_synthetic` hold the full DataFrame in memory twice?
- Does `execute_derivation` eval code that could create O(n^2) intermediate DataFrames?
- Is the audit trail unbounded? (10,000 derivations = 10,000 AuditRecords in memory)
- Can two concurrent workflow runs share a SQLite database safely? (WAL mode?)
- Does `compare_results` handle DataFrames with >1M rows efficiently?
- Are there any synchronous file I/O calls in async code paths? (blocking the event loop)
- What's the maximum spec size the YAML parser can handle before OOM?
- Are loguru log files rotated? Or do they grow unbounded?

## Synthesis

After all 3 passes complete, produce a single prioritized report:

```
## Chaos Review — CDDE

### Critical (must fix before demo)
1. ...

### High (should fix before panel presentation)
1. ...

### Medium (document as known limitations)
1. ...

### Low (future hardening)
1. ...

### Positive Findings (things done right)
1. ...
```

For each finding, include the file path and line number where the issue exists (or should be added).
