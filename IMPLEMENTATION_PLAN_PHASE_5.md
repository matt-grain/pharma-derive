# Phase 5 — CDISC Pilot ADSL Spec + XPT Loader

**Dependencies:** Phases 1-4 (complete)
**Agent:** `general-purpose`
**Estimated files:** 6

This phase adds real CDISC clinical data support: XPT file loading via pyreadstat, the ADSL transformation spec for 7 derivation variables from the cdiscpilot01 study, and ground-truth validation config pointing to the official ADSL dataset.

**New dependency:** `pyreadstat>=1.3,<2` (already installed)

---

## 5.1 XPT Format Support in Source Loader

### `src/domain/spec_parser.py` (MODIFY)

**Change:** Add XPT format support to `load_source_data()`.

Currently `load_source_data()` only handles CSV. Add an `elif fmt == "xpt":` branch that uses `pyreadstat.read_xport()`.

**Exact changes:**

1. Add `import pyreadstat` at the top (after `import yaml`). Since pyreadstat has no stubs, add a `# type: ignore[import-untyped]` comment.

2. In `load_source_data()`, after the CSV branch (line ~76), add:
```python
    elif fmt == "xpt":
        frames = []
        base_path = Path(spec.source.path)
        if not base_path.exists():
            msg = f"Source data path not found: {base_path}"
            raise FileNotFoundError(msg)
        for domain in spec.source.domains:
            file_path = base_path / f"{domain}.xpt"
            if not file_path.exists():
                msg = f"Domain file not found: {file_path}"
                raise FileNotFoundError(msg)
            df_domain, _ = pyreadstat.read_xport(str(file_path))
            frames.append(df_domain)
```

3. Update the `SourceFormat` handling — the `fmt != "csv"` check on line 75 should become a proper if/elif/else:
```python
    if fmt == "csv":
        # existing CSV logic...
    elif fmt == "xpt":
        # new XPT logic...
    else:
        msg = f"Unsupported source format: {fmt}"
        raise ValueError(msg)
```

4. The merge logic (lines 92-98) stays the same — it works for both CSV and XPT frames.

**Constraints:**
- `pyreadstat.read_xport()` requires a `str` path, not `Path` — use `str(file_path)`
- The function returns `(DataFrame, metadata)` — we only need the DataFrame
- Domain purity: pyreadstat is a data library like pandas, acceptable in domain/

---

## 5.2 CDISC ADSL Transformation Spec

### `specs/adsl_cdiscpilot01.yaml` (NEW)

**Purpose:** Real transformation spec for deriving 7 ADSL variables from CDISC pilot SDTM data.

**Data available in SDTM:**
- `dm.xpt` (306 rows): USUBJID, AGE, AGEU, SEX, RACE, ETHNIC, ARM, ARMCD, ACTARM, ACTARMCD, RFSTDTC, RFENDTC, RFXSTDTC, RFXENDTC, COUNTRY, SITEID, DTHFL, DTHDTC
- `ex.xpt`: USUBJID, EXTRT, EXDOSE, EXSTDTC, EXENDTC, VISIT
- `ds.xpt`: USUBJID, DSTERM, DSDECOD, DSCAT, DSSTDTC
- `sv.xpt`: USUBJID, VISITNUM, VISIT, SVSTDTC, SVENDTC

**Ground truth (ADSL):** 254 rows, contains all target variables.

**Spec content:**

```yaml
study: cdiscpilot01
description: "ADSL derivations for CDISC Pilot Study (Alzheimer's anti-dementia trial)"
version: "1.0.0"
author: "CDDE"

source:
  format: xpt
  path: data/sdtm/cdiscpilot01
  domains: [dm, ex, ds, sv]
  primary_key: USUBJID

synthetic:
  rows: 15

validation:
  ground_truth:
    path: data/adam/cdiscpilot01/adsl.xpt
    format: xpt
    key: USUBJID
  tolerance:
    numeric: 0.01

derivations:
  - variable: AGEGR1
    source_columns: [AGE]
    logic: "Age group: '<65' if AGE < 65, '65-80' if 65 <= AGE <= 80, '>80' if AGE > 80."
    output_type: str
    allowed_values: ["<65", "65-80", ">80"]

  - variable: TRTDUR
    source_columns: [RFXSTDTC, RFXENDTC]
    logic: "Treatment duration in days: (RFXENDTC - RFXSTDTC) + 1. Dates are ISO 8601 strings. Null if either date is missing."
    output_type: float
    nullable: true

  - variable: SAFFL
    source_columns: [ARM, ACTARMCD, RFXSTDTC]
    logic: "Safety population flag: 'Y' if the subject was randomized (ARM is not empty) AND received at least one dose (RFXSTDTC is not missing). Otherwise 'N'."
    output_type: str
    allowed_values: ["Y", "N"]

  - variable: ITTFL
    source_columns: [ARM, ARMCD]
    logic: "Intent-to-treat flag: 'Y' if the subject was randomized (ARMCD is not empty). Otherwise 'N'."
    output_type: str
    allowed_values: ["Y", "N"]

  - variable: EFFFL
    source_columns: [ITTFL, SAFFL]
    logic: "Efficacy population flag: 'Y' if both ITTFL='Y' and SAFFL='Y'. Otherwise 'N'."
    output_type: str
    allowed_values: ["Y", "N"]

  - variable: DISCONFL
    source_columns: [DSDECOD, DSCAT]
    logic: "Discontinuation flag: 'Y' if any DS record has DSCAT='DISPOSITION EVENT' and DSDECOD is NOT 'COMPLETED'. Otherwise '' (empty string). Note: requires per-subject aggregation across DS domain rows."
    output_type: str
    allowed_values: ["Y", ""]
    domain: ds

  - variable: DURDIS
    source_columns: [RFSTDTC]
    logic: "Duration of disease in months: not directly derivable from SDTM sources without disease onset date (DISONSDT from MH domain, not included in source). Set to null for all subjects. This tests the system's handling of underspecified derivations where the agent should flag the ambiguity."
    output_type: float
    nullable: true
```

