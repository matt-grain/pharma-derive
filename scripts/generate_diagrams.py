"""Generate Mermaid diagrams from the codebase: FSM state diagram + orchestration sequence diagram.

Outputs .mmd files (Mermaid source) to presentation/diagrams/.
Render with: npx @mermaid-js/mermaid-cli -i file.mmd -o file.svg

Usage:
    uv run python scripts/generate_diagrams.py
"""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from pathlib import Path

OUTPUT_DIR = Path("presentation/diagrams")
FSM_SOURCE = Path("src/domain/workflow_fsm.py")
ORCHESTRATOR_SOURCE = Path("src/engine/orchestrator.py")
RUNNER_SOURCE = Path("src/engine/derivation_runner.py")


# ---------------------------------------------------------------------------
# FSM state diagram — parsed from workflow_fsm.py
# ---------------------------------------------------------------------------


def _parse_fsm_transitions(source: Path) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Extract states and transitions from the WorkflowFSM class via AST."""
    tree = ast.parse(source.read_text(encoding="utf-8"))

    states: list[str] = []
    transitions: list[tuple[str, str, str]] = []  # (from, to, event_name)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "WorkflowFSM":
            continue
        for item in node.body:
            if not isinstance(item, ast.Assign) or len(item.targets) != 1:
                continue
            target = item.targets[0]
            if not isinstance(target, ast.Name):
                continue
            name = target.id
            # State(...) calls
            if isinstance(item.value, ast.Call) and _is_state_call(item.value):
                states.append(name)
            # Transitions: source.to(target)
            if isinstance(item.value, ast.Call) and _is_transition_call(item.value):
                src, dst = _extract_transition(item.value)
                if src and dst:
                    transitions.append((src, dst, name))
    return states, transitions


def _is_state_call(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Name) and node.func.id == "State"


def _is_transition_call(node: ast.Call) -> bool:
    """Check for pattern: something.to(something)."""
    return isinstance(node.func, ast.Attribute) and node.func.attr == "to" and len(node.args) == 1


def _extract_transition(node: ast.Call) -> tuple[str | None, str | None]:
    """Extract (source_state, target_state) from source.to(target) call."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None, None
    # source is the object the .to() is called on
    src = func.value
    src_name = src.id if isinstance(src, ast.Name) else None
    # target is the first argument
    dst = node.args[0]
    dst_name = dst.id if isinstance(dst, ast.Name) else None
    return src_name, dst_name


def generate_fsm_diagram(source: Path) -> str:
    """Generate Mermaid stateDiagram-v2 from WorkflowFSM class."""
    states, transitions = _parse_fsm_transitions(source)

    lines = ["stateDiagram-v2"]

    # Mark initial and final states
    for s in states:
        if s == "created":
            lines.append(f"    [*] --> {s}")
        if s in ("completed", "failed"):
            lines.append(f"    {s} --> [*]")

    # Add transitions (skip fail_from_* for readability — add a note instead)
    fail_sources: list[str] = []
    for src, dst, event in transitions:
        if dst == "failed":
            fail_sources.append(src)
            continue
        label = _humanize_event(event)
        lines.append(f"    {src} --> {dst} : {label}")

    # Summarize failure transitions
    if fail_sources:
        lines.append("")
        lines.append("    note right of failed : Any non-terminal state\\ncan transition to failed")

    # Style terminal states
    lines.append("")
    lines.append("    classDef terminal fill:#e74c3c,color:#fff,stroke:#c0392b")
    lines.append("    classDef success fill:#2ecc71,color:#fff,stroke:#27ae60")
    lines.append("    class failed terminal")
    lines.append("    class completed success")

    return "\n".join(lines)


def _humanize_event(event: str) -> str:
    """Convert event name to readable label."""
    return event.replace("_", " ")


# ---------------------------------------------------------------------------
# Orchestration sequence diagram — hand-crafted from code flow
# ---------------------------------------------------------------------------


def generate_sequence_diagram() -> str:
    """Generate Mermaid sequence diagram for the orchestration flow.

    Built from reading orchestrator.py and derivation_runner.py — the flow
    is stable enough that parsing it from AST isn't worth the complexity.
    """
    return """\
sequenceDiagram
    participant U as User / UI
    participant O as Orchestrator
    participant FSM as WorkflowFSM
    participant SP as SpecParser
    participant DAG as DerivationDAG
    participant C as Coder Agent
    participant QC as QC Agent
    participant V as Comparator
    participant D as Debugger Agent
    participant A as Auditor Agent
    participant DB as Repository (SQLite)

    U->>O: run(spec_path)
    activate O

    Note over O,FSM: Phase 1 — Spec Review
    O->>FSM: start_spec_review()
    O->>SP: parse_spec(path)
    SP-->>O: TransformationSpec
    O->>O: load_source_data() + generate_synthetic()
    O->>FSM: finish_spec_review()

    Note over O,DAG: Phase 2 — Build DAG
    O->>FSM: start_deriving()
    O->>DAG: DerivationDAG(rules, source_columns)
    DAG-->>O: topological layers

    Note over O,D: Phase 3 — Derive Variables (per layer)
    loop For each topological layer
        loop For each variable in layer (parallel)
            O->>FSM: start_verifying()

            par Coder + QC in parallel
                O->>C: run(rule, deps)
                C->>C: inspect_data() → execute_code()
                C-->>O: DerivationCode
            and
                O->>QC: run(rule, deps)
                QC->>QC: inspect_data() → execute_code()
                QC-->>O: DerivationCode
            end

            O->>V: verify_derivation(coder_code, qc_code)
            V-->>O: VerificationResult

            alt QC Match
                O->>DAG: apply_run_result(APPROVED)
            else QC Mismatch
                O->>D: run(debug mismatch)
                D-->>O: DebugAnalysis
                alt Fix found
                    O->>DAG: apply_run_result(APPROVED)
                else No fix
                    O->>DAG: apply_run_result(QC_MISMATCH)
                end
            end

            O->>DB: store QC result + pattern
        end
        O->>FSM: next_variable()
    end

    Note over O,A: Phase 4 — Audit
    O->>FSM: finish_review_from_verify()
    O->>FSM: start_auditing()
    O->>A: run(dag_summary)
    A-->>O: AuditSummary
    O->>DB: persist_state()
    O->>FSM: finish()

    O-->>U: WorkflowResult
    deactivate O"""


