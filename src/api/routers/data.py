"""Data endpoints — preview and download derived ADaM datasets."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from src.api.dependencies import (
    WorkflowManagerDep,  # noqa: TC001 — FastAPI resolves Annotated[Depends] at runtime
)
from src.api.schemas import (
    ColumnInfo,
    DataPreviewResponse,
    DatasetPreview,
)
from src.config.settings import get_settings
from src.domain.source_loader import load_source_data

router = APIRouter(prefix="/api/v1/workflows", tags=["data"])


@router.get("/{workflow_id}/adam", response_class=FileResponse, status_code=200)
async def download_adam(
    workflow_id: str,
    fmt: str = Query(default="csv", alias="format"),
) -> FileResponse:
    """Download the derived ADaM file in CSV or Parquet format."""
    settings = get_settings()
    if fmt == "parquet":
        adam_path = Path(settings.output_dir) / f"{workflow_id}_adam.parquet"
        media_type = "application/octet-stream"
        filename = f"{workflow_id}_adam.parquet"
    else:
        adam_path = Path(settings.output_dir) / f"{workflow_id}_adam.csv"
        media_type = "text/csv"
        filename = f"{workflow_id}_adam.csv"

    if not adam_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"ADaM file not found for workflow {workflow_id!r} (format={fmt})",
        )
    return FileResponse(adam_path, media_type=media_type, filename=filename)


@router.get("/{workflow_id}/data", response_model=DataPreviewResponse, status_code=200)
async def get_workflow_data(
    workflow_id: str,
    manager: WorkflowManagerDep,
    limit: int = 50,
) -> DataPreviewResponse:
    """Return column metadata and sample rows for source SDTM and derived ADaM data."""
    if not manager.is_known(workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")

    output_dir = Path(get_settings().output_dir)
    derived_formats = _detect_formats(output_dir, workflow_id)
    derived = _load_derived(output_dir, workflow_id, limit)
    source = _load_source(manager, workflow_id, limit)

    return DataPreviewResponse(
        workflow_id=workflow_id,
        source=source,
        derived=derived,
        derived_formats=derived_formats,
    )


def _detect_formats(output_dir: Path, workflow_id: str) -> list[str]:
    """Check which export formats are available on disk."""
    formats: list[str] = []
    if (output_dir / f"{workflow_id}_adam.csv").exists():
        formats.append("csv")
    if (output_dir / f"{workflow_id}_adam.parquet").exists():
        formats.append("parquet")
    return formats


def _load_derived(output_dir: Path, workflow_id: str, limit: int) -> DatasetPreview | None:
    """Load derived ADaM CSV into a preview, or None if not available."""
    csv_path = output_dir / f"{workflow_id}_adam.csv"
    if not csv_path.exists():
        return None
    return _build_dataset_preview(pd.read_csv(csv_path), "ADaM (Derived)", limit)


def _load_source(manager: WorkflowManagerDep, workflow_id: str, limit: int) -> DatasetPreview | None:
    """Load source SDTM data from the in-memory orchestrator spec."""
    orch = manager.get_orchestrator(workflow_id)
    spec = orch.state.spec if orch is not None else None
    if spec is None:
        return None
    try:
        return _build_dataset_preview(load_source_data(spec), "SDTM (Source)", limit)
    except FileNotFoundError:
        return None


def _build_dataset_preview(df: pd.DataFrame, label: str, limit: int) -> DatasetPreview:
    """Build a DatasetPreview from a pandas DataFrame."""
    columns: list[ColumnInfo] = []
    for col in df.columns:
        non_null = df[col].dropna()
        samples: list[str | int | float | None] = non_null.head(5).tolist()
        columns.append(
            ColumnInfo(
                name=str(col),
                dtype=str(df[col].dtype),
                null_count=int(df[col].isna().sum()),
                sample_values=samples,
            )
        )
    rows_data = df.head(limit).to_dict(orient="records")
    rows_clean: list[dict[str, str | int | float | None]] = [
        {k: (None if pd.isna(v) else v) for k, v in row.items()}  # type: ignore[arg-type]
        for row in rows_data
    ]
    return DatasetPreview(
        label=label,
        row_count=len(df),
        column_count=len(df.columns),
        columns=columns,
        rows=rows_clean,
    )
