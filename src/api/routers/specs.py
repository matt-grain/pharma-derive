"""Specs endpoint — list available transformation specifications."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter

from src.api.schemas import SpecListItem

router = APIRouter(prefix="/api/v1/specs", tags=["specs"])


@router.get("/", response_model=list[SpecListItem], status_code=200)
async def list_specs() -> list[SpecListItem]:
    """List available YAML specs in the specs/ directory."""
    specs_dir = Path("specs")
    if not specs_dir.exists():
        return []
    items: list[SpecListItem] = []
    for path in sorted(specs_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            # Spec YAML has study/description at top level, or nested under metadata
            meta = data.get("metadata", {})
            derivations = data.get("derivations", [])
            items.append(
                SpecListItem(
                    filename=path.name,
                    study=data.get("study") or meta.get("study", "unknown"),
                    description=data.get("description") or meta.get("description", ""),
                    derivation_count=len(derivations),
                )
            )
        except (yaml.YAMLError, KeyError, OSError):
            continue  # skip malformed specs
    return items
