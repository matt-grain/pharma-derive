# Implementation Plan — Phase 13.1: Data Preview API + Parquet Export

**Date:** 2026-04-11
**Feature:** F07 — ADaM Data Output (backend)
**Agent:** `python-fastapi`
**Dependencies:** None (builds on existing endpoints in `src/api/routers/workflows.py`)

---

## Context for Subagent

This project is a Clinical Data Derivation Engine (CDDE). Workflows derive ADaM datasets from SDTM source data. After a workflow completes, the derived ADaM CSV is saved to `output/{workflow_id}_adam.csv`. There is already a `GET /api/v1/workflows/{id}/adam` endpoint that returns the CSV as a FileResponse.

**What's missing:**
1. A data preview endpoint returning column metadata + sample rows (for both SDTM source and ADaM derived)
2. Parquet export alongside CSV
3. Format selection on the download endpoint

**Key files to read first:**
- `src/api/schemas.py` — existing API schemas (follow the same frozen BaseModel pattern)
- `src/api/routers/workflows.py` — existing endpoints (follow the same pattern for new endpoint)
- `src/engine/orchestrator.py:138-150` — `_export_adam()` method to enhance
- `src/domain/source_loader.py` — how source data is loaded
- `src/api/workflow_manager.py` — how orchestrators and historic workflows are accessed
- `src/config/settings.py` — `output_dir` setting

---

## Files to Modify

### 1. `src/api/schemas.py` (MODIFY)

**Change:** Add 3 new schema classes for data preview responses.

**Add after `DAGNodeOut` class (line ~65):**

```python
class ColumnInfo(BaseModel, frozen=True):
    """Column metadata for data preview."""
    name: str
    dtype: str
    null_count: int
    sample_values: list[str | int | float | None]


class DatasetPreview(BaseModel, frozen=True):
    """Preview of a single dataset (source or derived)."""
    label: str
    row_count: int
    column_count: int
    columns: list[ColumnInfo]
    rows: list[dict[str, str | int | float | None]]


class DataPreviewResponse(BaseModel, frozen=True):
    """Response for the data preview endpoint — source + derived side-by-side."""
    workflow_id: str
    source: DatasetPreview | None = None
    derived: DatasetPreview | None = None
    derived_formats: list[str] = []
```

**Constraints:**
- Use `frozen=True` on all schemas (matches existing pattern)
- `sample_values` contains up to 5 non-null values per column (for the column info card)
- `rows` contains the first N rows as dicts (default 50, controlled by query param)
- `derived_formats` lists available download formats: `["csv"]` or `["csv", "parquet"]`

---

### 2. `src/engine/orchestrator.py` (MODIFY)

**Change:** In `_export_adam()`, also save Parquet format alongside CSV.

**Current code (lines 138-150):**
```python
def _export_adam(self, output_dir: Path) -> None:
    if self._state.derived_df is None:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{self._state.workflow_id}_adam.csv"
    self._state.derived_df.to_csv(csv_path, index=False)
    logger.info(...)
```

**Replace with:**
```python
def _export_adam(self, output_dir: Path) -> None:
    """Save the derived DataFrame as CSV and Parquet for downstream consumption."""
    if self._state.derived_df is None:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{self._state.workflow_id}_adam.csv"
    self._state.derived_df.to_csv(csv_path, index=False)

    parquet_path = output_dir / f"{self._state.workflow_id}_adam.parquet"
    self._state.derived_df.to_parquet(parquet_path, index=False, engine="pyarrow")

    logger.info(
        "ADaM output saved to {csv} and {parquet} ({rows} rows, {cols} columns)",
        csv=csv_path,
        parquet=parquet_path,
        rows=len(self._state.derived_df),
        cols=len(self._state.derived_df.columns),
    )
```

**Constraints:**
- Use `engine="pyarrow"` — pyarrow is already a transitive dependency of pandas
- Verify pyarrow is available by checking: `uv run python -c "import pyarrow"`. If not, run `uv add pyarrow`
- Keep the existing CSV export — Parquet is additive

---

### 3. `src/api/routers/workflows.py` (MODIFY)

**Change 1:** Add a new `GET /{workflow_id}/data` endpoint for data preview.

**Add after the `download_adam` endpoint (after line 178):**

```python
@router.get("/{workflow_id}/data", response_model=DataPreviewResponse, status_code=200)
async def get_workflow_data(
    workflow_id: str,
    manager: WorkflowManagerDep,
    limit: int = 50,
) -> DataPreviewResponse:
    """Return column metadata and sample rows for source SDTM and derived ADaM data."""
```

**Implementation logic:**
1. Check if workflow exists (via `manager.get_orchestrator()` or `manager.is_known()`)
2. Load derived ADaM data:
   - First try: read from `output/{workflow_id}_adam.csv` via `pd.read_csv()`
   - Build `DatasetPreview` with label `"ADaM (Derived)"`, row_count, column_count, columns (with dtype, null_count, sample_values), and first `limit` rows as dicts
3. Load source SDTM data:
   - Try to get the spec from the in-memory orchestrator (`orch.state.spec`) or from the persisted state
   - If spec is available, use `load_source_data(spec)` to get the source DataFrame
   - Build `DatasetPreview` with label `"SDTM (Source)"`, same structure
   - If spec is not available (historic workflow without persisted spec), set `source=None`
