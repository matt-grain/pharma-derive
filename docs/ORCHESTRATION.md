# Orchestration Design

## 1. Agent Roster

### 1.1 Spec Interpreter Agent

| Property | Value |
|----------|-------|
| **Role** | Parse transformation specification, extract structured derivation rules, detect ambiguities |
| **Input** | Transformation spec (YAML) + SDTM dataset metadata (column names, types, sample values) |
| **Output** | List of `DerivationRule` objects (structured) + list of ambiguity flags |
| **LLM needed?** | Yes — natural language spec interpretation, ambiguity detection |
| **Tools** | `read_spec` (load YAML), `inspect_sdtm` (column stats), `flag_ambiguity` (record concern) |
| **Orchestration** | Sequential — runs first, before anything else |
| **HITL gate** | After output: human reviews extracted rules and resolves flagged ambiguities |

**Why a separate agent:** Spec interpretation is a document understanding task — fundamentally different from code generation. In real pharma, the biostatistician writes the SAP, a spec writer translates it to derivation specs, and a different programmer implements it. We mirror that separation.

**What it checks for:**
- Missing derivation logic (variable listed but no rule)
- Ambiguous conditions ("elderly" without age threshold)
- Conflicting rules (two rules deriving the same variable differently)
- Missing source variables (spec references a column not in SDTM)
- Circular dependencies (A depends on B depends on A)

---

### 1.2 Derivation Coder Agent (Primary Programmer)

| Property | Value |
|----------|-------|
| **Role** | Generate Python code implementing each derivation rule |
| **Input** | Single `DerivationRule` + SDTM DataFrame + previously derived columns (from DAG order) |
| **Output** | Python function `(df: DataFrame) -> Series` + explanation of approach |
| **LLM needed?** | Yes — translates structured rules into executable Python |
| **Tools** | `execute_code` (sandboxed pandas execution), `inspect_data` (peek at source columns) |
| **Orchestration** | Runs per-variable in DAG topological order |
| **HITL gate** | None by default — QC agent handles verification |

**Why a separate agent:** In regulatory double programming, the primary programmer works from the spec alone. This agent has access to the spec and data but NOT to the QC agent's work.

**Code generation constraints:**
- Must produce a pure function (no side effects, no global state)
- Must handle nulls/NaN explicitly (clinical data has missing values)
- Must include inline comments explaining the derivation logic
- Output validated: correct dtype, no unexpected nulls, value ranges match spec

---

### 1.3 QC Programmer Agent (Independent Verification)

