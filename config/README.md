# Configuration — CDDE

This directory contains YAML configuration files for the Clinical Data Derivation Engine.

## Directory Structure

```
config/
├── agents/                 # PydanticAI agent definitions
│   ├── coder.yaml          # Derivation coder agent
│   ├── qc_programmer.yaml  # QC double-programming agent
│   ├── debugger.yaml       # Mismatch debugger agent
│   ├── auditor.yaml        # Regulatory audit agent
│   └── spec_interpreter.yaml  # Spec parsing agent
├── pipelines/              # Orchestration pipeline definitions
│   ├── clinical_derivation.yaml  # Standard 6-step flow (default)
│   ├── express.yaml              # Fast prototyping — no QC, no audit
│   └── enterprise.yaml           # Full compliance — 3 HITL gates
└── README.md               # This file
```

## Agent YAML Format

Each agent YAML defines a PydanticAI agent loaded by `src/agents/factory.py`.

```yaml
name: coder                    # Agent identifier (matches AgentName enum)
output_type: DerivationCode    # Pydantic model for structured output
deps_type: CoderDeps           # Dataclass for runtime dependencies
retries: 3                     # Max retries on validation failure
tools:                         # PydanticAI tools attached to this agent
  - inspect_data
  - execute_code
system_prompt: |               # Multi-line system prompt (YAML block scalar)
  You are a senior statistical programmer...
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Unique agent identifier |
| `output_type` | string | yes | Key in `OUTPUT_TYPE_MAP` registry (`src/agents/registry.py`) |
| `deps_type` | string | yes | Key in `DEPS_TYPE_MAP` registry |
| `retries` | int | no | Max retries (default: 3) |
| `tools` | list[string] | no | Keys in `TOOL_MAP` registry |
| `system_prompt` | string | yes | Agent system prompt |

### Available Output Types

| Key | Python Type | Used By |
|-----|------------|---------|
| `DerivationCode` | `src.agents.types.DerivationCode` | coder, qc_programmer |
| `DebugAnalysis` | `src.agents.types.DebugAnalysis` | debugger |
| `AuditSummary` | `src.domain.models.AuditSummary` | auditor |
| `SpecInterpretation` | `src.agents.types.SpecInterpretation` | spec_interpreter |

### Available Tools

| Key | Function | Description |
|-----|----------|-------------|
| `inspect_data` | `src.agents.tools.inspect_data` | Returns schema + sample of the source DataFrame |
| `execute_code` | `src.agents.tools.execute_code` | Sandboxed eval of pandas code |

## Pipeline YAML Format

Each pipeline YAML defines an orchestration flow loaded by `src/domain/pipeline_models.py`.

```yaml
pipeline:
  name: clinical_derivation       # Pipeline identifier
  version: "1.0"                  # Semantic version
  description: "Standard flow"    # Human-readable description

  steps:
    - id: parse_spec              # Unique step identifier (snake_case)
      type: builtin               # Composition type (see below)
      builtin: parse_spec         # Builtin function name
      description: "Parse spec"

    - id: build_dag
      type: builtin
      builtin: build_dag
      depends_on: [parse_spec]    # Dependency — runs after parse_spec

    - id: derive_variables
      type: parallel_map          # Iterate DAG layers in parallel
      over: dag_layers
      depends_on: [build_dag]
      config:
        coder_agent: coder        # Agent YAML name for primary coder
        qc_agent: qc_programmer   # Agent YAML name for QC (omit for coder-only mode)
        debugger_agent: debugger   # Agent YAML name for mismatch debugging (omit to skip)

    - id: human_review
      type: hitl_gate             # Pause for human approval
      depends_on: [derive_variables]
      config:
        message: "Review before audit"

    - id: audit
      type: agent                 # Run a PydanticAI agent
      agent: auditor              # Agent YAML name (from config/agents/)
      depends_on: [human_review]

    - id: export
      type: builtin
      builtin: export_adam
      depends_on: [audit]
      config:
        formats: [csv, parquet]   # Export formats
```

### Step Types

| Type | Description | Required Fields |
|------|-------------|----------------|
| `agent` | Run a single PydanticAI agent | `agent` (name of YAML in `config/agents/`) |
| `builtin` | Run a non-LLM Python function | `builtin` (key in `BUILTIN_REGISTRY`) |
| `gather` | Run N agents in parallel | `agents` (list of agent names) |
| `parallel_map` | Map sub-steps over a collection | `over`, `config.coder_agent` (see below) |
| `hitl_gate` | Pause workflow for human approval | `config.message` (displayed in UI) |

### `parallel_map` Agent Config

The `parallel_map` step runs per-variable derivation across DAG layers. It uses a dedicated runner (`derivation_runner.py`) that orchestrates coder, QC, verification, and debugging. Agent assignments are declared in the `config` block:

| Config Key | Type | Required | Description |
|-----------|------|----------|-------------|
| `coder_agent` | string | yes | Agent name for primary code generation (e.g., `coder`) |
| `qc_agent` | string | no | Agent name for QC double-programming (e.g., `qc_programmer`). **Omit to skip QC** — coder output is auto-approved (express mode). |
| `debugger_agent` | string | no | Agent name for mismatch debugging (e.g., `debugger`). **Omit to skip debugging** — mismatches are recorded but not resolved. |

**Examples:**

```yaml
# Full QC pipeline (standard/enterprise)
config:
  coder_agent: coder
  qc_agent: qc_programmer
  debugger_agent: debugger

# Coder-only mode (express — rapid prototyping)
config:
  coder_agent: coder
  # qc_agent and debugger_agent omitted — no QC, no debugging
