# Phase 2 — Agent Definitions + LLM Gateway

**Dependencies:** Phase 1 (domain models, DAG, spec parser)
**Agent:** `python-fastapi`
**Estimated files:** 8

This phase defines the PydanticAI agents and the LLM gateway. Agents use domain models from Phase 1 as their input/output types and dependency injection types.

**Key reference:** Validated prototype patterns in `prototypes/proto_01..05.py` and `prototypes/WARNINGS.md`.

---

## 2.1 LLM Gateway

### `src/engine/__init__.py` (NEW)

Empty file.

### `src/engine/llm_gateway.py` (NEW)

**Purpose:** Single entry point for creating PydanticAI model instances. All agents use this — never construct `OpenAIChatModel` directly.

**Public functions:**

```python
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

def create_llm(
    model_name: str = "cdde-agent",
    base_url: str = "http://localhost:8650/v1",
    api_key: str = "not-needed-for-mailbox",
) -> OpenAIChatModel:
    """Create a PydanticAI LLM model pointing to AgentLens proxy.

    In dev: base_url points to AgentLens mailbox (no real LLM calls).
    In prod: base_url points to AgentLens proxy → real LLM.

    All agents share the same model config — swap LLM by changing base_url.
    """
```

**Constraints:**
- Uses `OpenAIChatModel` (not deprecated `OpenAIModel`)
- Default values point to AgentLens mailbox (dev mode)
- Override via environment variables in production: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- Read env vars with `os.environ.get()` with defaults — no Pydantic Settings (keep simple)

---

## 2.2 Agent Definitions

### `src/agents/__init__.py` (NEW)

Empty file.

### `src/agents/spec_interpreter.py` (NEW)

**Purpose:** PydanticAI agent that parses transformation specs and flags ambiguities.

**Output type (define in this file):**

```python
class SpecInterpretation(BaseModel, frozen=True):
    """Output of the Spec Interpreter agent."""
    rules: list[DerivationRule]
    ambiguities: list[str]
    summary: str  # One-line summary of what was parsed
```

**Agent definition:**

```python
from pydantic_ai import Agent
from dataclasses import dataclass

@dataclass
class SpecInterpreterDeps:
    spec_yaml: str          # Raw YAML content
    source_columns: list[str]  # Available columns in source data

spec_interpreter_agent = Agent(
    model=...,  # Injected at runtime via create_llm()
    output_type=SpecInterpretation,
    deps_type=SpecInterpreterDeps,
    retries=3,
    system_prompt="You are a clinical data specification analyst. Parse the transformation specification and extract structured derivation rules. Flag any ambiguities, missing logic, or potential issues. Return rules that match the DerivationRule schema exactly.",
)
```

**Constraints:**
- `model` is NOT set at definition time — it's set at runtime via `agent.override(model=create_llm())`
- No tools needed — spec interpretation is a single-turn prompt
- Output must match `SpecInterpretation` schema — PydanticAI validates automatically
- System prompt instructs the agent to flag ambiguities

### `src/agents/derivation_coder.py` (NEW)

**Purpose:** PydanticAI agent that generates Python derivation code from a rule.

**Output type (define in this file):**

```python
class DerivationCode(BaseModel, frozen=True):
    """Output of the Derivation Coder agent."""
    variable_name: str
    python_code: str        # Single expression or function body using pandas
    approach: str           # Brief description of implementation approach
    null_handling: str      # How nulls are handled
```

**Deps type:**

```python
@dataclass
class CoderDeps:
    df: pd.DataFrame            # Real source data (for tools only)
    synthetic_csv: str          # Synthetic data as CSV string (for prompts)
    rule: DerivationRule        # The derivation rule to implement
    available_columns: list[str]  # Columns available at this DAG layer
```

**Agent definition:**

```python
coder_agent = Agent(
    model=...,
    output_type=DerivationCode,
    deps_type=CoderDeps,
    retries=3,
    system_prompt=(
        "You are a senior statistical programmer. Generate clean, vectorized "
        "pandas code to derive the requested variable. Your code will be "
        "executed as: `result = eval(your_code, {'df': df, 'pd': pd, 'np': np})`. "
        "The result must be a pandas Series with the same index as df. "
        "Handle null values explicitly. Use the inspect_data tool first to "
        "understand the data schema, then write the derivation."
    ),
)
```

**Tools:**

```python
@coder_agent.tool
async def inspect_data(ctx: RunContext[CoderDeps]) -> str:
    """Inspect the source dataset — returns schema, null counts, value ranges.
    NEVER returns raw patient rows."""
    # Return: column names, dtypes, null counts, value ranges, row count
    # Use ctx.deps.df for real stats but format as aggregates only

@coder_agent.tool
async def execute_code(ctx: RunContext[CoderDeps], code: str) -> str:
    """Execute Python code on the dataset. Returns aggregate results only.
    The DataFrame is available as `df`, pandas as `pd`, numpy as `np`."""
    # Execute in restricted namespace
    # Return: success/fail + result dtype + null count + value distribution
    # NEVER return raw rows
```