# ---------------------------------------------------------------------------
# Per-variable derivation detail diagram
# ---------------------------------------------------------------------------


def generate_derivation_detail_diagram() -> str:
    """Generate Mermaid sequence diagram for the per-variable derivation flow."""
    return """\
sequenceDiagram
    participant R as derivation_runner
    participant C as Coder Agent
    participant QC as QC Agent
    participant S as Sandbox (exec)
    participant V as Comparator
    participant D as Debugger Agent
    participant DAG as DerivationDAG

    R->>R: get_node(variable)
    Note over R: Build CoderDeps(df, synthetic_csv, rule)

    par Fan-out: Coder + QC
        R->>C: agent.run(rule.logic)
        activate C
        C->>S: inspect_data(ctx)
        S-->>C: schema + nulls + ranges
        C->>S: execute_code(ctx, code)
        S-->>C: aggregate summary
        C-->>R: DerivationCode(python_code, approach)
        deactivate C
    and
        R->>QC: agent.run(rule.logic)
        activate QC
        QC->>S: inspect_data(ctx)
        S-->>QC: schema + nulls + ranges
        QC->>S: execute_code(ctx, code)
        S-->>QC: aggregate summary
        QC-->>R: DerivationCode(python_code, approach)
        deactivate QC
    end

    R->>V: verify_derivation(coder_code, qc_code, df)
    activate V
    V->>S: execute_derivation(df, coder_code)
    V->>S: execute_derivation(df, qc_code)
    V->>V: compare_results(primary, qc)
    V->>V: compute_ast_similarity()
    V-->>R: VerificationResult(verdict, comparison)
    deactivate V

    alt verdict == MATCH
        R->>DAG: apply_run_result(APPROVED)
        R->>R: derived_df[variable] = series
    else verdict == MISMATCH
        R->>D: agent.run(debug mismatch)
        activate D
        D-->>R: DebugAnalysis(root_cause, suggested_fix)
        deactivate D
        alt suggested_fix valid
            R->>S: execute_derivation(df, fix)
            R->>DAG: apply_run_result(APPROVED)
            R->>R: derived_df[variable] = series
        else no fix
            R->>DAG: apply_run_result(QC_MISMATCH)
        end
    end"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # FSM state diagram
    fsm_mmd = generate_fsm_diagram(FSM_SOURCE)
    fsm_path = OUTPUT_DIR / "fsm_states.mmd"
    fsm_path.write_text(fsm_mmd, encoding="utf-8")
    print(f"  {fsm_path}")

    # Orchestration sequence diagram
    seq_mmd = generate_sequence_diagram()
    seq_path = OUTPUT_DIR / "orchestration_sequence.mmd"
    seq_path.write_text(seq_mmd, encoding="utf-8")
    print(f"  {seq_path}")

    # Per-variable derivation detail
    detail_mmd = generate_derivation_detail_diagram()
    detail_path = OUTPUT_DIR / "derivation_detail.mmd"
    detail_path.write_text(detail_mmd, encoding="utf-8")
    print(f"  {detail_path}")

    mmd_files = [fsm_path, seq_path, detail_path]
    print(f"\nGenerated {len(mmd_files)} .mmd files in {OUTPUT_DIR}/")

    # Render to SVG if mmdc (mermaid-cli) or npx is available
    _render_svgs(mmd_files)
    return 0


def _render_svgs(mmd_files: list[Path]) -> None:
    """Render .mmd files to .svg using mermaid-cli (mmdc or npx fallback)."""
    mmdc = shutil.which("mmdc")
    npx = shutil.which("npx")

    if mmdc:
        cmd_prefix = [mmdc]
    elif npx:
        cmd_prefix = [npx, "@mermaid-js/mermaid-cli"]
    else:
        print("mmdc/npx not found — skipping SVG render. Install with: npm i -g @mermaid-js/mermaid-cli")
        return

    print("Rendering SVGs...")
    for mmd in mmd_files:
        svg = mmd.with_suffix(".svg")
        result = subprocess.run(  # noqa: S603 — trusted input: paths we just wrote
            [*cmd_prefix, "-i", str(mmd), "-o", str(svg)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  {svg} ({svg.stat().st_size // 1024}KB)")
        else:
            print(f"  FAILED: {mmd.name} — {result.stderr.strip()[:120]}")


if __name__ == "__main__":
    sys.exit(main())
