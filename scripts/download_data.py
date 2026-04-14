"""Download CDISC Pilot Study data from the PhUSE GitHub repository.

Usage:
    uv run python scripts/download_data.py

Downloads SDTM and ADaM datasets (cdiscpilot01) into data/ directory.
Source: https://github.com/phuse-org/phuse-scripts
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/phuse-org/phuse-scripts.git"
SPARSE_PATHS = [
    "data/adam/cdiscpilot01",
    "data/sdtm/cdiscpilot01",
]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TEMP_DIR = DATA_DIR / "_phuse_clone"


def _on_rmtree_readonly(func: object, path: str, _: object) -> None:
    """shutil.rmtree onexc handler for Windows — git packfiles are read-only.

    On Windows, git writes objects inside .git/objects/pack/*.idx (and similar)
    with the read-only flag set. shutil.rmtree then fails with PermissionError
    because Windows file semantics require W permission on the FILE itself
    (not just the parent directory) for unlink. We clear the read-only bit
    and retry the same operation.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)  # type: ignore[operator]


def _rmtree_cross_platform(path: Path) -> None:
    """Delete a directory tree, handling Windows read-only git metadata."""
    if not path.exists():
        return
    shutil.rmtree(path, onexc=_on_rmtree_readonly)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:  # type: ignore[type-arg]
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, text=True, **kwargs)  # noqa: S603


def download() -> None:
    print("Downloading CDISC Pilot Study data from PhUSE GitHub...\n")

    # Clean up any previous temp clone
    _rmtree_cross_platform(TEMP_DIR)

    # Sparse checkout — only download the folders we need
    run(["git", "clone", "--filter=blob:none", "--sparse", REPO_URL, str(TEMP_DIR)])
    run(["git", "sparse-checkout", "set", *SPARSE_PATHS], cwd=str(TEMP_DIR))

    # Move data folders to final location
    for sparse_path in SPARSE_PATHS:
        src = TEMP_DIR / sparse_path
        # sparse_path is like "data/adam/cdiscpilot01" — we want data/adam/cdiscpilot01
        dest = DATA_DIR / Path(sparse_path).relative_to("data")
        dest.parent.mkdir(parents=True, exist_ok=True)
        _rmtree_cross_platform(dest)
        shutil.move(str(src), str(dest))
        file_count = len(list(dest.rglob("*")))
        print(f"  ✓ {dest.relative_to(DATA_DIR)} ({file_count} files)")

    # Clean up temp clone
    _rmtree_cross_platform(TEMP_DIR)

    print(f"\nDone. Data saved to {DATA_DIR}/")
    print("  adam/cdiscpilot01/ — ADaM ground truth (ADSL, ADAE, ADLBC, ...)")
    print("  sdtm/cdiscpilot01/ — SDTM input (DM, EX, LB, VS, ...)")


if __name__ == "__main__":
    try:
        download()
    except subprocess.CalledProcessError as e:
        print(f"\nError: {e}", file=sys.stderr)
        print("Make sure git is installed and you have internet access.", file=sys.stderr)
        sys.exit(1)
