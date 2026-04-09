"""Pre-commit check: Datetime pattern enforcement for audit trail integrity.

Clinical audit timestamps must be timezone-aware and consistent.
A naive datetime on a drug approval record is a regulatory risk.

Forbidden patterns in src/**/*.py:
- datetime.utcnow()      → deprecated since Python 3.12
- datetime.now()          → use datetime.now(timezone.utc)
- .replace(tzinfo=None)   → stripping timezone from audit timestamps
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker

ALLOWED_FILES = ["test_"]


class DatetimePatternChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []

    def _is_allowed(self) -> bool:
        return any(a in self.file_path.name for a in ALLOWED_FILES)

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_allowed():
            self.generic_visit(node)
            return

        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "datetime":
                if node.func.attr == "utcnow":
                    self.violations.append(
                        Violation(
                            self.file_path,
                            node.lineno,
                            "datetime.utcnow() is deprecated — use datetime.now(timezone.utc)",
                        )
                    )
                elif node.func.attr == "now" and not node.args and not node.keywords:
                    self.violations.append(
                        Violation(
                            self.file_path,
                            node.lineno,
                            "datetime.now() without timezone — use datetime.now(timezone.utc)",
                        )
                    )

            if node.func.attr == "replace":
                for kw in node.keywords:
                    if kw.arg == "tzinfo" and isinstance(kw.value, ast.Constant) and kw.value.value is None:
                        self.violations.append(
                            Violation(
                                self.file_path,
                                node.lineno,
                                ".replace(tzinfo=None) strips timezone — forbidden for audit timestamps",
                            )
                        )

        self.generic_visit(node)


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    checker = DatetimePatternChecker(file_path)
    checker.visit(tree)
    return checker.violations


def main() -> int:
    src_dir = Path("src")
    if not src_dir.exists():
        print("src/ directory not found")
        return 1
    return run_checker(check_file, iter_python_files(src_dir), "Datetime pattern enforcement (audit integrity)")


if __name__ == "__main__":
    sys.exit(main())
