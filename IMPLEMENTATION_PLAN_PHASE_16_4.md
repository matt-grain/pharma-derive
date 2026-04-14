# Phase 16.4 — Ground Truth Comparison at Runtime

**Agent:** `python-fastapi`
**Depends on:** None (runs in parallel with 16.1)
**Fixes:** Slide demo claim `slides.md:254-262` ("Comparator checks outputs against each other AND ground truth")

## Goal

`specs/adsl_cdiscpilot01.yaml` declares `validation.ground_truth` pointing at the official CDISC ADaM XPT file, and `ValidationConfig` parses it. But **nothing in the pipeline reads `spec.validation.ground_truth`** — the comparator only compares coder vs QC.

This phase adds:
1. A new builtin `compare_against_ground_truth` that loads the reference XPT and compares the final `derived_df` to it per variable.
2. A new `GroundTruthReport` domain model attached to `PipelineContext`.
3. A new `GET /workflows/{id}/ground_truth` endpoint to surface results.
4. Unit/integration tests using the real cdiscpilot01 AGEGR1 file (already in repo).

**Out of scope:** Frontend Ground Truth tab (can be a follow-up; the backend exposure is the main fix).

---

## Files to create

### `src/domain/ground_truth.py` (NEW)
**Purpose:** Domain models for the ground-truth comparison report.
**Content:**
```python
"""Ground-truth comparison report for validating derivations against a reference ADaM dataset."""

from __future__ import annotations

from pydantic import BaseModel

from src.domain.models import QCVerdict


class VariableGroundTruthResult(BaseModel, frozen=True):
    """Comparison of a single derived variable against ground truth."""

    variable: str
    verdict: QCVerdict
    match_count: int
    mismatch_count: int
    total_rows: int
    mismatch_sample: list[str] = []  # first 5 divergent indices as strings (for display)
    error: str | None = None  # when variable not in ground truth or comparison failed


class GroundTruthReport(BaseModel, frozen=True):
    """Full ground-truth comparison report attached to a workflow."""

    ground_truth_path: str
    total_variables: int
    matched_variables: int
    results: list[VariableGroundTruthResult]
```
**Constraints:** Frozen models. No I/O in this file — just types.

### `tests/integration/test_ground_truth_runtime.py` (NEW)
**Purpose:** End-to-end test using the real cdiscpilot01 data.
**Tests to write:**
- `test_ground_truth_builtin_compares_derived_to_reference_xpt` — run the AGEGR1 derivation in isolation, call the builtin with the real `adsl.xpt`, assert `GroundTruthReport.matched_variables >= 1`.
- `test_ground_truth_skips_variables_not_in_reference` — variable that only exists in derived_df → `error` field set, not a crash.
- `test_ground_truth_endpoint_returns_report` — full workflow run end-to-end, `GET /workflows/{id}/ground_truth` returns the report JSON.
- `test_ground_truth_endpoint_404_when_not_run` — fresh workflow, no ground-truth step executed yet → 404 with message.
**Fixtures:** Use `data/adam/cdiscpilot01/adsl.xpt` (exists in repo — verified).

---

## Files to modify

### `src/engine/pipeline_context.py` (MOD)
**Change:** Add `ground_truth_report: GroundTruthReport | None = None` field.
**Exact change:** Add to dataclass:
```python
ground_truth_report: GroundTruthReport | None = None
```
Add `TYPE_CHECKING` import for `GroundTruthReport`.

### `src/engine/step_builtins.py` (MOD)
**Change:** Add `_builtin_compare_ground_truth` + register.
**Critical detail (W3 fix):** Derived and ground-truth dataframes do NOT share an index. `derived_df` is built from SDTM domains merged on `USUBJID`; ground-truth `adsl.xpt` has its own row order and subject set (potentially different subject counts). Comparing `derived_df[var]` vs `gt_df[var]` by position is **wrong** — must align on the primary key first. The builtin does this via a left join on `spec.source.primary_key` (usually `USUBJID`).
**Exact change:**
```python
async def _builtin_compare_ground_truth(step: StepDefinition, ctx: PipelineContext) -> None:
    """Load ground-truth XPT, align on primary key, compare derived variables, attach report to ctx."""
    if ctx.spec is None or ctx.derived_df is None:
        return
    gt_config = ctx.spec.validation.ground_truth
    if gt_config is None:
        logger.info("Step '{step_id}': no ground truth configured, skipping", step_id=step.id)
        return

    import pandas as pd
    import pyreadstat

    from src.domain.executor import compare_results
    from src.domain.ground_truth import GroundTruthReport, VariableGroundTruthResult
    from src.domain.models import QCVerdict

    primary_key = ctx.spec.source.primary_key  # e.g. "USUBJID"
    gt_df, _ = pyreadstat.read_xport(gt_config.path)

    if primary_key not in ctx.derived_df.columns or primary_key not in gt_df.columns:
        logger.warning(
            "Primary key '{key}' missing from derived or ground truth — skipping comparison",
            key=primary_key,
        )
        return

    # Inner join on primary key aligns the two series row-by-row. Only subjects present
    # in BOTH datasets are compared — subjects missing from either side are reported
    # via the `total_rows` field and mismatch_sample length.
    aligned = ctx.derived_df.merge(
        gt_df,
        on=primary_key,
        how="inner",
        suffixes=("_derived", "_gt"),
    )
    tolerance = ctx.spec.validation.tolerance.numeric
    results: list[VariableGroundTruthResult] = []
    matched = 0

    for rule in ctx.spec.derivations:
        var = rule.variable
        derived_col = f"{var}_derived" if f"{var}_derived" in aligned.columns else var
        gt_col = f"{var}_gt" if f"{var}_gt" in aligned.columns else var
        if derived_col not in aligned.columns or gt_col not in aligned.columns:
            results.append(
                VariableGroundTruthResult(
                    variable=var,
                    verdict=QCVerdict.MISMATCH,
                    match_count=0,
                    mismatch_count=0,
                    total_rows=0,
                    error=f"Variable '{var}' not in aligned dataframe (derived or ground truth missing)",
                )
            )
            continue

        # Reset index so compare_results sees 0..N integers (it expects positional alignment).
        comparison = compare_results(
            var,
            aligned[derived_col].reset_index(drop=True),
            aligned[gt_col].reset_index(drop=True),
            tolerance,
        )
        if comparison.verdict == QCVerdict.MATCH:
            matched += 1
        results.append(
            VariableGroundTruthResult(
                variable=var,
                verdict=comparison.verdict,
                match_count=comparison.match_count,
                mismatch_count=comparison.mismatch_count,
                total_rows=comparison.total_rows,
                mismatch_sample=[str(i) for i in comparison.divergent_indices[:5]],
            )
        )

    ctx.ground_truth_report = GroundTruthReport(
        ground_truth_path=gt_config.path,
        total_variables=len(results),
        matched_variables=matched,
        results=results,
    )
    logger.info(
        "Ground truth: {matched}/{total} variables match (aligned on {key})",
        matched=matched,
        total=len(results),
        key=primary_key,
    )
```
Register in `BUILTIN_REGISTRY`: `"compare_ground_truth": _builtin_compare_ground_truth`.
**Constraints:**
- **Align on `spec.source.primary_key` before comparing** — never positional-compare.
- Inner join drops subjects missing from either side; that's acceptable for this homework (alternative would be a richer report distinguishing "not in ground truth" vs "mismatched").
- Pandas merge with `suffixes=("_derived", "_gt")` only renames columns that collide. If a derivation is unique to one side, no suffix is added — the fallback `f"{var}_derived" if ... in aligned.columns else var` handles both cases.
- Use `compare_results` from domain (already exists) — don't reimplement.
- Use `QCVerdict` enum, not strings.
- Import `pyreadstat` and `pandas` inside the function.