**Constraints:**
- `inspect_data` returns aggregates only (data security — see ARCHITECTURE.md)
- `execute_code` returns summary stats, not raw data
- The synthetic CSV is included in the agent's prompt context (via system prompt or deps), NOT the real data
- Code output must be evaluable as a pandas expression

### `src/agents/qc_programmer.py` (NEW)

**Purpose:** Independent QC agent — same interface as coder but different system prompt enforcing alternative approach.

**Output type:** Reuse `DerivationCode` from `derivation_coder.py`.

**Deps type:** Reuse `CoderDeps` from `derivation_coder.py`.

**Agent definition:**

```python
qc_agent = Agent(
    model=...,
    output_type=DerivationCode,
    deps_type=CoderDeps,
    retries=3,
    system_prompt=(
        "You are a QC (quality control) programmer performing INDEPENDENT "
        "verification. Generate pandas code to derive the requested variable "
        "using a DIFFERENT approach than the obvious one. "
        "If the obvious approach uses pd.cut, use np.select or np.where. "
        "If the obvious approach uses conditionals, use a mapping. "
        "Your code must produce the same result but via a different path. "
        "Use the inspect_data tool first."
    ),
)
```

**Tools:** Same `inspect_data` and `execute_code` as coder — registered with `@qc_agent.tool`.

**Constraints:**
- QC agent has NO ACCESS to coder's output — enforced by isolated `agent.run()` calls
- Different system prompt encourages alternative implementation
- Same output schema enables programmatic comparison

### `src/agents/debugger.py` (NEW)

**Purpose:** Diagnoses QC mismatches — compares two implementations and proposes a fix.

**Output type (define in this file):**

```python
class DebugAnalysis(BaseModel, frozen=True):
    variable_name: str
    root_cause: str             # Why the implementations diverge
    correct_implementation: str  # "coder" or "qc" or "neither"
    suggested_fix: str          # Corrected code if applicable
    confidence: str             # "high", "medium", "low"
```

**Deps type:**

```python
@dataclass
class DebuggerDeps:
    rule: DerivationRule
    coder_code: str
    qc_code: str
    divergent_summary: str   # Summary of divergent rows (aggregated, no PII)
    available_columns: list[str]
```

**Constraints:**
- No access to raw patient data in prompts
- `divergent_summary` contains counts and patterns, not individual values
- No tools needed — single-turn analysis

### `src/agents/auditor.py` (NEW)

**Purpose:** Generates audit trail summary from the enhanced DAG.

**Output type (define in this file):**

```python
class AuditSummary(BaseModel, frozen=True):
    study: str
    total_derivations: int
    auto_approved: int
    qc_mismatches: int
    human_interventions: int
    summary: str                # Natural language summary of the workflow
    recommendations: list[str]  # Suggestions for improvement
```

**Deps type:**

```python
@dataclass
class AuditorDeps:
    dag_summary: str            # Serialized DAG state (no patient data)
    workflow_id: str
    spec_metadata: SpecMetadata
```

**Constraints:**
- No access to patient data — only DAG metadata and provenance
- No tools needed — single-turn summarization

---

## 2.3 Tests

### `tests/unit/test_agents.py` (NEW)

**Purpose:** Test agent definitions are correctly configured. These tests do NOT call the LLM — they verify the agent objects are properly set up.

**Tests:**
- `test_spec_interpreter_agent_has_correct_output_type` — verify `output_type` is `SpecInterpretation`
- `test_coder_agent_has_inspect_and_execute_tools` — verify tool registration
- `test_qc_agent_has_inspect_and_execute_tools` — verify tool registration
- `test_qc_agent_system_prompt_mentions_different_approach` — verify independence enforcement
- `test_debugger_agent_has_correct_output_type` — verify `output_type` is `DebugAnalysis`
- `test_auditor_agent_has_correct_output_type` — verify `output_type` is `AuditSummary`
- `test_inspect_data_returns_aggregates_only` — call the tool function directly with a mock DataFrame, verify no raw rows in output
- `test_execute_code_returns_summary_not_raw_data` — call with `print(df.head())`, verify output is sanitized or blocked
- `test_llm_gateway_creates_correct_model` — verify `create_llm()` returns `OpenAIChatModel` with correct base_url

**Constraints:**
- Do NOT call `agent.run()` — that requires a real LLM. Test the tool functions and agent config directly.
- Tool functions can be tested by calling them with mock `RunContext` objects.
- Use `pytest.importorskip` if needed for optional deps.
