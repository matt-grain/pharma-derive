# Phase 1 — Project Setup + Domain Layer

**Dependencies:** None (foundation phase)
**Agent:** `python-fastapi`
**Estimated files:** 14

This phase creates the project skeleton and the pure domain layer. Domain has ZERO framework dependencies — just Python, Pydantic, networkx, pandas, PyYAML.

---

## 1.1 Project Setup

### `pyproject.toml` (NEW)

**Purpose:** Project metadata, dependencies, and tool configs.
**Key sections:**

```toml
[project]
name = "pharma-derive"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "pydantic>=2.10,<3",
    "pydantic-ai>=1.0,<2",
    "pandas>=2.2,<3",
    "networkx>=3.4,<4",
    "pyyaml>=6.0,<7",
    "loguru>=0.7,<1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<9",
    "pytest-asyncio>=0.24,<1",
    "pytest-cov>=6.0,<7",
    "ruff>=0.8,<1",
    "pyright>=1.1,<2",
]

[tool.ruff]
target-version = "py313"
line-length = 120
[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH", "RUF"]

[tool.pyright]
pythonVersion = "3.13"
typeCheckingMode = "strict"
venvPath = "."
venv = ".venv"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Constraints:**
- Pin all deps with `>=X.Y,<X+1` bounds
- No `pyreadstat` yet (not needed for CSV mock data)
- `pytest-asyncio` needed for async agent tests later

### `.github/workflows/ci.yml` (NEW)

**Purpose:** CI pipeline — lint + typecheck + test on every push.
**Content:**

```yaml
name: CI
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pyright .
      - run: uv run pytest --cov=src --cov-report=term-missing
```

### `src/__init__.py` (NEW)

**Purpose:** Package root. Empty file.

### `src/domain/__init__.py` (NEW)

**Purpose:** Domain package init. Empty file.

---

## 1.2 Domain Models

### `src/domain/models.py` (NEW)

**Purpose:** All Pydantic models for the domain layer. These are used everywhere.

**Models to define:**

```python
class DerivationRule(BaseModel, frozen=True):
    """A single derivation from the transformation spec."""
    variable: str                    # Target variable name (e.g., "AGE_GROUP")
    source_columns: list[str]        # Input columns (source OR derived)
    logic: str                       # Plain English derivation logic
    output_type: str                 # Expected dtype: "str", "int", "float", "bool"
    domain: str | None = None        # Source domain if ambiguous
    nullable: bool = True            # Can result contain nulls?
    allowed_values: list[str] | None = None  # Valid values for categorical

class SpecMetadata(BaseModel, frozen=True):
    """Metadata from the transformation spec header."""
    study: str
    description: str
    version: str = "0.1.0"
    author: str = ""

class SourceConfig(BaseModel, frozen=True):
    """Source data configuration from the spec."""
    format: str                      # "csv", "xpt", "parquet"
    path: str                        # Relative path to data directory
    domains: list[str]               # List of domain files to load
    primary_key: str = "USUBJID"     # Subject identifier column

class SyntheticConfig(BaseModel, frozen=True):
    """Optional synthetic reference dataset config."""
    path: str | None = None
    rows: int = 15

class ValidationConfig(BaseModel, frozen=True):
    """Optional ground truth validation config."""
    path: str | None = None
    format: str | None = None
    key: str | None = None
    tolerance_numeric: float = 0.0

class TransformationSpec(BaseModel, frozen=True):
    """Complete transformation specification parsed from YAML."""
    metadata: SpecMetadata
    source: SourceConfig
    synthetic: SyntheticConfig = SyntheticConfig()
    validation: ValidationConfig = ValidationConfig()
    derivations: list[DerivationRule]

class QCVerdict(StrEnum):
    """Result of comparing primary and QC implementations."""
    MATCH = "match"
    MISMATCH = "mismatch"
    INSUFFICIENT_INDEPENDENCE = "insufficient_independence"

class WorkflowStep(StrEnum):
    """States in the workflow FSM."""
    CREATED = "created"
    SPEC_REVIEW = "spec_review"
    DAG_BUILT = "dag_built"
    DERIVING = "deriving"
    VERIFYING = "verifying"
    DEBUGGING = "debugging"
    REVIEW = "review"
    AUDITING = "auditing"
    COMPLETED = "completed"
    FAILED = "failed"

