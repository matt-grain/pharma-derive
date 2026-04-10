# Phase 12 — YAML Agent Config (F06)

**Depends on:** Nothing (standalone feature)
**Agent:** `python-fastapi`
**Goal:** Externalize agent definitions (prompts, retries, tool bindings) to YAML config files. A factory loads them dynamically, enabling per-study prompt customization without code changes.

**Key principle:** Python files keep the **types** (output models, deps dataclasses, tool functions). YAML files own the **configuration** (prompts, retries, names, tool bindings). The factory bridges them via registries.

---

## 1. YAML Agent Configs — `config/agents/*.yaml` (5 NEW files)

### 1a. `config/agents/coder.yaml`
```yaml
name: coder
output_type: DerivationCode
deps_type: CoderDeps
retries: 3
tools:
  - inspect_data
  - execute_code
system_prompt: |
  You are a senior statistical programmer. Generate clean, vectorized
  pandas code to derive the requested variable. Your code will be
  executed as: `result = eval(your_code, {'df': df, 'pd': pd, 'np': np})`.
  The result must be a pandas Series with the same index as df.
  Handle null values explicitly. Use the inspect_data tool first to
  understand the data schema, then write the derivation.
```

### 1b. `config/agents/qc_programmer.yaml`
```yaml
name: qc_programmer
output_type: DerivationCode
deps_type: CoderDeps
retries: 3
tools:
  - inspect_data
  - execute_code
system_prompt: |
  You are a QC (quality control) programmer performing INDEPENDENT
  verification. Generate pandas code to derive the requested variable
  using a DIFFERENT approach than the obvious one.
  If the obvious approach uses pd.cut, use np.select or np.where.
  If the obvious approach uses conditionals, use a mapping.
  Your code must produce the same result but via a different path.
  Use the inspect_data tool first.
```

### 1c. `config/agents/debugger.yaml`
```yaml
name: debugger
output_type: DebugAnalysis
deps_type: DebuggerDeps
retries: 3
tools: []
system_prompt: |
  You are a senior clinical programmer debugging a QC mismatch.
  Analyze why two implementations of the same derivation rule
  produce different results. Determine which is correct and suggest a fix.
```

### 1d. `config/agents/auditor.yaml`
```yaml
name: auditor
output_type: AuditSummary
deps_type: AuditorDeps
retries: 3
tools: []
system_prompt: |
  You are a regulatory compliance auditor reviewing a clinical data
  derivation workflow. Summarize the derivation process, flag concerns,
  and provide recommendations for the audit trail.
```

### 1e. `config/agents/spec_interpreter.yaml`
```yaml
name: spec_interpreter
output_type: SpecInterpretation
deps_type: SpecInterpreterDeps
retries: 3
tools: []
system_prompt: |
  You are a clinical data specification analyst.
  Given a YAML transformation specification and a list of available source columns,
  extract each derivation rule with its variable name, source columns, derivation logic,
  and expected output type.
  Flag any ambiguities (missing source columns, unclear logic, conflicting rules).
  Return structured rules that can be directly executed by a statistical programmer.
```

---

## 2. Extract output types — `src/agents/types.py` (NEW)

**Purpose:** Centralize all agent output types (Pydantic models) in a leaf module with NO factory dependency. This breaks the circular import: registry.py → types.py (no factory) ← agent modules.

**CRITICAL — Circular import prevention:** If output types stay in agent modules (e.g., `DerivationCode` in `derivation_coder.py`) and those modules import `factory.py`, which imports `registry.py`, which imports the agent modules → circular crash. Extracting types to a leaf module breaks the cycle.

**Move these classes here:**
- `DerivationCode` from `src/agents/derivation_coder.py`
- `DebugAnalysis` from `src/agents/debugger.py`
- `SpecInterpretation` from `src/agents/spec_interpreter.py`

(`AuditSummary` already lives in `src/domain/models.py` — leave it there.)

