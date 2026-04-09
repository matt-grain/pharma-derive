"""Pre-commit check: Engine layer must not contain SQL or direct DB access.

engine/ files should use repositories (injected via DI), never raw SQL or SQLAlchemy sessions.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker

FORBIDDEN_IMPORTS = {
    "sqlalchemy",
    "sqlite3",
    "asyncpg",
    "aiosqlite",
}

SQL_PATTERNS = ["SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE TABLE"]


class RawSQLChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in FORBIDDEN_IMPORTS:
                self.violations.append(
                    Violation(self.file_path, node.lineno, f"DB import '{alias.name}' in engine — use repository DI")
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            root = node.module.split(".")[0]
            if root in FORBIDDEN_IMPORTS:
                self.violations.append(
                    Violation(
                        self.file_path, node.lineno, f"DB import 'from {node.module}' in engine — use repository DI"
                    )
                )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            upper = node.value.upper().strip()
            for pattern in SQL_PATTERNS:
                if upper.startswith(pattern):
                    self.violations.append(
                        Violation(self.file_path, node.lineno, f"Raw SQL string in engine: '{node.value[:40]}...'")
                    )
                    break
        self.generic_visit(node)


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    checker = RawSQLChecker(file_path)
    checker.visit(tree)
    return checker.violations


def main() -> int:
    engine_dir = Path("src/engine")
    if not engine_dir.exists():
        print("src/engine/ directory not found")
        return 1
    return run_checker(check_file, iter_python_files(engine_dir), "No raw SQL/DB access in engine layer")


if __name__ == "__main__":
    sys.exit(main())
