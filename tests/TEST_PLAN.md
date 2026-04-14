# Test Plan — simple_mock.yaml End-to-End Validation

## Overview

This plan validates all 4 phases of the CDDE using the `specs/simple_mock.yaml` spec and `tests/fixtures/patients.csv` dataset. The spec defines 4 derivations forming a 3-layer DAG — small enough to reason about manually, complex enough to exercise every code path.

## Test Dataset

**File:** `tests/fixtures/patients.csv` (8 rows)

| patient_id | age | treatment_start | treatment_end | group |
|-----------|-----|----------------|--------------|-------|
| P001 | 72 | 2024-01-15 | 2024-06-20 | treatment |
| P002 | 45 | 2024-02-01 | 2024-07-15 | treatment |
| P003 | 38 | 2024-01-20 | 2024-05-10 | placebo |
| P004 | 65 | 2024-03-01 | *(null)* | placebo |
| P005 | 55 | 2024-02-15 | 2024-08-01 | treatment |
| P006 | *(null)* | 2024-01-10 | 2024-04-30 | placebo |
| P007 | 15 | 2024-04-01 | 2024-09-15 | treatment |
| P008 | 81 | 2024-01-25 | 2024-06-01 | placebo |

**Edge cases by design:** 1 null age (P006), 1 null treatment_end (P004), 1 minor (P007), mix of treatment/placebo.

## Expected Derivation Results

### Layer 0 (no dependencies)

**AGE_GROUP** — `source: [age]`

| patient_id | age | AGE_GROUP |
|-----------|-----|-----------|
| P001 | 72 | senior |
| P002 | 45 | adult |
| P003 | 38 | adult |
| P004 | 65 | senior |
| P005 | 55 | adult |
| P006 | null | **null** |
| P007 | 15 | minor |
| P008 | 81 | senior |

**TREATMENT_DURATION** — `source: [treatment_start, treatment_end]`

| patient_id | start | end | TREATMENT_DURATION |
|-----------|-------|-----|--------------------|
| P001 | 2024-01-15 | 2024-06-20 | 158.0 |
| P002 | 2024-02-01 | 2024-07-15 | 166.0 |
| P003 | 2024-01-20 | 2024-05-10 | 112.0 |
| P004 | 2024-03-01 | null | **null** |
| P005 | 2024-02-15 | 2024-08-01 | 169.0 |
| P006 | 2024-01-10 | 2024-04-30 | 112.0 |
| P007 | 2024-04-01 | 2024-09-15 | 168.0 |
| P008 | 2024-01-25 | 2024-06-01 | 129.0 |

*(days between end and start + 1, inclusive)*

### Layer 1 (depends on AGE_GROUP)

**IS_ELDERLY** — `source: [AGE_GROUP]`

| patient_id | AGE_GROUP | IS_ELDERLY |
|-----------|-----------|------------|
| P001 | senior | True |
| P002 | adult | False |
| P003 | adult | False |
| P004 | senior | True |
| P005 | adult | False |
| P006 | null | **null** |
| P007 | minor | False |
| P008 | senior | True |

### Layer 2 (depends on IS_ELDERLY + TREATMENT_DURATION)

**RISK_SCORE** — `source: [IS_ELDERLY, TREATMENT_DURATION]`

| patient_id | IS_ELDERLY | TREATMENT_DURATION | RISK_SCORE |
|-----------|------------|-------------------|------------|
| P001 | True | 158.0 | high |
| P002 | False | 166.0 | low |
| P003 | False | 112.0 | low |
| P004 | True | null | **null** |
| P005 | False | 169.0 | low |
| P006 | null | 112.0 | **null** |
| P007 | False | 168.0 | low |
| P008 | True | 129.0 | medium |

---

## Phase 1 — Domain Layer Validation

### What to verify