```python
"""Agent output types — Pydantic models for structured agent responses.

Extracted to a leaf module to avoid circular imports with the agent factory.
Agent modules and the registry both import from here safely.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.domain.models import (  # noqa: TC001 — used at runtime by Pydantic
    ConfidenceLevel,
    CorrectImplementation,
    DerivationRule,
)


class DerivationCode(BaseModel, frozen=True):
    """Structured output of the derivation coder and QC programmer agents."""

    variable_name: str
    python_code: str
    approach: str
    null_handling: str


class DebugAnalysis(BaseModel, frozen=True):
    """Structured output of the debugger agent."""

    variable_name: str
    root_cause: str
    correct_implementation: CorrectImplementation
    suggested_fix: str
    confidence: ConfidenceLevel


class SpecInterpretation(BaseModel, frozen=True):
    """Structured output of the spec interpreter agent."""

    rules: list[DerivationRule]
    ambiguities: list[str]
    summary: str
```

**After creating this file, update imports in all files that used to import these types from agent modules:**
- `src/agents/derivation_coder.py` — remove `DerivationCode` class, add `from src.agents.types import DerivationCode`
- `src/agents/qc_programmer.py` — change `from src.agents.derivation_coder import DerivationCode` to `from src.agents.types import DerivationCode`
- `src/agents/debugger.py` — remove `DebugAnalysis` class, add `from src.agents.types import DebugAnalysis`
- `src/agents/spec_interpreter.py` — remove `SpecInterpretation` class, add `from src.agents.types import SpecInterpretation`
- `src/engine/derivation_runner.py` — change `from src.agents.derivation_coder import DerivationCode` to `from src.agents.types import DerivationCode` and `from src.agents.debugger import DebugAnalysis` to `from src.agents.types import DebugAnalysis`
- `tests/unit/test_agent_config.py` — update imports similarly
- `tests/unit/test_derivation_runner.py` — update imports similarly
- `src/api/mcp_server.py` — no change (doesn't import output types)

---

## 3. Move all deps to `src/agents/deps.py` (MODIFY)

**Purpose:** `deps.py` already has `CoderDeps`. Move `AuditorDeps`, `DebuggerDeps`, `SpecInterpreterDeps` here too — another leaf module with no factory dependency.

**Add to `src/agents/deps.py`:**
```python
# Already exists:
@dataclass
class CoderDeps: ...

# Move from auditor.py:
@dataclass
class AuditorDeps:
    dag_summary: str
    workflow_id: str
    spec_metadata: SpecMetadata

# Move from debugger.py:
@dataclass
class DebuggerDeps:
    rule: DerivationRule
    coder_code: str
    qc_code: str
    divergent_summary: str
    available_columns: list[str]

# Move from spec_interpreter.py:
@dataclass
class SpecInterpreterDeps:
    spec_yaml: str
    source_columns: list[str]
```

**Update imports in:**
- `src/agents/auditor.py` — remove `AuditorDeps` class, add `from src.agents.deps import AuditorDeps`
- `src/agents/debugger.py` — remove `DebuggerDeps` class, add `from src.agents.deps import DebuggerDeps`
- `src/agents/spec_interpreter.py` — remove `SpecInterpreterDeps` class, add `from src.agents.deps import SpecInterpreterDeps`
- `src/engine/derivation_runner.py` — change `from src.agents.debugger import DebuggerDeps` to `from src.agents.deps import DebuggerDeps`
- `src/engine/orchestrator.py` — change `from src.agents.auditor import AuditorDeps` to `from src.agents.deps import AuditorDeps`

**IMPORTANT:** Keep re-exports in agent modules so existing external imports still work:
```python
# In auditor.py — keep backward compatibility:
from src.agents.deps import AuditorDeps as AuditorDeps  # re-export
```

---

## 4. Type & Tool Registries — `src/agents/registry.py` (NEW)

**Purpose:** Maps string names from YAML to actual Python types and tool functions.

**Now imports from leaf modules only (no circular import):**

```python
"""Agent registries — maps YAML string names to Python types and tool functions."""

from __future__ import annotations

from typing import Any  # Any: heterogeneous type registry mapping strings to various Pydantic/dataclass types

from src.agents.deps import AuditorDeps, CoderDeps, DebuggerDeps, SpecInterpreterDeps
from src.agents.tools import execute_code, inspect_data
from src.agents.types import DebugAnalysis, DerivationCode, SpecInterpretation
from src.domain.models import AuditSummary

OUTPUT_TYPE_MAP: dict[str, type[Any]] = {
    "DerivationCode": DerivationCode,
    "DebugAnalysis": DebugAnalysis,
    "AuditSummary": AuditSummary,
    "SpecInterpretation": SpecInterpretation,
}

DEPS_TYPE_MAP: dict[str, type[Any]] = {
    "CoderDeps": CoderDeps,
    "DebuggerDeps": DebuggerDeps,
    "AuditorDeps": AuditorDeps,
    "SpecInterpreterDeps": SpecInterpreterDeps,
}

TOOL_MAP: dict[str, Any] = {  # Any: PydanticAI tool signatures vary
    "inspect_data": inspect_data,
    "execute_code": execute_code,
}
```

**Import chain (verified no circular):**
```
registry.py → deps.py (leaf, no factory)
registry.py → types.py (leaf, no factory)
registry.py → tools/ (leaf, no factory)
registry.py → domain/models.py (leaf)
factory.py → registry.py
agent modules → factory.py (for load_agent)
agent modules → types.py (for re-export)
agent modules → deps.py (for re-export)
```

---

## 3. Agent Factory — `src/agents/factory.py` (NEW)

**Purpose:** Load a PydanticAI Agent from a YAML config file using the registries.

```python
"""Agent factory — creates PydanticAI agents from YAML config files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic_ai import Agent

from src.agents.registry import DEPS_TYPE_MAP, OUTPUT_TYPE_MAP, TOOL_MAP


def load_agent(yaml_path: str | Path) -> Agent[Any, Any]:
    """Load a PydanticAI agent from a YAML configuration file.

    The YAML must contain: name, output_type, deps_type, retries, system_prompt.
    Optional: tools (list of tool function names from TOOL_MAP).

    Raises:
        FileNotFoundError: If YAML file doesn't exist.
        KeyError: If output_type, deps_type, or tool name not in registry.
    """
    path = Path(yaml_path)
    if not path.exists():
        msg = f"Agent config not found: {path}"
        raise FileNotFoundError(msg)

    config = yaml.safe_load(path.read_text(encoding="utf-8"))

    name: str = config["name"]
    output_type = OUTPUT_TYPE_MAP[config["output_type"]]
    deps_type = DEPS_TYPE_MAP[config["deps_type"]]
    retries: int = config.get("retries", 3)
    system_prompt: str = config["system_prompt"].strip()
    tool_names: list[str] = config.get("tools", [])

    agent: Agent[Any, Any] = Agent(  # Any: agent type params resolved from YAML at runtime
        "test",  # overridden at call time via model= parameter
        name=name,
        output_type=output_type,
        deps_type=deps_type,
        retries=retries,
        system_prompt=system_prompt,
    )

    for tool_name in tool_names:
        if tool_name not in TOOL_MAP:
            msg = f"Unknown tool '{tool_name}' in agent config '{path.name}'. Available: {list(TOOL_MAP.keys())}"
            raise KeyError(msg)
        agent.tool(TOOL_MAP[tool_name])

    return agent
```

**Constraints:**
- `Agent[Any, Any]` return type is justified — the factory creates agents with different type params depending on YAML. Add comment.
- Validate that required YAML keys exist — raise `KeyError` with clear message if missing
- Strip trailing whitespace from system_prompt (YAML `|` blocks may include trailing newline)
- Keep `"test"` as the model placeholder — same as current pattern, overridden at call time
- Do NOT parse the YAML at import time — the function is called explicitly

---

## 4. Update Agent Modules (5 MODIFY)

Each agent module keeps its **types** (output model, deps dataclass) but replaces the hardcoded `Agent(...)` constructor with a `load_agent()` call.

### 5a. `src/agents/derivation_coder.py` (MODIFY)

**Remove:** `DerivationCode` class (moved to `types.py`), `Agent(...)` constructor, tool imports, `agent.tool()` calls
**Keep:** Module docstring
**Add:** Re-export `DerivationCode` from types + factory call

```python
"""Derivation coder agent — generates primary pandas implementation for each variable."""

from __future__ import annotations

from src.agents.factory import load_agent
from src.agents.types import DerivationCode as DerivationCode  # re-export for backward compat

coder_agent = load_agent("config/agents/coder.yaml")
```

**IMPORTANT:** `DerivationCode as DerivationCode` re-export ensures `from src.agents.derivation_coder import DerivationCode` still works for all existing importers.

### 5b. `src/agents/qc_programmer.py` (MODIFY)

**Remove:** Everything except docstring
**Add:** factory call

```python
"""QC programmer agent — independent verification using an alternative approach."""

from __future__ import annotations

from src.agents.factory import load_agent

qc_agent = load_agent("config/agents/qc_programmer.yaml")
```

### 5c. `src/agents/auditor.py` (MODIFY)

**Remove:** `AuditorDeps` class (moved to `deps.py`), `Agent(...)` constructor
**Keep:** Module docstring
**Add:** Re-export `AuditorDeps` + factory call

```python
"""Auditor agent — generates regulatory compliance summary for the audit trail."""

from __future__ import annotations

from src.agents.deps import AuditorDeps as AuditorDeps  # re-export for backward compat
from src.agents.factory import load_agent

auditor_agent = load_agent("config/agents/auditor.yaml")
```

### 5d. `src/agents/debugger.py` (MODIFY)

**Remove:** `DebugAnalysis` class (→ types.py), `DebuggerDeps` class (→ deps.py), `Agent(...)` constructor
**Add:** Re-exports + factory call

```python
"""Debugger agent — analyses QC mismatches and identifies the correct implementation."""

from __future__ import annotations

from src.agents.deps import DebuggerDeps as DebuggerDeps  # re-export
from src.agents.factory import load_agent
from src.agents.types import DebugAnalysis as DebugAnalysis  # re-export

debugger_agent = load_agent("config/agents/debugger.yaml")
```

### 5e. `src/agents/spec_interpreter.py` (MODIFY)

**Remove:** `SpecInterpretation` class (→ types.py), `SpecInterpreterDeps` class (→ deps.py), `Agent(...)` constructor
**Add:** Re-exports + factory call

```python
"""Spec interpreter agent — parses YAML specs into structured DerivationRule objects."""

from __future__ import annotations

from src.agents.deps import SpecInterpreterDeps as SpecInterpreterDeps  # re-export
from src.agents.factory import load_agent
from src.agents.types import SpecInterpretation as SpecInterpretation  # re-export

spec_interpreter_agent = load_agent("config/agents/spec_interpreter.yaml")
```

### 5f. Update imports in consumer files

These files import types from agent modules — update to import from `types.py` and `deps.py` directly (the re-exports in agent modules also work, but direct imports are cleaner):

- `src/engine/derivation_runner.py`:
  - `from src.agents.debugger import DebugAnalysis, DebuggerDeps` → `from src.agents.types import DebugAnalysis` + `from src.agents.deps import DebuggerDeps`
  - `from src.agents.derivation_coder import DerivationCode` → `from src.agents.types import DerivationCode`
- `src/engine/orchestrator.py`:
  - `from src.agents.auditor import AuditorDeps` → `from src.agents.deps import AuditorDeps`
- `tests/unit/test_agent_config.py`:
  - Update type imports to come from `src.agents.types` and `src.agents.deps`
- `tests/unit/test_derivation_runner.py`:
  - Update type imports similarly

---

## 5. Tests — `tests/unit/test_agent_factory.py` (NEW)

**Purpose:** Test the factory and registry, verify all 5 agents load correctly from YAML.

**Tests to write:**

```python
def test_load_agent_creates_agent_with_correct_name() -> None:
    """Factory creates an agent with the name from YAML."""
    # Arrange & Act
    agent = load_agent("config/agents/coder.yaml")
    # Assert
    assert agent.name == "coder"

def test_load_agent_creates_agent_with_correct_output_type() -> None:
    """Factory resolves output_type from registry."""
    # Arrange & Act
    agent = load_agent("config/agents/coder.yaml")
    # Assert
    assert agent.output_type is DerivationCode

def test_load_agent_registers_tools() -> None:
    """Factory registers tools listed in YAML."""
    # Arrange & Act
    agent = load_agent("config/agents/coder.yaml")
    tool_names = get_tool_names(agent)  # from tests/unit/conftest.py
    # Assert
    assert "inspect_data" in tool_names
    assert "execute_code" in tool_names

def test_load_agent_no_tools_for_debugger() -> None:
    """Agents with empty tools list have no registered tools."""
    # Arrange & Act
    agent = load_agent("config/agents/debugger.yaml")
    # Assert
    assert len(get_tool_names(agent)) == 0

def test_load_agent_nonexistent_file_raises() -> None:
    """Factory raises FileNotFoundError for missing YAML."""
    # Act & Assert
    with pytest.raises(FileNotFoundError, match="Agent config not found"):
        load_agent("config/agents/nonexistent.yaml")

def test_load_agent_unknown_output_type_raises() -> None:
    """Factory raises KeyError for unregistered output_type."""
    # Arrange — write a temp YAML with bad output_type
    # (use tmp_path fixture)
    ...

def test_load_agent_unknown_tool_raises() -> None:
    """Factory raises KeyError for unregistered tool name."""
    ...

def test_all_five_agents_load_successfully() -> None:
    """Smoke test: all 5 production agent configs load without error."""
    # Arrange
    configs = [
        "config/agents/coder.yaml",
        "config/agents/qc_programmer.yaml",
        "config/agents/debugger.yaml",
        "config/agents/auditor.yaml",
        "config/agents/spec_interpreter.yaml",
    ]
    # Act & Assert
    for config_path in configs:
        agent = load_agent(config_path)
        assert agent.name is not None
```

**Fixtures:** Use `tmp_path` for writing invalid YAML configs in error tests.
**Pattern:** AAA markers, `test_<action>_<scenario>_<expected>` naming.
**Import:** `from tests.unit.conftest import get_tool_names` — existing helper that safely introspects PydanticAI tool registration.
**Import:** `from src.agents.factory import load_agent` and `from src.agents.types import DerivationCode` for type assertions.

---

## 6. Update existing test — `tests/unit/test_agent_config.py` (MODIFY)

**Change:** The existing test `test_all_agents_have_name_set` imports agents from their modules. After the refactor, agents are still importable from the same modules — no import changes needed. BUT the existing tests that check `coder_agent.output_type is DerivationCode` should still pass because the factory sets the output_type correctly.

**Verify:** All existing tests in `test_agent_config.py` should pass without modification. If any fail, the factory is wiring incorrectly.

---

## 7. Update `decisions.md` (MODIFY)

**Append ADR:**
```markdown
## 2026-04-10 — YAML Agent Config (F06)

**Status:** accepted
**Context:** Agent prompts, retries, and tool bindings were hardcoded in Python. Changing a prompt required a code change and redeploy. For a platform serving multiple studies, clinical teams need to customize agent behavior per therapeutic area without touching code.
**Decision:** Externalize agent configuration to YAML files in `config/agents/`. A factory (`src/agents/factory.py`) loads them using type/tool registries (`src/agents/registry.py`). Python modules keep output types, deps dataclasses, and tool functions — only configuration moves to YAML.
**Alternatives considered:** (1) Pydantic Settings with env vars per agent — rejected because prompts are multi-line text, awkward in env vars. (2) JSON config — rejected because YAML is more readable for multi-line prompts (block scalar `|`). (3) Database-stored prompts — rejected as over-engineering for the current scope.
**Consequences:** Adding a new agent = create a YAML file + add types to registry. Per-study prompt variants = copy YAML, modify prompt, pass different config path. Trade-off: runtime error if YAML references unregistered type (caught by startup tests).
```

---

## Verification

1. `uv run ruff check . --fix && uv run ruff format .`
2. `uv run pyright .`
3. `uv run pytest --tb=short -q` — all existing 165 tests + ~8 new factory tests pass (~173 total)
4. Smoke test: `uv run python -c "from src.agents.derivation_coder import coder_agent; print(coder_agent.name)"`
5. Verify no YAML files are imported at Python import time (factory is called during module init, verify no startup slowdown)
