# Phase 7 — Streamlit HITL UI

**Dependencies:** Phase 5 (CDISC data for demo), Phases 1-4 (engine)
**Agent:** `general-purpose`
**Estimated files:** 8
**New dependency:** `streamlit>=1.40,<2`

This phase builds the Streamlit human-in-the-loop interface — the primary deliverable UI. It provides 4 approval gates (spec review, code review, QC dispute resolution, audit sign-off) and a real-time workflow dashboard.

## Design System — AgentLens CSS

**Reuse the AgentLens report design system** (from `C:\Projects\AgentLens\src\agentlens\report\templates\report.html.j2`). This creates visual cohesion between the CDDE UI and AgentLens trace reports.

**CSS variables to carry into Streamlit custom theme:**

```css
:root {
  --bg-deep:        #101114;
  --bg-surface:     #16181c;
  --bg-elevated:    #1e2025;
  --bg-hover:       #282a30;
  --border:         #363840;
  --text-primary:   #f0f1f3;
  --text-secondary: #c2c4c9;
  --text-tertiary:  #9a9da5;
  --text-muted:     #7d808a;
  --accent:         #E86F33;       /* AgentLens orange */
  --accent-dim:     rgba(232, 111, 51, 0.22);
  --success:        #3ecf8e;
  --warning:        #f0b429;
  --danger:         #ef4444;
  --blue:           #60a5fa;
  --mono:  'IBM Plex Mono', monospace;
  --serif: 'Playfair Display', Georgia, serif;
}
```

**Apply via Streamlit's `st.markdown()` with `unsafe_allow_html=True`** for custom styling:
- Inject a `<style>` block at the top of each page with the AgentLens palette
- Use `st.markdown(html_content, unsafe_allow_html=True)` for custom-styled cards, badges, score displays
- Cards with left-border color for status (green=pass, orange=warning, red=fail) — same `.card.pass`, `.card.warn`, `.card.fail` pattern
- Badges for agent types: `.badge-llm` (blue), `.badge-tool` (orange) 
- IBM Plex Mono for all data/code displays
- Playfair Display for main headings

**Key CSS patterns to reuse directly:**
- `.overall` score card (big number + status text)
- `.card` grid for level scores (derivation status per variable)
- `.badge` pills for agent names and verdict labels
- `.result-row` for evaluator/QC results
- `details/summary` for expandable trajectory/code sections
- `.meta` bar with monospace metadata
- Dark background hierarchy: `--bg-deep` → `--bg-surface` → `--bg-elevated`

### `src/ui/theme.py` (NEW)

**Purpose:** Single source for the CDDE/AgentLens design system CSS injected into Streamlit.

**Content:** A single function `inject_theme()` that calls `st.markdown(CSS, unsafe_allow_html=True)` with the full AgentLens CSS palette adapted for Streamlit. Also configure `st.set_page_config()` with matching dark theme.

**Public API:**
```python
def inject_theme() -> None:
    """Inject AgentLens-inspired dark theme into the current Streamlit page."""

def status_badge(text: str, variant: str = "default") -> str:
    """Return HTML for a styled badge. Variants: 'llm', 'tool', 'pass', 'warn', 'fail'."""

def score_card(label: str, value: str, variant: str = "default") -> str:
    """Return HTML for a score card (big number + label). Variants: 'pass', 'warn', 'fail'."""

def result_row(name: str, score: str, message: str, variant: str = "default") -> str:
    """Return HTML for a result row (name + score + message)."""
```

**Constraints:**
- Max 120 lines
- All CSS in a single `_CSS` constant string — no external CSS files
- Include the Google Fonts link for IBM Plex Mono + Playfair Display
- Functions return HTML strings — caller uses `st.markdown(html, unsafe_allow_html=True)`

---

## 7.1 Streamlit App Entry Point

### `src/ui/__init__.py` (NEW)

Empty file.

### `src/ui/app.py` (NEW)

**Purpose:** Main Streamlit app — sidebar navigation + page routing.

**Structure:**
```python
"""CDDE — Clinical Data Derivation Engine"""
import streamlit as st
from src.ui.theme import inject_theme

st.set_page_config(page_title="CDDE", page_icon="🧬", layout="wide")
inject_theme()

# Sidebar with AgentLens-styled heading
st.sidebar.markdown('<h1 style="font-family: Playfair Display; color: #E86F33;">CDDE</h1>', unsafe_allow_html=True)
```

**Pages:**
1. **Workflow** — Start a new derivation run, monitor progress, approve at gates
2. **Audit Trail** — View audit records, export JSON

**Constraints:**
- No business logic in the UI — all logic goes through the orchestrator
- Session state for workflow tracking: `st.session_state.workflow_id`, `.workflow_result`
- Use `asyncio.run()` to call async orchestrator from Streamlit's sync context
- Call `inject_theme()` at the top of every page

---

## 7.2 Workflow Page

### `src/ui/pages/__init__.py` (NEW)

Empty file.

