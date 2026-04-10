# Phase 8 — Design Document + Presentation

**Dependencies:** Phases 5-7 (content to write about)
**Agent:** `general-purpose`
**Estimated files:** 2-3

This phase produces the two non-code deliverables: the 2-4 page design document and the 15-20 minute presentation slides.

---

## 8.1 Design Document

### `docs/design.md` (NEW)

**Purpose:** Consolidated design document — THE deliverable that Sanofi evaluates alongside the code.

**Length:** 2-4 pages (strict — assignment requirement). Use concise prose, diagrams, tables.

**Required sections (from homework §8.3):**

1. **System Architecture** (~0.5 page)
   - One-paragraph overview: what CDDE does, why it exists
   - Architecture diagram (ASCII or mermaid): Spec → Agents → DAG → Verify → Audit
   - Layer stack: domain → agents → engine → persistence → ui
   - Key design choice: PydanticAI + custom orchestrator (not LangChain/CrewAI)

2. **Agent/Module Roles** (~0.5 page)
   - Table: 5 agents with role, output type, key insight
   - Spec Interpreter: document understanding ≠ code generation
   - Coder + QC: double programming (regulatory requirement, not just testing)
   - Debugger: specialized diagnostic when primary and QC diverge
   - Auditor: compliance-focused summary

3. **Orchestration Logic** (~0.5 page)
   - 5 patterns: sequential, fan-out/fan-in, concurrent+compare, retry+escalation, HITL gate
   - FSM diagram (states + transitions)
   - Why: clinical workflow has regulatory constraints that generic orchestration ignores

4. **Dependency Handling** (~0.25 page)
   - Enhanced DAG: not just dependency order but lineage+computation+audit
   - Each node carries: rule, generated code, agent provenance, QC status, human approval
   - Topological sort ensures correct execution order
   - Example: AGE_GROUP → IS_ELDERLY → RISK_SCORE chain

5. **HITL Design** (~0.25 page)
   - 4 gates: spec review, code review, QC dispute, audit sign-off
   - Streamlit UI with approval workflow
   - Feedback captured → long-term memory → improves future runs

6. **Traceability** (~0.25 page)
   - 3 layers: AgentLens traces (agent-level), loguru (system-level), audit trail (business-level)
   - Append-only audit trail with source-to-output lineage
   - Export: JSON + HTML (via AgentLens)

7. **Memory Design** (~0.25 page)
   - Short-term: per-run workflow state (JSON/DB)
   - Long-term: validated patterns, feedback, QC history (SQLite → PostgreSQL)
   - Retrieval: by variable type, by spec similarity — injected into agent prompts

8. **Trade-offs** (~0.5 page)
   - Automation vs control: guard configs dial the level per study
   - LLM vs rules: hybrid — LLM generates, deterministic rules evaluate
   - Flexibility vs compliance: same engine, different YAML specs per study
   - Data security: dual-dataset architecture (agents never see patient data)
   - Production path: Docker Compose → K8s, SQLite → PostgreSQL, API gateway

**Constraints:**
- Target exactly 3 pages (sweet spot between 2 and 4)
- Use markdown — will render nicely on GitHub and as PDF
- Include at least 2 diagrams (architecture + FSM)
- Reference actual code locations (e.g., "see `src/engine/orchestrator.py`")
- Mention CDISC pilot study as the validation dataset
- End with "Limitations and Future Work" — honest about what's prototype vs production

**Source material:** Draw from (do NOT copy — synthesize):
- `ARCHITECTURE.md` — structure and diagrams
- `docs/REQUIREMENTS.md` — Q&A decisions
- `docs/ORCHESTRATION.md` — workflow patterns
- `decisions.md` — ADRs

---

## 8.2 Presentation Slides

### `presentation/slides.md` (NEW)

**Purpose:** Markdown-based slides for 15-20 minute panel presentation. Use a format compatible with Marp, reveal.js, or similar markdown-to-slides tools.

**Slide outline (15-20 min = ~15-18 slides):**

1. **Title** — CDDE: Clinical Data Derivation Engine | Sanofi AI/ML Lead Homework
2. **Problem** — SDTM → ADaM is manual, error-prone, requires double programming
3. **Solution Overview** — Multi-agent system with regulatory-grade verification
4. **Architecture** — Layered diagram (domain → agents → engine → ui)
5. **Agent Roles** — 5 agents table with the "why separate" column
6. **Orchestration** — FSM + 5 patterns (sequential, fan-out, compare, retry, HITL)
7. **DAG** — Enhanced DAG diagram with lineage example
8. **Double Programming** — Coder + QC parallel → Compare → Debug if mismatch
9. **Data Security** — Dual-dataset: agents see schema only, tools run on real data
10. **HITL Design** — Streamlit screenshot or mockup of approval workflow
11. **Traceability** — 3-layer audit: AgentLens + loguru + business trail
12. **Memory** — Short-term (per-run) + Long-term (cross-run patterns)
13. **Demo** — Live demo or screenshots of the system running on CDISC pilot data
14. **Trade-offs** — Automation vs control dial, LLM vs rules hybrid
15. **Production Path** — Docker → K8s, SQLite → PostgreSQL, multi-study
16. **Implementation Quality** — 118+ tests, 85%+ coverage, strict typing, CI
17. **Limitations & Future** — BDS, PDF parsing, multi-study, real RBAC
18. **Q&A** — Questions welcome

**Constraints:**
- Use Marp-compatible markdown (`---` slide separators, `<!-- _class: lead -->` for title slides)
- Each slide: 1 key point, 1 visual (diagram/table/code snippet), minimal text
- Include speaker notes as HTML comments `<!-- Speaker notes: ... -->`
- Total word count: ~2000 words (enough for 15-20 min at natural pace)
- No slides with walls of text — use diagrams and bullet points

### `presentation/README.md` (NEW)

**Purpose:** Instructions for rendering the slides.

**Content:**
```markdown
# Presentation

## Render with Marp

```bash
# Install Marp CLI
npx @marp-team/marp-cli slides.md --html --allow-local-files -o slides.html

# Or use VS Code Marp extension for live preview
```

## Slide count: ~18 slides
## Duration: 15-20 minutes
```

---

## 8.3 Implementation Notes

- The design doc should be written by reading the actual codebase — not by copying from ARCHITECTURE.md
- Diagrams should use ASCII art (for markdown compatibility) or mermaid (for GitHub rendering)
- The presentation should tell a story: Problem → Solution → How → Evidence → Future
- Both documents should mention the CDISC pilot study by name — signals domain knowledge
