# Implementation Plan — Phase 14.4: Scenario Pipelines + Integration Tests

**Date:** 2026-04-11
**Feature:** F02/F03 — Alternative pipeline configs (express, enterprise) + integration tests
**Agent:** `python-fastapi`
**Dependencies:** Phase 14.2 must be complete — `pipeline_interpreter.py`, `step_executors.py`, `clinical_derivation.yaml` must exist.

---

## Context for Subagent

Phases 14.1–14.3 built the pipeline infrastructure. This phase creates **two alternative pipeline configurations** that demonstrate the platform's flexibility, plus integration tests that validate the pipeline interpreter works end-to-end.

**Key files to read first:**
- `config/pipelines/clinical_derivation.yaml` — the standard pipeline (from Phase 14.2)
- `src/engine/pipeline_interpreter.py` — the interpreter we're testing
- `src/engine/step_executors.py` — executor classes + BUILTIN_REGISTRY
- `src/domain/pipeline_models.py` — `load_pipeline`, `PipelineDefinition`, `StepType`
- `tests/conftest.py` — existing fixtures (sample_spec, sample_df, sample_dag)

---

## Files to Create

### 1. `config/pipelines/express.yaml` (NEW)

**Purpose:** Scenario 2 — fast iteration pipeline that skips QC, debugging, and audit. For rapid prototyping during study setup, before formal validation is needed.

```yaml
pipeline:
  name: express
  version: "1.0"
  description: "Rapid prototyping — single coder, no QC, no audit, no human gate"

  steps:
    - id: parse_spec
      type: builtin
      builtin: parse_spec
      description: "Parse spec and load source data"

    - id: build_dag
      type: builtin
      builtin: build_dag
      depends_on: [parse_spec]
      description: "Build derivation DAG"

    - id: derive_variables
      type: parallel_map
      over: dag_layers
      depends_on: [build_dag]
      description: "Derive variables — coder only, no QC double-programming"

    - id: export
      type: builtin
      builtin: export_adam
      depends_on: [derive_variables]
      config:
        formats:
          - csv
      description: "Export as CSV only"
```

**Key differences from standard:**
- No `gather` step (single coder, no QC agent)
- No `human_review` HITL gate
- No `audit` agent step
- Export CSV only (no Parquet)
- 4 steps instead of 6

---

### 2. `config/pipelines/enterprise.yaml` (NEW)

**Purpose:** Scenario 3 — full enterprise pipeline with multiple HITL gates for 21 CFR Part 11 compliance. Demonstrates maximum configurability.

```yaml
pipeline:
  name: enterprise
  version: "1.0"
  description: "Enterprise pipeline — spec approval, derivation QC, variable review, final sign-off"

  steps:
    - id: parse_spec
      type: builtin
      builtin: parse_spec
      description: "Parse transformation spec and load source data"

    - id: spec_approval
      type: hitl_gate
      depends_on: [parse_spec]
      config:
        message: "Review spec interpretation — verify source columns and derivation rules"
      description: "HITL gate: approve spec before building DAG"

    - id: build_dag
      type: builtin
      builtin: build_dag
      depends_on: [spec_approval]
      description: "Build derivation dependency graph"

    - id: derive_variables
      type: parallel_map
      over: dag_layers
      depends_on: [build_dag]
      description: "Derive with coder+QC double programming, verify, debug if mismatch"

    - id: variable_review
      type: hitl_gate
      depends_on: [derive_variables]
      config:
        message: "Review each derived variable — inspect code, QC results, and debugger fixes"
      description: "HITL gate: approve variables before audit"

    - id: audit
      type: agent
      agent: auditor
      depends_on: [variable_review]
      description: "Generate regulatory audit summary"

    - id: final_signoff
      type: hitl_gate
      depends_on: [audit]
      config:
        message: "Final sign-off — confirm audit results and approve export"
      description: "HITL gate: final approval before data export"

    - id: export
      type: builtin
      builtin: export_adam
      depends_on: [final_signoff]
      config:
        formats:
          - csv
          - parquet
      description: "Export derived ADaM dataset in all formats"
```

