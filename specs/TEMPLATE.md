# Transformation Spec — Format Reference

## Overview

A transformation spec is a YAML file that tells the derivation engine:
1. Where to find the source data
2. What variables to derive
3. The logic for each derivation (in plain English)
4. Dependencies between derivations

The engine is **spec-agnostic** — it doesn't know about CDISC, ADaM, or any specific data standard. The spec is the interface contract.

## Full Schema

```yaml
# ─── Study Metadata ───────────────────────────────────────────
study: string                    # Study identifier (e.g., "cdiscpilot01")
description: string              # Human-readable description
version: string                  # Spec version (e.g., "1.0.0")
author: string                   # Who wrote this spec (for audit trail)

# ─── Source Data ──────────────────────────────────────────────
source:
  format: xpt | csv | parquet    # Data file format
  path: string                   # Relative path to data directory
  domains:                       # List of source data files to load
    - string                     # e.g., "dm", "ex", "lb" (without extension)
  primary_key: string            # Subject identifier column (default: "USUBJID")

# ─── Synthetic Reference (for LLM prompts) ───────────────────
# Optional: if not provided, engine generates synthetic data from schema
synthetic:
  path: string                   # Path to synthetic reference CSV
  rows: int                      # Number of synthetic rows (default: 15)

# ─── Derivations ─────────────────────────────────────────────
derivations:
  - variable: string             # Target variable name (e.g., "AGE_GROUP")
    source_columns: [string]     # Input columns — can be source OR derived
    logic: string                # Plain English derivation logic
    output_type: str | int | float | bool | category
                                 # Expected pandas dtype of the result
    domain: string               # Source domain if ambiguous (e.g., "dm")
                                 # Optional — needed when column names overlap
    nullable: bool               # Can the result contain nulls? (default: true)
    allowed_values: [string]     # Optional — valid values for categorical outputs
                                 # Used by QC for output validation

# ─── Validation Rules (optional) ─────────────────────────────
validation:
  ground_truth:
    path: string                 # Path to ground truth dataset (e.g., ADaM ADSL)
    format: xpt | csv | parquet
    key: string                  # Join key to match derived vs expected
  tolerance:
    numeric: float               # Acceptable difference for float comparisons
                                 # (default: 0.0 — exact match)
```

## Dependency Detection

The engine automatically detects dependencies between derivations by scanning `source_columns`:
- If a `source_column` matches another derivation's `variable` name → dependency edge in DAG
- If a `source_column` matches a column in the source data → no dependency (available immediately)
- If a `source_column` matches neither → Spec Interpreter flags it as an ambiguity

Example:
```yaml
derivations:
  - variable: AGE_GROUP          # Layer 0 (depends only on source column AGE)
    source_columns: [AGE]
    logic: "..."

  - variable: SAFFL              # Layer 0 (depends only on source columns)
    source_columns: [ARMCD, EXSTDTC]
    logic: "..."

  - variable: RISK_GROUP         # Layer 1 (depends on AGE_GROUP + SAFFL)
    source_columns: [AGE_GROUP, SAFFL]
    logic: "..."
```

DAG built automatically:
```
AGE → AGE_GROUP ──┐
                   ├──→ RISK_GROUP
ARMCD → SAFFL ────┘
EXSTDTC ─┘
```

## Spec Validation

Before agents run, the engine validates the spec:

| Check | What It Catches |
|-------|----------------|
| All `source_columns` resolve to a source domain column OR another derivation | Typos, missing columns |
| No circular dependencies in derivation graph | A depends on B depends on A |
| `output_type` is a valid pandas dtype | Invalid type names |
| `allowed_values` present for categorical `output_type` | Unconstrained categoricals |
| `ground_truth` path exists (if provided) | Missing validation data |

## Example: Minimal Spec (for testing)

```yaml
study: unit_test
description: "Minimal spec for engine development"
version: "0.1.0"
author: "dev"

source:
  format: csv
  path: tests/fixtures
  domains: [patients]
  primary_key: patient_id

derivations:
  - variable: AGE_GROUP
    source_columns: [age]
    logic: "If age < 18: 'minor'. If 18 <= age < 65: 'adult'. If age >= 65: 'senior'. Null if age missing."
    output_type: str
    allowed_values: ["minor", "adult", "senior"]

  - variable: IS_ELDERLY
    source_columns: [AGE_GROUP]
    logic: "True if AGE_GROUP is 'senior', False otherwise. Null if AGE_GROUP is null."
    output_type: bool
```

## Example: CDISC Pilot Study

```yaml
study: cdiscpilot01
description: "ADSL derivations for CDISC Pilot Alzheimer's study"
version: "1.0.0"
author: "Matt Boujonnier"

source:
  format: xpt
  path: data/sdtm/cdiscpilot01
  domains: [dm, ex, ds, sv]
  primary_key: USUBJID

validation:
  ground_truth:
    path: data/adam/cdiscpilot01/adsl.xpt
    format: xpt
    key: USUBJID

derivations:
  - variable: AGE_GROUP
    source_columns: [AGE]
    domain: dm
    logic: "Categorize AGE into groups: '<18' if AGE < 18, '18-64' if 18 <= AGE < 65, '>=65' if AGE >= 65. Null if AGE is missing."
    output_type: str
    allowed_values: ["<18", "18-64", ">=65"]

  - variable: TREATMENT_DURATION
    source_columns: [RFSTDTC, RFENDTC]
    domain: dm
    logic: "Number of days between RFENDTC and RFSTDTC plus 1 (inclusive). Null if either date is missing. Parse dates as YYYY-MM-DD."
    output_type: float
    nullable: true

  - variable: SAFFL
    source_columns: [ARMCD]
    domain: dm
    logic: "Y if patient was randomized to a treatment arm (ARMCD is not empty/null and not 'Scrnfail'). N otherwise."
    output_type: str
    allowed_values: ["Y", "N"]

  - variable: ITTFL
    source_columns: [ARMCD]
    domain: dm
    logic: "Y if patient was randomized (ARMCD is not empty/null). N otherwise."
    output_type: str
    allowed_values: ["Y", "N"]

  - variable: RISK_GROUP
    source_columns: [AGE_GROUP, SAFFL]
    logic: "High if AGE_GROUP is '>=65' and SAFFL is 'Y'. Medium if AGE_GROUP is '18-64' and SAFFL is 'Y'. Low otherwise. Null if any source is null."
    output_type: str
    allowed_values: ["High", "Medium", "Low"]
```
