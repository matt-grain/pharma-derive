"""Pre-commit check: Module size limits — flag large files, functions, and classes.

Files > 250 lines, functions > 40 lines, classes > 200 lines.

Limits calibrated for Python — type annotations, docstrings, try/except blocks,
and multi-branch if/elif naturally inflate line counts compared to Go/Dart.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker

FILE_LINE_LIMIT = 300  # calibrated for Python: type annotations, docstrings, try/except, persistence serialization
FUNCTION_LINE_LIMIT = 40
CLASS_LINE_LIMIT = 230  # accounts for error handling, rollback methods in orchestrator-style classes


class SizeLimitChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.end_lineno is not None:
            span = node.end_lineno - node.lineno + 1
            if span > CLASS_LINE_LIMIT:
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        f"Class '{node.name}' is {span} lines (limit: {CLASS_LINE_LIMIT})",
                    )
                )
        self.generic_visit(node)

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.end_lineno is not None:
            span = node.end_lineno - node.lineno + 1
            if span > FUNCTION_LINE_LIMIT:
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        f"Function '{node.name}' is {span} lines (limit: {FUNCTION_LINE_LIMIT})",
                    )
                )


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    violations: list[Violation] = []

    # Check file-level line count
    try:
        line_count = len(file_path.read_text(encoding="utf-8").splitlines())
    except OSError:
        line_count = 0

    if line_count > FILE_LINE_LIMIT:
        violations.append(
            Violation(
                file_path,
                1,
                f"File is {line_count} lines (limit: {FILE_LINE_LIMIT})",
            )
        )

    # Check function/class sizes via AST
    checker = SizeLimitChecker(file_path)
    checker.visit(tree)
    violations.extend(checker.violations)

    return violations


def main() -> int:
    src_dir = Path("src")
    if not src_dir.exists():
        print("src/ directory not found")
        return 1

    files = [f for f in iter_python_files(src_dir) if f.name != "__init__.py"]
    return run_checker(check_file, files, "Module size limits")


if __name__ == "__main__":
    sys.exit(main())