| Test | How | Pass Criteria |
|------|-----|---------------|
| Spec parsing | `parse_spec("specs/simple_mock.yaml")` | Returns `TransformationSpec` with 4 derivations, study="simple_mock" |
| Data loading | `load_source_data(spec)` | Returns DataFrame with 8 rows, 5 columns |
| Source columns | `get_source_columns(df)` | Returns `{"patient_id", "age", "treatment_start", "treatment_end", "group"}` |
| Synthetic generation | `generate_synthetic(df, rows=15)` | Same columns, 15 rows, no exact match with real values (numeric) |
| DAG construction | `DerivationDAG(rules, source_cols)` | 3 layers: [AGE_GROUP, TREATMENT_DURATION], [IS_ELDERLY], [RISK_SCORE] |
| DAG execution order | `dag.execution_order` | RISK_SCORE comes after IS_ELDERLY, IS_ELDERLY after AGE_GROUP |
| Cycle detection | Add circular dep | Raises `ValueError("Circular dependency detected")` |
| Unknown column | Reference nonexistent col | Raises `ValueError("Unknown source column")` |

### Status: ✅ 25 unit tests passing (Phase 1)

---

## Phase 2 — Agent Layer Validation

### What to verify

| Test | How | Pass Criteria |
|------|-----|---------------|
| Agent output types | Inspect agent objects | Each agent has correct `output_type` (SpecInterpretation, DerivationCode, etc.) |
| Tool registration | Inspect coder/QC agents | Both have `inspect_data` and `execute_code` tools |
| QC independence | Read QC system prompt | Contains "DIFFERENT approach" / "INDEPENDENT" |
| inspect_data security | Call with sample_df | Returns schema+aggregates, NOT raw patient rows or IDs |
| execute_code sandbox | Execute `import os` | Blocked (no builtins) |
| execute_code sandbox | Execute `open('/etc/passwd')` | Blocked |
| execute_code results | Execute valid pandas code | Returns summary (dtype, null count), NOT raw DataFrame |
| LLM gateway | `create_llm()` | Returns `OpenAIChatModel` with correct base_url |
| LLM gateway env vars | Set `LLM_BASE_URL` env var | Overrides default |

### Status: ✅ 27 unit tests passing (52 total, Phase 2)

---

## Phase 3 — Orchestration + Verification Validation

### What to verify

| Test | How | Pass Criteria |
|------|-----|---------------|
| FSM initial state | `WorkflowFSM("wf-1")` | `current_state_value == "created"` |
| FSM happy path | Walk full transition chain | created → spec_review → dag_built → deriving → verifying → review → auditing → completed |
| FSM invalid transition | `start_deriving()` from created | Raises `TransitionNotAllowed` |
| FSM fail from any state | `fail()` from deriving, verifying | Transitions to failed |
| FSM audit callback | Any transition | `fsm.audit_records` grows |
| FSM loops | verifying → debugging → verifying | Works (retry loop) |
| Code execution | `execute_derivation(df, "df['age'] * 2")` | Returns `ExecutionResult(success=True)` with correct dtype |
| Code execution error | Invalid code | Returns `ExecutionResult(success=False, error=...)` |
| Code sandbox | `__import__('os')` | Returns error (restricted namespace) |
| Compare match | Identical Series | `QCVerdict.MATCH`, mismatch_count=0 |
| Compare mismatch | Different values | `QCVerdict.MISMATCH`, divergent_indices populated |
| Compare NaN=NaN | Both NaN | Considered equal (not mismatch) |
| Compare tolerance | Values within tolerance | MATCH |
| AST similarity | Same code | 1.0 |
| AST similarity | Different code | < 0.5 |
| Verify match | Same output, different AST | `QCVerdict.MATCH`, recommendation="auto_approve" |
| Verify mismatch | Different output | `QCVerdict.MISMATCH`, recommendation="needs_debug" |
| Verify independence | Same AST | `QCVerdict.INSUFFICIENT_INDEPENDENCE` |

### Status: ✅ 35 unit tests passing (87 total, Phase 3)

---

## Phase 4 — Persistence + Audit + Integration Validation

### What to verify

#### Persistence (unit tests, in-memory SQLite)

