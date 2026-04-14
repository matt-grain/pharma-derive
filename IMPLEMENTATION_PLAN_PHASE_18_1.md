# Phase 18.1 — Bug #6: Persist SDTM Source Snapshot

**Date:** 2026-04-14
**Branch:** `feat/yaml-pipeline` (from HEAD `7ff3c54`)
**Agent:** `python-fastapi` (single-agent dispatch — all changes are Python backend + test)
**Source of bug:** `BUGS.md` → Bug #6 "Data tab loses SDTM source panel after backend restart"
**Estimated cost:** 30–45 min implementation + test + `/check` gate.

---

## Goal

Close Bug #6 so that the Data tab's **SDTM (Source)** panel remains populated after an unrelated backend restart, for any workflow that reached `parse_spec` before the restart.

**Acceptance criteria (manual):**
1. Start a workflow on `simple_mock.yaml`, let it reach `derive_variables` (or `human_review`).
2. Kill the backend (`Ctrl+C` or `uvicorn --reload` swap), restart it.
3. Open the Data tab for the pre-restart workflow.
4. Both the **SDTM (Source)** and **ADaM (Derived)** panels render with rows.

Today, step 4 shows only the ADaM panel.

---

## Root cause recap (from BUGS.md #6 + Phase 17 memory)

- `src/api/routers/data.py::_load_source()` calls `manager.get_context(workflow_id)`, which only returns the live `PipelineContext` from `WorkflowManager._contexts`.
- `WorkflowManager.load_history()` rehydrates pre-restart workflows into `self._history` (a separate dict), **not** into `self._contexts`. See `src/api/workflow_manager.py:54` (load_history) and `:142-143` (get_context: `return self._contexts.get(workflow_id)`).
- Therefore, after a restart, `get_context(wf_id)` → `None`, `_load_source` short-circuits (`spec is None → return None`), and the router returns `DataPreviewResponse(source=None, derived=<still-valid>)`.
- The derived panel keeps working because `_load_derived()` reads from `output_dir/{wf_id}_adam.csv` on disk — the ADaM file survives restarts.
- The source panel has no disk backing today — SDTM data is reconstructed on-the-fly from `ctx.spec` via `load_source_data(spec)`, and `ctx.spec` is in-memory only.

**How Matt reproduces it:** Phase 16 testing restarted the backend multiple times; workflows `bfdb3536`, `290eda64`, `c7329784`, `47f0f061`, `c208a8c2` all show the empty SDTM panel after reload.

---

## Chosen approach — Option 1 (persisted SDTM snapshot)

1. **At `parse_spec` time**, after `load_source_data(spec)` returns the source DataFrame, write it to disk as `{ctx.output_dir}/{ctx.workflow_id}_source.csv`. This is a side-effect of the builtin, symmetric with how `export_adam` writes `{wf_id}_adam.csv`.
2. **In the `_load_source` data-router helper**, check disk first:
   - If `{output_dir}/{workflow_id}_source.csv` exists → read it and return a preview.
   - Otherwise fall back to the existing in-memory `ctx.spec` + `load_source_data` path (handles the narrow window between workflow creation and the `parse_spec` step completing, and keeps dev-mode unit tests working if `output_dir` is unset).
   - Return `None` only when both paths fail.

**Why Option 1 (vs. Option 2 "re-read `ctx.spec.source.path`" or Option 3 "keep ctx in `_history`"):**

| Criterion | Option 1 (snapshot) | Option 2 (re-read source) | Option 3 (retain ctx) |
|---|---|---|---|
| Survives backend restart | ✅ | ⚠ only if source file unchanged | ❌ restart drops in-memory state |
| Symmetric with ADaM persist | ✅ same disk pattern | ❌ | ❌ |
| Regulatory-friendly (snapshot = reproducibility) | ✅ freezes the input | ❌ source can drift | ❌ |
| New persistence layer needed | no (extend `output_dir`) | no | yes (rehydrate ctx from DB) |
| Estimated effort | 30–45 min | 30 min | 2–3 hours |

Option 1 is cheapest AND closest to a production pattern (data snapshotting for reproducibility is a standard regulatory practice in pharma).

---

## Architectural constraints the implementation must respect