**Constraints:**
- DISCONFL requires joining DS domain — the `domain: ds` field is a hint that this variable needs DS records per subject, not just the DM row. Ground truth: 144 Y / 110 blank.
- DURDIS is intentionally underspecified — it tests the Spec Interpreter agent's ability to flag ambiguity. Ground truth has real values (requires MH domain not in our source list).
- SAFFL is 'Y' for all 254 subjects in ground truth — trivially satisfiable. Kept for domain realism but not a strong test.
- All allowed_values match the official ADSL ground truth
- The source merge uses USUBJID as primary key across all 4 domains

---

## 5.3 Multi-Domain Merge Logic

### `src/domain/spec_parser.py` (MODIFY — additional change)

**Change:** The current merge logic does a simple left join on `primary_key` for all domains. For CDISC data, some domains have multiple rows per subject (DS ~2 rows/subject, EX ~2.3 rows/subject). A naive join will produce ~600 rows instead of 306 (some subjects repeated).

**Decision:** Merge ALL domains with left join on USUBJID. The resulting DataFrame will have duplicate USUBJID rows where multi-row domains contribute multiple records. This is acceptable because:
- The agent sandbox only has `df`, `pd`, `np` — it cannot read external files
- Derivation logic for multi-row variables (like DISCONFL) must use `groupby('USUBJID')` — the spec explicitly says "requires per-subject aggregation"
- Subject-level derivations (AGEGR1, SAFFL, etc.) work correctly on duplicated rows since source values repeat
- Ground-truth comparison merges on USUBJID, which handles the row-count difference naturally

**Exact code for the XPT multi-domain merge (replaces the existing CSV merge logic for XPT format):**

```python
# In load_source_data(), inside the elif fmt == "xpt": branch, after loading all frames:
if len(frames) == 1:
    return frames[0]
result = frames[0]  # DM is always first (anchor, one row per subject)
for frame in frames[1:]:
    result = result.merge(frame, on=spec.source.primary_key, how="left", suffixes=("", "_dup"))
    # Drop duplicate columns created by suffixes (e.g., STUDYID_dup, DOMAIN_dup)
    dup_cols = [c for c in result.columns if c.endswith("_dup")]
    result = result.drop(columns=dup_cols)
return result
```

**Constraints:**
- DM must be the first domain in the spec's `domains` list (anchor with one row per subject)
- Left join preserves all DM subjects; multi-row domains add columns with repeated rows
- `suffixes=("", "_dup")` prevents column name collisions; `_dup` columns are dropped to keep only the DM version of shared columns (STUDYID, DOMAIN, USUBJID)
- DISCONFL derivation spec explicitly notes "requires per-subject aggregation" — the agent will generate `groupby` code

---

## 5.4 Tests

### `tests/unit/test_spec_parser.py` (MODIFY)

**Add tests:**
- `test_parse_spec_xpt_format_accepted` — parse ADSL spec, verify `source.format == "xpt"`
- `test_load_source_data_xpt_reads_dm` — load DM.xpt via the spec, verify 306 rows and AGE column exists
- `test_load_source_data_unsupported_format_raises` — format "parquet" → ValueError

**Constraints:**
- XPT tests use real files in `data/sdtm/cdiscpilot01/` — these are committed to the repo
- Tests must use `Path` for platform-independent paths
- Follow existing test naming: `test_<what>_<condition>_<expected>`

### `tests/integration/test_cdisc.py` (NEW)

**Purpose:** Integration test that parses the ADSL spec, loads real CDISC data, and verifies the spec-to-DAG pipeline works with real clinical data.

**Tests:**
- `test_adsl_spec_parses_successfully` — parse `specs/adsl_cdiscpilot01.yaml`, verify 7 derivations
- `test_adsl_source_loads_all_domains` — load source data, verify USUBJID, AGE, RFXSTDTC columns exist
- `test_adsl_dag_builds_correct_layers` — build DAG from ADSL spec, verify AGEGR1 is layer 0, EFFFL is layer 1+
- `test_adsl_synthetic_generates_correct_shape` — generate synthetic from loaded source, verify 15 rows, same columns

**Constraints:**
- These tests hit real files — mark them appropriately
- Use `conftest.py` fixture for the ADSL spec path
- No LLM calls — this tests data loading + DAG construction only

---

## 5.5 pyproject.toml (MODIFY)

**Change:** Add `pyreadstat` to dependencies if not already present.

Currently `pyreadstat>=1.3.3` (no upper bound — added by `uv add`). Fix to:
```toml
"pyreadstat>=1.3,<2",
```
This follows the project convention of `>=X.Y,<X+1` bounds used by all other dependencies.

---

## 5.6 Post-implementation: Update GAP_ANALYSIS.md

After Phase 5 is complete, update `docs/GAP_ANALYSIS.md`:
- §6.1 Dataset: ✅ (CDISC pilot with real XPT files)
- §6.2 Derived outputs: 🔶 → ✅ (7 ADSL variables scoped in spec)
- §7.6 Working prototype: 🔶 (data loading works, full pipeline needs LLM)