| Test | How | Pass Criteria |
|------|-----|---------------|
| Pattern store+query | Store pattern, query by type | Returns `PatternRecord` with all fields |
| Pattern empty query | Query nonexistent type | Returns `[]` |
| Pattern limit | Store 10, query limit=3 | Returns 3 most recent |
| Feedback store+query | Store feedback, query by variable | Returns `FeedbackRecord` |
| QC stats | Store 3 (2 match, 1 mismatch) | `match_rate ≈ 0.667` |
| QC stats empty | No data | `total=0, match_rate=0.0` |
| Workflow state save+load | Save JSON, load back | Identical JSON string |
| Workflow state missing | Load nonexistent workflow_id | Returns `None` |
| Workflow state delete | Save then delete | `load()` returns `None` |
| DB init | `init_db("sqlite+aiosqlite:///:memory:")` | Tables created, sessionmaker works |

#### Audit trail (unit tests, no DB)

| Test | How | Pass Criteria |
|------|-----|---------------|
| Append-only | Record 3 items | `len(trail.records) == 3`, no delete method |
| Timestamp | Record an item | Timestamp is valid ISO 8601 with timezone |
| Variable history | Record for 2 variables, filter | Only matching records returned |
| JSON export | `to_json(tmp_path / "trail.json")` | Valid JSON file with correct structure |
| Summary counts | Record multiple actions | Counts by `agent:action` key |

#### Integration (mocked LLM via TestModel)

| Test | How | Pass Criteria |
|------|-----|---------------|
| Full workflow | Run orchestrator with simple_mock.yaml + TestModel | Status "completed", 4 variables derived, no errors |
| QC mismatch flow | Mock QC to return wrong code | Debugger triggered, audit trail shows mismatch |
| DAG order | Track agent call order via audit trail | Layer 0 before Layer 1 before Layer 2 |

---

## Phase 5 — CDISC Pilot Data Validation

### What to verify

| Test | How | Pass Criteria |
|------|-----|---------------|
| XPT format accepted | Parse `specs/adsl_cdiscpilot01.yaml` | `source.format == "xpt"` |
| XPT loading (DM) | `load_source_data(spec)` with real XPT | DataFrame with >0 rows, AGE column exists |
| Unsupported format | Spec with `format: parquet` | Raises `ValueError("Unsupported source format")` |
| ADSL spec parse | Parse full ADSL spec | 7 derivations, study="cdiscpilot01" |
| Multi-domain merge | Load 4 domains (DM+EX+DS+SV) | USUBJID, AGE, RFXSTDTC, DSDECOD all present |
| DAG from ADSL | Build DAG from ADSL derivations | AGEGR1 in layer 0, EFFFL in later layer |
| Synthetic from CDISC | Generate synthetic from merged SDTM | 15 rows, same columns as source |

### Status: ✅ 3 unit + 4 integration tests passing (125 total)

---

## Phase 6 — Review Fix: Deferred Items

### What to verify

#### File Splits

| Test | How | Pass Criteria |
|------|-----|---------------|
| orchestrator split | Import `WorkflowState` from `workflow_models` | Module exists, imports work |
| spec_parser split | Import `load_source_data` from `source_loader` | Module exists, function works |
| synthetic split | Import `generate_synthetic` from `synthetic` | Module exists, function works |
| tools split | Import `CoderDeps` from `deps` | Module exists, class works |

#### Derivation Runner Tests

| Test | How | Pass Criteria |
|------|-----|---------------|
| resolve — suggested fix preferred | `DebugAnalysis` with `suggested_fix` | Returns suggested_fix |
| resolve — coder selected | `correct_implementation=CODER` | Returns coder code |
| resolve — qc selected | `correct_implementation=QC` | Returns QC code |
| resolve — neither returns none | `correct_implementation=NEITHER` | Returns None |
| apply approved — adds column | Call with valid series JSON | Column in derived_df, node APPROVED |
| apply debug fix — success | Mock `execute_derivation` success | Node APPROVED, column added |
| apply debug fix — failure | Mock `execute_derivation` failure | Node QC_MISMATCH |

#### Logging Tests

| Test | How | Pass Criteria |
|------|-----|---------------|
| default setup | `setup_logging()` | No exception |
| file sink | `setup_logging(log_file=...)` | No exception |
| custom level | `setup_logging(level="DEBUG")` | No exception |