1. **Layered architecture.** `src/engine/step_builtins.py` touches `ctx.output_dir` directly (already does for `export_adam`). `src/api/routers/data.py` reads from disk via `pd.read_csv` (already does for `_load_derived`). No new imports across layers.
2. **File-size hooks.** The only enforced limit is `FILE_LINE_LIMIT = 300` in `tools/pre_commit_checks/check_file_length.py:16`. `step_builtins.py` is at **244/300 lines** today and will be ~247 after. `data.py` is at **127/300** and will be ~137 after. Both comfortably under the 300-line hard limit. The 200-line "soft limit" from the global style rules is NOT a pre-commit hook — no enforcement risk.
3. **Function-length hook.** The enforced limit is `FUNCTION_LINE_LIMIT = 40` (same file, line 17) — NOT 30. `_builtin_parse_spec` goes from 14 → ~19 lines, `_load_source` goes from 9 → ~20 lines. Both well under 40. If a subagent mis-remembers "30" from the global style rules, remind them the pre-push hook is 40.
4. **Class-length hook.** `CLASS_LINE_LIMIT = 230` (same file, line 18) — irrelevant for this phase, no class modifications.
5. **No raw SQL in engine.** This fix touches zero SQL. Safe.
6. **Typing discipline.** Both modified functions already have full type annotations. Continue using `Path` from `ctx.output_dir` (already `Path | None`).
7. **Exception handling.** The disk read branch in `_load_source` may raise `FileNotFoundError` (file was deleted between `.exists()` check and `read_csv`) or `pd.errors.ParserError` / `pd.errors.EmptyDataError` / `ValueError` (corrupt or unparseable snapshot). Catch the specific exception tuple, log at `WARNING` via loguru, and fall through to the in-memory fallback — never bare `except`, never `except Exception`.
8. **Logging.** `_builtin_parse_spec` should log at INFO when the snapshot is written (`logger.info("Wrote SDTM snapshot", path=..., rows=...)`) so operators can confirm it landed. `_load_source` should log at WARNING only on the error-fallback branch (not on happy-path disk reads).
9. **Enum discipline.** No new enums. This fix touches zero status fields.
10. **Import contracts.** No new `.importlinter` `ignore_imports` entries needed. `uv run lint-imports` should be clean (unchanged) — do NOT add exceptions preemptively; if it fails, the fix is wrong, not the contract.
11. **Test coverage rule.** Every new source edge adds a test in the same commit — two new tests for `parse_spec`, one new test for the data router, one new test (or assertion addition) for `delete_workflow`.

---

## Files — explicit list

### NEW files
None. All changes land in existing files.

### MODIFIED files

| # | Absolute path | Lines delta (approx) | Purpose |
|---|---|---|---|
| 1 | `src/engine/step_builtins.py` | +6 / -0 | Write source snapshot to disk in `_builtin_parse_spec` |
| 2 | `src/api/routers/data.py` | +11 / -1 | `_load_source` reads disk snapshot first, falls back to ctx path |
| 3 | `src/api/workflow_manager.py` | +1 / -1 | `delete_workflow` also removes the `_source.csv` snapshot |
| 4 | `tests/unit/test_step_builtins.py` | +30 / -0 | Two new tests for the snapshot write path |
| 5 | `tests/unit/test_api.py` | +45 / -0 | One new integration test for the post-restart disk-read path |

All paths are relative to the repo root `C:/Projects/Interviews/jobs/Sanofi-AI-ML-Lead/homework/`.

### DELETED files
None.

### Reference files (read-only, for subagent context — do NOT modify)

| Path | Why it matters |
|---|---|
| `src/engine/pipeline_context.py:33` | Confirms `output_dir: Path \| None = None` field exists — no schema change needed |
| `src/api/workflow_manager.py:46` (`_contexts`) + `:50` (`_history`) + `:54-58` (`load_history`) + `:142-143` (`get_context`) + `:174-176` (`is_known`) | Documents the `_history` vs `_contexts` split this fix works around |
| `src/api/workflow_manager.py:37` | `_HistoricState = HistoricState` — **module-level alias**, NOT a dataclass. The real class lives in `src/api/workflow_serializer.py:15-32` |
| `src/api/workflow_serializer.py:15-32` | `HistoricState.__init__(self, workflow_id: str, fsm_state: str, state_json: str)` — `state_json` **MUST be a valid JSON string**, parsed via `json.loads()` at line 19. Fields are populated via `.get(key, default)` so `"{}"` is a safe minimal input |
| `src/api/routers/data.py:59` | Pattern: `output_dir = Path(get_settings().output_dir)` — called directly (NOT via `Depends()`). This is WHY tests must use `patch("src.api.routers.data.get_settings")`, not `dependency_overrides` |
| `frontend/src/components/DataTab.tsx:195` | Consumer: `{data.source != null && <DatasetPanel dataset={data.source} />}` — NO frontend change needed |
| `src/domain/source_loader.py` | `load_source_data(spec)` — the existing function whose output we snapshot |
| `tools/pre_commit_checks/check_file_length.py:16-18` | `FILE_LINE_LIMIT=300`, `FUNCTION_LINE_LIMIT=40`, `CLASS_LINE_LIMIT=230` — authoritative hook values |

---

## Per-file specifications

### (1) `src/engine/step_builtins.py` — MODIFY

**Purpose:** Write a disk snapshot of the loaded SDTM DataFrame to `{ctx.output_dir}/{ctx.workflow_id}_source.csv` immediately after `load_source_data(spec)` returns, so the Data tab can rebuild the SDTM panel after a backend restart.

**Exact change (in function `_builtin_parse_spec`):**

