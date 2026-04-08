# Requirements Analysis & Decision Log

## 1. Starting Point — Assignment Framing

The homework (see [homework.md](homework.md)) asks for an **Agentic AI Workflow for Clinical Data Derivation, Verification, and Traceability**.

### What the assignment actually asks (our interpretation)

Automate the **SDTM → ADaM derivation step** of the clinical trial data pipeline using a multi-agent system. This is the step where standardized raw clinical data (SDTM) is transformed into analysis-ready datasets (ADaM) through documented derivation rules — a process that, in real pharma, is done by SAS/R statistical programmers following a transformation specification.

### The full clinical data lifecycle (for context)

```
Raw CRF/EDC Data → SDTM (standardized tabulation) → ADaM (analysis-ready) → TFLs (Tables, Figures, Listings)
                                                     ↑
                                              THIS IS THE SCOPE
```

- **SDTM (Study Data Tabulation Model):** Data "as collected," restructured into CDISC-standard domains (DM=demographics, LB=labs, VS=vitals, EX=exposure, etc.)
- **ADaM (Analysis Data Model):** Derived datasets with computed variables, population flags, change-from-baseline, groupings. Two core structures: ADSL (one row per patient) and BDS (one row per patient/visit/parameter).
- **Transformation Specification:** A formal document mapping every ADaM variable to its SDTM source(s) and derivation logic.

---

## 2. Questions We Asked Ourselves

### Q1: What is "verification" in the output?

**Answer:** In regulated pharma, every ADaM derivation must be **independently verified** via **double programming** (ICH E6 / FDA expectation). A second programmer independently implements the same spec, and both outputs are compared programmatically (like SAS `PROC COMPARE`). Discrepancies are flagged and resolved.

**Implication for our system:** A natural fit for a **QC Agent** that independently generates derivation code without seeing the primary agent's implementation, then compares outputs. This is not just testing — it's a regulatory requirement.

### Q2: What does the DAG represent?

**Answer:** A Directed Acyclic Graph where **nodes = variables** (source and derived) and **edges = "must be computed before" dependencies**.

In its pure textbook form, a DAG only carries dependency order — it says "AGE_GROUP needs `age` first" but not HOW the computation works. That's useful for execution order (topological sort) but underwhelming for auditability.

**Our enhancement:** We enrich the DAG into a **Lineage + Computation + Audit graph**. Each derived node carries metadata:
- **Derivation rule** (from the spec, in plain language)
- **Generated code** (the actual Python function the agent wrote)
- **Agent provenance** (which agent produced it, timestamp)
- **Verification status** (QC pass/fail, discrepancies if any)
- **Human approval** (who reviewed, when, any edits made)

Example — enhanced DAG:

```
age ──[bucket(age, [18,65]) | agent:coder | qc:PASS | approved:human@T3]──► AGE_GROUP ──┐
                                                                                         │
treatment_start ──[end - start + 1 | agent:coder | qc:PASS | approved:auto]──► DURATION  │
visit_date ──────►                                                                       │
                                                                                         ├──► RISK_GROUP
response ──[threshold(≥50%) | agent:coder | qc:FAIL→fixed | approved:human@T5]──► FLAG──┘
lab_value ►
```

This means the DAG serves three purposes simultaneously:
1. **Execution engine** — topological sort gives correct computation order
2. **Audit trail** — every derivation is traceable to source, logic, agent, and human approval
3. **Debugging tool** — when a QC mismatch occurs, the graph shows exactly which node diverged and its full provenance

Without topological sort, derived variables may silently compute from nulls — an undetected data integrity failure that propagates into regulatory submissions.

**This is a deliberate design choice (not standard).** Traditional pharma DAGs (SAS macro flows, dbt-style) only track dependencies. Ours embeds the full audit context in the graph structure itself, making traceability a first-class property of the execution model rather than a separate logging concern. This aligns with 21 CFR Part 11 requirements where every computation must be attributable and reproducible.

### Q3: Should we generate mock data or use a real dataset?

**Answer:** The **CDISC Pilot Study (cdiscpilot01)** is the canonical public clinical trial dataset — an Alzheimer's disease trial with full SDTM + ADaM data, freely available on GitHub. Using it:
- Provides real-world complexity (partial dates, missing values, multiple visit windows)
- Allows **ground-truth validation** — our derived ADaM can be compared against the official ADaM
- Signals domain fluency to the panel (every pharma data scientist knows this dataset)

**Decision:** Use CDISC pilot SDTM as input. Use official ADaM as ground truth for verification.