class DerivationStatus(StrEnum):
    """Status of a single derivation in the DAG."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    QC_PASS = "qc_pass"
    QC_MISMATCH = "qc_mismatch"
    APPROVED = "approved"
    FAILED = "failed"

class DAGNode(BaseModel):
    """Enhanced DAG node — carries rule + execution provenance."""
    rule: DerivationRule
    status: DerivationStatus = DerivationStatus.PENDING
    layer: int = 0                           # Topological layer (0 = no deps)
    coder_code: str | None = None            # Primary implementation
    coder_approach: str | None = None
    qc_code: str | None = None               # QC implementation
    qc_approach: str | None = None
    qc_verdict: QCVerdict | None = None
    debug_analysis: str | None = None
    approved_code: str | None = None         # Final approved code
    approved_by: str | None = None           # "auto" or human identifier
    approved_at: str | None = None           # ISO timestamp

class AuditRecord(BaseModel, frozen=True):
    """Immutable audit trail entry."""
    timestamp: str                           # ISO 8601
    workflow_id: str
    variable: str
    action: str                              # "spec_parsed", "code_generated", "qc_compared", "human_approved", ...
    agent: str                               # "spec_interpreter", "coder", "qc", "debugger", "human"
    details: dict[str, str | int | float | bool | None] = {}
```

**Constraints:**
- All models use `frozen=True` or are immutable where possible
- Use `StrEnum` for all status fields (not raw strings)
- `DAGNode` is mutable (status changes as workflow progresses) — the only non-frozen model
- No framework imports (no PydanticAI, no pandas in this file)
- `dict[str, str | int | float | bool | None]` for AuditRecord details — no `Any`

---

## 1.3 DAG Engine

### `src/domain/dag.py` (NEW)

**Purpose:** Build a DAG from derivation rules, compute topological layers, detect cycles.

**Public functions/classes:**

```python
class DerivationDAG:
    """Dependency graph for derivation rules."""

    def __init__(self, rules: list[DerivationRule], source_columns: set[str]) -> None:
        """Build DAG from rules. source_columns are columns available in the source data."""

    @property
    def nodes(self) -> dict[str, DAGNode]:
        """Variable name → DAGNode mapping."""

    @property
    def layers(self) -> list[list[str]]:
        """Topological layers — variables in same layer have no mutual dependencies."""

    @property
    def execution_order(self) -> list[str]:
        """Flat topological order of variable names."""

    def get_node(self, variable: str) -> DAGNode:
        """Get node by variable name. Raises KeyError if not found."""

    def update_node(self, variable: str, **kwargs: ...) -> None:
        """Update node fields (status, code, verdict, etc.)."""
```

**Implementation details:**
- Use `networkx.DiGraph` internally
- For each rule, add edges from `source_columns` that match other rules' `variable` names
- Source columns that exist in the source data get no dependency edges
- Topological layers via `networkx.topological_generations()`
- Raise `ValueError("Circular dependency detected: {cycle}")` if cycle found
- Raise `ValueError("Unknown source column: {col}")` if a source_column matches neither a derivation nor a source data column

**Constraints:**
- Pure domain — imports only `networkx`, `models`
- No pandas, no PydanticAI
- `layers` property is cached after first computation

---

## 1.4 Spec Parser

### `src/domain/spec_parser.py` (NEW)

**Purpose:** Parse YAML spec file into `TransformationSpec` model. Load source data.

**Public functions:**

```python
def parse_spec(spec_path: str | Path) -> TransformationSpec:
    """Parse a YAML spec file into a TransformationSpec model.
    Raises: FileNotFoundError if path doesn't exist.
    Raises: ValidationError if YAML doesn't match schema.
    """

def load_source_data(spec: TransformationSpec) -> pd.DataFrame:
    """Load source data based on spec.source config.
    Supports: csv, xpt, parquet.
    Merges multiple domains on primary_key if >1 domain.
    Raises: FileNotFoundError if data path doesn't exist.
    Raises: ValueError if format is unsupported.
    """

def get_source_columns(df: pd.DataFrame) -> set[str]:
    """Extract column names from a DataFrame as a set."""

def generate_synthetic(df: pd.DataFrame, rows: int = 15) -> pd.DataFrame:
    """Generate a synthetic reference dataset from a real DataFrame.
    For each column:
    - Numeric: random values in [min, max] range, with some nulls
    - String/categorical: sample from unique values
    - Date strings: random dates in [min, max] range
    Synthetic data is safe to include in LLM prompts.
    """
```

**Constraints:**
- Uses `pyyaml` for YAML parsing, `pandas` for data loading
- `load_source_data` only supports CSV for now (XPT via pyreadstat is a later phase)
- `generate_synthetic` must NOT reproduce real patient values — it generates random values within observed ranges
- No PydanticAI imports

---

## 1.5 Test Fixtures + Simple Mock Spec

### `tests/__init__.py` (NEW)

Empty file.

### `tests/unit/__init__.py` (NEW)

Empty file.

### `tests/conftest.py` (NEW)

**Purpose:** Shared test fixtures for all tests.

**Fixtures to define:**

```python
@pytest.fixture
def sample_spec_path(tmp_path: Path) -> Path:
    """Write simple_mock.yaml to tmp_path and return the path."""

@pytest.fixture
def sample_spec() -> TransformationSpec:
    """Return a parsed TransformationSpec for the simple mock scenario."""

@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Return a mock patients DataFrame matching simple_mock.yaml.
    8 rows with: patient_id, age (incl. 1 null), treatment_start, treatment_end (incl. 1 null), group.
    """

