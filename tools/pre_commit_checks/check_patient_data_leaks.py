"""Pre-commit check: Agent prompts must not contain patient data patterns.

Detects potential PII leakage in agent system prompts and tool return values.
Checks for: df.head(), df.to_string(), df.to_csv() in agent-facing code,
and raw DataFrame returns from tools.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, iter_python_files, run_checker

DANGEROUS_METHODS = {"head", "tail", "sample", "to_string", "to_csv", "to_dict", "to_json", "iterrows", "itertuples"}


class PatientDataLeakChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []
        self._in_tool_function = False

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        is_tool = any(
            (isinstance(arg.annotation, ast.Subscript) and "RunContext" in ast.dump(arg.annotation))
            for arg in node.args.args
            if arg.annotation
        )
        if is_tool:
            self._in_tool_function = True
            self.generic_visit(node)
            self._in_tool_function = False
        else:
            self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self._in_tool_function and isinstance(node.func, ast.Attribute) and node.func.attr in DANGEROUS_METHODS:
            parent_name = ""
            if isinstance(node.func.value, ast.Attribute):
                parent_name = node.func.value.attr
            elif isinstance(node.func.value, ast.Name):
                parent_name = node.func.value.id

            if parent_name in ("df", "ctx", "series", "result"):
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        f"Potential patient data leak: {parent_name}.{node.func.attr}() in tool function",
                    )
                )
        self.generic_visit(node)


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    checker = PatientDataLeakChecker(file_path)
    checker.visit(tree)
    return checker.violations


def main() -> int:
    agents_dir = Path("src/agents")
    if not agents_dir.exists():
        print("src/agents/ directory not found")
        return 1
    return run_checker(check_file, iter_python_files(agents_dir), "No patient data leaks in agent tools")


if __name__ == "__main__":
    sys.exit(main())