### Q4: How many agents? What are the roles?

**Answer:** The workflow decomposes into 5 distinct cognitive tasks:

| Agent | Role | Why it's a separate agent |
|-------|------|---------------------------|
| **Spec Interpreter** | Parse transformation spec, extract structured rules, detect ambiguities | Document understanding ≠ code generation |
| **Derivation Coder** | Generate Python code implementing the derivation rules | Primary programmer (regulatory role) |
| **QC Programmer** | Independently re-implement derivations for double-programming verification | Must NOT see primary code (regulatory requirement) |
| **Debugger** | When primary and QC outputs diverge, trace the discrepancy | Specialized diagnostic reasoning |
| **Auditor** | Generate lineage report, verify traceability, produce audit trail | Compliance-focused, not implementation-focused |

**Orchestrator** manages the workflow, DAG execution order, and human-in-the-loop gates.

### Q5: What level of "production readiness" to target?

**Answer:** Assignment says "prototype" but we treat this as a **production-grade deliverable**, not a throwaway POC. This is a deliberate differentiator: most candidates (especially PhD-heavy profiles) will submit a brilliant notebook that works on their laptop. We submit a system that could be deployed.

**Our approach: apply the same engineering discipline we use on real projects.**

This costs almost nothing extra because these practices are already our default workflow — not bolt-on extras:

| Practice | What We Do | Why It Matters for Sanofi |
|----------|-----------|--------------------------|
| **Architecture docs** | ARCHITECTURE.md with layer responsibilities, data flow, domain concepts | Shows the system is understandable by someone who didn't build it |
| **Decision records** | decisions.md with ADR format (context, decision, alternatives, consequences) | Demonstrates Lead-level reasoning, not just implementation |
| **Code quality** | ruff (linting) + pyright (type checking) + strict configs | GxP environments require code quality controls |
| **Type safety** | Full Python type annotations, no `Any` without justification | Catches bugs before they become data integrity issues |
| **Test coverage** | pytest with unit + integration tests, target >80% on core logic | Derivation logic MUST be tested — wrong output = wrong drug approval |
| **CI pipeline** | GitHub Actions running lint + typecheck + tests on every push | Demonstrates continuous quality, not "it works on my machine" |
| **Clean architecture** | Layered separation (domain / agents / infrastructure / UI) | Shows the system can evolve — swap agent framework, change UI, add domains |
| **Dependency management** | uv + pyproject.toml + lockfile, pinned versions | Reproducible builds — critical for regulated environments |
| **Pre-commit hooks** | Automated quality gates before code enters the repo | Prevents regressions, enforces standards |
| **Security** | No secrets in code, .env for API keys, .gitignore hygiene | Basic but often missed in homework submissions |

**The signal to the panel:** "This person builds systems that teams can maintain, extend, and trust — not just demos that impress once."

**What we still keep at prototype level** (documented honestly):
- No real deployment (no Docker/K8s/cloud infra running)
- No load testing or performance optimization
- No real RBAC/auth — described in design doc only
- Cloud architecture described in design doc, not implemented

### Q6: How to handle Observability, Audit & Traceability?

The assignment (§10) explicitly asks for:
- **Observability:** logging, monitoring, metrics
- **Audit & Traceability:** audit logs, lineage storage, versioning

**Answer:** We layer THREE distinct observability concerns, each with its own tool:

| Concern | Tool | What It Captures | Level |
|---------|------|-----------------|-------|
| **Trajectory tracing** | AgentLens (proxy mode) | Every LLM call, tool call, agent response — the full agent trajectory with OTel spans | Agent-level |
| **Real-time evaluation** | AgentLens (guards) | Hallucination flags, policy violations, unauthorized actions — caught BEFORE they enter workflow state | Agent-level |
| **Circuit breaker** | AgentLens (guards + Sentinel) | ESCALATE to external agent or human when critical violations detected — observe AND act | Agent-level |
| **Orchestration logging** | loguru | Workflow state transitions, DAG execution progress, HITL gate events, timing | System-level |
| **Functional audit trail** | Custom (audit/ module) | Source-to-output lineage, derivation provenance, human approvals, QC results — append-only | Business-level |
| **Metrics** | Structured JSON export | Token usage, derivation times, QC match rates, human intervention rates | Operational |

