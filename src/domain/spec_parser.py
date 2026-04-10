"""Spec parser — parse YAML spec files into TransformationSpec models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.domain.models import (
    DerivationRule,
    GroundTruthConfig,
    SourceConfig,
    SpecMetadata,
    SyntheticConfig,
    ToleranceConfig,
    TransformationSpec,
    ValidationConfig,
)


def parse_spec(spec_path: str | Path) -> TransformationSpec:
    """Parse a YAML spec file into a TransformationSpec model."""
    path = Path(spec_path)
    if not path.exists():
        msg = f"Spec file not found: {path}"
        raise FileNotFoundError(msg)

    with path.open() as f:
        loaded: object = yaml.safe_load(f)

    if not isinstance(loaded, dict):
        msg = f"Invalid spec format: expected a YAML mapping, got {type(loaded).__name__}"
        raise ValueError(msg)

    raw: dict[str, Any] = dict(loaded)  # type: ignore[arg-type]  # YAML safe_load returns untyped dict

    metadata = SpecMetadata(
        study=raw["study"],
        description=raw["description"],
        version=raw.get("version", "0.1.0"),
        author=raw.get("author", ""),
    )
    source = SourceConfig(**raw["source"])

    synthetic = SyntheticConfig(**raw["synthetic"]) if "synthetic" in raw else SyntheticConfig()

    validation = ValidationConfig()
    if "validation" in raw:
        val_raw: dict[str, Any] = raw["validation"]
        gt = GroundTruthConfig(**val_raw["ground_truth"]) if "ground_truth" in val_raw else None
        tol = ToleranceConfig(**val_raw["tolerance"]) if "tolerance" in val_raw else ToleranceConfig()
        validation = ValidationConfig(ground_truth=gt, tolerance=tol)

    derivations = [DerivationRule(**d) for d in raw["derivations"]]

    return TransformationSpec(
        metadata=metadata,
        source=source,
        synthetic=synthetic,
        validation=validation,
        derivations=derivations,
    )
