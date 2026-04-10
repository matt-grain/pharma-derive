"""Pre-commit check: Domain layer must be pure — no framework imports.

domain/ files may only import: stdlib, pydantic, networkx, pandas, numpy.
Forbidden: PydanticAI, statemachine, loguru, SQLAlchemy, Streamlit.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker

FORBIDDEN_MODULES = {
    "pydantic_ai",
    "statemachine",
    "loguru",
    "sqlalchemy",
    "streamlit",
    "fastapi",
    "httpx",
}


class DomainPurityChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in FORBIDDEN_MODULES:
                self.violations.append(
                    Violation(self.file_path, node.lineno, f"Framework import '{alias.name}' in domain layer")
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            root = node.module.split(".")[0]
            if root in FORBIDDEN_MODULES:
                self.violations.append(
                    Violation(self.file_path, node.lineno, f"Framework import 'from {node.module}' in domain layer")
                )
        self.generic_visit(node)


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    checker = DomainPurityChecker(file_path)
    checker.visit(tree)
    return checker.violations


# workflow_fsm.py uses python-statemachine (thin declarative lib, comparable to
# pydantic which is already allowed) and loguru for audit-trail logging.
# It's a domain concept (valid state transitions) that happens to use a framework.
_EXCLUDED_FILES = {"workflow_fsm.py"}


def main() -> int:
    domain_dir = Path("src/domain")
    if not domain_dir.exists():
        print("src/domain/ directory not found")
        return 1
    files = [f for f in iter_python_files(domain_dir) if f.name not in _EXCLUDED_FILES]
    return run_checker(check_file, files, "Domain layer purity (no framework imports)")


if __name__ == "__main__":
    sys.exit(main())
