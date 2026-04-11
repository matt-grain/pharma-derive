# Adding a New Agent

This guide walks through adding a new PydanticAI agent to the CDDE pipeline. Each agent is defined by a YAML config file in this directory and backed by typed Python classes in the `src/agents/` package.

## What You Need

| Step | File | What to add |
|------|------|-------------|
| 1 | `config/agents/<name>.yaml` | Agent config (prompt, tools, retries) |
| 2 | `src/agents/types.py` | Output Pydantic model (what the agent returns) |
| 3 | `src/agents/deps.py` | Deps dataclass (what the agent receives at runtime) |
| 4 | `src/agents/registry.py` | Register output type, deps type, and any new tools |
| 5 | `src/engine/step_builtins.py` | Deps builder function (how to construct deps from pipeline context) |
| 6 | Pipeline YAML | Reference the agent in a pipeline step |

## Step-by-Step Example: Adding a `data_quality` Agent

### 1. Create the YAML config

```yaml
# config/agents/data_quality.yaml
name: data_quality
output_type: DataQualityReport
deps_type: DataQualityDeps
retries: 2
tools: []
system_prompt: |
  You are a data quality analyst. Given a dataset schema and summary
  statistics, identify potential issues: missing values, outliers,
  inconsistent formats, and referential integrity problems.
```

**Fields:**
- `name` — unique identifier, must match the filename (without `.yaml`)
- `output_type` — key in `OUTPUT_TYPE_MAP` (you'll register it in step 2)
- `deps_type` — key in `DEPS_TYPE_MAP` (you'll register it in step 3)
- `retries` — max LLM retries on validation failure (default: 3)
- `tools` — list of tool names from `TOOL_MAP` (use `[]` for single-turn agents)
- `system_prompt` — multi-line YAML block scalar (`|`)

### 2. Define the output model

```python
# src/agents/types.py — add after existing classes

class DataQualityReport(BaseModel, frozen=True):
    """Structured output of the data quality agent."""
    issues: list[str]
    severity: str           # Use a StrEnum if this becomes a fixed set
    recommendations: list[str]
    overall_score: float    # 0.0 = critical, 1.0 = clean
```

**Rules:**
- Must inherit `BaseModel` with `frozen=True`
- All fields must be typed (no `Any`)
- PydanticAI validates the LLM response against this schema automatically

### 3. Define the deps dataclass

```python
# src/agents/deps.py — add after existing classes

@dataclass
class DataQualityDeps:
    """Dependencies for the data quality agent."""
    schema_summary: str       # Column names + dtypes
    null_counts: dict[str, int]
    row_count: int
    study: str
```

**Rules:**
- Must be a `@dataclass` (not Pydantic — deps are internal, not serialized)
- Fields should contain only what the agent needs — not the full DataFrame
- Patient data must NEVER be included (see `docs/COMPOSITION_LAYER.md`)

### 4. Register in the registries

```python
# src/agents/registry.py

# Add to OUTPUT_TYPE_MAP:
from src.agents.types import DataQualityReport
OUTPUT_TYPE_MAP["DataQualityReport"] = DataQualityReport

# Add to DEPS_TYPE_MAP:
from src.agents.deps import DataQualityDeps
DEPS_TYPE_MAP["DataQualityDeps"] = DataQualityDeps

# If your agent uses tools, add them to TOOL_MAP:
# TOOL_MAP["my_new_tool"] = my_tool_function
```

### 5. Add a deps builder

The deps builder tells the pipeline interpreter how to construct the agent's deps from the shared `PipelineContext`.

```python
# src/engine/step_builtins.py — add a builder function

def _build_data_quality_deps(ctx: PipelineContext) -> tuple[Any, str]:
    from src.agents.deps import DataQualityDeps

    if ctx.derived_df is None:
        msg = "data_quality requires ctx.derived_df"
        raise ValueError(msg)
    schema = ", ".join(f"{c}: {ctx.derived_df[c].dtype}" for c in ctx.derived_df.columns)
    null_counts = {str(c): int(ctx.derived_df[c].isna().sum()) for c in ctx.derived_df.columns}
    deps = DataQualityDeps(
        schema_summary=schema,
        null_counts=null_counts,
        row_count=len(ctx.derived_df),
        study=ctx.spec.metadata.study if ctx.spec else "unknown",
    )
    return deps, "Analyze data quality"

# Register it:
AGENT_DEPS_BUILDERS["data_quality"] = _build_data_quality_deps
```

### 6. Use in a pipeline

```yaml
# config/pipelines/my_study.yaml
pipeline:
  name: my_study
  steps:
    - id: parse_spec
      type: builtin
      builtin: parse_spec

    - id: data_quality           # Your new step
      type: agent
      agent: data_quality        # Matches the YAML filename
      depends_on: [parse_spec]
      description: "Check source data quality before derivation"

    - id: build_dag
      type: builtin
      builtin: build_dag
      depends_on: [data_quality]
    # ... remaining steps
```

## Verification

After adding all files, run:

```bash
# Verify the YAML parses and agent loads
uv run python -c "
from src.agents.factory import load_agent
a = load_agent('config/agents/data_quality.yaml')
print(f'{a.name}: output={a.output_type.__name__}')
"

# Run full quality suite
uv run ruff check . && uv run pyright . && uv run pytest
```

## Architecture Notes

- **Why typed deps?** PydanticAI uses `RunContext[DepsType]` — the type parameter enforces that tools and agents receive the correct data at compile time. A generic `dict[str, Any]` would lose this safety.
- **Why a deps builder?** Each agent needs different data from the pipeline context. The builder function is the bridge between the generic context and the typed deps.
- **Data security:** Agent deps should contain schema metadata and aggregates, never raw patient rows. See the dual-dataset architecture in `ARCHITECTURE.md`.
