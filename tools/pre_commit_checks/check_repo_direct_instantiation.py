"""Pre-commit check: No direct repository instantiation outside wiring code.

Repositories must be injected via constructor DI, never instantiated directly
in engine/, agents/, verification/, or audit/ code. Direct instantiation
bypasses the abstraction layer and couples code to a specific database.

Allowed locations for Repository():
- src/persistence/ (the repos themselves)
- tests/ (test fixtures create repos with test sessions)
- main.py / dependencies.py (DI wiring)

Forbidden in: src/engine/, src/agents/, src/verification/, src/audit/, src/domain/
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker

REPO_CLASS_SUFFIXES = ("Repository",)

FORBIDDEN_LAYERS = ("domain", "agents", "engine", "verification", "audit")


class RepoInstantiationChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []
        self._layer = _get_layer(file_path)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            name = node.func.name if hasattr(node.func, "name") else node.func.id
            if any(name.endswith(suffix) for suffix in REPO_CLASS_SUFFIXES):
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        f"Direct instantiation of '{name}' in {self._layer}/ — inject via constructor DI",
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and "persistence" in node.module:
            for alias in node.names:
                name = alias.name
                if any(name.endswith(suffix) for suffix in REPO_CLASS_SUFFIXES):
                    self.violations.append(
                        Violation(
                            self.file_path,
                            node.lineno,
                            f"Importing '{name}' from persistence in {self._layer}/ — accept repos via constructor DI",
                        )
                    )
        self.generic_visit(node)


def _get_layer(path: Path) -> str:
    parts = path.parts
    for layer in FORBIDDEN_LAYERS:
        if layer in parts:
            return layer
    return "unknown"


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    checker = RepoInstantiationChecker(file_path)
    checker.visit(tree)
    return checker.violations


def main() -> int:
    layers = [Path(f"src/{layer}") for layer in FORBIDDEN_LAYERS]
    existing = [d for d in layers if d.exists()]
    if not existing:
        print("No source layer directories found")
        return 1

    files: list[Path] = []
    for layer_dir in existing:
        files.extend(iter_python_files(layer_dir))

    return run_checker(check_file, files, "No direct repository instantiation outside wiring code")


if __name__ == "__main__":
    sys.exit(main())