### `config/pipelines/clinical_derivation.yaml` (MOD)
**Change:** Add `compare_ground_truth` step between `derive_variables` and `human_review`.
**Exact change:** Insert:
```yaml
    - id: ground_truth_check
      type: builtin
      builtin: compare_ground_truth
      depends_on: [derive_variables]
      description: "Compare derived output against reference ADaM (if configured)"
```
Update `human_review.depends_on` to `[ground_truth_check]`.

### `src/api/routers/workflows.py` (MOD)
**Change:** Add `GET /workflows/{id}/ground_truth` endpoint.
**Exact change:**
```python
@router.get(
    "/{workflow_id}/ground_truth",
    response_model=GroundTruthReportResponse,
    status_code=200,
)
async def get_ground_truth(
    workflow_id: str,
    manager: WorkflowManagerDep,
) -> GroundTruthReportResponse:
    ctx = manager.get_context(workflow_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    if ctx.ground_truth_report is None:
        raise HTTPException(
            status_code=404,
            detail="Ground truth check has not been run for this workflow",
        )
    return GroundTruthReportResponse.model_validate(ctx.ground_truth_report.model_dump())
```

### `src/api/schemas.py` (MOD)
**Change:** Add `GroundTruthReportResponse` + `VariableGroundTruthResponse` schemas.
**Exact change:**
```python
class VariableGroundTruthResponse(BaseModel, frozen=True):
    variable: str
    verdict: str
    match_count: int
    mismatch_count: int
    total_rows: int
    mismatch_sample: list[str] = []
    error: str | None = None


class GroundTruthReportResponse(BaseModel, frozen=True):
    ground_truth_path: str
    total_variables: int
    matched_variables: int
    results: list[VariableGroundTruthResponse]
```
**Constraints:** These are DTOs (HTTP boundary) — separate from domain models in `src/domain/ground_truth.py` per layering rules.

---

## Test constraints

- Integration test uses the real `data/adam/cdiscpilot01/adsl.xpt` file — read it with `pyreadstat`.
- **Coder+QC MUST be mocked** (existing pattern from `tests/integration/test_workflow.py`) — do NOT make real LLM calls. Only the ground-truth comparison path is under test.
- The `test_ground_truth_builtin_compares_derived_to_reference_xpt` test should call `_builtin_compare_ground_truth` directly on a hand-crafted `PipelineContext` with `derived_df` containing the correct AGEGR1 values derived manually — bypasses the full pipeline entirely. Avoids LLM + orchestrator overhead.
- Expect AGEGR1 to match ground truth (CDISC pilot reference — we've validated this previously). If it doesn't, the bug is in the alignment logic, not the ground truth.
- **Watch for dtype surprises:** `pyreadstat` may return `object` dtype for categorical XPT columns. If comparison fails unexpectedly, cast both series to `str` before comparing.

## Tooling gate

```bash
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run pytest tests/integration/test_ground_truth_runtime.py -v
uv run pytest
uv run lint-imports
```

## Acceptance criteria

1. ✅ `compare_ground_truth` builtin registered and runs in the clinical_derivation pipeline.
2. ✅ `PipelineContext.ground_truth_report` populated after the step runs.
3. ✅ `GET /workflows/{id}/ground_truth` returns the report for a completed run.
4. ✅ Graceful skip when no ground truth configured (express pipeline should still work unchanged).
5. ✅ Variables missing from ground truth produce an `error` field, not a crash.
6. ✅ All existing tests still pass.
7. ✅ ≥4 new tests passing.
8. ✅ Tooling gate green.