Current body (lines 21–35):
```python
async def _builtin_parse_spec(step: StepDefinition, ctx: PipelineContext) -> None:
    """Parse spec, load source data, generate synthetic CSV — mirrors orchestrator._step_spec_review."""
    from src.domain.source_loader import get_column_domain_map, load_source_data
    from src.domain.spec_parser import parse_spec
    from src.domain.synthetic import generate_synthetic

    spec_path = ctx.step_outputs.get("_init", {}).get("spec_path")
    if spec_path is None:
        msg = f"Step '{step.id}' requires '_init.spec_path' in context"
        raise ValueError(msg)
    ctx.spec = parse_spec(spec_path)
    source_df = load_source_data(ctx.spec)
    ctx.derived_df = source_df.copy()
    ctx.synthetic_csv = generate_synthetic(source_df, rows=ctx.spec.synthetic.rows).to_csv(index=False)
    ctx.source_column_domains = get_column_domain_map(ctx.spec)
```

Target body — insert a snapshot write between `source_df = load_source_data(ctx.spec)` and `ctx.derived_df = source_df.copy()`:

```python
async def _builtin_parse_spec(step: StepDefinition, ctx: PipelineContext) -> None:
    """Parse spec, load source data, write SDTM snapshot, generate synthetic CSV."""
    from loguru import logger

    from src.domain.source_loader import get_column_domain_map, load_source_data
    from src.domain.spec_parser import parse_spec
    from src.domain.synthetic import generate_synthetic

    spec_path = ctx.step_outputs.get("_init", {}).get("spec_path")
    if spec_path is None:
        msg = f"Step '{step.id}' requires '_init.spec_path' in context"
        raise ValueError(msg)
    ctx.spec = parse_spec(spec_path)
    source_df = load_source_data(ctx.spec)
    if ctx.output_dir is not None:
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = ctx.output_dir / f"{ctx.workflow_id}_source.csv"
        source_df.to_csv(snapshot_path, index=False)
        logger.info("Wrote SDTM snapshot", path=str(snapshot_path), rows=len(source_df))
    ctx.derived_df = source_df.copy()
    ctx.synthetic_csv = generate_synthetic(source_df, rows=ctx.spec.synthetic.rows).to_csv(index=False)
    ctx.source_column_domains = get_column_domain_map(ctx.spec)
```

**Constraints:**
- Function body stays at **~19 lines** (well under the **40-line** function hook limit — `FUNCTION_LINE_LIMIT=40` in `tools/pre_commit_checks/check_file_length.py:17`).
- File size goes from **244 → ~247** lines (comfortably under the 300 hard limit). No helper extraction required. If (unexpectedly) a hook objects, extract `_write_source_snapshot(ctx, source_df) -> None` as a module-level helper immediately above `_builtin_parse_spec` and call it from inside the builtin. Don't split the builtin into multiple functions otherwise.
- Use `logger.info("Wrote SDTM snapshot", path=..., rows=...)` — structured fields, NOT an f-string — per the project's logging-instrumentation rule.
- The snapshot write is a **no-op** when `ctx.output_dir is None`. This mirrors `_builtin_export_adam`'s existing `if ctx.derived_df is None or ctx.output_dir is None: return` guard (line 51).
- `source_df.to_csv(..., index=False)` — never write the pandas index to disk. Same contract as `export_adam`.
- Do NOT change the function signature. Do NOT add new fields to `PipelineContext`. Do NOT introduce a new step — the snapshot is part of the existing `parse_spec` builtin.

**Reference:** `_builtin_export_adam` at lines 49–58 — identical pattern for `mkdir` + `to_csv(..., index=False)` on `ctx.output_dir`.

---

### (2) `src/api/routers/data.py` — MODIFY

**Purpose:** Change `_load_source` to read the persisted SDTM snapshot from disk before falling back to the in-memory `ctx.spec` reconstruction path. This is the fix that makes the Data tab's SDTM panel populated for historic/post-restart workflows.

**Exact change (in function `_load_source`):**

Current body (lines 90–99):
```python
def _load_source(manager: WorkflowManagerDep, workflow_id: str, limit: int) -> DatasetPreview | None:
    """Load source SDTM data from the pipeline context spec."""
    ctx = manager.get_context(workflow_id)
    spec = ctx.spec if ctx is not None else None
    if spec is None:
        return None
    try:
        return _build_dataset_preview(load_source_data(spec), "SDTM (Source)", limit)
    except FileNotFoundError:
        return None
```