#### FSM Transition Tests

| Test | How | Pass Criteria |
|------|-----|---------------|
| fail from dag_built | Transition to dag_built, call fail | `current_state_value == "failed"` |
| fail from debugging | Transition to debugging, call fail | `current_state_value == "failed"` |
| fail from review | Transition to review, call fail | `current_state_value == "failed"` |
| fail from auditing | Transition to auditing, call fail | `current_state_value == "failed"` |
| debug to review | Transition to debugging, finish_review | `current_state_value == "review"` |
| fail() from any state | Parametrized across 5 non-terminal states | All reach "failed" |

#### Persistence Edge Cases

| Test | How | Pass Criteria |
|------|-----|---------------|
| feedback empty query | Query nonexistent variable | Returns `[]` |
| feedback respects limit | Store 5, query limit=2 | Returns 2 |
| QC stats by variable | Store for 2 variables, filter | Only matching variable counted |

### Status: ✅ 23 new tests passing (148 total)

---

## Phase 7 — Streamlit HITL UI

### What to verify (manual — Streamlit not unit testable)

| Test | How | Pass Criteria |
|------|-----|---------------|
| App starts | `uv run streamlit run src/ui/app.py` | Page loads, sidebar shows CDDE branding |
| Theme applied | Visual inspection | Dark background, orange accent, IBM Plex Mono |
| Spec dropdown | Navigate to Workflow page | Shows available specs from `specs/*.yaml` |
| Run button | Click "Start Derivation Run" (needs AgentLens) | Spinner → results or error |
| Audit page | Navigate to Audit Trail | Shows dropdown of audit JSON files from output/ |
| Import contract | `uv run lint-imports` | `ui-no-persistence` contract passes |

### Status: ✅ Tooling passes (19 contracts, 0 violations). UI is integration-tested manually.

---

## Phases 8-9 — Documentation + Docker

### What to verify

| Test | How | Pass Criteria |
|------|-----|---------------|
| Design doc exists | Read `docs/design.md` | ~3 pages, all 8 sections present |
| Mermaid diagrams | Check design doc | At least 2 diagrams (architecture + FSM) |
| Slides exist | Read `presentation/slides.md` | 18 slides, Marp format |
| Speaker notes | Check slides | `<!-- Speaker notes: -->` in each slide |
| Dockerfile builds | `docker build -t cdde .` | Image builds successfully |
| Compose up | `docker compose up` | Container starts, port 8501 accessible |
| README quick start | Follow README instructions | Works in ≤5 commands |

### Status: ✅ All deliverables created. Docker tested via build.

---

## Manual Functional Validation (Live Run)

This section walks through running the full system end-to-end with a real LLM via AgentLens. Do this after all automated tests pass.

### Prerequisites

1. **AgentLens installed and configured:**
   ```bash
   # Install AgentLens (if not already)
   pip install agentlens

   # Start AgentLens in mailbox mode (no real LLM — for dry run)
   agentlens serve --mode mailbox --port 8650
   ```

2. **Or use AgentLens in proxy mode with a real LLM:**
   ```bash
   # Proxy mode — routes to Claude API
   export ANTHROPIC_API_KEY=sk-ant-...
   agentlens serve --mode proxy --port 8650 --provider anthropic --model claude-sonnet-4-20250514
   ```

3. **Database ready:**
   ```bash
   # SQLite is the default — no setup needed
   # File will be created at ./cdde.db on first run
   ```

### Step 1 — Verify Spec Parsing (No LLM Needed)

```bash
uv run python -c "
from src.domain.spec_parser import parse_spec, load_source_data, get_source_columns
from src.domain.dag import DerivationDAG

spec = parse_spec('specs/simple_mock.yaml')
print(f'Study: {spec.metadata.study}')
print(f'Derivations: {len(spec.derivations)}')
for d in spec.derivations:
    print(f'  {d.variable} <- {d.source_columns}')

df = load_source_data(spec)
print(f'\nSource data: {df.shape[0]} rows, {df.shape[1]} columns')
print(f'Columns: {list(df.columns)}')
print(f'Null counts: {dict(df.isnull().sum())}')

dag = DerivationDAG(spec.derivations, get_source_columns(df))
print(f'\nDAG layers: {len(dag.layers)}')
for i, layer in enumerate(dag.layers):
    print(f'  Layer {i}: {layer}')
print(f'Execution order: {dag.execution_order}')
"
```