**Key insight:** AgentLens is unique here because it serves BOTH the observability AND the trade-off sections of the homework:
- **Automation vs control** → Guards let you dial the control level per evaluator (warn/block/escalate)
- **LLM vs rules** → Deterministic evaluators (rules) run on LLM output in real time — hybrid by design
- **Flexibility vs compliance** → Same system, different guard configs per study or regulatory context

**Logging strategy (loguru levels):**
- `DEBUG` — Agent prompt/response details (dev only, disabled in prod)
- `INFO` — Workflow state transitions, DAG execution steps, derivation completions
- `WARNING` — QC mismatches, guard warnings, approaching token budget
- `ERROR` — Failed derivations, unresolvable QC disputes, agent crashes
- `CRITICAL` — Guard blocks, Sentinel escalations, data integrity violations

**AgentLens is optional — but trajectory observability is NOT.**

AgentLens is our preferred tool because it combines trajectory tracing, evaluation, and circuit-breaking in one component. However, the architecture must not be coupled to it. If AgentLens is not used, the orchestration layer must emit a **full trace log** (every LLM request/response, tool call, timing) in a standard format (OpenTelemetry spans or structured JSON) that can be consumed by third-party tools:

| If AgentLens is... | Trajectory tracing | Evaluation | Circuit breaker |
|--------------------|--------------------|-----------|----------------|
| **Used (preferred)** | AgentLens proxy captures automatically | AgentLens guards (real-time) | AgentLens guards + Sentinel |
| **Not used** | Orchestration layer emits OTel spans or structured JSON logs | Post-hoc evaluation pipeline (batch) | No real-time circuit breaker — rely on HITL gates only |

Compatible third-party alternatives if AgentLens is not available:
- **LangSmith** — trajectory tracing + evaluation (no circuit breaker)
- **Arize Phoenix** — OTel-native, open-source tracing + evaluation
- **Custom OTel collector** → Datadog / Grafana Tempo — raw tracing, no agent-specific evaluation

The LLM gateway abstraction (`llm_gateway.py`) is the integration point. It wraps all LLM calls and can emit traces regardless of whether AgentLens is in the path. This means:
- With AgentLens: traces captured at the proxy level (transparent to agents)
- Without AgentLens: traces emitted at the gateway level (explicit logging)

**Decision:** AgentLens is the recommended and default observability stack. The LLM gateway emits trace data independently, so the system degrades gracefully to structured logging + post-hoc evaluation when AgentLens is not deployed. Orchestration logging via loguru at different levels separates technical from functional concerns. Audit trail is custom, append-only, exportable to JSON + HTML.

### Q7: How to handle Memory and Reusability?

The assignment (§5E) explicitly asks for both short-term and long-term memory, with explanations of what is stored, how it is retrieved, and how it improves performance.

**Answer:** Memory serves two fundamentally different purposes in this system:

**Short-Term Memory (per workflow run):**

| What | How Stored | How Retrieved | Purpose |
|------|-----------|--------------|---------|
| Workflow state (current FSM step) | JSON file per run | By workflow_id | Resume after interruption, track progress |
| Intermediate outputs (derived columns so far) | In-memory DataFrame + JSON checkpoint | By variable name | Feed downstream derivations (DAG order) |
| Pending HITL approvals | DB record (SQLite) | By gate_id, polled by UI | Pause/resume workflow for human review |
| Agent conversation history | PydanticAI internal (per agent.run()) | Automatic within a run | Multi-turn tool use within a single agent task |
| QC comparison results | JSON per variable | By variable name | Feed Debugger agent if mismatch |

Short-term memory is **scoped to a single workflow run** and cleared on completion. It's analogous to working memory — holds what's needed for the current task.

**Long-Term Memory (cross-run knowledge base):**

| What | How Stored | How Retrieved | How It Improves Performance |
|------|-----------|--------------|----------------------------|
| Validated derivation patterns | SQLite: `patterns` table (variable_type, spec_text, approved_code, study_id) | Query by variable type + spec similarity | Pre-populate code generation — agent sees "here's an approved pattern for AGE_GROUP from a previous study" → fewer LLM iterations |
| Human feedback history | SQLite: `feedback` table (variable, feedback_text, action_taken, timestamp) | Query by variable type | Agent learns from past corrections — "last time a human changed the boundary from >= to >, include that context" |
| QC match/mismatch patterns | SQLite: `qc_history` table (variable, coder_approach, qc_approach, verdict) | Aggregate stats by variable type | Identify which derivation types consistently cause QC mismatches → flag for extra human attention |
| Reusable code snippets | SQLite: `snippets` table (pattern_name, code, description, usage_count) | By pattern name or spec keyword | Common operations (date parsing, null handling, population flags) don't need re-generation |

