"""Integration tests for CDISC pilot data loading and DAG construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.dag import DerivationDAG
from src.domain.source_loader import get_source_columns, load_source_data
from src.domain.spec_parser import parse_spec
from src.domain.synthetic import generate_synthetic

_ADSL_SPEC = Path("specs/adsl_cdiscpilot01.yaml")
_CDISC_DATA = Path("data/sdtm/cdiscpilot01")
_SKIP_NO_DATA = pytest.mark.skipif(
    not _CDISC_DATA.exists(), reason="CDISC data not downloaded (run scripts/download_data.py)"
)


def test_adsl_spec_parses_successfully() -> None:
    """Parse the real ADSL spec and verify 7 derivation rules."""
    # Act
    spec = parse_spec(_ADSL_SPEC)

    # Assert
    assert spec.metadata.study == "cdiscpilot01"
    assert len(spec.derivations) == 7
    variables = [d.variable for d in spec.derivations]
    assert "AGEGR1" in variables
    assert "TRTDUR" in variables
    assert "SAFFL" in variables
    assert "DISCONFL" in variables
    assert "DURDIS" in variables


@_SKIP_NO_DATA
def test_adsl_source_loads_all_domains() -> None:
    """Load source data from 4 SDTM domains and verify key columns exist."""
    # Arrange
    spec = parse_spec(_ADSL_SPEC)

    # Act
    df = load_source_data(spec)

    # Assert
    assert len(df) > 0
    assert "USUBJID" in df.columns
    assert "AGE" in df.columns
    assert "RFXSTDTC" in df.columns
    # DS domain columns should be present after merge
    assert "DSDECOD" in df.columns


@_SKIP_NO_DATA
def test_adsl_dag_builds_correct_layers() -> None:
    """Build DAG from ADSL spec and verify layer ordering."""
    # Arrange
    spec = parse_spec(_ADSL_SPEC)
    df = load_source_data(spec)
    source_cols = get_source_columns(df)

    # Act
    dag = DerivationDAG(spec.derivations, source_cols)

    # Assert
    layers = dag.layers
    assert len(layers) >= 2
    # AGEGR1, TRTDUR, SAFFL, ITTFL, DISCONFL, DURDIS — all source from SDTM columns → layer 0
    layer0_vars = set(layers[0])
    assert "AGEGR1" in layer0_vars
    assert "TRTDUR" in layer0_vars
    # EFFFL depends on ITTFL + SAFFL → must be in a later layer
    efffl_layer = next(i for i, layer in enumerate(layers) if "EFFFL" in layer)
    assert efffl_layer > 0


@_SKIP_NO_DATA
def test_adsl_synthetic_generates_correct_shape() -> None:
    """Generate synthetic dataset from loaded CDISC source data."""
    # Arrange
    spec = parse_spec(_ADSL_SPEC)
    df = load_source_data(spec)

    # Act
    synthetic = generate_synthetic(df, rows=15)

    # Assert
    assert len(synthetic) == 15
    assert set(synthetic.columns) == set(df.columns)