**Expected output:**
```
Study: simple_mock
Derivations: 4
  AGE_GROUP <- ['age']
  TREATMENT_DURATION <- ['treatment_start', 'treatment_end']
  IS_ELDERLY <- ['AGE_GROUP']
  RISK_SCORE <- ['IS_ELDERLY', 'TREATMENT_DURATION']

Source data: 8 rows, 5 columns
Columns: ['patient_id', 'age', 'treatment_start', 'treatment_end', 'group']
Null counts: {'patient_id': 0, 'age': 1, 'treatment_start': 0, 'treatment_end': 1, 'group': 0}

DAG layers: 3
  Layer 0: ['AGE_GROUP', 'TREATMENT_DURATION']
  Layer 1: ['IS_ELDERLY']
  Layer 2: ['RISK_SCORE']
Execution order: ['AGE_GROUP', 'TREATMENT_DURATION', 'IS_ELDERLY', 'RISK_SCORE']
```

### Step 2 — Verify FSM Transitions (No LLM Needed)

```bash
uv run python -c "
from src.engine.workflow_fsm import WorkflowFSM

fsm = WorkflowFSM(workflow_id='test-001')
print(f'Initial state: {fsm.current_state_value}')

fsm.start_spec_review()
print(f'After start_spec_review: {fsm.current_state_value}')

fsm.finish_spec_review()
print(f'After finish_spec_review: {fsm.current_state_value}')

fsm.start_deriving()
fsm.start_verifying()
fsm.finish_review_from_verify()
fsm.start_auditing()
fsm.finish()
print(f'Final state: {fsm.current_state_value}')
print(f'Audit records: {len(fsm.audit_records)}')
for r in fsm.audit_records:
    print(f'  {r.action} (from {r.details.get(\"from\", \"init\")})')
"
```

**Expected:** States transition through the full happy path, audit records accumulated.

### Step 3 — Verify Synthetic Data Generation (No LLM Needed)

```bash
uv run python -c "
from src.domain.spec_parser import parse_spec, load_source_data, generate_synthetic

spec = parse_spec('specs/simple_mock.yaml')
df = load_source_data(spec)
synthetic = generate_synthetic(df, rows=10)

print('Synthetic dataset (safe for LLM prompts):')
print(synthetic.to_string(index=False))
print(f'\nShape: {synthetic.shape}')
print(f'Columns match: {list(synthetic.columns) == list(df.columns)}')
"
```

**Expected:** 10 rows of fake data with same schema, no real patient values.

**Note:** Numeric columns will have ~10% NaN values — this is intentional. The synthetic sample
is included in agent prompts, and showing nulls ensures the LLM generates code that handles
null propagation correctly. Without synthetic nulls, the agent might write code that crashes
on real data where nulls exist (P006 has null age, P004 has null treatment_end).

### Step 4 — Verify Code Execution Sandbox (No LLM Needed)

```bash
uv run python -c "
from src.domain.spec_parser import parse_spec, load_source_data
from src.domain.executor import execute_derivation

spec = parse_spec('specs/simple_mock.yaml')
df = load_source_data(spec)

# Test a valid derivation
result = execute_derivation(df, \"pd.cut(df['age'], bins=[0,18,65,200], labels=['minor','adult','senior'], right=False)\", list(df.columns))
print(f'AGE_GROUP derivation: success={result.success}, dtype={result.dtype}, nulls={result.null_count}')
print(f'Value counts: {result.value_counts}')

# Security test: verify sandbox blocks code injection
blocked = execute_derivation(df, \"__import__('os').system('echo hacked')\", list(df.columns))
print(f'\nSandbox test: success={blocked.success} (expected: False)')
print(f'Blocked with: {blocked.error}')
"
```

