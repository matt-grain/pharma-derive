# Transformation Specifications

This folder contains the transformation specs that drive the derivation engine. Each YAML file defines a study-specific set of derivations — the engine is agnostic to the study, domain, or data standard.

## How It Works

```
specs/my_study.yaml  +  data/sdtm/my_study/  →  Engine  →  Derived ADaM + Audit Trail
```

The spec is the **interface contract** between clinical teams and the engine:
- Clinical/biostat teams write the spec (what to derive, from what, with what logic)
- The engine reads the spec, builds a DAG, and runs agents to generate + verify code
- The same engine handles any study — swap the YAML, swap the data

## Spec Format

See [TEMPLATE.md](TEMPLATE.md) for the full format reference with all fields documented.

Quick example:

```yaml
study: cdiscpilot01
description: "ADSL derivations for Alzheimer's pilot study"

source:
  format: xpt
  path: data/sdtm/cdiscpilot01
  domains: [dm, ex, ds]

derivations:
  - variable: AGE_GROUP
    source_columns: [AGE]
    logic: "Categorize into '<18', '18-64', '>=65'. Null if missing."
    output_type: str

  - variable: RISK_GROUP
    source_columns: [AGE_GROUP, SAFFL]   # depends on other derived variables
    logic: "High if >=65 and safety population. Low otherwise."
    output_type: str
```

The engine detects that `RISK_GROUP` depends on `AGE_GROUP` (a derived variable) and builds the DAG accordingly.

## Files

| File | Purpose |
|------|---------|
| `TEMPLATE.md` | Full spec format reference with all fields and validation rules |
| `cdiscpilot01_adsl.yaml` | CDISC Pilot Study — ADSL derivations (our demo scenario) |
| `simple_mock.yaml` | Minimal spec for engine development and unit testing |

## Platform Thinking

The spec format is designed to scale across studies:
- **Same engine, different YAML** = different study
- **Version the specs** alongside the data in study-specific repos
- **Long-term memory** accumulates validated patterns per `variable` type across studies
- **Guard configs** can vary per study (different compliance levels in `guards.yaml`)