| Property | Value |
|----------|-------|
| **Role** | Independently re-implement the same derivation from the spec — double programming |
| **Input** | Same `DerivationRule` + same SDTM DataFrame (NO access to Coder's output or code) |
| **Output** | Python function `(df: DataFrame) -> Series` + explanation of approach |
| **LLM needed?** | Yes — independent code generation |
| **Tools** | Same as Coder: `execute_code`, `inspect_data` |
| **Orchestration** | Runs concurrently with Coder (Concurrent + Compare pattern) |
| **HITL gate** | Only on QC mismatch that Debugger can't resolve |

**Why a separate agent:** This is the pharma gold standard for data integrity. FDA expects independent verification of all derived variables. Two separate agents with isolated contexts mirror the real-world practice where two programmers sit in different rooms.

**Independence enforcement:**
- QC agent has a DIFFERENT system prompt: "You are a QC programmer. Your job is to verify a derivation by implementing it independently. Use a different approach than you normally would — if the obvious implementation is a conditional, try a mapping; if the obvious approach is iterative, try vectorized."
- QC agent's conversation history is isolated — never injected with Coder's responses
- Post-comparison: AST similarity check between the two implementations. If similarity > 80%, flag as "insufficient independence" — the QC added no value

---

### 1.4 Debugger Agent

| Property | Value |
|----------|-------|
| **Role** | When Coder and QC outputs diverge, diagnose why and propose a fix |
| **Input** | Both implementations (code + output), the `DerivationRule`, the divergent rows |
| **Output** | Root cause analysis + recommended fix + which implementation is correct |
| **LLM needed?** | Yes — reasoning over two code paths and their divergent outputs |
| **Tools** | `diff_outputs` (row-level comparison), `execute_code` (test hypotheses), `inspect_data` |
| **Orchestration** | Runs only on QC mismatch (Retry with Escalation pattern) |
| **HITL gate** | If Debugger can't resolve → escalate to human with full context |

**Why a separate agent:** Debugging requires a different cognitive mode than generation — comparing two approaches, reasoning about edge cases, and identifying which assumptions were wrong. Keeping this separate prevents the Coder from "marking its own homework."

**Debugging strategy:**
1. Identify divergent rows (which patient IDs differ?)
2. For each divergent row, trace through both implementations step by step
3. Check against the spec: which implementation matches the rule?
4. If the spec is ambiguous (both interpretations are valid), flag for human
5. Propose a fix and re-run to verify

---

### 1.5 Auditor Agent

| Property | Value |
|----------|-------|
| **Role** | Generate full audit trail: lineage report, compliance checks, summary |
| **Input** | Complete enhanced DAG (all nodes with provenance, QC status, approvals) |
| **Output** | Audit report (JSON + human-readable HTML), compliance checklist |
| **LLM needed?** | Yes — natural language summarization, anomaly highlighting |
| **Tools** | `export_lineage` (DAG → JSON), `generate_report` (HTML), `check_compliance` |
| **Orchestration** | Runs last, after all derivations are approved |
| **HITL gate** | Final review: human signs off on the audit report |

**Why a separate agent:** Auditing requires a compliance mindset — reviewing the entire process, not generating or verifying individual derivations. In pharma, QA/QC review is always independent from production.

**Audit trail contents:**
- For each derived variable: source columns → rule → code → agent → QC result → human approval
- Timeline of all agent actions with timestamps
- All human interventions (edits, approvals, rejections) with before/after
- Summary statistics: % auto-approved, % QC mismatches, % human interventions
- DAG visualization with status coloring (green=passed, yellow=warning, red=failed)

---

## 2. Orchestration Patterns

### 2.1 Pattern Catalog

| Pattern | Description | Where Used |
|---------|-------------|------------|
| **Sequential** | Steps execute in strict order, each depends on the previous | Overall workflow: spec → DAG → derive → audit |
| **Fan-out / Fan-in** | Independent tasks launch in parallel, results collected when all complete | Derivations with no mutual dependencies in the DAG |
| **Concurrent + Compare** | Two agents work on the same task independently, outputs compared | Double programming: Coder and QC on same variable |
| **Retry with Escalation** | On failure, retry with a specialized agent; if still failing, escalate to human | QC mismatch → Debugger → if unresolved → human |
| **Gate (HITL)** | Workflow pauses until human approves, edits, or rejects | Spec review, QC disputes, final approval |

### 2.2 Overall Workflow — Sequential

```
┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐
│   SPEC     │───►│    DAG     │───►│  DERIVE    │───►│   REVIEW   │───►│   AUDIT    │
│ INTERPRET  │    │  BUILDER   │    │  + VERIFY  │    │  (HITL)    │    │            │
└────────────┘    └────────────┘    └────────────┘    └────────────┘    └────────────┘
     │                  │                 │                  │                 │
  HITL gate 1      (automatic)      per-variable       HITL gate 3      HITL gate 4
  (spec review)                    (see 2.3+2.4)     (final outputs)   (audit sign-off)
```

**Decision:** Sequential is the only safe choice for the overall workflow. Each phase depends on the previous: you can't build a DAG without parsed rules, can't derive without a DAG, can't audit without completed derivations.

### 2.3 Per-Variable — Fan-out / Fan-in

Within the DERIVE phase, multiple derivations CAN run in parallel — but only if they don't depend on each other.

```
DAG topological sort produces layers:

Layer 0 (no dependencies):     AGE_GROUP    TREATMENT_DURATION
                                  │              │
Layer 1 (depends on layer 0):  RESPONSE_FLAG  SAFFL  ITTFL  PPROTFL
                                  │
Layer 2 (depends on layer 1):  RISK_GROUP

Layer 0: all variables fan-out (parallel)  ───► fan-in (collect results)
Layer 1: all variables fan-out (parallel)  ───► fan-in (collect results)
Layer 2: sequential (only RISK_GROUP)
```

**Decision:** Fan-out within DAG layers for performance. Fan-in collects all results before the next layer starts. This is safe because topological layering guarantees no cross-dependencies within a layer.

### 2.4 Per-Variable — Concurrent + Compare (Double Programming)

For EACH variable, the Coder and QC agents run concurrently:

```
                    ┌──────────────────┐
                    │  DerivationRule   │
                    │  + SDTM data     │
                    └────────┬─────────┘
                             │
                 ┌───────────┴───────────┐
                 │                       │
          ┌──────▼──────┐         ┌──────▼──────┐
          │   CODER     │         │     QC      │
          │   Agent     │         │   Agent     │
          │ (primary)   │         │ (independent│
          │             │         │  context)   │
          └──────┬──────┘         └──────┬──────┘
                 │                       │
                 └───────────┬───────────┘
                             │
                      ┌──────▼──────┐
                      │ COMPARATOR  │
                      │             │
                      │ 1. Output   │
                      │    match?   │
                      │ 2. AST      │
                      │    similar? │
                      └──────┬──────┘
                             │
                 ┌───────────┼───────────┐
                 │           │           │
              MATCH       MISMATCH    TOO SIMILAR
              + independent              (>80% AST)
                 │           │           │
            auto-approve  Debugger    re-run QC
                         Agent       with stronger
                             │       divergence prompt
                             │
                    ┌────────┼────────┐
                    │                 │
                 RESOLVED         UNRESOLVED
                    │                 │
               auto-approve     escalate to
                               human (HITL gate 2)
```

**Decision:** Concurrent execution for performance (both agents call the LLM at the same time). Compare phase is deterministic (no LLM needed) — pandas DataFrame comparison + AST similarity via `ast.dump()`. Three outcomes: match, mismatch, or insufficient independence.

### 2.5 Retry with Escalation

When QC detects a mismatch:

```
QC mismatch detected
       │
       ▼
  Debugger Agent analyzes (attempt 1)
       │
   ┌───┴───┐
   │       │
 fixed   still broken
   │       │
   ▼       ▼
 re-verify  Debugger Agent (attempt 2, different strategy)
               │
           ┌───┴───┐
           │       │
         fixed   still broken
           │       │
           ▼       ▼
         re-verify  ESCALATE to human
                       │
                    Human reviews:
                    - Both implementations
                    - Debugger analysis
                    - Divergent rows
                    - Spec text
                       │
                    Human decides:
                    - Pick Coder's version
                    - Pick QC's version
                    - Write manual override
                    - Flag spec as ambiguous
```

**Decision:** Max 2 Debugger attempts before human escalation. Rationale: if the Debugger can't figure it out in 2 tries, the issue is likely a spec ambiguity that requires human judgment — not a coding bug.

### 2.6 HITL Gates

**Design choice:** One deep gate with three actions instead of four shallow gates.

The original design proposed 4 gates (Spec Review, QC Dispute, Final Review, Audit Sign-off). After evaluation, we consolidated to **one deep review gate** (`human_review` step in `config/pipelines/clinical_derivation.yaml`) with richer actions. Rationale: every HITL gate is a reviewer context switch. Clinical SMEs are expensive; their time is the bottleneck. A single rich dialog where the reviewer handles all concerns at once is more efficient than four separate interruptions.

| Action | Endpoint | What Human Sees | What Gets Persisted |
|--------|----------|----------------|---------------------|
| **Approve with feedback** | `POST /workflows/{id}/approve` | ApprovalDialog with per-variable checkboxes (defaulting to approved), optional free-text notes | One `FeedbackRow` per variable with `action_taken = approved/rejected` |
| **Reject with reason** | `POST /workflows/{id}/reject` | RejectDialog requiring mandatory reason | Workflow-level `FeedbackRow`, `HUMAN_REJECTED` audit event, FSM transitions to `HUMAN_REJECTED` via `WorkflowRejectedError` |
| **Override code** | `POST /workflows/{id}/variables/{var}/override` | CodeEditorDialog with current code editable, mandatory change reason | New code executed on `derived_df` before state mutation; on success DAG node + audit trail + `FeedbackRow` updated together |

**Enterprise mode:** `config/pipelines/enterprise.yaml` defines 3 separate `hitl_gate` steps for 21 CFR Part 11 environments requiring more formal separation of concerns. Same engine, different pipeline YAML.

---

## 2.7 Concurrency Model — Why asyncio.gather, Not Framework-Level Parallelism

PydanticAI's `agent.run()` is natively async (I/O-bound LLM calls). However, PydanticAI does **not** provide a built-in parallel agent dispatcher — its documented multi-agent patterns (delegation, hand-off, graph) are all sequential. Pydantic Graph explicitly notes that parallel node execution is not yet supported (GitHub issue #704).

**Our approach:** Compose parallel execution at the orchestration layer using Python's standard `asyncio.gather`:

```python
coder_result, qc_result = await asyncio.gather(
    coder_agent.run(task, deps=coder_deps),
    qc_agent.run(task, deps=qc_deps),
)
```

**Why this is the right design:**

| Concern | Why asyncio.gather is correct |
|---------|------------------------------|
| **It works** | Validated in prototype — two requests arrived within 0.01s, true I/O parallelism |
| **Isolation** | Each `agent.run()` is an independent coroutine with its own state — no shared memory contamination. For double programming, this isolation is a regulatory **requirement**, not a limitation |
| **Explicit control** | The orchestrator decides which agents run concurrently based on the DAG layer. This is domain logic (clinical workflow rules), not agent framework logic |
| **No framework lock-in** | `asyncio.gather` is Python standard library. If we swap PydanticAI for another async-capable framework, the parallelism code doesn't change |
| **Error handling** | `asyncio.gather(return_exceptions=True)` lets us handle per-agent failures without crashing the entire DAG layer |

**The principle:** Parallelism belongs in the orchestration layer, not in the agent framework. The agent framework handles LLM communication, tool binding, and output validation. The orchestrator handles workflow topology, concurrency, and error recovery. Clean separation of concerns.

---

## 3. AgentLens Integration — Observer AND Circuit Breaker

### 3.1 The Dual Role

AgentLens sits between CrewAI and the LLM as an OpenAI-compatible proxy. In standard mode, it observes and traces. With **guards enabled**, it becomes an active participant — evaluating every LLM response in real time and intervening when violations are detected.

```
                                    AgentLens Proxy
                                    ┌─────────────────────────────────┐
CrewAI Agent ──── request ─────────►│  1. Forward to LLM              │
                                    │  2. Receive response            │
                                    │  3. Capture trace (observer)    │
                                    │  4. Run guard evaluators        │──── if ESCALATE ──► Mailbox
                                    │  5. Act on result:              │                     (human/agent)
                                    │     - PASS: return as-is        │
                                    │     - WARN: append warning      │◄── human/agent responds
                                    │     - BLOCK: replace response   │
                                    │     - ESCALATE: hold for review │
                                    └─────────────────┬───────────────┘
                                                      │
CrewAI Agent ◄──── (modified) response ───────────────┘
```

The agent framework never knows it's being evaluated — the proxy is invisible at the OpenAI API protocol level.

### 3.2 Guard Rules for Clinical Derivation

```yaml
# guards.yaml — Clinical Data Derivation Engine
enabled: true
rules:
  # --- Data integrity guards ---
  - evaluator_name: hallucination_flag
    threshold: 0.5
    action: warn
    # Agent claims a data fact without tool evidence?
    # Warn and let it self-correct on next turn.

  - evaluator_name: unauthorized_action
    threshold: 1.0
    action: block
    # Agent tries to modify source SDTM data or write outside sandbox?
    # Hard block. Source data is immutable.

  - evaluator_name: policy_violation
    threshold: 1.0
    action: escalate
    # Agent generates code that drops patients from analysis population
    # without explicit spec justification? Hold for human review.

  # --- Derivation-specific guards ---
  - evaluator_name: loop_detector
    threshold: 0.5
    action: warn
    # Agent stuck retrying the same failed derivation approach?
    # Warn to break the loop.

  # --- Cost/operational guards ---
  - evaluator_name: cost_threshold
    threshold: 0.8
    action: warn
    # Approaching token budget? Warn the orchestrator.
```

### 3.3 The Sentinel Agent — External Intervention via Mailbox

This is the key innovation: when a guard **escalates**, the response doesn't just go to a human — it goes to the **mailbox**, where an external agent (or human) can review and respond.

In production, this external agent is the **Sentinel** — a separate, independent AI agent (outside the CrewAI workflow) that:
- Receives escalated responses with full context
- Has access to the transformation spec, CDISC compliance rules, and organizational policies
- Can approve, modify, or reject the response
- Logs its decision as an audit record

```
┌──────────────────────────────────────────────────────────────────┐
│                    CrewAI Orchestration                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐              │
│  │  Spec   │  │  Coder  │  │   QC    │  │ Auditor │              │
│  │Interpret│  │         │  │         │  │         │              │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘              │
│       │            │            │            │                   │
│       └────────────┴────────────┴────────────┘                   │
│                           │                                      │
│                    All LLM calls                                 │
│                           │                                      │
└───────────────────────────┼──────────────────────────────────────┘
                            │
                     ┌──────▼──────┐
                     │  AgentLens  │
                     │   Proxy     │
                     │  + Guards   │
                     └──────┬──────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
           normal        warn          ESCALATE
           (pass)     (append +         │
              │       continue)    ┌────▼────┐
              │          │         │ Mailbox │
              ▼          ▼         └────┬────┘
           return     return            │
                                 ┌──────▼──────┐
                                 │  SENTINEL   │  ◄── Independent agent
                                 │  AGENT      │      (outside CrewAI)
                                 │             │
                                 │  - Reviews  │
                                 │    context  │
                                 │  - Checks   │
                                 │    policies │
                                 │  - Decides  │
                                 │    action   │
                                 └──────┬──────┘
                                        │
                              ┌─────────┼─────────┐
                              │         │         │
                           approve    modify    reject
                              │         │         │
                              ▼         ▼         ▼
                           response  corrected  block
                           released  response   message
                                     released   returned
```

### 3.4 What the Sentinel Guards Against

In clinical data derivation, the following violations are critical enough to warrant external intervention:

| Violation | Why It Matters | Guard Action |
|-----------|---------------|--------------|
| **Patient exclusion without justification** | Dropping patients from analysis changes efficacy/safety results. FDA will audit this. | ESCALATE → Sentinel checks spec for exclusion criteria |
| **Hardcoded values instead of derivation logic** | `return "High"` instead of computing from source. Passes QC but isn't a real derivation. | ESCALATE → Sentinel verifies code references source columns |
| **Source data mutation** | Agent modifies SDTM input instead of deriving new columns. Destroys data integrity. | BLOCK (immediate) |
| **Non-deterministic code** | `random.choice()`, `datetime.now()` in derivation. Results aren't reproducible. | BLOCK (immediate) |
| **Derivation references non-existent column** | Code uses a column name that doesn't exist in the dataset. Will crash at runtime. | WARN → self-correct |
| **Token budget exceeded** | Runaway agent consuming excessive LLM tokens (infinite retry loops). | WARN → orchestrator can terminate |

### 3.5 Why This Matters for Sanofi

Traditional approach: agents run → bad output → detected during review → re-run → costly.

AgentLens guard approach: agents run → bad output **caught in real time** → blocked or escalated **before it enters the workflow state** → no contaminated intermediate results.

In regulated environments, this distinction is critical:
- **Post-hoc detection** means contaminated results may have been used downstream before the error was caught. You need to prove they weren't.
- **Real-time prevention** means the bad output never entered the audit trail. Cleaner compliance story.

This is what Shanshan meant by "AgentLens to observe AND act" — the proxy isn't just logging, it's enforcing quality gates at the LLM response level, before the agent framework even sees the response.

---

## 4. Agent Framework Selection — CrewAI vs PydanticAI

### 4.1 CrewAI Evaluation — What Works, What Doesn't

We evaluated CrewAI v1.10+ for our orchestration patterns. Honest findings:

| Capability | CrewAI Status | Impact |
|-----------|---------------|--------|
| Agent definition & role prompting | **Stable, excellent** | Good abstractions |
| Sequential process | **Stable** | Works for simple chains |
| `async_execution=True` | **Buggy** — missed/duplicated tasks (PR #2466) | Cannot rely on for production parallelism |
| `context=[task_a, task_b]` | **Works** but dumps raw text | No structured merging |
| `human_input=True` | **CLI stdin only** | Cannot integrate with Streamlit |
| Hierarchical process | **Unpredictable** | Manager LLM makes poor delegation choices |
| Consensual process | **Not implemented** | Listed in docs but doesn't work |

### 4.2 PydanticAI Evaluation — Prototype Validated

We evaluated PydanticAI as an alternative and **prototyped all 5 required patterns (5/5 passed)**:

| Capability | PydanticAI Status | Prototype Result |
|-----------|-------------------|-----------------|
| Agent definition with typed I/O | **Excellent** — `Agent[DepsType, OutputType]` | ✓ Proto 01: `DerivationResult` model validated |
| Structured Pydantic output | **First-class** — retries on validation failure | ✓ Proto 01: auto-retry on malformed JSON |
| True async parallelism | **Native** — `asyncio.gather()` works cleanly | ✓ Proto 02: two requests arrived within 0.01s |
| Custom tools | **Decorator-based** — `@agent.tool` with typed params | ✓ Proto 03: inspect_data + execute_code in multi-turn loop |
| Dependency injection | **`RunContext[DepsType]`** — typed, tool-accessible | ✓ Proto 04: DataFrame + DerivationRule injected |
| Multi-agent orchestration | **Compose yourself** — no built-in crew abstraction | ✓ Proto 05: full Spec→Coder+QC→Compare workflow |
| HITL | **Built-in approval workflows** | Not yet prototyped (Streamlit integration planned) |
| Observability | **Logfire (OTel-native)** + AgentLens proxy | ✓ All protos: full traces captured in AgentLens |
| OpenAI-compatible endpoint | **Yes** — `OpenAIChatModel` with custom `OpenAIProvider` | ✓ All protos: AgentLens mailbox as LLM backend |

**Decision: PydanticAI chosen.** It solves every CrewAI limitation we found, validates against our required patterns, and aligns with our type-safe, production-grade engineering discipline.
| Cross-crew memory | **No sharing** between parallel crews | Must pass outputs explicitly |

### 4.2 Our Strategy: CrewAI for Agents, Custom Orchestration for Workflow

**Decision:** Use CrewAI for what it's good at (agent abstractions), build our own orchestration for what it's not (parallelism, HITL, workflow state).

```
┌─────────────────────────────────────────────────────────────┐
│                    Custom Orchestrator                        │
│              (Python async + workflow FSM)                    │
│                                                              │
│  Responsibilities:                                           │
│  - Workflow state machine (CREATED → SPEC_REVIEW → ...)     │
│  - DAG layer execution (topological order)                   │
│  - Fan-out via asyncio.gather()                             │
│  - HITL gates via Streamlit (DB-backed pending state)       │
│  - Error handling, retries, escalation                      │
│                                                              │
│  For each agent task, delegates to:                          │
│  ┌───────────────────────────────────────────────────┐      │
│  │              CrewAI (per-task Crews)               │      │
│  │                                                    │      │
│  │  - Agent definition (role, goal, backstory)       │      │
│  │  - Tool binding                                    │      │
│  │  - Single-task Crew execution (kickoff)           │      │
│  │  - Prompt management                               │      │
│  └───────────────────────────────────────────────────┘      │
│                           │                                  │
│                    All LLM calls via:                        │
│  ┌───────────────────────────────────────────────────┐      │
│  │              AgentLens Proxy                       │      │
│  │  - Trace capture (observer)                       │      │
│  │  - Guard evaluation (circuit breaker)             │      │
│  │  - Mailbox (dev mode) / Proxy (prod mode)         │      │
│  └───────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Pattern Implementation — How Each Actually Works

**Sequential (overall workflow):**
```python
# Our orchestrator controls the flow, NOT CrewAI's Process.sequential
async def run_workflow(state: WorkflowState) -> WorkflowState:
    state = await run_spec_interpretation(state)
    state = await wait_for_hitl_approval(state, gate="spec_review")  # Streamlit
    state = build_dag(state)
    state = await run_derivations(state)  # DAG-ordered, see below
    state = await wait_for_hitl_approval(state, gate="final_review")
    state = await run_audit(state)
    return state
```

**Fan-out / Fan-in (parallel derivations within a DAG layer):**
```python
async def run_dag_layer(layer: list[DerivationRule], state: WorkflowState):
    # True parallelism via asyncio.gather — NOT CrewAI async_execution
    results = await asyncio.gather(*[
        run_single_derivation(rule, state) for rule in layer
    ])
    return merge_results(results, state)
```

**Concurrent + Compare (double programming):**
```python
async def run_single_derivation(rule: DerivationRule, state: WorkflowState):
    # Two separate single-task Crews, launched in parallel
    coder_crew = build_coder_crew(rule)
    qc_crew = build_qc_crew(rule)  # isolated context — no access to coder

    coder_result, qc_result = await asyncio.gather(
        coder_crew.akickoff(inputs={"rule": rule, "data": state.sdtm}),
        qc_crew.akickoff(inputs={"rule": rule, "data": state.sdtm}),
    )

    # Programmatic comparison — NOT an LLM task
    comparison = compare_outputs(coder_result, qc_result)
    if comparison.match:
        return auto_approve(coder_result, comparison)
    else:
        return await run_debugger(rule, coder_result, qc_result, comparison, state)
```

**HITL Gates (Streamlit-based, not CLI stdin):**
```python
async def wait_for_hitl_approval(state: WorkflowState, gate: str):
    # Write pending approval to DB — Streamlit reads this
    pending = PendingApproval(
        gate=gate,
        workflow_id=state.id,
        data=state.current_output,
        requested_at=datetime.utcnow(),
    )
    await state.db.save_pending(pending)

    # Poll DB until human approves/rejects via Streamlit UI
    while True:
        decision = await state.db.get_decision(pending.id)
        if decision is not None:
            state.audit.record_human_decision(gate, decision)
            if decision.action == "reject":
                raise HumanRejectionError(gate, decision.reason)
            return state.apply_human_edits(decision.edits)
        await asyncio.sleep(1)  # poll interval
```

### 4.4 Agent ↔ CrewAI Configuration

Each agent is a single-task Crew — simple, reliable, no orchestration complexity:

```python
from crewai import Agent, Task, Crew, LLM

llm = LLM(
    model="openai/cdde-agent",
    base_url="http://localhost:8650/v1",  # AgentLens proxy
    api_key="not-needed-for-mailbox",
)

def build_coder_crew(rule: DerivationRule) -> Crew:
    agent = Agent(
        role="derivation_coder",
        goal="Generate correct Python derivation code from a structured rule",
        backstory="You are a senior statistical programmer...",
        llm=llm,
        allow_delegation=False,
        max_iter=5,
        tools=[execute_code_tool, inspect_data_tool],
    )
    task = Task(
        description=f"Implement derivation for {rule.target_variable}...",
        agent=agent,
        expected_output="Python function (df: DataFrame) -> Series",
    )
    return Crew(agents=[agent], tasks=[task])
```

### 4.5 LLM Modes via AgentLens

```python
# Same LLM config for all modes — only AgentLens server config changes
llm = LLM(
    model="openai/cdde-agent",
    base_url="http://localhost:8650/v1",
    api_key="not-needed-for-mailbox",
)
```

| Mode | AgentLens Config | Use Case |
|------|-----------------|----------|
| **Mailbox** | `--mode mailbox` | Dev: Anima plays the LLM, zero token cost |
| **Proxy** | `--mode proxy --proxy-to https://api.anthropic.com` | Test: real Claude API, validates end-to-end |
| **Proxy + Guards** | `--mode proxy --proxy-to ... --guards guards.yaml` | Prod: real LLM + real-time evaluation + Sentinel |

---

## 5. Possible Improvements — Not Implemented in This Version

### 5.1 AutoGen Coordination Layer for Verification

**Idea:** Add an AutoGen group chat layer specifically for the Comparison phase. Instead of a simple programmatic comparison (output match + AST similarity), an AutoGen conversation between Coder, QC, and a Moderator agent could:
- Have the Coder explain their approach
- Have the QC explain their approach
- Have the Moderator identify whether the approaches are truly independent
- Reach consensus on which implementation is correct when outputs diverge

**Why not now:** Adds a second framework dependency (AutoGen alongside CrewAI), increases complexity significantly, and the programmatic comparison + Debugger agent already covers the core need. The value of AutoGen's conversational verification is highest when derivation rules are complex and ambiguous — our prototype scope (5-7 ADSL variables) doesn't require it.

**When it would make sense:** Multi-study deployments where transformation specs are long, ambiguous, and involve domain-specific edge cases that benefit from multi-agent debate rather than binary comparison.

### 5.2 AutoGen for Spec Ambiguity Resolution

**Idea:** When the Spec Interpreter flags ambiguities, instead of immediately escalating to human, an AutoGen group chat between the Spec Interpreter, a "Domain Expert" agent (with CDISC/ADaM knowledge), and a "Regulatory" agent could attempt to resolve the ambiguity automatically.

**Why not now:** Same framework overhead concern. Also, in regulated environments, ambiguous specs SHOULD go to humans — auto-resolving ambiguity in clinical data is risky and auditors will question it.

**When it would make sense:** As a "pre-filter" before human escalation — the multi-agent debate can provide a recommendation + rationale, but the human still makes the final call. Reduces human cognitive load without removing human authority.

### 5.3 Sentinel Agent with Full CDISC Knowledge Base

**Idea:** The Sentinel agent (Section 3.3) could be backed by a RAG system with the full CDISC ADaM Implementation Guide, FDA guidance documents, and ICH E6 GCP text. When a guard escalates, the Sentinel doesn't just check basic rules — it reasons against the regulatory corpus.

**Why not now:** Building a pharma-regulatory RAG is a project in itself. For the prototype, the Sentinel uses simple rule-based checks + human fallback.

**When it would make sense:** Production deployment where the volume of escalations justifies the RAG investment. This is the natural evolution path.

### 5.4 Multi-Study Learning

**Idea:** Long-term memory accumulates validated derivation patterns across studies. When a new study has similar demographics or endpoints, the system pre-populates derivation code from historical patterns, reducing LLM calls and improving consistency.

**Why not now:** Single-study prototype. But the memory architecture (repository interface, SQLite) is designed to support this.

### 5.5 CDISC Conformance Validation (Pinnacle 21 Equivalent)

**Idea:** After derivation, run the output ADaM through a CDISC conformance checker (like Pinnacle 21 / Formedix) to validate against the ADaM IG rules automatically.

**Why not now:** Pinnacle 21 is proprietary ($$$). Open-source alternatives are limited. We can mention this as an integration point.

**When it would make sense:** Immediately in production. This should be a standard post-derivation step.