**Expected output:**
```
AGE_GROUP derivation: success=True, dtype=category, nulls=1
Value counts: {'adult': 3, 'senior': 3, 'minor': 1, 'nan': 1}

Sandbox test: success=False (expected: False)
Blocked with: name '__import__' is not defined
```

**Notes:**
- `nan` in value_counts is expected — `value_counts(dropna=False)` counts NaN as a category entry
- The sandbox test confirms code injection is blocked — `__builtins__` is restricted to safe operations only

### Step 5 — Verify Double-Programming Verification (No LLM Needed)

```bash
uv run python -c "
from src.domain.spec_parser import parse_spec, load_source_data
from src.verification.comparator import verify_derivation, compute_ast_similarity

spec = parse_spec('specs/simple_mock.yaml')
df = load_source_data(spec)

# Two different implementations of AGE_GROUP
coder_code = \"pd.cut(df['age'], bins=[0,18,65,200], labels=['minor','adult','senior'], right=False)\"
qc_code = \"df['age'].apply(lambda x: 'minor' if x < 18 else ('adult' if x < 65 else 'senior') if pd.notna(x) else None)\"

result = verify_derivation('AGE_GROUP', coder_code, qc_code, df, list(df.columns))
print(f'Verdict: {result.verdict}')
print(f'AST similarity: {result.ast_similarity:.2f}')
print(f'Recommendation: {result.recommendation}')
print(f'Match count: {result.comparison.match_count if result.comparison else \"N/A\"}')
print(f'Mismatch count: {result.comparison.mismatch_count if result.comparison else \"N/A\"}')
"
```

**Expected output:**
```
Verdict: match
AST similarity: 0.18
Recommendation: auto_approve
Match count: 8
Mismatch count: 0
```

Both implementations produce identical results for all 8 rows (including null propagation for P006).
AST similarity is low (0.18) because `pd.cut` vs `apply(lambda)` are structurally different → passes independence check → `auto_approve`.

### Step 6 — Run Full Orchestrator (Requires AgentLens)

```bash
# Start AgentLens first (in another terminal):
# agentlens serve --mode proxy --port 8650 --provider anthropic --model claude-sonnet-4-20250514

uv run python -c "
import asyncio
from pathlib import Path
from src.engine.factory import create_orchestrator

async def main():
    orch, session = await create_orchestrator(
        spec_path='specs/simple_mock.yaml',
        llm_base_url='http://localhost:8650/v1',
        output_dir=Path('output'),
    )
    try:
        result = await orch.run()
        await session.commit()
    finally:
        await session.close()
    print(f'Status: {result.status}')
    print(f'Study: {result.study}')
    print(f'Derived variables: {result.derived_variables}')
    print(f'QC summary: {result.qc_summary}')
    print(f'Errors: {result.errors}')
    print(f'Duration: {result.duration_seconds:.1f}s')
    print(f'Audit records: {len(result.audit_records)}')
    if result.audit_summary:
        print(f'\nAudit summary:')
        print(f'  Auto-approved: {result.audit_summary.auto_approved}')
        print(f'  QC mismatches: {result.audit_summary.qc_mismatches}')
        print(f'  Recommendations: {result.audit_summary.recommendations}')

asyncio.run(main())
"
```

**Expected output:**
```
Status: completed
Study: simple_mock
Derived variables: ['AGE_GROUP', 'TREATMENT_DURATION', 'IS_ELDERLY', 'RISK_SCORE']
QC summary: {'AGE_GROUP': 'match', 'TREATMENT_DURATION': 'match', 'IS_ELDERLY': 'match', 'RISK_SCORE': 'match'}
Errors: []
Duration: ~30-60s (depends on LLM)
Audit records: ~20-30
```

**Verify afterward:**
```bash
# Check audit trail was exported
cat output/{id}_auditl.json | python -m json.tool | head -30

# Check SQLite database was populated (if repos were wired)
uv run python -c "
import sqlite3
conn = sqlite3.connect('cdde.db')
print('Patterns:', conn.execute('SELECT COUNT(*) FROM patterns').fetchone()[0])
print('QC history:', conn.execute('SELECT COUNT(*) FROM qc_history').fetchone()[0])
conn.close()
"
```

