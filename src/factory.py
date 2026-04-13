"""Factory for creating a fully-wired pipeline interpreter instance."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from src.audit.trail import AuditTrail
from src.config.settings import get_settings
from src.domain.pipeline_models import load_pipeline
from src.engine.pipeline_context import PipelineContext
from src.engine.pipeline_fsm import PipelineFSM
from src.engine.pipeline_interpreter import PipelineInterpreter
from src.persistence.database import init_db

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession


async def create_pipeline_orchestrator(
    spec_path: str | Path,
    pipeline_path: str | Path | None = None,
    llm_base_url: str | None = None,
    output_dir: Path | None = None,
    database_url: str | None = None,
) -> tuple[PipelineInterpreter, PipelineContext, PipelineFSM, AsyncSession]:
    """Create a pipeline interpreter with persistence wired up.

    Returns (interpreter, context, fsm, session). Caller must commit/close the session.
    """
    from pathlib import Path as _Path

    settings = get_settings()
    url = database_url or settings.database_url
    session_factory = await init_db(url)
    session = session_factory()

    resolved_pipeline_path = pipeline_path if pipeline_path is not None else settings.default_pipeline
    pipeline = load_pipeline(resolved_pipeline_path)
    wf_id = uuid4().hex[:8]

    ctx = PipelineContext(
        workflow_id=wf_id,
        audit_trail=AuditTrail(wf_id),
        llm_base_url=llm_base_url or settings.llm_base_url,
        output_dir=output_dir,
        session=session,
    )
    # Seed spec_path so the parse_spec builtin can locate the file
    ctx.step_outputs["_init"] = {"spec_path": _Path(spec_path)}

    fsm = PipelineFSM(wf_id, [s.id for s in pipeline.steps])
    interpreter = PipelineInterpreter(pipeline, ctx, fsm)
    return interpreter, ctx, fsm, session