### `src/ui/pages/workflow.py` (NEW)

**Purpose:** Main workflow page — start runs, view progress, approve at HITL gates.

**Layout (top to bottom):**

1. **Header** — Playfair Display title with AgentLens orange accent
2. **Spec Selection** — File picker or dropdown for available specs (`specs/*.yaml`)
3. **Configuration** — LLM base URL (default: `http://localhost:8650/v1`), output directory
4. **Start Button** — styled with `--accent` orange background
5. **Progress** — AgentLens-style score cards showing FSM state, variables processed
6. **Results** — Card grid per variable: status badge (pass/warn/fail), code in monospace `<pre>` blocks
7. **Download** — Export audit trail as JSON, download derived dataset as CSV

**Key implementation details:**

```python
async def run_workflow(spec_path: str, llm_url: str, output_dir: Path) -> WorkflowResult:
    """Run the orchestrator and return results."""
    orch = DerivationOrchestrator(
        spec_path=spec_path,
        llm_base_url=llm_url,
        output_dir=output_dir,
    )
    return await orch.run()
```

**HITL Gates (simplified for prototype):**
- HITL gates are shown as **review screens after the run completes**. The user sees the spec, the generated code per variable, the QC results, and can approve/reject.
- Full mid-workflow blocking gates are a production extension — mention this in the design doc.

**Display sections using AgentLens components:**
- **Overall Score** — `.overall` card showing workflow status (COMPLETED=green, FAILED=red)
- **Variable Cards** — `.cards` grid with one `.card` per variable: status color on left border, variable name, QC verdict badge
- **Code Review** — `details/summary` expandable sections per variable showing coder's code, QC's code in `<pre>` blocks with `--bg-deep` background
- **QC Results** — `.result-row` per variable with verdict score and recommendation
- **Audit Summary** — `.meta` bar with key stats from AuditSummary

**Constraints:**
- Max 200 lines — extract components into `src/ui/components/` if needed
- Use `st.expander()` for per-variable details (code, QC, debug)
- Use `st.dataframe()` for tabular data, `st.json()` for audit records
- Handle errors gracefully — show `st.error()` with the error message if workflow fails

---

## 7.3 Audit Trail Page

### `src/ui/pages/audit.py` (NEW)

**Purpose:** View and export the audit trail from completed runs.

**Layout:**
1. **Run Selection** — Dropdown of completed runs (from output directory JSON files)
2. **Audit Records Table** — `st.dataframe()` showing timestamp, variable, action, agent
3. **Variable Filter** — Filter audit records by variable name
4. **Export** — Download button for the JSON file

**Styling:** Use `.result-row` pattern for each audit record, with `.badge-tool` for agent names.

**Constraints:**
- Read audit trail from JSON files (produced by orchestrator)
- Max 100 lines
- No LLM calls — purely a data viewer

---

## 7.4 UI Components

### `src/ui/components/__init__.py` (NEW)

Empty file.

### `src/ui/components/dag_view.py` (NEW)

**Purpose:** Visual DAG rendering showing variable dependencies and status.

**Implementation:** Use `st.graphviz_chart()` with AgentLens colors:
```python
def render_dag(dag: DerivationDAG) -> str:
    """Convert DAG to Graphviz DOT format with AgentLens color scheme."""
    colors = {
        DerivationStatus.APPROVED: "#3ecf8e",      # --success
        DerivationStatus.QC_MISMATCH: "#ef4444",    # --danger
        DerivationStatus.QC_PASS: "#60a5fa",        # --blue
        DerivationStatus.IN_PROGRESS: "#f0b429",    # --warning
        DerivationStatus.PENDING: "#7d808a",        # --text-muted
        DerivationStatus.FAILED: "#ef4444",         # --danger
    }
    # Build DOT graph with dark theme
    lines = [
        'digraph G {',
        '  rankdir=LR;',
        '  bgcolor="#101114";',
        '  node [fontname="IBM Plex Mono" fontcolor="#f0f1f3" style=filled];',
        '  edge [color="#363840"];',
    ]
    ...
```

**Constraints:**
- Max 50 lines
- No business logic — pure presentation
- Uses `DerivationStatus` enum members for color mapping, never raw strings
- Dark background matches AgentLens `--bg-deep`

---

## 7.5 Integration Wiring

### `src/engine/orchestrator.py` (MODIFY — minimal)

**No changes needed** — the Streamlit app calls `DerivationOrchestrator` directly. The orchestrator already:
- Accepts `spec_path`, `llm_base_url`, `output_dir` via constructor
- Returns `WorkflowResult` with all data the UI needs
- Exports audit trail to JSON via `self._audit_trail.to_json()`

---

## 7.6 pyproject.toml (MODIFY)

**Add to dependencies:**
```toml
"streamlit>=1.40,<2",
```

---

## 7.7 Run Command

**Add to README (Phase 9):**
```bash
# Start the Streamlit app
uv run streamlit run src/ui/app.py
```
