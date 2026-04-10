---
marp: true
theme: default
paginate: true
backgroundColor: #101114
color: #f0f1f3
style: |
  section { font-family: 'IBM Plex Mono', monospace; }
  h1 { color: #E86F33; font-family: 'Playfair Display', serif; }
  h2 { color: #E86F33; }
  table { font-size: 0.8em; }
  code { background: #1e2025; }
  blockquote { border-left: 4px solid #E86F33; padding-left: 1em; font-style: italic; }
  img { background: transparent; }
---

# Clinical Data Derivation Engine

**CDDE** -- Agentic AI for SDTM-to-ADaM transformation
with regulatory-grade verification and full audit traceability

<br/>

Matthieu Boujonnier | AI/ML Lead Candidate | April 2026

<!-- Speaker notes: Introduce myself. This is a multi-agent AI system that automates the most error-prone step in clinical data workflows: deriving analysis-ready datasets from standardized tabulations. Built in one week, production-grade engineering. -->

---

## The Problem

```
Raw CRF/EDC  -->  SDTM (standardized)  -->  ADaM (analysis-ready)  -->  TFLs
                                              ^^^
                                          THIS IS THE SCOPE
```

**Today:** SAS/R programmers manually implement derivation specs. Every variable requires **double programming** (ICH E6). Error-prone, slow, expensive.

**The risk:** A wrong derivation can change the outcome of a drug approval decision.

**The opportunity:** LLMs can generate derivation code -- but the regulated environment demands verification, traceability, and human oversight that no off-the-shelf agent framework provides.

<!-- Speaker notes: Frame the domain. SDTM is the cleaned database, ADaM is the feature-engineered dataset. Every derived variable must be independently verified by a second programmer -- that's the FDA expectation. This is where agentic AI fits: generate code, verify independently, audit everything. -->

---

## Solution Overview

**Multi-agent system** with 5 specialized agents mirroring the real pharma workflow:

1. **Parse** the transformation spec (detect ambiguities)
2. **Generate** derivation code (primary programmer)
3. **Verify** independently (QC programmer -- isolated context)
4. **Debug** discrepancies (when primary and QC diverge)
5. **Audit** the entire process (lineage + compliance report)

**Validated on real data:** CDISC Pilot Study (cdiscpilot01) -- Alzheimer's trial, 7 ADSL derivations

<!-- Speaker notes: The agent decomposition mirrors how pharma actually works: spec writer, primary programmer, independent QC programmer, debugging team, QA auditor. Each is a separate cognitive task requiring different prompting strategies. We run against real CDISC data, not mock data -- the panel knows this dataset. -->

---

## Architecture

```
  Streamlit UI (HITL approval gates)
          |
  Orchestration Engine (WorkflowFSM + DAG executor)
          |
  PydanticAI Agents (5 agents, typed I/O, async)
          |
  LLM Gateway (OpenAI-compatible endpoint)
          |
  AgentLens Proxy (traces + guards + circuit breaker)
          |
  LLM API (Claude / Azure OpenAI / any)
```

**Layered architecture** -- 19 import-linter contracts enforce boundaries
**No circular imports** -- domain is pure Python, agents depend on domain only

<!-- Speaker notes: Four layers, strict dependency rules. Domain layer has zero framework dependencies -- pure dataclasses and Pydantic models. This means we can swap PydanticAI for another framework without touching domain logic. 19 import-linter contracts are enforced on every push. -->

---

## Agent Roles

| Agent | Output Type | Why Separate? |
|-------|------------|---------------|
| **Spec Interpreter** | `SpecInterpretation` | Document understanding ≠ code generation |
| **Derivation Coder** | `DerivationCode` | Primary programmer (regulatory role) |
| **QC Programmer** | `DerivationCode` | Must NOT see primary code (ICH E6) |
| **Debugger** | `DebugAnalysis` | Debugging ≠ generation (no self-grading) |
| **Auditor** | `AuditSummary` | Compliance review is independent |

All agents produce **validated Pydantic output types**
PydanticAI retries automatically on malformed LLM responses

<!-- Speaker notes: Each agent maps to a real role in pharma. The critical one is the QC Programmer: it has a DIFFERENT system prompt, isolated conversation history, and we even check AST similarity -- if the two implementations are more than 80% similar, we flag it as insufficient independence. This mirrors the real-world practice where two programmers sit in different rooms. -->

---

## Orchestration: 5 Patterns

| Pattern | Where Used |
|---------|-----------|
| **Sequential** | Spec -> DAG -> Derive -> Audit |
| **Fan-out / Fan-in** | Independent variables in parallel |
| **Concurrent + Compare** | Coder + QC on same variable |
| **Retry + Escalation** | QC mismatch -> Debugger -> human |
| **HITL Gate** | 4 approval points in workflow |

**Why custom orchestration?** PydanticAI provides agent abstractions.
But *which* agents run in parallel, *when* to pause for human review, and *how* to handle QC failures -- that is domain logic.

`asyncio.gather` for parallelism. `python-statemachine` for the FSM.

<!-- Speaker notes: We evaluated CrewAI -- async_execution has known bugs, human_input is CLI-only, structured output is not native. PydanticAI gives us typed agents; we compose them with standard Python async. The orchestration topology IS the clinical workflow -- it belongs in our code, not in a framework. -->

---

## The DAG: Enhanced Dependency Graph

Each node carries **lineage + computation + audit** -- not just execution order:

```
AGE (source) ---> AGEGR1 [code | agent:coder | qc:PASS | approved:human]
ARM (source) ---> SAFFL  [code | agent:coder | qc:PASS | approved:auto]
ARMCD (source) -> ITTFL  [code | agent:coder | qc:PASS | approved:auto]
ITTFL + SAFFL --> EFFFL   [code | agent:coder | qc:PASS | approved:auto]
```

**Three purposes simultaneously:**
1. **Execution engine** -- topological sort gives correct computation order
2. **Audit trail** -- every derivation traceable to source, logic, agent, approval
3. **Debugging tool** -- when QC fails, the graph shows exactly where

<!-- Speaker notes: A standard DAG just says "compute A before B." Ours embeds the full provenance in the graph structure itself. When the auditor asks "who derived EFFFL and was it verified?" -- the answer is in the node, not in a separate log file. This aligns with 21 CFR Part 11. -->

---

## Double Programming: The Regulatory Pattern

```
         Derivation Rule (from spec)
              |              |
         Coder Agent    QC Agent
         (primary)      (isolated context, different prompt)
              |              |
              v              v
           Output A       Output B
              \            /
            Programmatic Comparison
           /        |          \
        MATCH    MISMATCH    TOO SIMILAR
          |         |         (>80% AST)
     auto-approve  Debugger   re-run QC
                     |
              RESOLVED / UNRESOLVED
                |            |
           auto-approve   HUMAN (HITL)
```

Both agents use `asyncio.gather` -- true parallel execution, isolated contexts.

<!-- Speaker notes: This is the heart of the system. Double programming is not testing -- it's a regulatory requirement. Two independent implementations of the same spec, compared programmatically. If they match, we auto-approve. If they diverge, the Debugger agent analyzes both. If the Debugger can't resolve in 2 attempts, we escalate to a human with full context. The AST similarity check prevents gaming: if the QC is too similar to the primary, it added no verification value. -->

---

## Data Security: Dual-Dataset Architecture

| Layer | Sees | Purpose |
|-------|------|---------|
| **LLM (prompts)** | Schema + synthetic reference (10-20 fake rows) | Understand data shape |
| **Tools (local)** | Real SDTM data | Execute code, return aggregates |
| **LLM (results)** | "5 nulls in AGE", "QC: 3 rows diverge" | Never raw patient rows |

**Agents need data shape, not data content.**

The `inspect_data` tool is the security gate: column names, dtypes, null counts, value ranges. Never raw rows, never USUBJID-level data.

Not a demo constraint -- the correct production architecture for pharma.

<!-- Speaker notes: Even de-identified data is regulated under GDPR. If an agent sends df.head() to Claude, patient rows leave the perimeter. Our agents never see patient data -- they see synthetic reference data in prompts and get aggregate statistics from tools. This works because code generation requires understanding structure, not content. Same architecture whether the LLM is external or inside Sanofi's VNet. -->

---

## Human-in-the-Loop

| Gate | When | Human Actions |
|------|------|--------------|
| **1. Spec Review** | After Spec Interpreter | Approve / edit rules / resolve ambiguities |
| **2. QC Dispute** | Unresolved mismatch | Pick Coder / Pick QC / manual override |
| **3. Final Review** | All derivations done | Approve / reject specific variables |
| **4. Audit Sign-off** | After Auditor | Sign off on compliance report |

**Streamlit UI** with DB-backed approval state
Human feedback stored in long-term memory for future runs

<!-- Speaker notes: The gates are positioned where human judgment adds the most value: ambiguous specs, unresolvable QC disputes, final quality assessment, and compliance sign-off. The workflow pauses and resumes -- approvals are persisted in the database, not held in memory. Human corrections feed back into the system: if a human changes a boundary condition, that correction is stored and surfaced to agents in future studies. -->

---

## Traceability: 3-Layer Audit Architecture

| Layer | Tool | Captures |
|-------|------|---------|
| **Agent trajectory** | AgentLens (OTel proxy) | Every LLM call, tool use, response |
| **Orchestration** | loguru | State transitions, DAG progress, timing |
| **Business audit** | Custom (`audit/trail.py`) | Lineage, provenance, approvals, QC results |

**Append-only audit trail** -- no record deletion
Every `AuditRecord`: timestamp, agent, input hash, output hash, rule, QC result, approval

Export: **JSON** (programmatic) + **HTML** (presentation)

Satisfies 21 CFR Part 11 traceability requirements.

<!-- Speaker notes: Three layers because they serve different audiences. Agent trajectory is for debugging agent behavior. Orchestration logs are for operations. The business audit trail is for regulators and QA -- it answers "who derived this variable, from what source, with what logic, was it independently verified, and who approved it?" The audit trail is append-only by design. -->

---

## Memory: Short-Term + Long-Term

| | Short-Term | Long-Term |
|---|-----------|----------|
| **Scope** | Single workflow run | Cross-run knowledge base |
| **Storage** | JSON per run | SQLite (SQLAlchemy async) |
| **Contains** | FSM state, intermediate outputs, pending approvals | Validated patterns, human feedback, QC history |
| **Lifecycle** | Cleared on completion | Persists and grows |
| **Retrieval** | By workflow_id | By variable type + spec similarity |

**Before generating code:** agent tools query long-term memory for matching patterns. Matches injected as reference implementations -- context, not constraint.

**Production:** `DATABASE_URL` env var change -> PostgreSQL. Zero code changes.

<!-- Speaker notes: Short-term memory is working memory -- what's needed for the current derivation run. Long-term memory is institutional knowledge -- what the team has learned over time. When a new study has an AGE_GROUP derivation, the agent sees "here's an approved pattern from cdiscpilot01" and can adapt it rather than generating from scratch. This reduces LLM calls and improves consistency. Repository pattern means swapping SQLite for PostgreSQL is a config change. -->

---

## Demo: Running on CDISC Pilot Data

**Input:** `specs/adsl_cdiscpilot01.yaml` + SDTM XPT files (DM, EX, DS, SV domains)

**7 derivations:** AGEGR1, TRTDUR, SAFFL, ITTFL, EFFFL, DISCONFL, DURDIS

```
1. Spec Interpreter parses YAML, flags DURDIS as underspecified
   (requires MH domain not in source -- tests ambiguity handling)
2. DAG built: EFFFL depends on ITTFL + SAFFL (computed first)
3. Coder + QC run in parallel per variable
4. Comparator checks outputs against each other AND ground truth
   (official CDISC ADaM as reference)
5. Auditor generates lineage report
```

**Ground truth validation:** derived ADaM compared against official cdiscpilot01 ADaM.

<!-- Speaker notes: Walk through the demo. The DURDIS derivation is deliberately underspecified in the spec -- it requires disease onset date from MH domain which we don't include. This tests whether the Spec Interpreter flags the ambiguity. The ground truth comparison is key: we're not just checking internal consistency, we're validating against the official CDISC pilot ADaM dataset. Every pharma data scientist on the panel knows this dataset. -->

---

## Trade-offs

| Decision | Trade-off | Our Choice |
|----------|----------|------------|
| **Automation vs. control** | Fully autonomous vs. human gates everywhere | 4 gates at critical points; auto-approve on QC match |
| **LLM vs. rules** | Pure generation vs. deterministic engine | Hybrid: LLM generates, rules verify, guards enforce |
| **Flexibility vs. compliance** | Adaptable vs. locked-down | Same engine, different guard configs per study |
| **Framework vs. custom** | CrewAI orchestration vs. own workflow | PydanticAI agents + custom async orchestration |
| **Data exposure** | Send data to LLM vs. no data | Dual-dataset: agents see shape, not content |

The system is designed so that **doing the right thing is the path of least resistance.**

<!-- Speaker notes: Every trade-off is deliberate and documented in decisions.md. The framework choice is particularly important: we could have used CrewAI's built-in orchestration, but it doesn't support reliable async, web-based HITL, or structured Pydantic output. We chose PydanticAI for agent abstractions and built domain-specific orchestration -- because the orchestration topology IS the clinical workflow. -->

---

## Production Path

| Prototype | Production |
|-----------|------------|
| SQLite | PostgreSQL (same SQLAlchemy models) |
| External Claude API | Azure OpenAI in Sanofi VNet |
| Single process | Docker Compose (6 containers) |
| Docker Compose | Kubernetes (same images, Helm chart) |
| Single `guards.yaml` | ConfigMap per study |

**6 containers:** nginx, Streamlit, FastAPI, PostgreSQL, AgentLens, Grafana/Loki

**Backend is stateless** -- all state in PostgreSQL.
N replicas behind nginx = horizontal scaling, zero code changes.

<!-- Speaker notes: The prototype runs locally. Production is Docker Compose with 6 service-separated containers. The migration path to Kubernetes is deployment-level only -- same container images, same database schema, same agent definitions. The backend is stateless by design, so scaling is just adding replicas. Guard configurations become per-study ConfigMaps in K8s, enabling different compliance levels per regulatory context. -->

---

## Quality

| Metric | Value |
|--------|-------|
| Tests passing | **148** |
| Coverage (core logic) | **85%** |
| Pyright errors (strict mode) | **0** |
| Ruff violations | **0** |
| Import-linter contracts | **19/19** |
| Custom pre-commit checks | **10** (AST-based) |
| Dead code (vulture) | **0** |

**10 custom AST checks:** domain purity, patient data leak detection, datetime safety,
enum discipline, LLM gateway enforcement, file/function length, no SQL in engine,
no UI exceptions in lower layers, repo DI enforcement

<!-- Speaker notes: This is not typical for a one-week homework. These are our default engineering practices, not bolt-on extras. The 10 custom pre-commit checks use AST parsing, not regex -- they catch real architectural violations. Patient data leak detection scans agent tool functions for df.head() or df.to_csv() calls that would send data to the LLM. Every push runs all of these. -->

---

## Limitations & Future Work

**Current prototype boundaries:**
- **ADSL only** -- BDS (longitudinal per-visit) is the natural next phase
- **YAML specs only** -- production needs PDF/Word parsing (SAP documents)
- **Single study** -- memory architecture supports multi-study, not yet implemented
- **No CDISC conformance validation** -- Pinnacle 21 integration is needed
- **Rule-based guards** -- RAG-backed Sentinel with CDISC IG is the evolution

**What we would build next:**
1. BDS support (ADAE, ADLB -- one row per patient/visit/parameter)
2. PDF spec parsing (SAP -> YAML -> engine)
3. Multi-study pattern learning (cross-study long-term memory)
4. CDISC conformance post-check (Pinnacle 21 integration)

<!-- Speaker notes: Be honest about boundaries. The prototype covers ADSL -- one row per patient. BDS datasets are more complex but the architecture supports them. PDF parsing is a separate NLP problem we deliberately scoped out. Multi-study learning is the real platform play -- derivation patterns validated in Study A accelerate Study B. The memory architecture is already designed for this. -->

---

## Thank You -- Questions?

<br/>

> *"Science sans conscience n'est que ruine de l'ame."* -- Rabelais

<br/>

In clinical AI, conscience is not philosophy.
It is **double programming**, **human gates**, **append-only audit trails**,
and agents that **never see patient data**.

<br/>

**GitHub:** [repository link] | **148 tests** | **85% coverage** | **19 contracts**

<!-- Speaker notes: Close with the Rabelais quote -- it connects directly to the assignment. In pharma AI, "conscience" means building verification, oversight, and traceability into the architecture itself. The system is designed so that the safe path and the easy path are the same path. Thank the panel, open for questions. -->
