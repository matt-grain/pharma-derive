"""Pre-commit check: Enum discipline — catch raw string comparisons against known enum values.

Comparisons like `status == "match"` should use `QCVerdict.MATCH` instead.
Excludes: __init__.py, models.py (enum definitions), test files,
and `.value ==` patterns in src/persistence/ (ORM boundary).
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker

# Known enum values that must not appear as raw string comparisons
KNOWN_ENUM_VALUES: frozenset[str] = frozenset(
    {
        "match",
        "mismatch",
        "coder",
        "qc",
        "neither",
        "high",
        "medium",
        "low",
        "needs_debug",
        "auto_approve",
        "insufficient_independence",
        "completed",
        "failed",
        "pending",
        "in_progress",
        "qc_pass",
        "qc_mismatch",
        "approved",
        "spec_parsed",
        "derivation_complete",
        "audit_complete",
    }
)

# Map of known enum values to their enum class + member name (for messages)
ENUM_SUGGESTIONS: dict[str, str] = {
    "match": "QCVerdict.MATCH",
    "mismatch": "QCVerdict.MISMATCH",
    "coder": "TrustDecision.TRUST_CODER",
    "qc": "TrustDecision.TRUST_QC",
    "neither": "TrustDecision.TRUST_NEITHER",
    "high": "Confidence.HIGH",
    "medium": "Confidence.MEDIUM",
    "low": "Confidence.LOW",
    "needs_debug": "TrustDecision.NEEDS_DEBUG",
    "auto_approve": "TrustDecision.AUTO_APPROVE",
    "insufficient_independence": "TrustDecision.INSUFFICIENT_INDEPENDENCE",
    "completed": "DerivationStatus.COMPLETED / WorkflowState (check context)",
    "failed": "DerivationStatus.FAILED / WorkflowState (check context)",
    "pending": "DerivationStatus.PENDING / WorkflowState (check context)",
    "in_progress": "DerivationStatus.IN_PROGRESS",
    "qc_pass": "DerivationStatus.QC_PASS",
    "qc_mismatch": "DerivationStatus.QC_MISMATCH",
    "approved": "DerivationStatus.APPROVED",
    "spec_parsed": "WorkflowState (check context)",
    "derivation_complete": "WorkflowState (check context)",
    "audit_complete": "WorkflowState (check context)",
}


def _is_dot_value_comparison(node: ast.Compare) -> bool:
    """Check if this is a `.value == "..."` pattern (ORM boundary, legitimate)."""
    left = node.left
    if isinstance(left, ast.Attribute) and left.attr == "value":
        return True
    return any(isinstance(comparator, ast.Attribute) and comparator.attr == "value" for comparator in node.comparators)


class EnumDisciplineChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path, is_persistence: bool) -> None:
        self.file_path = file_path
        self.is_persistence = is_persistence
        self.violations: list[Violation] = []
        self._in_strenum_init = False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Check if this class inherits from StrEnum
        is_strenum = any(
            (isinstance(base, ast.Name) and base.id == "StrEnum")
            or (isinstance(base, ast.Attribute) and base.attr == "StrEnum")
            for base in node.bases
        )
        if is_strenum:
            # Skip entire StrEnum class body — assignments like MATCH = "match" are fine
            return
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        # Skip `.value ==` patterns in persistence layer
        if self.is_persistence and _is_dot_value_comparison(node):
            self.generic_visit(node)
            return

        # Collect all constant strings in the comparison
        string_constants: list[tuple[int, str]] = []

        if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
            string_constants.append((node.lineno, node.left.value))

        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                string_constants.append((node.lineno, comparator.value))

        for lineno, value in string_constants:
            if value in KNOWN_ENUM_VALUES:
                suggestion = ENUM_SUGGESTIONS.get(value, "the appropriate enum member")
                self.violations.append(
                    Violation(
                        self.file_path,
                        lineno,
                        f'Raw string "{value}" in comparison — use {suggestion} instead',
                    )
                )

        self.generic_visit(node)


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    is_persistence = "persistence" in file_path.parts
    checker = EnumDisciplineChecker(file_path, is_persistence)
    checker.visit(tree)
    return checker.violations


def main() -> int:
    src_dir = Path("src")
    if not src_dir.exists():
        print("src/ directory not found")
        return 1

    excluded_names = {"__init__.py", "models.py"}
    files = [f for f in iter_python_files(src_dir) if f.name not in excluded_names]

    return run_checker(check_file, files, "Enum discipline (no raw string comparisons)")


if __name__ == "__main__":
    sys.exit(main())
