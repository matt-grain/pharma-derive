"""Pre-commit check: Domain, agents, verification, and audit layers must not raise UI exceptions.

These layers must raise domain-specific exceptions only. UI-tier exceptions
(Streamlit, FastAPI) belong in the UI/API layer. Catching this early prevents
tight coupling between core logic and presentation framework.

Forbidden patterns in src/{domain,agents,verification,audit}/**/*.py:
- import streamlit / from streamlit import ...
- from fastapi import HTTPException
- from fastapi.exceptions import HTTPException
- raise HTTPException(...)
- raise st.error(...) or any streamlit call used as error handling
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker

FORBIDDEN_UI_MODULES = {"streamlit", "fastapi", "fastapi.exceptions", "starlette.exceptions"}


class UIExceptionChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []
        self._layer = _get_layer(file_path)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in ("streamlit", "fastapi", "starlette"):
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        f"UI framework import '{alias.name}' in {self._layer}/ — use domain exceptions",
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
                        f"UI import 'from {node.module} import {alias.name}' in {self._layer}/ — use domain exceptions",
                    )
                )
        if node.module and node.module.startswith("streamlit"):
            self.violations.append(
                Violation(
                    self.file_path,
                    node.lineno,
                    f"Streamlit import 'from {node.module}' in {self._layer}/ — UI belongs in ui/ only",
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
                    f"raise HTTPException in {self._layer}/ — raise domain exceptions instead",
                )
            )
        self.generic_visit(node)


def _get_layer(path: Path) -> str:
    parts = path.parts
    for layer in ("domain", "agents", "verification", "audit"):
        if layer in parts:
            return layer
    return "unknown"


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    checker = UIExceptionChecker(file_path)
    checker.visit(tree)
    return checker.violations


def main() -> int:
    layers = [Path(f"src/{layer}") for layer in ("domain", "agents", "verification", "audit")]
    existing = [d for d in layers if d.exists()]
    if not existing:
        print("No domain/agents/verification/audit directories found")
        return 1

    files: list[Path] = []
    for layer_dir in existing:
        files.extend(iter_python_files(layer_dir))

    return run_checker(check_file, files, "No UI exceptions in domain/agents/verification/audit layers")


if __name__ == "__main__":
    sys.exit(main())