```

### Available Builtins

| Key | Description |
|-----|-------------|
| `parse_spec` | Parse YAML spec, load source data, generate synthetic CSV |
| `build_dag` | Build derivation dependency graph from spec rules |
| `export_adam` | Export derived DataFrame as CSV/Parquet |

### Step Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique step identifier |
| `type` | string | yes | One of: `agent`, `builtin`, `gather`, `parallel_map`, `hitl_gate` |
| `description` | string | no | Human-readable step description |
| `agent` | string | no | Agent YAML name (for `type: agent`) |
| `agents` | list[string] | no | Agent names (for `type: gather`) |
| `builtin` | string | no | Builtin function name (for `type: builtin`) |
| `depends_on` | list[string] | no | Step IDs that must complete before this step |
| `config` | dict | no | Step-specific configuration |
| `over` | string | no | Iteration target (for `type: parallel_map`) |
| `sub_steps` | list[step] | no | Nested steps (for `type: parallel_map`) |
| `condition` | string | no | Condition for conditional execution |

### Creating a New Pipeline

1. Copy an existing pipeline YAML as a starting point
2. Modify steps — add/remove HITL gates, change agent assignments, adjust export formats
3. Validate: `uv run python -c "from src.domain.pipeline_models import load_pipeline; print(load_pipeline('config/pipelines/your_pipeline.yaml'))"`
4. Every pipeline must start with `parse_spec` and end with `export`

## Adding a New Step Type

Most pipeline customizations DON'T require new code — they combine existing step types:

| I want to... | How | New code? |
|-------------|-----|-----------|
| Add an LLM agent step | `type: agent` + new agent YAML (see `config/agents/README.md`) | Deps class + builder only |
| Run agents in parallel | `type: gather` with `agents: [a, b]` | No |
| Add a human approval gate | `type: hitl_gate` with `config.message` | No |
| Add a data transformation | `type: builtin` + register a new function | Small Python function |
| Change derivation agents | Update `config` block on `derive_variables` step | No |

### When you DO need new code: adding a builtin

Builtins are non-LLM Python functions (data loading, DAG construction, file export). To add one:

**1. Write the async function** in `src/engine/step_builtins.py`:

```python
async def _builtin_validate_data(step: StepDefinition, ctx: PipelineContext) -> None:
    """Check data quality before derivation — example builtin."""
    if ctx.derived_df is None:
        msg = f"Step '{step.id}' requires derived_df in context"
        raise ValueError(msg)
    null_pct = ctx.derived_df.isna().mean().mean()
    threshold = float(step.config.get("max_null_pct", 0.5))
    if null_pct > threshold:
        msg = f"Data quality check failed: {null_pct:.1%} nulls exceeds {threshold:.0%} threshold"
        raise ValueError(msg)
```

**Rules:**
- Signature must be `async def(step: StepDefinition, ctx: PipelineContext) -> None`
- Read inputs from `ctx` (spec, derived_df, dag, etc.)
- Write outputs back to `ctx` (mutate in place)
- Read step-specific config from `step.config`
- Raise `ValueError` with descriptive message on failure

**2. Register in `BUILTIN_REGISTRY`:**

```python
BUILTIN_REGISTRY: dict[str, Any] = {
    "parse_spec": _builtin_parse_spec,
    "build_dag": _builtin_build_dag,
    "export_adam": _builtin_export_adam,
    "validate_data": _builtin_validate_data,  # new
}
```

**3. Use in a pipeline:**

```yaml
steps:
  - id: parse_spec
    type: builtin
    builtin: parse_spec

  - id: data_quality_gate
    type: builtin
    builtin: validate_data
    depends_on: [parse_spec]
    config:
      max_null_pct: 0.3    # fail if >30% nulls

  - id: build_dag
    type: builtin
    builtin: build_dag
    depends_on: [data_quality_gate]
```

### The `parallel_map` special case

The `parallel_map` step type is the only one with a dedicated Python runner (`src/engine/derivation_runner.py`). It exists because per-variable derivation is a complex multi-step process:

```
For each DAG layer (sequential):
  For each variable in layer (parallel):
    1. Load coder + QC agents from config
    2. Run both in parallel (asyncio.gather)
    3. Verify outputs match (comparator)
    4. If mismatch: run debugger agent
    5. Apply approved code to DataFrame
```

This logic is too complex for a single builtin function and too domain-specific for a generic executor. The `parallel_map` executor delegates to `run_variable()` which handles the full coder/QC/verify/debug cycle.

Agent names are declared in the pipeline YAML (`config.coder_agent`, `config.qc_agent`, `config.debugger_agent`) and passed to `run_variable()` at runtime. Omitting `qc_agent` enables coder-only mode (express pipeline).

### Architecture summary

```
Pipeline YAML          Step Executors              Python Code
─────────────          ──────────────              ───────────
type: agent       →    AgentStepExecutor      →    load_agent(yaml) + AGENT_DEPS_BUILDERS
type: builtin     →    BuiltinStepExecutor    →    BUILTIN_REGISTRY[name](step, ctx)
type: gather      →    GatherStepExecutor     →    load_agent(yaml) x N + asyncio.gather
type: hitl_gate   →    HITLGateStepExecutor   →    asyncio.Event (generic, no custom code)
type: parallel_map →   ParallelMapStepExecutor →   derivation_runner.run_variable()
```

Adding new step types (e.g., `type: conditional`, `type: retry_loop`) requires:
1. Add a member to `StepType` enum in `src/domain/pipeline_models.py`
2. Create a new `StepExecutor` subclass in `src/engine/step_executors.py`
3. Register it in `STEP_EXECUTOR_REGISTRY`