Target body — try disk snapshot first, then fall back:
```python
def _load_source(manager: WorkflowManagerDep, workflow_id: str, limit: int) -> DatasetPreview | None:
    """Load source SDTM data, preferring the disk snapshot over in-memory reconstruction.

    Disk-first so historic workflows (loaded from _history after backend restart)
    still render the SDTM panel. Falls back to ctx.spec reconstruction only when
    the snapshot hasn't been written yet (very narrow window).
    """
    output_dir = Path(get_settings().output_dir)
    snapshot_path = output_dir / f"{workflow_id}_source.csv"
    if snapshot_path.exists():
        try:
            df = pd.read_csv(snapshot_path, low_memory=False)
        except (FileNotFoundError, pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as exc:
            from loguru import logger
            logger.warning("SDTM snapshot unreadable, falling back to ctx", path=str(snapshot_path), error=str(exc))
        else:
            return _build_dataset_preview(df, "SDTM (Source)", limit)

    ctx = manager.get_context(workflow_id)
    spec = ctx.spec if ctx is not None else None
    if spec is None:
        return None
    try:
        return _build_dataset_preview(load_source_data(spec), "SDTM (Source)", limit)
    except FileNotFoundError:
        return None
```

**Constraints:**
- Function body stays at **~20 lines** (under the **40-line** function hook limit — `FUNCTION_LINE_LIMIT=40`).
- Imports at the TOP of the file already cover `Path`, `pd`, `get_settings`. The only new import is `loguru.logger` inside the exception block (local import is fine because it's only needed on the error path — avoids pulling loguru into the module header for one call site; this matches the existing style at line 146 of `step_builtins.py` where `from loguru import logger` is inside `_builtin_compare_ground_truth`).
- **`get_settings()` is called DIRECTLY, not via `Depends()`**. This matches the existing pattern at `data.py:59` inside `get_workflow_data`. This is important for the test strategy — tests must use `patch("src.api.routers.data.get_settings")` and cannot use `app.dependency_overrides[get_settings]` because `dependency_overrides` only intercepts FastAPI-resolved `Depends()` chains, NOT direct module-level calls.
- **Race condition handling:** the `.exists()` check and `pd.read_csv()` are not atomic — a concurrent delete would raise `FileNotFoundError` despite the guard. The try/except catches this explicitly, which is why the `.exists()` check is a quick pre-filter and not a substitute for the try.
- Catch **only** `FileNotFoundError`, `pd.errors.ParserError`, `pd.errors.EmptyDataError`, and `ValueError`. Never `except Exception` — the project's exception-handling rule forbids it without re-raise or log. `ValueError` and `EmptyDataError` cover pandas' behaviour on malformed or empty CSVs. Any exception outside this tuple (e.g., `MemoryError`, `PermissionError`) should propagate — it indicates a system-level problem the caller needs to see.
- On parse failure, log at WARNING with structured fields (`path=`, `error=`) and fall through to the ctx fallback — DO NOT return None from the error branch. The fallback is the whole point of keeping the old code path intact.
- Variable named `df` at the disk-read site — matches the `_build_dataset_preview(pd.read_csv(csv_path, low_memory=False), "ADaM (Derived)", limit)` pattern at line 87 for `_load_derived`.
- **Do NOT modify `_load_derived`, `_detect_formats`, `_build_dataset_preview`, `download_adam`, or the router handler `get_workflow_data`**. The fix is local to `_load_source`.
- **Do NOT change `DataPreviewResponse`, `DatasetPreview`, or `ColumnInfo` schemas**. No frontend-facing wire changes.
- **Do NOT change the function signature**. Keep `(manager, workflow_id, limit)` — the existing call site at `data.py:62` passes exactly these three args.

**Reference:** `_load_derived` at lines 82–87 — identical disk-read pattern using `pd.read_csv(csv_path, low_memory=False)`.

---

### (3) `src/api/workflow_manager.py` — MODIFY (1 line + cleanup on delete)

**Purpose:** Ensure `delete_workflow` also removes the `{wf_id}_source.csv` snapshot from `output_dir` so deleted workflows don't leave orphan snapshot files.

**Exact change** in `delete_workflow` at `src/api/workflow_manager.py:229`:

Current:
```python
        output_dir = Path(get_settings().output_dir)
        for suffix in ("_audit.json", "_adam.csv", "_adam.parquet"):
            path = output_dir / f"{workflow_id}{suffix}"
            if path.exists():
                path.unlink()
```

Target:
```python
        output_dir = Path(get_settings().output_dir)
        for suffix in ("_audit.json", "_adam.csv", "_adam.parquet", "_source.csv"):
            path = output_dir / f"{workflow_id}{suffix}"
            if path.exists():
                path.unlink()
```

**Constraints:**
- Single-tuple-element addition. Nothing else in `delete_workflow` changes.
- The `delete_workflow` method already catches the case where any of these files is missing (`if path.exists()`), so the added entry is safe even for workflows created before this fix.
- Test coverage: add one assertion to the existing delete-workflow test if one exists, OR a new test `test_delete_workflow_removes_source_snapshot` in `tests/unit/test_api.py` that: creates a workflow with `manager._history[wf_id]`, writes a fake `{wf_id}_source.csv` to the output dir, calls `DELETE /api/v1/workflows/{wf_id}`, asserts the file is gone. Reuse the `patch("src.api.routers.data.get_settings")` pattern.

**Reference:** `delete_workflow` at `src/api/workflow_manager.py:212-232` — the full method is visible; only line 229 changes.

---

### (4) `tests/unit/test_step_builtins.py` — MODIFY (add 2 tests)

**Purpose:** Verify that `_builtin_parse_spec` writes the SDTM snapshot to disk when `output_dir` is set, and gracefully skips it when `output_dir` is None.

**Tests to add** (place after the existing `test_builtin_parse_spec_missing_spec_path_key_raises_value_error` at line 111, before the `build_dag` section at line 115):

```python
async def test_builtin_parse_spec_writes_source_snapshot_to_output_dir(
    sample_spec_path: Path,
    tmp_path: Path,
) -> None:
    """parse_spec writes {workflow_id}_source.csv to output_dir with the loaded source data."""
    # Arrange
    wf_id = "wf-snapshot-001"
    ctx = _make_ctx(workflow_id=wf_id, output_dir=tmp_path / "output")
    ctx.set_output("_init", "spec_path", str(sample_spec_path))
    step = _minimal_step("parse_spec")

    # Act
    await BUILTIN_REGISTRY["parse_spec"](step, ctx)

    # Assert — snapshot file exists with the same rows as derived_df
    snapshot_path = tmp_path / "output" / f"{wf_id}_source.csv"
    assert snapshot_path.exists(), f"Expected SDTM snapshot at {snapshot_path}"
    assert ctx.derived_df is not None  # type guard
    snapshot_df = pd.read_csv(snapshot_path)
    assert len(snapshot_df) == len(ctx.derived_df)
    assert list(snapshot_df.columns) == list(ctx.derived_df.columns)


async def test_builtin_parse_spec_skips_snapshot_when_output_dir_is_none(
    sample_spec_path: Path,
    tmp_path: Path,
) -> None:
    """parse_spec does not crash and writes no file when output_dir is None."""
    # Arrange
    ctx = _make_ctx(output_dir=None)  # output_dir unset
    ctx.set_output("_init", "spec_path", str(sample_spec_path))
    step = _minimal_step("parse_spec")

    # Act — must not raise
    await BUILTIN_REGISTRY["parse_spec"](step, ctx)

    # Assert — ctx is still populated normally, no stray CSVs in tmp_path
    assert ctx.spec is not None
    assert ctx.derived_df is not None
    assert list(tmp_path.glob("*_source.csv")) == []
```

**Constraints:**
- Use the existing `_make_ctx` helper at line 32 — **do not introduce a new helper**.
- Use the existing `sample_spec_path` fixture — it's already threaded through `test_builtin_parse_spec_populates_context` at line 75, so `conftest.py` already provides it.
- AAA markers (`# Arrange`, `# Act`, `# Assert`) in every test body — project convention per `.claude/rules/test-quality.md`.
- Test names follow `test_<action>_<scenario>_<expected>` — both names do.
- Import `pd` at the top of the file (already imported at line 12 as `import pandas as pd`).
- No mocking — these are pure-function tests against the real builtin.

**Reference:** `test_builtin_export_adam_creates_csv` at line 167 — same shape (tmp_path fixture, output_dir, glob for the file).

---

### (5) `tests/unit/test_api.py` — MODIFY (add 1 test)

**Purpose:** End-to-end integration test proving the data router correctly reads the disk snapshot when no live `PipelineContext` exists (post-restart scenario).

**Test to add** — place **after** the existing `test_get_data_preview_completed_workflow_returns_columns_and_rows` which runs from **line 144 to line 194** (grep for the exact end if line numbers have drifted from this plan's writing). Insert the new test between that test and `test_download_adam_default_csv_format` at line 197.

**Canonical pattern to mirror:** The existing test at lines 144–194 is the reference. Copy its structure verbatim:
- Uses `patch("src.api.routers.data.get_settings")` as a context manager (NOT `dependency_overrides`)
- Creates a **fresh** `WorkflowManager()`, populates `_history` BEFORE assignment, then assigns to `app.state.workflow_manager`
- Does NOT take the shared `client` fixture — because that fixture creates a vanilla manager with no `_history`
- Imports `_HistoricState` with `# type: ignore[attr-defined]`

**Test code to add:**

```python
async def test_get_data_preview_reads_source_snapshot_when_ctx_missing(
    tmp_path: Path,
) -> None:
    """GET /data returns source panel from disk snapshot when no in-memory ctx exists.

    Simulates the post-restart scenario: the workflow is known (in _history) but
    has no live PipelineContext in _contexts. The disk snapshot must be enough
    for the Data tab to render the SDTM panel.
    """
    # Arrange — write a fake source snapshot + adam file directly to disk
    workflow_id = "wf-post-restart"
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    source_df = pd.DataFrame(
        {
            "USUBJID": ["SUBJ-001", "SUBJ-002", "SUBJ-003"],
            "AGE": [45, 72, 18],
            "SEX": ["M", "F", "F"],
        }
    )
    source_df.to_csv(output_dir / f"{workflow_id}_source.csv", index=False)

    adam_df = pd.DataFrame(
        {
            "USUBJID": ["SUBJ-001", "SUBJ-002", "SUBJ-003"],
            "AGEGR1": [">=18 to 64", ">=65", "<18"],
        }
    )
    adam_df.to_csv(output_dir / f"{workflow_id}_adam.csv", index=False)

    # Patch settings so the router reads from tmp_path, and register the workflow
    # in a FRESH manager's _history (not _contexts) to mimic the post-restart state.
    with patch("src.api.routers.data.get_settings") as mock_settings:
        mock_settings.return_value.output_dir = str(output_dir)

        from src.api.app import create_app
        from src.api.workflow_manager import _HistoricState  # type: ignore[attr-defined]

        app = create_app()
        manager = WorkflowManager()
        manager._history[workflow_id] = _HistoricState(  # type: ignore[attr-defined]
            workflow_id, "completed", '{"derived_variables": [], "errors": []}'
        )
        app.state.workflow_manager = manager

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Act
            response = await ac.get(f"/api/v1/workflows/{workflow_id}/data")

    # Assert — source panel is non-null and carries the snapshot rows
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    assert body["source"] is not None
    source: dict[str, object] = body["source"]  # type: ignore[assignment]
    assert source["row_count"] == 3
    assert source["label"] == "SDTM (Source)"
    column_names = {c["name"] for c in source["columns"]}  # type: ignore[index]
    assert column_names == {"USUBJID", "AGE", "SEX"}
```

**Constraints:**

- **DO NOT use `app.dependency_overrides[get_settings]`.** It will NOT work. `_load_source` calls `get_settings()` **directly** (see `data.py:59` — `output_dir = Path(get_settings().output_dir)`), not via `Depends(get_settings)`. FastAPI's `dependency_overrides` mechanism ONLY intercepts functions wrapped in `Depends()`. The real `get_settings()` will be called, return the default `Settings()` with `output_dir="output"`, and the test will fail to find the snapshot in `tmp_path`. The only correct approach is `with patch("src.api.routers.data.get_settings") as mock_settings: mock_settings.return_value.output_dir = str(output_dir)` — this monkey-patches the module-level symbol that `_load_source` imports.
- **DO NOT use the shared `client` fixture** (defined at `test_api.py:19-30`). That fixture creates a vanilla `WorkflowManager()` with no `_history` population, and the fixture's `yield` happens BEFORE we have a chance to mutate `_history`. Instead, self-manage the app + manager + transport inside the test body, exactly like the existing test at line 144.
- **`_HistoricState` is a module-level alias**, NOT a dataclass. It's defined at `src/api/workflow_manager.py:37` as `_HistoricState = HistoricState`, and `HistoricState` itself lives in `src/api/workflow_serializer.py:15-32`. Its `__init__` signature is `(self, workflow_id: str, fsm_state: str, state_json: str)` and **`state_json` MUST be a valid JSON string** — it's parsed via `json.loads()` at serializer line 19. Pass `'{"derived_variables": [], "errors": []}'` (matching the existing test at line 175) as the safe minimal input. Do NOT pass a dict literal `{}` — that will crash at `json.loads()`.
- **Import `_HistoricState` with `# type: ignore[attr-defined]`**. Pyright can't resolve the module-level alias reliably, so without the ignore comment the pre-commit pyright check fails. See existing import at `test_api.py:172`.
- **Create manager → populate `_history` → THEN assign to `app.state.workflow_manager`.** This is the canonical order from the existing test at lines 170–177. Doing it in a different order may race against `create_app()`'s lifespan and leak state between tests.
- **Use `ASGITransport(app=app)` with `# type: ignore[arg-type]`** — matches the existing test at line 179. Don't try to instantiate transport any other way.
- **Use `tmp_path` pytest fixture** — standard pattern, no new fixture needed.
- **AAA markers** (`# Arrange`, `# Act`, `# Assert`) in every test body — project convention.
- **Test name** follows `test_<action>_<scenario>_<expected>`: `test_get_data_preview_reads_source_snapshot_when_ctx_missing`.
- **Already-available imports** (do NOT re-import): `pd` (line 8), `pytest` (line 9), `ASGITransport` + `AsyncClient` (line 10), `WorkflowManager` (line 12), `patch` (line 6). Only NEW local imports inside the test body: `create_app` from `src.api.app`, `_HistoricState` from `src.api.workflow_manager`. Both are local imports matching the existing test's style (lines 167, 172).
- **Do NOT introduce a new pytest fixture** beyond `tmp_path`.
- **Do NOT mock `pd.read_csv` or `WorkflowManager`** — the whole point is to exercise the real disk-read code path in `_load_source`.
- **Do NOT add a frontend test** — the fix is entirely backend, and the frontend `{data.source != null && ...}` branch is already covered by existing TanStack Query hook tests.

**Reference:** `test_get_data_preview_completed_workflow_returns_columns_and_rows` at **`tests/unit/test_api.py:144-194`** — the canonical template for this test shape. Copy the `with patch(...)` + fresh manager + `app.state` + `ASGITransport` + `AsyncClient` block verbatim, just swap the assertions to check `body["source"]` instead of `body["derived"]`.

---

## Implementation order (single subagent, sequential within the dispatch)

1. Read the reference files listed in the "Reference files" table above to load context. Pay special attention to `src/api/workflow_manager.py:37` (where `_HistoricState` is defined as an alias) and `src/api/workflow_serializer.py:15-32` (the real class — NOT a dataclass).
2. Modify `src/engine/step_builtins.py` (spec 1) — add the snapshot write inside `_builtin_parse_spec`.
3. Modify `src/api/routers/data.py` (spec 2) — replace the `_load_source` body with the disk-first version.
4. Modify `src/api/workflow_manager.py` (spec 3) — add `_source.csv` to the `delete_workflow` cleanup tuple at line 229.
5. Modify `tests/unit/test_step_builtins.py` (spec 4) — add the two new parse_spec tests.
6. Modify `tests/unit/test_api.py` (spec 5) — add the one new data-router integration test. **CRITICAL: use `patch("src.api.routers.data.get_settings")`, NOT `dependency_overrides[get_settings]`.** Re-read spec 5's constraints before writing the test.
7. Run the local quality gate (next section).

---

## Quality gate — MUST pass before commit

Run each of these from the repo root. All must be clean:

```bash
# 1. Unit + integration test runs
uv run pytest tests/unit/test_step_builtins.py -v
uv run pytest tests/unit/test_api.py -v
uv run pytest  # full suite — expect 315 → 318 or 319 backend tests passing

# 2. Type checking
uv run pyright .

# 3. Linting + formatting
uv run ruff check .
uv run ruff format --check .

# 4. Import contracts — MUST be unchanged (no new ignore_imports)
uv run lint-imports

# 5. Custom arch checks (run the full pre-push suite)
pre-commit run --all-files
```

**Expected test delta:** +3 backend tests (2 in `test_step_builtins.py` + 1 in `test_api.py`), optionally +1 if you add a dedicated `test_delete_workflow_removes_source_snapshot` test (recommended). Total goes from **315 → 318 (or 319) backend** + **14 frontend** = **332 or 333 tests**.

**Import contracts MUST be unchanged.** No new `ignore_imports` entries are needed for this phase — the fix does not cross any layer boundary. If `lint-imports` fails, the implementation is wrong, not the contract. DO NOT add an exception to `.importlinter` to "make it pass" — investigate the layer violation and fix the code instead.

**Zero new pyright/ruff/import-linter violations.** If any custom arch check flags a new issue (file length >300, function length >40, raw SQL in engine, etc.), extract a helper or split the change — don't disable the hook.

**The test must actually FAIL against the pre-fix `_load_source`** before passing with the new version. Quick sanity check: after writing the test but before modifying `_load_source`, run `uv run pytest tests/unit/test_api.py::test_get_data_preview_reads_source_snapshot_when_ctx_missing` — it should fail with `assert body["source"] is not None` → False (proving the test exercises the bug). Then apply the `_load_source` fix and it passes. This is the red-green signal that the test is actually doing its job.

---

## `/check` gate — run before committing

After the subagent reports completion, run `/check` to validate:
- Architecture layer purity (no new engine→persistence edges, no new api→engine edges beyond what already exists)
- Plan alignment (file list matches what was delivered — no surprise additions)
- No dead code, no TODOs without issue references
- The snapshot write is NOT called from any other step (only `_builtin_parse_spec`)
- The `_load_source` disk-read branch is hit by the new integration test

If `/check` reports any deviation, fix it before committing.

---

## Manual verification — do this after the commit lands, before merge

**Stack setup:**
1. Terminal 1: `cd C:\Projects\AgentLens && uv run agentlens serve --mode mailbox --port 8650`
2. Terminal 2: `cd <homework> && uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload`
3. Terminal 3: `cd <homework>\frontend && npm run dev`
4. Terminal 4: `cd <homework> && python scripts/mailbox_simple_mock.py`

**Happy-path scenario (fresh workflow):**
1. Open http://localhost:5173, click **New Workflow**, pick `simple_mock.yaml`, confirm.
2. Watch the workflow reach `derive_variables` or the HITL gate.
3. Open the **Data** tab — confirm BOTH panels (SDTM and ADaM) render.
4. Run `ls output/` — there should be a new file `{workflow_id}_source.csv` alongside the pre-existing `{workflow_id}_adam.csv`.

**Restart-recovery scenario (the actual bug fix):**
1. With the workflow above still running or completed, `Ctrl+C` the uvicorn backend in Terminal 2.
2. Restart uvicorn with the same command.
3. In the browser, refresh the workflow detail page and open the **Data** tab.
4. **Expected (after fix):** both panels still render — SDTM panel shows the same rows as before the restart.
5. **Before fix (current `main`):** SDTM panel is missing; only the ADaM panel renders.

**Regression check on pre-existing Phase 16 workflows** (the ones Matt was hitting):
1. Delete their `{wf_id}_source.csv` files if you want to test that the fallback path still does the right thing (it should still return None cleanly, not crash).
2. For workflows that DID go through the new `parse_spec` builtin after this fix ships, the snapshot will be present and the panel populates.

**Negative path (spec with no source file on disk):**
1. Start a workflow with a broken spec (source path points to a nonexistent file).
2. `parse_spec` itself fails (pre-existing behavior — raises from `load_source_data`), so no snapshot is written.
3. The workflow reaches `failed` status cleanly. Data tab shows an empty state (expected — there was no successful parse).

---

## Mapping back to BUGS.md

- **Bug #6 — Data tab loses SDTM source panel after backend restart**
- **Status after Phase 18.1:** ✅ CLOSED — commit `<TBD after merge>`
- **Root cause addressed:** `_load_source` now reads from disk first, bypassing the `_contexts` vs `_history` dichotomy entirely. The snapshot is written at `parse_spec` time, so it's available for the full workflow lifetime (restart or no).
- **Remaining caveat:** Workflows created before this fix shipped (e.g. `bfdb3536`, `290eda64`, `c7329784`, `47f0f061`, `c208a8c2` from Matt's Phase 16 test run) have no snapshot on disk, so their SDTM panel will STILL be empty post-restart. This is acceptable — those workflows are pre-fix artifacts and not part of the demo.

---

## Docs updates — MANDATORY in the same commit as the fix

These are NOT optional — they're part of the definition of done for the phase:

1. **`BUGS.md`** — flip Bug #6 in the status overview table from `⏳ OPEN — deferred to Phase 18` to `✅ CLOSED | Phase 18.1 — commit <SHA>`. Add the commit SHA after `git commit -m ...` completes (amend the commit OR fill in the SHA via `git commit --amend` if the SHA needs to be written INTO the commit that closes it — alternative: use a `(pending SHA)` placeholder and fix it in a follow-up `docs:` commit).
2. **`ARCHITECTURE.md`** §Data Layer — append a one-line mention of `{workflow_id}_source.csv` alongside the existing `{workflow_id}_adam.csv` description in the output_dir table. If the §Data Layer section is missing the output_dir artifact list entirely, add a small subsection listing all four artifacts: `_adam.csv`, `_adam.parquet`, `_source.csv` (new), `_audit.json`.

### Optional (low-priority, only if you have time)

- `decisions.md` — one-paragraph ADR titled "2026-04-14 — SDTM source snapshot persisted at parse_spec time" documenting why we chose Option 1 over re-reading `ctx.spec.source.path` (Option 2) or rehydrating `PipelineContext` from DB history (Option 3). The three-paragraph structure from prior ADRs (Status / Context / Decision / Consequences) is fine.

---

## Summary for `/plan-validate` + `/implement-phase`

- **1 sub-phase**, **1 subagent dispatch** (`python-fastapi`).
- **3 source files modified**, **2 test files modified**, **0 new files**, **0 deletions**.
- **+3 (or +4) tests** (315 → 318 or 319 backend).
- **Function lengths:** both modified functions stay under **40 lines** (hook limit `FUNCTION_LINE_LIMIT=40`) — `_builtin_parse_spec` 14 → ~19, `_load_source` 9 → ~20.
- **File lengths:** `step_builtins.py` **244 → ~247** (under 300 hard limit); `data.py` **127 → ~137** (under 300 hard limit); `workflow_manager.py` **265 → 265** (no net change — one-character tuple addition).
- **Layer purity:** no new layer-crossing imports. `lint-imports` should be unchanged — do NOT add new `ignore_imports` entries.
- **Test coverage:** happy path (disk present) + edge case (output_dir None) for the snapshot write + restart scenario for the router read + (recommended) snapshot cleanup in delete.
- **Key traps for subagents to avoid:**
  1. **Do NOT use `dependency_overrides[get_settings]`** — use `patch("src.api.routers.data.get_settings")`. The plan explains why in spec 5's constraints.
  2. **Do NOT describe `_HistoricState` as a dataclass** — it's a module-level alias at `workflow_manager.py:37` pointing at `src/api/workflow_serializer.py:15`. Its `state_json` arg must be a valid JSON STRING, not a dict literal.
  3. **Do NOT forget `# type: ignore[attr-defined]`** on the `_HistoricState` import.
  4. **Do NOT mis-remember the function length limit as 30** — it's 40 (see `tools/pre_commit_checks/check_file_length.py:17`).

All 6 implementation steps are sequential within a single `python-fastapi` dispatch. No inter-file race conditions. The subagent can safely implement in the order listed.
