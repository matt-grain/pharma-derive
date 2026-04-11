"""Pipeline endpoint — serves the pipeline YAML definition as JSON."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.api.schemas import PipelineOut, PipelineStepOut
from src.config.settings import get_settings
from src.domain.pipeline_models import PipelineDefinition, load_pipeline

router = APIRouter(prefix="/api/v1", tags=["pipeline"])


@router.get("/pipeline", response_model=PipelineOut, status_code=200)
async def get_pipeline() -> PipelineOut:
    """Return the current pipeline definition for UI rendering."""
    try:
        pipeline = load_pipeline(get_settings().default_pipeline)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_pipeline_out(pipeline)


def _to_pipeline_out(pipeline: PipelineDefinition) -> PipelineOut:
    """Convert domain PipelineDefinition to API response schema."""
    return PipelineOut(
        name=pipeline.name,
        version=pipeline.version,
        description=pipeline.description,
        steps=[
            PipelineStepOut(
                id=s.id,
                type=s.type.value,
                description=s.description,
                agent=s.agent,
                agents=s.agents,
                builtin=s.builtin,
                depends_on=s.depends_on,
                config=s.config,
                has_sub_steps=s.sub_steps is not None and len(s.sub_steps) > 0,
            )
            for s in pipeline.steps
        ],
    )