### Step 7 — Verify AgentLens Traces (After Step 6)

AgentLens exposes an API only — no built-in web UI. Generate an HTML report from the recorded traces:

```bash
# Export traces to HTML report (after running the orchestrator in Step 6)
agentlens report --output docs/agentlens_report.html

# Open the report
start docs/agentlens_report.html  # Windows
# open docs/agentlens_report.html  # macOS
```

**Verify in the report:**
- [ ] Each agent call is visible in the trace timeline
- [ ] Prompts contain synthetic data, NOT real patient data (search for patient IDs like P001 — should NOT appear in prompts)
- [ ] Structured outputs match expected schemas (SpecInterpretation, DerivationCode, etc.)
- [ ] Coder and QC agents ran in parallel (check timestamps — should be within ~0.1s of each other)
- [ ] Tool calls (inspect_data, execute_code) are logged with inputs and outputs
- [ ] No raw DataFrame rows in any tool output

**Alternative — inspect traces via API:**
```bash
# List recent traces
curl http://localhost:8650/v1/traces | python -m json.tool | head -50

# Or programmatically
uv run python -c "
import httpx, json
traces = httpx.get('http://localhost:8650/v1/traces').json()
for t in traces[:5]:
    print(f'{t[\"timestamp\"]} | {t[\"agent\"]} | {t[\"action\"][:50]}')
"
```

### Step 8 — Verify FSM Diagram Export (For Presentation)

```bash
uv run python -c "
from src.engine.workflow_fsm import WorkflowFSM

fsm = WorkflowFSM('demo')
# Generate state diagram (if python-statemachine supports it)
try:
    graph = fsm._graph()
    graph.write_png('docs/workflow_fsm.png')
    print('FSM diagram exported to docs/workflow_fsm.png')
except Exception as e:
    print(f'Graph export not available: {e}')
    print('Alternative: use fsm.current_state to walk through states for presentation')
"
```

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ConnectionRefusedError` on port 8650 | AgentLens not running | Start with `agentlens serve` |
| `TimeoutError` on agent.run() | LLM not responding | Check AgentLens logs, verify API key |
| `TransitionNotAllowed` | FSM in wrong state | Check logs for which transition failed, likely an error in a prior step |
| Agent returns malformed output | LLM didn't match schema | PydanticAI retries 3 times; if still failing, check the system prompt |
| `FileNotFoundError` on spec | Wrong path | Run from project root (`homework/`) |
| Empty audit trail | Repos not wired | Pass `output_dir=Path("output")` to orchestrator |

---

## Manual Validation Checklist (Pre-Panel)

After all automated tests AND manual functional validation pass:

- [ ] `uv run pytest --cov=src --cov-report=term-missing` — coverage ≥ 80% (current: 89%)
- [ ] `uv run lint-imports` — all 19 contracts kept
- [ ] `uv run vulture src/ --min-confidence 80` — no dead code
- [ ] `uv run radon cc src/ -a -nc` — no D or F complexity
- [ ] All 10 custom pre-push checks pass + 18 total pre-push hooks green
- [ ] Step 1-5 above pass without errors (no LLM needed)
- [ ] Step 6 runs successfully with AgentLens (real LLM)
- [ ] Streamlit UI loads and displays correctly
- [ ] Docker build + compose up works
- [ ] Audit trail JSON export is human-readable
- [ ] Design doc is 2-4 pages with required sections
- [ ] Presentation has 18 slides with speaker notes

## Test Coverage Targets

| Module | Target | Rationale |
|--------|--------|-----------|
| `src/domain/` | ≥ 90% | Critical path — wrong derivation = wrong drug approval |
| `src/verification/` | ≥ 90% | QC verification must be reliable |
| `src/engine/` | ≥ 80% | Orchestration logic (some paths need integration tests) |
| `src/agents/` | ≥ 80% | Config + tools tested; agent.run() needs LLM mocking |
| `src/persistence/` | ≥ 85% | Repository CRUD fully testable with in-memory DB |
| `src/audit/` | ≥ 90% | Append-only trail, fully testable |
| **Overall** | **≥ 80%** | Enforced by pre-push hook |