**Key differences from standard:**
- 3 HITL gates (spec_approval, variable_review, final_signoff) vs 1
- 8 steps instead of 6
- Gates have specific review messages for each phase

---

### 3. `tests/unit/test_pipeline_scenarios.py` (NEW)

**Purpose:** Validate all 3 pipeline YAML configs parse correctly and have expected structure.

**Tests to write:**

```python
"""Tests for pipeline YAML scenario configs — validates all 3 pipelines parse correctly."""

from __future__ import annotations

import pytest

from src.domain.pipeline_models import PipelineDefinition, StepType, load_pipeline


class TestStandardPipeline:
    """Tests for config/pipelines/clinical_derivation.yaml."""

    @pytest.fixture
    def pipeline(self) -> PipelineDefinition:
        return load_pipeline("config/pipelines/clinical_derivation.yaml")

    def test_standard_pipeline_name(self, pipeline: PipelineDefinition) -> None:
        assert pipeline.name == "clinical_derivation"

    def test_standard_pipeline_has_six_steps(self, pipeline: PipelineDefinition) -> None:
        assert len(pipeline.steps) == 6

    def test_standard_pipeline_has_hitl_gate(self, pipeline: PipelineDefinition) -> None:
        gate_steps = [s for s in pipeline.steps if s.type == StepType.HITL_GATE]
        assert len(gate_steps) == 1
        assert gate_steps[0].id == "human_review"

    def test_standard_pipeline_has_parallel_map(self, pipeline: PipelineDefinition) -> None:
        map_steps = [s for s in pipeline.steps if s.type == StepType.PARALLEL_MAP]
        assert len(map_steps) == 1
        assert map_steps[0].over == "dag_layers"

    def test_standard_pipeline_has_audit_agent(self, pipeline: PipelineDefinition) -> None:
        agent_steps = [s for s in pipeline.steps if s.type == StepType.AGENT]
        assert len(agent_steps) == 1
        assert agent_steps[0].agent == "auditor"

    def test_standard_pipeline_dependency_chain_is_linear(self, pipeline: PipelineDefinition) -> None:
        """Each step depends on exactly the previous step (linear chain)."""
        for i, step in enumerate(pipeline.steps):
            if i == 0:
                assert step.depends_on == []
            else:
                assert len(step.depends_on) == 1


class TestExpressPipeline:
    """Tests for config/pipelines/express.yaml."""

    @pytest.fixture
    def pipeline(self) -> PipelineDefinition:
        return load_pipeline("config/pipelines/express.yaml")

    def test_express_pipeline_name(self, pipeline: PipelineDefinition) -> None:
        assert pipeline.name == "express"

    def test_express_pipeline_has_four_steps(self, pipeline: PipelineDefinition) -> None:
        assert len(pipeline.steps) == 4

    def test_express_pipeline_has_no_hitl_gate(self, pipeline: PipelineDefinition) -> None:
        gate_steps = [s for s in pipeline.steps if s.type == StepType.HITL_GATE]
        assert len(gate_steps) == 0

    def test_express_pipeline_has_no_agent_steps(self, pipeline: PipelineDefinition) -> None:
        """Express pipeline has no LLM agent steps (auditor is skipped)."""
        agent_steps = [s for s in pipeline.steps if s.type == StepType.AGENT]
        assert len(agent_steps) == 0

    def test_express_pipeline_exports_csv_only(self, pipeline: PipelineDefinition) -> None:
        export_step = next(s for s in pipeline.steps if s.id == "export")
        formats = export_step.config.get("formats", [])
        assert formats == ["csv"]


class TestEnterprisePipeline:
    """Tests for config/pipelines/enterprise.yaml."""

    @pytest.fixture
    def pipeline(self) -> PipelineDefinition:
        return load_pipeline("config/pipelines/enterprise.yaml")

    def test_enterprise_pipeline_name(self, pipeline: PipelineDefinition) -> None:
        assert pipeline.name == "enterprise"

    def test_enterprise_pipeline_has_eight_steps(self, pipeline: PipelineDefinition) -> None:
        assert len(pipeline.steps) == 8

    def test_enterprise_pipeline_has_three_hitl_gates(self, pipeline: PipelineDefinition) -> None:
        gate_steps = [s for s in pipeline.steps if s.type == StepType.HITL_GATE]
        assert len(gate_steps) == 3
        gate_ids = {s.id for s in gate_steps}
        assert gate_ids == {"spec_approval", "variable_review", "final_signoff"}

    def test_enterprise_pipeline_gates_have_messages(self, pipeline: PipelineDefinition) -> None:
        gate_steps = [s for s in pipeline.steps if s.type == StepType.HITL_GATE]
        for gate in gate_steps:
            assert "message" in gate.config, f"Gate '{gate.id}' missing 'message' in config"
            assert len(str(gate.config["message"])) > 10, f"Gate '{gate.id}' message too short"

    def test_enterprise_pipeline_exports_both_formats(self, pipeline: PipelineDefinition) -> None:
        export_step = next(s for s in pipeline.steps if s.id == "export")
        formats = export_step.config.get("formats", [])
        assert "csv" in formats  # type: ignore[operator]
        assert "parquet" in formats  # type: ignore[operator]


class TestAllPipelinesValid:
    """Cross-cutting tests for all pipeline configs."""

    @pytest.fixture(params=["clinical_derivation", "express", "enterprise"])
    def pipeline(self, request: pytest.FixtureRequest) -> PipelineDefinition:
        return load_pipeline(f"config/pipelines/{request.param}.yaml")

    def test_all_pipelines_have_parse_spec_first(self, pipeline: PipelineDefinition) -> None:
        """Every pipeline starts with parse_spec."""
        first = pipeline.steps[0]
        assert first.id == "parse_spec"
        assert first.depends_on == []

    def test_all_pipelines_end_with_export(self, pipeline: PipelineDefinition) -> None:
        """Every pipeline ends with export."""
        last = pipeline.steps[-1]
        assert last.id == "export"

    def test_all_pipeline_step_ids_are_unique(self, pipeline: PipelineDefinition) -> None:
        """No duplicate step IDs."""
        ids = [s.id for s in pipeline.steps]
        assert len(ids) == len(set(ids)), f"Duplicate step IDs in {pipeline.name}"

    def test_all_pipeline_dependencies_reference_existing_steps(self, pipeline: PipelineDefinition) -> None:
        """Every depends_on reference points to an existing step ID."""
        valid_ids = {s.id for s in pipeline.steps}
        for step in pipeline.steps:
            for dep in step.depends_on:
                assert dep in valid_ids, f"Step '{step.id}' depends on unknown '{dep}' in {pipeline.name}"
```

