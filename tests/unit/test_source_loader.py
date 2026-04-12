"""Unit tests for source_loader — get_column_domain_map and get_source_columns."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers — build a minimal TransformationSpec pointing at tmp_path
# ---------------------------------------------------------------------------


def _make_csv_spec(tmp_path: Path, domains: list[str]) -> object:
    """Return a TransformationSpec with CSV source pointing at tmp_path."""
    from src.domain.models import (
        DerivationRule,
        OutputDType,
        SourceConfig,
        SpecMetadata,
        SyntheticConfig,
        TransformationSpec,
        ValidationConfig,
    )

    return TransformationSpec(
        metadata=SpecMetadata(study="test", description="test spec"),
        source=SourceConfig(format="csv", path=str(tmp_path), domains=domains),
        synthetic=SyntheticConfig(),
        validation=ValidationConfig(),
        derivations=[
            DerivationRule(
                variable="DUMMY",
                source_columns=["COL_A"],
                logic="passthrough",
                output_type=OutputDType.STR,
            )
        ],
    )


# ---------------------------------------------------------------------------
# get_column_domain_map — happy paths
# ---------------------------------------------------------------------------


def test_get_column_domain_map_single_domain_csv_returns_expected_map(tmp_path: Path) -> None:
    """Single CSV domain produces correct {column: domain} mapping."""
    # Arrange
    (tmp_path / "dm.csv").write_text("USUBJID,AGE,SEX\n001,45,M\n")
    spec = _make_csv_spec(tmp_path, domains=["dm"])

    # Act
    from src.domain.source_loader import get_column_domain_map

    result = get_column_domain_map(spec)  # type: ignore[arg-type]

    # Assert
    assert result == {"USUBJID": "dm", "AGE": "dm", "SEX": "dm"}


def test_get_column_domain_map_multiple_domains_csv_returns_all_columns(tmp_path: Path) -> None:
    """Multiple CSV domains are merged; each column maps to its source domain."""
    # Arrange
    (tmp_path / "dm.csv").write_text("USUBJID,AGE\n001,45\n")
    (tmp_path / "ex.csv").write_text("USUBJID,EXTRT,EXDOSE\n001,DRUG,10\n")
    spec = _make_csv_spec(tmp_path, domains=["dm", "ex"])

    # Act
    from src.domain.source_loader import get_column_domain_map

    result = get_column_domain_map(spec)  # type: ignore[arg-type]

    # Assert
    assert result["AGE"] == "dm"
    assert result["EXTRT"] == "ex"
    assert result["EXDOSE"] == "ex"
    # USUBJID appears in both — later domain (ex) wins
    assert result["USUBJID"] == "ex"


def test_get_column_domain_map_missing_domain_file_is_tolerated(tmp_path: Path) -> None:
    """Missing domain files are skipped without raising — remaining domains are still mapped."""
    # Arrange — only dm.csv exists; ds.csv is absent
    (tmp_path / "dm.csv").write_text("USUBJID,AGE\n001,45\n")
    spec = _make_csv_spec(tmp_path, domains=["dm", "ds"])

    # Act
    from src.domain.source_loader import get_column_domain_map

    result = get_column_domain_map(spec)  # type: ignore[arg-type]

    # Assert — dm columns present; no crash for missing ds
    assert "AGE" in result
    assert result["AGE"] == "dm"


def test_get_column_domain_map_reads_header_only_not_data(tmp_path: Path) -> None:
    """get_column_domain_map returns correct column count without loading data rows."""
    # Arrange — 100-row file; only headers should be read
    rows = "\n".join(f"P{i},{i}" for i in range(100))
    (tmp_path / "dm.csv").write_text(f"USUBJID,AGE\n{rows}\n")
    spec = _make_csv_spec(tmp_path, domains=["dm"])

    # Act
    from src.domain.source_loader import get_column_domain_map

    result = get_column_domain_map(spec)  # type: ignore[arg-type]

    # Assert — still exactly 2 columns mapped
    assert len(result) == 2


# ---------------------------------------------------------------------------
# get_column_domain_map — error paths
# ---------------------------------------------------------------------------


def test_get_column_domain_map_missing_base_path_raises_file_not_found(tmp_path: Path) -> None:
    """FileNotFoundError is raised when the source base path does not exist."""
    # Arrange — point spec at a directory that does not exist
    nonexistent = tmp_path / "nonexistent_dir"
    from src.domain.models import (
        DerivationRule,
        OutputDType,
        SourceConfig,
        SpecMetadata,
        SyntheticConfig,
        TransformationSpec,
        ValidationConfig,
    )

    spec = TransformationSpec(
        metadata=SpecMetadata(study="test", description="test"),
        source=SourceConfig(format="csv", path=str(nonexistent), domains=["dm"]),
        synthetic=SyntheticConfig(),
        validation=ValidationConfig(),
        derivations=[
            DerivationRule(variable="X", source_columns=["Y"], logic="passthrough", output_type=OutputDType.STR)
        ],
    )

    # Act & Assert
    from src.domain.source_loader import get_column_domain_map

    with pytest.raises(FileNotFoundError, match="Source data path not found"):
        get_column_domain_map(spec)  # type: ignore[arg-type]


def test_get_column_domain_map_unsupported_format_raises_value_error(tmp_path: Path) -> None:
    """ValueError is raised for an unrecognised source format."""
    # Arrange
    from src.domain.models import (
        DerivationRule,
        OutputDType,
        SourceConfig,
        SpecMetadata,
        SyntheticConfig,
        TransformationSpec,
        ValidationConfig,
    )

    spec = TransformationSpec(
        metadata=SpecMetadata(study="test", description="test"),
        source=SourceConfig(format="sas7bdat", path=str(tmp_path), domains=["dm"]),
        synthetic=SyntheticConfig(),
        validation=ValidationConfig(),
        derivations=[
            DerivationRule(variable="X", source_columns=["Y"], logic="passthrough", output_type=OutputDType.STR)
        ],
    )

    # Act & Assert
    from src.domain.source_loader import get_column_domain_map

    with pytest.raises(ValueError, match="Unsupported source format"):
        get_column_domain_map(spec)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# get_source_columns — unchanged function, sanity check
# ---------------------------------------------------------------------------


def test_get_source_columns_returns_column_names_as_set() -> None:
    """get_source_columns returns a set of column names from a DataFrame."""
    # Arrange
    import pandas as pd

    from src.domain.source_loader import get_source_columns

    df = pd.DataFrame({"A": [1], "B": [2], "C": [3]})

    # Act
    result = get_source_columns(df)

    # Assert
    assert result == {"A", "B", "C"}
