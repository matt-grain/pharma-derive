"""Pre-commit check: LLM gateway enforcement — no direct model construction.

All LLM model/provider instantiation must go through engine/llm_gateway.py.
Direct imports of pydantic_ai.models.openai or pydantic_ai.providers.openai
outside the gateway are forbidden.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker

FORBIDDEN_MODULES = {
    "pydantic_ai.models.openai",
    "pydantic_ai.providers.openai",
}


class LLMGatewayChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if any(alias.name.startswith(mod) for mod in FORBIDDEN_MODULES):
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        f"Direct LLM import '{alias.name}' — use llm_gateway instead",
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and any(node.module.startswith(mod) for mod in FORBIDDEN_MODULES):
            self.violations.append(
                Violation(
                    self.file_path,
                    node.lineno,
                    f"Direct LLM import 'from {node.module}' — use llm_gateway instead",
                )
            )
        self.generic_visit(node)


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    checker = LLMGatewayChecker(file_path)
    checker.visit(tree)
    return checker.violations


def main() -> int:
    dirs = [Path("src/agents"), Path("src/engine")]
    files: list[Path] = []
    for d in dirs:
        if d.exists():
            files.extend(f for f in iter_python_files(d) if f.name != "llm_gateway.py")

    if not files:
        print("No files to check (src/agents/ and src/engine/ not found)")
        return 0

    files.sort()
    return run_checker(check_file, files, "LLM gateway enforcement (no direct model construction)")


if __name__ == "__main__":
    sys.exit(main())
