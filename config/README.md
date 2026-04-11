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
| `parallel_map` | Map sub-steps over a collection | `over` (currently only `dag_layers`) |
| `hitl_gate` | Pause workflow for human approval | `config.message` (displayed in UI) |

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