**Constraints:**
- Use `pytest` class grouping for organization (one class per scenario + one cross-cutting)
- Use `@pytest.fixture(params=...)` for parameterized cross-cutting tests
- Every test has `# Arrange`, `# Act`, `# Assert` or single-line assertions
- Test names: `test_<pipeline>_<aspect>`
- `pytest.raises` with `match=` whenever used
- No mocking — these tests validate real YAML files on disk

**Reference:** `tests/unit/test_spec_parser.py` for YAML validation test pattern

---

### 4. `tests/unit/test_pipeline_integration.py` (NEW)

**Purpose:** Integration test that runs the pipeline interpreter with the builtin steps (no LLM calls) to verify the interpreter + executors + context flow works end-to-end.

**Tests to write:**

```python
"""Integration tests for the pipeline interpreter — validates step execution flow."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.audit.trail import AuditTrail
from src.domain.exceptions import CDDEError
from src.domain.pipeline_models import PipelineDefinition, StepDefinition, StepType, load_pipeline
from src.engine.pipeline_context import PipelineContext
from src.engine.pipeline_interpreter import PipelineInterpreter


@pytest.fixture
def base_ctx(tmp_path: Path) -> PipelineContext:
    """Minimal context for integration tests."""
    return PipelineContext(
        workflow_id="integ-test",
        audit_trail=AuditTrail("integ-test"),
        llm_base_url="http://localhost:8650/v1",
        output_dir=tmp_path / "output",
    )


async def test_interpreter_runs_builtin_only_pipeline(base_ctx: PipelineContext, sample_spec_path: Path) -> None:
    """A pipeline with only builtin steps runs without errors."""
    # Arrange — seed spec path into context
    base_ctx.step_outputs["_init"] = {"spec_path": sample_spec_path}
    pipeline = PipelineDefinition(
        name="test",
        steps=[
            StepDefinition(id="parse_spec", type=StepType.BUILTIN, builtin="parse_spec"),
            StepDefinition(id="build_dag", type=StepType.BUILTIN, builtin="build_dag", depends_on=["parse_spec"]),
        ],
    )
    interpreter = PipelineInterpreter(pipeline, base_ctx)

    # Act
    await interpreter.run()

    # Assert
    assert base_ctx.spec is not None
    assert base_ctx.dag is not None
    assert base_ctx.derived_df is not None
    assert len(base_ctx.dag.execution_order) > 0


async def test_interpreter_stops_on_step_error(base_ctx: PipelineContext) -> None:
    """If a step fails, interpreter raises CDDEError and stops."""
    # Arrange — parse_spec without seeded spec_path will fail
    pipeline = PipelineDefinition(
        name="test_fail",
        steps=[
            StepDefinition(id="parse_spec", type=StepType.BUILTIN, builtin="parse_spec"),
        ],
    )
    interpreter = PipelineInterpreter(pipeline, base_ctx)

    # Act & Assert
    with pytest.raises(CDDEError, match="Step 'parse_spec' failed"):
        await interpreter.run()


async def test_interpreter_tracks_current_step(base_ctx: PipelineContext, sample_spec_path: Path) -> None:
    """current_step property reflects the running step."""
    # Arrange
    base_ctx.step_outputs["_init"] = {"spec_path": sample_spec_path}
    pipeline = PipelineDefinition(
        name="test_tracking",
        steps=[
            StepDefinition(id="parse_spec", type=StepType.BUILTIN, builtin="parse_spec"),
        ],
    )
    interpreter = PipelineInterpreter(pipeline, base_ctx)

    # Assert before
    assert interpreter.current_step is None

    # Act
    await interpreter.run()

    # Assert after
    assert interpreter.current_step is None  # finished


async def test_interpreter_export_creates_files(base_ctx: PipelineContext, sample_spec_path: Path) -> None:
    """Export step creates CSV file in output directory."""
    # Arrange
    base_ctx.step_outputs["_init"] = {"spec_path": sample_spec_path}
    pipeline = PipelineDefinition(
        name="test_export",
        steps=[
            StepDefinition(id="parse_spec", type=StepType.BUILTIN, builtin="parse_spec"),
            StepDefinition(id="export", type=StepType.BUILTIN, builtin="export_adam", depends_on=["parse_spec"],
                           config={"formats": ["csv"]}),
        ],
    )
    interpreter = PipelineInterpreter(pipeline, base_ctx)

    # Act
    await interpreter.run()

    # Assert
    assert base_ctx.output_dir is not None
    csv_path = base_ctx.output_dir / "integ-test_adam.csv"
    assert csv_path.exists()
```

**Constraints:**
- Use `sample_spec_path` fixture from `tests/conftest.py` (already exists — creates temp YAML + CSV)
- Integration tests are async (executors are async)
- Tests do NOT call any LLM agents — only builtin steps
- `pytest.raises(CDDEError, match="...")` for error cases
- Each test creates its own `PipelineDefinition` programmatically (not from YAML files) for isolation
- `base_ctx` fixture uses `tmp_path` for output directory

**Reference:** `tests/integration/test_workflow.py` for integration test patterns with fixtures

---

## After Implementation

1. Run: `uv run ruff check . --fix && uv run ruff format .`
2. Run: `uv run pyright .`
3. Run: `uv run pytest tests/unit/test_pipeline_scenarios.py tests/unit/test_pipeline_integration.py -v`
4. Run: `uv run pytest` — full suite
5. Count total tests: should be ~210+ (189 existing + ~20 new)