@pytest.fixture
def sample_rules() -> list[DerivationRule]:
    """Return the derivation rules from the simple mock spec."""

@pytest.fixture
def sample_source_columns() -> set[str]:
    """Return the set of source column names from the mock DataFrame."""
```

**Constraints:**
- All fixtures return typed objects (not dicts)
- `sample_df` includes edge cases: 1 null age, 1 null treatment_end, mix of groups
- Fixtures are reusable across unit and integration tests

### `tests/fixtures/patients.csv` (NEW)

**Purpose:** Mock source data for simple_mock.yaml.

**Content:**
```csv
patient_id,age,treatment_start,treatment_end,group
P001,72,2024-01-15,2024-06-20,treatment
P002,45,2024-02-01,2024-07-15,treatment
P003,38,2024-01-20,2024-05-10,placebo
P004,65,2024-03-01,,placebo
P005,55,2024-02-15,2024-08-01,treatment
P006,,2024-01-10,2024-04-30,placebo
P007,15,2024-04-01,2024-09-15,treatment
P008,81,2024-01-25,2024-06-01,placebo
```

### `specs/simple_mock.yaml` (NEW)

**Purpose:** Minimal transformation spec for engine development and testing.

**Content:**
```yaml
study: simple_mock
description: "Minimal spec for engine development and testing"
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

  - variable: TREATMENT_DURATION
    source_columns: [treatment_start, treatment_end]
    logic: "Number of days between treatment_end and treatment_start plus 1 (inclusive). Null if either date is missing."
    output_type: float
    nullable: true

  - variable: IS_ELDERLY
    source_columns: [AGE_GROUP]
    logic: "True if AGE_GROUP is 'senior', False otherwise. Null if AGE_GROUP is null."
    output_type: bool

  - variable: RISK_SCORE
    source_columns: [IS_ELDERLY, TREATMENT_DURATION]
    logic: "If IS_ELDERLY is True and TREATMENT_DURATION > 120, result is 'high'. If IS_ELDERLY is True and TREATMENT_DURATION <= 120, result is 'medium'. Otherwise 'low'. Null if any source is null."
    output_type: str
    allowed_values: ["high", "medium", "low"]
```

**Why this spec:**
- 4 derivations with a 3-layer DAG: `AGE_GROUP` + `TREATMENT_DURATION` (layer 0) → `IS_ELDERLY` (layer 1) → `RISK_SCORE` (layer 2)
- Tests all dependency patterns: source-only, derived-from-derived, multi-source derived
- Tests null propagation at every level
- Tests multiple output types: str, float, bool
- Small enough to reason about manually

---

## 1.6 Unit Tests

### `tests/unit/test_models.py` (NEW)

**Tests:**
- `test_derivation_rule_frozen_raises_on_mutation` — immutability
- `test_transformation_spec_from_valid_data` — happy path construction
- `test_dag_node_status_updates` — mutable status field
- `test_workflow_step_enum_values` — all states exist
- `test_qc_verdict_enum_values` — all verdicts exist
- `test_audit_record_frozen` — immutability

### `tests/unit/test_dag.py` (NEW)

**Tests:**
- `test_build_dag_simple_linear_chain` — A→B→C, 3 layers
- `test_build_dag_parallel_layer` — A and B both layer 0, C depends on both
- `test_build_dag_from_simple_mock_spec` — the actual simple_mock spec → 3 layers
- `test_dag_layers_correct_order` — layer 0 has AGE_GROUP+TREATMENT_DURATION, layer 1 has IS_ELDERLY, layer 2 has RISK_SCORE
- `test_dag_execution_order_respects_dependencies` — RISK_SCORE comes after IS_ELDERLY
- `test_dag_cycle_detection_raises` — A→B→A raises ValueError
- `test_dag_unknown_source_column_raises` — references non-existent column
- `test_dag_update_node_status` — update node and verify

### `tests/unit/test_spec_parser.py` (NEW)

**Tests:**
- `test_parse_spec_simple_mock` — parse simple_mock.yaml, verify all fields
- `test_parse_spec_missing_file_raises` — FileNotFoundError
- `test_parse_spec_invalid_yaml_raises` — malformed YAML
- `test_load_source_data_csv` — load patients.csv, verify shape and columns
- `test_load_source_data_missing_path_raises` — FileNotFoundError
- `test_get_source_columns` — returns correct set
- `test_generate_synthetic_same_schema` — synthetic has same columns and dtypes
- `test_generate_synthetic_correct_row_count` — respects `rows` param
- `test_generate_synthetic_no_real_values` — no exact matches with real data (probabilistic but with >8 unique values per column, collision is unlikely)

**Pattern:** Follow `test_<what>_<condition>_<expected>` naming. Use fixtures from conftest.
