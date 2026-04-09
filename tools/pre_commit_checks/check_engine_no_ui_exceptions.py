"""Pre-commit check: Engine layer must not raise UI exceptions.

The orchestrator/engine must raise domain exceptions (e.g., WorkflowError,
DerivationError) — never Streamlit, FastAPI, or any presentation-tier exception.
The UI layer catches domain exceptions and maps them to user-facing messages.

Forbidden patterns in src/engine/**/*.py:
- import streamlit / from streamlit import ...
- from fastapi import HTTPException
- raise HTTPException(...)
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker

FORBIDDEN_UI_MODULES = {"streamlit", "fastapi", "fastapi.exceptions", "starlette.exceptions"}


class EngineUIExceptionChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in ("streamlit", "fastapi", "starlette"):
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        f"UI framework import '{alias.name}' in engine/ — raise domain exceptions instead",
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.module in FORBIDDEN_UI_MODULES:
            for alias in node.names:
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        f"UI import 'from {node.module} import {alias.name}' in engine/ — raise domain exceptions",
                    )
                )
        if node.module and node.module.startswith("streamlit"):
            self.violations.append(
                Violation(
                    self.file_path,
                    node.lineno,
                    "Streamlit import in engine/ — UI belongs in ui/ only",
                )
            )
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        if (
            node.exc
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "HTTPException"
        ):
            self.violations.append(
                Violation(
                    self.file_path,
                    node.lineno,
                    "raise HTTPException in engine/ — raise domain exceptions (e.g., WorkflowError)",
                )
            )
        self.generic_visit(node)


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    checker = EngineUIExceptionChecker(file_path)
    checker.visit(tree)
    return checker.violations


def main() -> int:
    engine_dir = Path("src/engine")
    if not engine_dir.exists():
        print("src/engine/ directory not found")
        return 1
    return run_checker(check_file, iter_python_files(engine_dir), "No UI exceptions in engine layer")


if __name__ == "__main__":
    sys.exit(main())