4. Determine `derived_formats`: check which files exist (`_adam.csv`, `_adam.parquet`) in output dir
5. Return `DataPreviewResponse`

**Helper function to extract** (add as module-level helper near `_dag_node_out`):

```python
def _build_dataset_preview(
    df: pd.DataFrame,
    label: str,
    limit: int,
) -> DatasetPreview:
    """Build a DatasetPreview from a pandas DataFrame."""
    columns = []
    for col in df.columns:
        non_null = df[col].dropna()
        samples = non_null.head(5).tolist()
        columns.append(
            ColumnInfo(
                name=str(col),
                dtype=str(df[col].dtype),
                null_count=int(df[col].isna().sum()),
                sample_values=samples,
            )
        )
    rows_data = df.head(limit).to_dict(orient="records")
    # Sanitize NaN → None for JSON serialization
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
```

**Imports to add at top of file:**
```python
import pandas as pd
from src.api.schemas import DataPreviewResponse, DatasetPreview, ColumnInfo
from src.domain.source_loader import load_source_data
```

**Note:** `pd` import is used at runtime (reading CSV files), so it must NOT go in `TYPE_CHECKING` block.

**Change 2:** Enhance `download_adam` to support format query param.

**Replace current endpoint (lines 172-178):**
```python
@router.get("/{workflow_id}/adam", response_class=FileResponse, status_code=200)
async def download_adam(
    workflow_id: str,
    format: str = "csv",
) -> FileResponse:
    """Download the derived ADaM file in CSV or Parquet format."""
    settings = get_settings()
    if format == "parquet":
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
            detail=f"ADaM file not found for workflow {workflow_id!r} (format={format})",
        )
    return FileResponse(adam_path, media_type=media_type, filename=filename)
```

**Constraints:**
- `format` query param defaults to `"csv"` for backward compatibility
- Only `"csv"` and `"parquet"` are valid — but since this is a simple 2-value param, a plain string with an if/else is fine (no enum overhead for a query param)
- The endpoint already has `response_class=FileResponse` — keep it

---

### 4. `tests/unit/test_api.py` (MODIFY)

**Change:** Add test cases for the new data preview endpoint and enhanced download endpoint.

**Reference pattern:** Follow existing tests in `tests/unit/test_api.py` — they use `httpx.AsyncClient` with the FastAPI `TestClient` pattern.

**Read the existing test file first** to understand the fixture setup (how `client` fixture is defined, how workflows are started in tests).

**Add these test functions:**

```python
async def test_get_data_preview_completed_workflow_returns_columns_and_rows(client: AsyncClient) -> None:
    """GET /data on a completed workflow returns source + derived preview."""
    # Arrange — create a small CSV in the output dir to simulate a completed workflow
    # (Follow the pattern used in test_download_adam if it exists, or create a temp CSV)

    # Act
    response = await client.get(f"/api/v1/workflows/{workflow_id}/data")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["workflow_id"] == workflow_id
    assert body["derived"] is not None
    assert body["derived"]["row_count"] > 0
    assert len(body["derived"]["columns"]) > 0
    assert "csv" in body["derived_formats"]


async def test_get_data_preview_unknown_workflow_returns_404(client: AsyncClient) -> None:
    """GET /data on unknown workflow returns 404."""
    # Act
    response = await client.get("/api/v1/workflows/nonexistent/data")

    # Assert
    assert response.status_code == 404


async def test_download_adam_parquet_format_returns_file(client: AsyncClient) -> None:
    """GET /adam?format=parquet returns parquet file when it exists."""
    # Arrange — create a temp parquet file in output dir

    # Act
    response = await client.get(f"/api/v1/workflows/{workflow_id}/adam?format=parquet")

    # Assert
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"


async def test_download_adam_default_csv_format(client: AsyncClient) -> None:
    """GET /adam without format param returns CSV (backward compatible)."""
    # Arrange — ensure CSV exists in output dir

    # Act
    response = await client.get(f"/api/v1/workflows/{workflow_id}/adam")

    # Assert
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
```

**Fixture strategy:**
- For data preview tests, you need a CSV file in the output directory. Use `tmp_path` fixture or mock `get_settings().output_dir` to point to a temp dir, then write a small DataFrame to CSV/Parquet.
- Read the existing test fixtures in `tests/unit/test_api.py` and `tests/conftest.py` to understand the current approach for mocking the workflow manager.
- The workflow manager mock needs to return `is_known(workflow_id) = True` for these tests.

**Constraints:**
- Test names follow `test_<action>_<scenario>_<expected>` pattern
- Each test has `# Arrange`, `# Act`, `# Assert` comments
- No `pytest.raises(Exception)` — use specific exception types
- Add `match=` to any `pytest.raises` calls

---

## Dependency Check

Before implementing, verify pyarrow is available:
```bash
uv run python -c "import pyarrow; print(pyarrow.__version__)"
```

If it fails, add it:
```bash
uv add pyarrow
```

---

## After Implementation

1. Run: `uv run ruff check . --fix && uv run ruff format .`
2. Run: `uv run pyright .`
3. Run: `uv run pytest tests/unit/test_api.py -v`
4. Run: `uv run pytest` (full suite — ensure no regressions)
5. Verify the new endpoint works manually if possible: start the server and call `GET /api/v1/workflows/<id>/data`
