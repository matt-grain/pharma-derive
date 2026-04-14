"""Regenerate + render the Mermaid diagrams under presentation/diagrams/.

What this script does:

1. **Auto-generates** ``fsm_states.mmd`` from the clinical_derivation pipeline
   YAML at ``config/pipelines/clinical_derivation.yaml``. The FSM states are
   the pipeline step IDs in topological order, with ``created`` at the start,
   ``completed`` after the last step, and ``failed`` as the terminal-error
   sink. HITL-gate steps (``type: hitl_gate``) are styled distinctly so the
   human review gate is visually obvious.

2. **Renders** every ``.mmd`` file in ``presentation/diagrams/`` to an SVG of
   the same name via ``npx @mermaid-js/mermaid-cli``. The other two diagrams
   (``orchestration_sequence.mmd`` and ``derivation_detail.mmd``) are
   hand-authored because they describe behavioral flow rather than static
   step structure — the script never overwrites them, only re-renders them.

The pre-yaml-pipeline version of this script AST-parsed
``src/domain/workflow_fsm.py`` to extract FSM transitions. That module was
removed in Phase 14 when the PipelineInterpreter replaced the hardcoded
orchestrator; the diagram is now sourced from the same YAML the runtime uses,
so it cannot drift.

Usage:
    uv run python scripts/generate_diagrams.py

Requirements:
    - Node.js + ``npx`` on PATH (for ``@mermaid-js/mermaid-cli``).
    - PyYAML (already a project dependency via pipeline_interpreter).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import yaml

DIAGRAMS_DIR = Path("presentation/diagrams")
PIPELINE_YAML = Path("config/pipelines/clinical_derivation.yaml")
FSM_MMD = DIAGRAMS_DIR / "fsm_states.mmd"


def _resolve_npx() -> str:
    """Return the absolute path to npx, failing fast if Node.js is not installed.

    On Windows, shutil.which resolves ``npx`` to ``npx.cmd`` or ``npx.ps1``;
    ``subprocess.run`` needs that absolute path because cmd-shims are not
    discoverable via bare names without ``shell=True``.
    """
    path = shutil.which("npx")
    if path is None:
        print("ERROR: 'npx' not found on PATH. Install Node.js to render Mermaid diagrams.", file=sys.stderr)
        sys.exit(1)
    return path


def _load_pipeline_steps(path: Path) -> list[dict[str, Any]]:
    """Load and validate the pipeline YAML. Returns ordered step dicts."""
    if not path.exists():
        msg = f"Pipeline YAML not found at {path}"
        raise FileNotFoundError(msg)
    data = cast("dict[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8")))
    pipeline = data.get("pipeline", data)  # tolerate both top-level styles
    steps = pipeline.get("steps", [])
    if not isinstance(steps, list) or not steps:
        msg = f"Pipeline YAML {path} has no 'steps' list"
        raise ValueError(msg)
    return cast("list[dict[str, Any]]", steps)


def _generate_fsm_mmd(steps: list[dict[str, Any]], pipeline_name: str) -> str:
    """Build a Mermaid stateDiagram-v2 from an ordered step list."""
    lines = [
        "---",
        f"title: Pipeline FSM — {pipeline_name}.yaml",
        "---",
        "stateDiagram-v2",
        "    [*] --> created",
        "    completed --> [*]",
        "    failed --> [*]",
        "",
        "    created --> " + str(steps[0]["id"]) + " : start",
    ]
    hitl_steps: list[str] = []
    for i, step in enumerate(steps):
        step_id = str(step["id"])
        step_type = str(step.get("type", "builtin"))
        if step_type == "hitl_gate":
            hitl_steps.append(step_id)
        if i + 1 < len(steps):
            next_id = str(steps[i + 1]["id"])
            lines.append(f"    {step_id} --> {next_id} : {step_id} complete")
        else:
            lines.append(f"    {step_id} --> completed : pipeline finished")

    # HITL-gate steps additionally branch to 'failed' on reject
    for hitl_id in hitl_steps:
        lines.append(f"    {hitl_id} --> failed : reviewer rejected")

    lines.extend(
        [
            "",
            "    note right of failed",
            "        Any non-terminal step can transition to failed.",
            "        Rejection from a HITL gate is a clean failure",
            "        (WorkflowRejectedError, inherits from Exception).",
            "    end note",
            "",
            "    classDef terminal fill:#e74c3c,color:#fff,stroke:#c0392b",
            "    classDef success fill:#2ecc71,color:#fff,stroke:#27ae60",
            "    classDef hitl fill:#f39c12,color:#fff,stroke:#d68910",
            "    class failed terminal",
            "    class completed success",
        ]
    )
    for hitl_id in hitl_steps:
        lines.append(f"    class {hitl_id} hitl")
    return "\n".join(lines) + "\n"


def _render(npx_path: str, mmd_path: Path) -> bool:
    svg_path = mmd_path.with_suffix(".svg")
    print(f"  {mmd_path.name} -> {svg_path.name}")
    result = subprocess.run(  # noqa: S603 — controlled argv, no shell
        [npx_path, "--yes", "@mermaid-js/mermaid-cli", "-i", str(mmd_path), "-o", str(svg_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"    FAILED: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def main() -> int:
    npx_path = _resolve_npx()
    if not DIAGRAMS_DIR.exists():
        print(f"ERROR: {DIAGRAMS_DIR} does not exist", file=sys.stderr)
        return 1

    # 1. Regenerate fsm_states.mmd from the pipeline YAML
    try:
        steps = _load_pipeline_steps(PIPELINE_YAML)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR loading pipeline YAML: {exc}", file=sys.stderr)
        return 1
    pipeline_name = PIPELINE_YAML.stem
    FSM_MMD.write_text(_generate_fsm_mmd(steps, pipeline_name), encoding="utf-8")
    print(f"Regenerated {FSM_MMD.name} from {PIPELINE_YAML}")

    # 2. Render every .mmd file (including the hand-authored sequence + detail diagrams)
    sources = sorted(DIAGRAMS_DIR.glob("*.mmd"))
    print(f"\nRendering {len(sources)} Mermaid diagram(s) from {DIAGRAMS_DIR}:")
    failures = sum(1 for s in sources if not _render(npx_path, s))
    if failures:
        print(f"\n{failures} diagram(s) failed to render.", file=sys.stderr)
        return 1
    print("\nAll diagrams rendered successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
