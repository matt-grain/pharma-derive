"""Unit tests for spec parser."""

import re
from pathlib import Path

import pandas as pd
import pytest

from src.domain.models import OutputDType, TransformationSpec
from src.domain.spec_parser import (
    generate_synthetic,
    get_source_columns,
    load_source_data,
    parse_spec,
)


def test_parse_spec_simple_mock(sample_spec_path: Path) -> None:
    spec = parse_spec(sample_spec_path)
    assert spec.metadata.study == "simple_mock"
    assert spec.metadata.version == "0.1.0"
    assert len(spec.derivations) == 4
    assert spec.derivations[0].variable == "AGE_GROUP"
    assert spec.derivations[0].output_type == OutputDType.STR
    assert spec.source.format == "csv"
    assert spec.source.primary_key == "patient_id"


def test_parse_spec_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        parse_spec("/nonexistent/path/spec.yaml")


def test_parse_spec_invalid_yaml_raises(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("not: a: valid: spec: [")
    with pytest.raises(Exception):  # noqa: B017
        parse_spec(bad_file)


def test_load_source_data_csv(sample_spec: TransformationSpec) -> None:
    df = load_source_data(sample_spec)
    assert df.shape == (8, 5)
    assert "patient_id" in df.columns
    assert "age" in df.columns


def test_load_source_data_missing_path_raises() -> None:
    from src.domain.models import SourceConfig, SpecMetadata

    spec = TransformationSpec(
        metadata=SpecMetadata(study="test", description="test"),
        source=SourceConfig(format="csv", path="/nonexistent", domains=["dm"]),
        derivations=[],
    )
    with pytest.raises(FileNotFoundError):
        load_source_data(spec)


def test_load_source_data_unsupported_format_raises(tmp_path: Path) -> None:
    from src.domain.models import SourceConfig, SpecMetadata

    spec = TransformationSpec(
        metadata=SpecMetadata(study="test", description="test"),
        source=SourceConfig(format="xlsx", path=str(tmp_path), domains=["dm"]),
        derivations=[],
    )
    with pytest.raises(ValueError, match="Unsupported source format"):
        load_source_data(spec)


def test_get_source_columns(sample_df: pd.DataFrame) -> None:
    cols = get_source_columns(sample_df)
    assert cols == {"patient_id", "age", "treatment_start", "treatment_end", "group"}


def test_generate_synthetic_same_schema(sample_df: pd.DataFrame) -> None:
    synthetic = generate_synthetic(sample_df, rows=10)
    assert list(synthetic.columns) == list(sample_df.columns)


def test_generate_synthetic_correct_row_count(sample_df: pd.DataFrame) -> None:
    synthetic = generate_synthetic(sample_df, rows=20)
    assert len(synthetic) == 20


def test_generate_synthetic_no_real_values(sample_df: pd.DataFrame) -> None:
    synthetic = generate_synthetic(sample_df, rows=50)
    # For numeric columns, verify values are within the original range
    for age in synthetic["age"].dropna():
        assert 15 <= int(age) <= 81


def test_generate_synthetic_detects_date_columns(sample_df: pd.DataFrame) -> None:
    synthetic = generate_synthetic(sample_df, rows=10)
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for val in synthetic["treatment_start"].dropna():
        assert date_pattern.match(str(val)), f"Not a valid date: {val}"
