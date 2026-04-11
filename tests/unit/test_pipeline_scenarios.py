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