Long-term memory persists across runs and grows with usage. It's analogous to institutional knowledge — what the team has learned over time.

**Retrieval strategy:**
- Before generating code, the Coder agent's tools query long-term memory for matching patterns
- Matches are injected into the agent's prompt as "reference implementations"
- The agent can use them as-is, adapt them, or ignore them — it's context, not constraint
- If the agent produces a new pattern that passes QC, it's stored for future runs

**How this maps to pharma-catalyst's memory:**
pharma-catalyst used a simple `memory.json` for experiment history. CDDE needs more structure because:
- Multiple variable types with different patterns (unlike pharma-catalyst's single RMSE optimization)
- Human feedback must be queryable by variable type (not just chronological)
- QC history enables statistical analysis of reliability patterns
- SQLite gives us ACID guarantees and query flexibility vs flat JSON

**Storage behind repository interface:**
```
MemoryRepository (abstract)
  ├── ShortTermMemory  → JSON files (per run)
  └── LongTermMemory   → SQLite (cross-run)
                          → PostgreSQL in production (config change)
```

**Decision:** Short-term = JSON per run (simple, disposable). Long-term = SQLite with structured tables behind a repository interface (swappable to PostgreSQL). Agents access memory through tools (`query_patterns`, `get_feedback`) — memory is a tool capability, not a framework feature.

### Q8: How to handle data security — do agents see patient data?

The assignment (§10B) asks for data security: VPC, encryption, access control, no raw data exposure. Sanofi is a French pharmaceutical company (GDPR applies). Clinical trial data — even de-identified (pseudonymized USUBJID) — is regulated.

**The problem:** If agents send SDTM patient rows to an external LLM (Claude API, Azure OpenAI), those rows leave the security perimeter. Even with de-identification, this is a compliance risk:
- GDPR treats pseudonymized data as personal data (re-identification risk)
- 21 CFR Part 11 requires controlled access to electronic records
- Sanofi's data governance likely prohibits sending patient-level data to external APIs

**The question:** Can the agents do their job WITHOUT seeing actual patient data?

**Answer: Yes.** The agents need to understand the *shape* of the data to write correct code — not the data itself. We use a **dual-dataset architecture**:

| Layer | Sees | Purpose |
|-------|------|---------|
| **LLM (via prompts)** | Schema metadata + synthetic reference dataset | Understand column names, types, value ranges, cardinality — enough to write correct pandas code |
| **Tools (local execution)** | Real SDTM data | Execute generated code on real data, return aggregate results (counts, dtypes, pass/fail) to LLM |
| **LLM (via tool results)** | Aggregated outputs only | "5 nulls in AGE column", "QC comparison: 3 rows diverge" — never raw patient rows |

**Synthetic reference dataset:**
- Same column names, same dtypes, same value ranges as real SDTM
- Generated programmatically from the schema (e.g., random ages 18-90, random dates in study window)
- Small (10-20 rows) — enough for the LLM to understand patterns
- Included in agent prompts as context
- Can be committed to git (no compliance risk)

**What each agent sees:**

| Agent | In prompt (sent to LLM) | In tool results (returned to LLM) |
|-------|------------------------|----------------------------------|
| Spec Interpreter | Spec YAML + schema metadata | — (no tools) |
| Derivation Coder | Schema + synthetic sample + derivation rule | Code execution: success/fail + aggregate stats (null count, value distribution) |
| QC Programmer | Schema + synthetic sample + derivation rule | Same as Coder (independent) |
| Debugger | Schema + divergent row INDICES + derived values (not source PII) | Diff analysis: which derivation step diverged |
| Auditor | DAG metadata, provenance, timestamps | — (pure metadata) |

**The `inspect_data` tool is the key control point.** It returns schema info (column names, types, null counts, value distributions) — never raw rows. The `execute_code` tool runs code on real data but returns only stdout output (which we control: aggregate stats, not `df.head()`).

**Production deployment implications:**

| Deployment | LLM location | Data security |
|-----------|-------------|---------------|
| **Prototype (our demo)** | External Claude API | Only synthetic/public data in prompts. Real CDISC pilot data (already public) in tools. |
| **Sanofi internal** | Azure OpenAI in Sanofi VNet (private endpoint) | LLM calls never leave the network. But dual-dataset still applies as defense-in-depth. |
| **Sovereign AI** | Self-hosted LLM on Sanofi infrastructure | Maximum control. Dual-dataset still best practice (least-privilege: agents don't need what they don't need). |

**Decision:** Dual-dataset architecture. LLM prompts contain schema + synthetic reference data only. Tools execute on real data locally and return aggregates. This is not just a demo constraint — it's the correct production architecture for pharma. The principle: **agents need to understand data shape, not data content.**

---

## 3. Assumptions

| # | Assumption | Rationale |
|---|-----------|-----------|
| A1 | We scope to ADSL (subject-level) derivations only, not BDS (longitudinal per-visit) | ADSL is the most impactful (population flags, demographics) and keeps scope manageable in 1 week |
| A2 | Transformation spec is provided as structured YAML/JSON, not parsed from Word/PDF | Focus on agentic workflow, not document parsing. Mention PDF parsing as production extension |
| A3 | We use Claude as the LLM but design for model-agnostic swappability | Shows LLM gateway pattern for production section |
| A4 | Python + pandas for derivations (not SAS) | Modern stack, readable for the panel, industry trending away from SAS |
| A5 | Streamlit for HITL UI | Quick to build, impressive to demo, appropriate for prototype |
| A6 | The "double programming" verification uses a separate agent with isolated context, not just re-running the same prompt | Mirrors the real pharma QC process where two programmers work independently |

---

## 4. Decisions

| # | Decision | Alternatives Considered | Why This Choice |
|---|----------|------------------------|-----------------|
| D1 | Use CDISC Pilot Study (cdiscpilot01) as dataset | Generate synthetic mock data | Real data, ground truth available, signals domain knowledge |
| D2 | CrewAI for agent definition + custom orchestration layer | LangGraph, custom agents, AutoGen | CrewAI for role-based agents + task abstractions; custom Python async for workflow orchestration (CrewAI's built-in async has known bugs with parallel tasks, and HITL is CLI-only — we need Streamlit integration and reliable fan-out) |
| D3 | DAG built from spec at runtime, not hardcoded | Hardcoded pipeline | Shows the system generalizes to any spec (platform thinking) |
| D4 | AgentLens for observability/traceability | Custom logging, LangSmith | Matt built AgentLens — demonstrates deep expertise, and it IS the traceability answer |
| D5 | Streamlit UI with approval gates | CLI-only, FastAPI + React | Best demo-to-effort ratio for 1-week timeline |
| D6 | Short-term memory = workflow state (JSON), Long-term memory = validated patterns DB (SQLite) | Vector store, in-memory only | Concrete and auditable, not a black box |
| D7 | Scope: 5-7 ADSL derivation variables | Full ADaM suite | Demonstrates the pattern without drowning in clinical data complexity |

---

## 5. Mapping to Evaluation Criteria

| Criterion (from homework §9) | Our Answer |
|-------------------------------|------------|
| **Agentic Architecture** | 5 agents with clear roles mirroring real pharma workflow |
| **Data Logic & Dependency** | Runtime DAG from spec, topological sort, handles missing/partial data |
| **Verification & Reliability** | Double-programming via independent QC agent — the pharma gold standard |
| **Human-in-the-Loop** | Streamlit approval gates at spec review, code review, and QC resolution |
| **Traceability & Auditability** | AgentLens OTel spans + DAG lineage + full audit log |
| **Memory & Reusability** | Short-term workflow state + long-term validated patterns |
| **Implementation Quality** | Clean architecture, real dataset, working end-to-end |
| **Communication & Reasoning** | This document + design doc + 15-20 min presentation |

---

## 6. Out of Scope (documented for the panel)

- Full BDS (per-visit longitudinal) derivations — mention as "next phase"
- PDF/Word spec parsing — mention as production feature
- Multi-study support — discuss in platform thinking section
- Real LLM gateway with fallback models — discuss in production architecture
- CDISC conformance validation (Pinnacle 21 equivalent) — mention as integration point

---

## 7. Data Source

**CDISC Pilot Study (cdiscpilot01)**
- **Disease:** Alzheimer's (anti-dementia drug trial)
- **SDTM source:** `https://github.com/phuse-org/phuse-scripts/tree/master/data/sdtm/cdiscpilot01`
- **ADaM ground truth:** `https://github.com/phuse-org/phuse-scripts/tree/master/data/adam/cdiscpilot01`
- **Key domains used:** DM (demographics), EX (exposure), SV (visits), LB (labs), DS (disposition), QS (questionnaires)
- **Target derivations (ADSL):** AGE_GROUP, TREATMENT_DURATION, SAFFL, ITTFL, PPROTFL, EOSSTT, RESPONSE_FLAG

---

## 8. Glossary

| Acronym | Full Name | What It Is (Plain English) |
|---------|-----------|---------------------------|
| **CDISC** | Clinical Data Interchange Standards Consortium | The organization that defines data standards for clinical trials. Think of it as "the W3C of pharma data" — they decide how clinical data must be structured for regulatory submissions. |
| **SDTM** | Study Data Tabulation Model | The **raw-but-standardized** data layer. Takes messy data collected during a clinical trial (lab results, visit notes, drug doses) and organizes it into standard tables (called "domains"). Data is stored "as collected" — no calculations or derivations. Think: **the cleaned database.** |
| **ADaM** | Analysis Data Model | The **analysis-ready** data layer, built on top of SDTM. Contains computed/derived variables (age groups, treatment duration, population flags, change-from-baseline). This is what statisticians use to run analyses. Think: **the feature-engineered dataset.** Our system produces this. |
| **ADSL** | ADaM Subject-Level | A specific ADaM dataset with **one row per patient**. Contains demographics, treatment assignment, population flags (who's in which analysis), and key derived variables. Think: **the patient summary table.** This is our primary output scope. |
| **BDS** | Basic Data Structure | A specific ADaM dataset structure with **multiple rows per patient** (one per visit, per timepoint, per lab parameter). Used for longitudinal data like lab results over time. Think: **the time-series table.** Out of scope for our prototype. |
| **TFLs** | Tables, Figures, and Listings | The **final reports** — statistical tables, charts, and patient listings that go into the regulatory submission dossier. Produced by running statistical analyses on ADaM datasets. Think: **the presentation layer / frontend.** NOT our output — this is downstream of us. |
| **SAS** | Statistical Analysis System | The legacy programming language that dominates pharma data analysis (since the 1970s). Most SDTM→ADaM transformations are historically written in SAS. The industry is slowly moving to R and Python. |
| **SAP** | Statistical Analysis Plan | The formal document written by biostatisticians describing exactly what analyses will be performed on the trial data. The transformation spec is derived from this. Think: **the requirements doc** that drives all derivation logic. |
| **CRF** | Case Report Form | The form (paper or electronic) used to record patient data during a clinical trial — vital signs, lab results, adverse events, etc. This is the ultimate raw data source. |
| **EDC** | Electronic Data Capture | The software system used to fill in CRFs electronically at clinical trial sites. Examples: Medidata Rave, Oracle InForm. |
| **ICH E6 (GCP)** | International Council for Harmonisation — Good Clinical Practice | The global regulatory guideline for conducting clinical trials. Requires data integrity, traceability, and independent verification of results. This is WHY double programming exists. |
| **21 CFR Part 11** | Title 21, Code of Federal Regulations, Part 11 | FDA regulation for electronic records. Requires audit trails, access controls, and data integrity for any electronic data used in regulatory submissions. Drives our traceability requirements. |
| **SAFFL** | Safety Analysis Flag | A Y/N flag in ADSL: "Did this patient receive at least one dose of study drug?" If Y, they're in the safety analysis population. |
| **ITTFL** | Intent-to-Treat Flag | A Y/N flag in ADSL: "Was this patient randomized?" If Y, they're in the ITT analysis population (the primary efficacy analysis). |
| **PPROTFL** | Per-Protocol Flag | A Y/N flag in ADSL: "Did this patient complete the study without major protocol deviations?" Most restrictive population. |
| **USUBJID** | Unique Subject Identifier | The universal patient ID in CDISC data — format: `STUDYID-SITEID-SUBJID`. Like a primary key across all domains. |
| **DAG** | Directed Acyclic Graph | A graph where edges have direction and no cycles exist. We use it to model variable dependencies: if RISK_GROUP depends on AGE_GROUP, the DAG ensures AGE_GROUP is computed first. |
| **Double Programming** | (no acronym) | The pharma QC practice where two independent programmers implement the same derivation spec separately, then compare outputs programmatically. Any discrepancy is investigated. This is the industry-standard verification method. |
| **Pinnacle 21** | (product name) | Industry-standard software for validating CDISC compliance of SDTM/ADaM datasets before regulatory submission. Think: **the linter for clinical data.** |
| **XPT** | SAS Transport Format | The file format required by FDA for submitting SDTM/ADaM datasets. Binary format, readable by SAS, R (`haven` package), and Python (`xport`/`pyreadstat` packages). |
