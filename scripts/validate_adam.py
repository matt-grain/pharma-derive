"""Validate derived ADaM output against CDISC ground truth.

Compares the derived CSV from a workflow run against the official ADaM XPT file.
Reports match/mismatch per variable with row-level statistics.

Usage:
    uv run python scripts/validate_adam.py output/<workflow_id>_adam.csv
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

import pandas as pd
import pyreadstat  # type: ignore[import-untyped]


def load_ground_truth(xpt_path: str | Path) -> pd.DataFrame:
    """Load the official ADaM XPT file."""
    path = Path(xpt_path)
    if not path.exists():
        print(f"Ground truth not found: {path}")
        sys.exit(1)
    return cast("pd.DataFrame", pyreadstat.read_xport(str(path))[0])  # type: ignore[no-untyped-call]


def compare_variable(
    derived: pd.Series[object],
    truth: pd.Series[object],
    variable: str,
) -> dict[str, object]:
    """Compare a single derived variable against ground truth."""
    both_null = derived.isna() & truth.isna()
    if pd.api.types.is_numeric_dtype(truth):
        matches = both_null | ((derived - truth).abs() <= 0.01)  # type: ignore[operator]
    else:
        matches = both_null | (derived.astype(str) == truth.astype(str))

    match_mask = matches.fillna(False)
    n_match = int(match_mask.sum())
    n_total = len(derived)
    n_mismatch = n_total - n_match

    return {
        "variable": variable,
        "total": n_total,
        "match": n_match,
        "mismatch": n_mismatch,
        "match_rate": round(n_match / max(n_total, 1) * 100, 1),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/validate_adam.py output/<workflow_id>_adam.csv")
        print("       uv run python scripts/validate_adam.py <csv> data/adam/cdiscpilot01/adsl.xpt")
        return 1

    derived_path = Path(sys.argv[1])
    if not derived_path.exists():
        print(f"Derived file not found: {derived_path}")
        return 1

    # Default ground truth for CDISC pilot
    gt_path = sys.argv[2] if len(sys.argv) > 2 else "data/adam/cdiscpilot01/adsl.xpt"

    print(f"Derived:      {derived_path}")
    print(f"Ground truth: {gt_path}")
    print()

    derived_df = pd.read_csv(derived_path)
    truth_df = load_ground_truth(gt_path)

    # Find derived variables (columns in derived that are not in the original SDTM)
    # The derived CSV has source + derived columns; ground truth has all ADaM columns
    # We compare only columns that exist in both
    common = [c for c in derived_df.columns if c in truth_df.columns]
    derived_only = [c for c in derived_df.columns if c not in truth_df.columns]

    if not common:
        print("No common columns found between derived and ground truth.")
        return 1

    # Merge on USUBJID
    key = "USUBJID"
    if key not in derived_df.columns or key not in truth_df.columns:
        print(f"Key column '{key}' not found in both datasets.")
        return 1

    truth_cols = [key] + [c for c in common if c != key]
    merged = derived_df.merge(truth_df[truth_cols], on=key, suffixes=("_derived", "_truth"))

    print(f"Subjects: {len(merged)} (derived: {len(derived_df)}, truth: {len(truth_df)})")
    print(f"Common variables: {len(common) - 1}")  # minus key
    print(f"Derived-only variables: {derived_only}")
    print()

    # Compare each common variable
    results = []
    for col in common:
        if col == key:
            continue
        d_col = f"{col}_derived" if f"{col}_derived" in merged.columns else col
        t_col = f"{col}_truth" if f"{col}_truth" in merged.columns else col
        if d_col not in merged.columns or t_col not in merged.columns:
            continue
        result = compare_variable(merged[d_col], merged[t_col], col)
        results.append(result)

    # Report
    print(f"{'Variable':<25s} {'Total':>6s} {'Match':>6s} {'Mismatch':>9s} {'Rate':>7s}")
    print("-" * 55)
    total_match = 0
    total_cells = 0
    for r in results:
        status = "✅" if r["mismatch"] == 0 else "❌"
        name, total, match, mismatch, rate = r["variable"], r["total"], r["match"], r["mismatch"], r["match_rate"]
        print(f"{status} {name:<23s} {total:>6d} {match:>6d} {mismatch:>9d} {rate:>6.1f}%")
        total_match += int(r["match"])
        total_cells += int(r["total"])

    print("-" * 55)
    overall = round(total_match / max(total_cells, 1) * 100, 1)
    print(f"{'OVERALL':<25s} {total_cells:>6d} {total_match:>6d} {total_cells - total_match:>9d} {overall:>6.1f}%")

    return 0 if all(r["mismatch"] == 0 for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
