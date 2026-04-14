# CDDE Panel Interview — Quiz & Prep

**Target:** Sanofi AI/ML Lead panel interview, 1 hour, SDTM → ADaM agentic workflow
**Format:** ~90 seconds per Q on average → short answers, no rehearsed paragraphs
**Audience:** Likely mix of pharma SMEs (SDTM/ADaM/regulatory) + technical leads (architecture/AI) + hiring manager
**Your situation:** You are NOT a pharma expert. You built a working prototype and need to demonstrate that you understood the domain well enough to make the right technical decisions.

---

## How to use this quiz

1. **Read the whole file end-to-end once** (~15 min). Don't try to memorize — just build the map.
2. **Pick the 6-8 questions you're weakest on** and say the answer out loud. If it doesn't come out cleanly in 30s, write your own 3-bullet crib.
3. **During the interview**, pause 1-2 seconds before answering. Say "Good question" only if you mean it, never as a filler.
4. **If you don't know, say so.** "I didn't implement X — here's what I'd do if I had another week." Pharma reviewers respect honesty; they're trained to spot handwaving.

---

## Section 1 — SDTM basics (pharma reviewer will probe here)

### Q1.1 — What is SDTM and why does it exist?

**A:** SDTM (Study Data Tabulation Model) is the CDISC standard for representing raw clinical trial data before analysis. It exists because every sponsor used to submit data to the FDA in custom formats, which was slow and error-prone to review. SDTM forces a standardized tabular structure so the FDA reviewer can open any sponsor's dataset and immediately know where to find subject ID, adverse events, vital signs, etc.

### Q1.2 — Name 5 SDTM domains and what they contain.

**A:** DM = Demographics (one row per subject: age, sex, race, treatment arm). EX = Exposure (drug dosing records, one row per dose). DS = Disposition (completion/discontinuation events, one row per reason). SV = Subject Visits (visit schedule adherence). LB = Lab test results (one row per lab measurement). AE = Adverse Events (one row per event). VS = Vital Signs.

### Q1.3 — What's USUBJID and why does it matter?

**A:** Unique Subject Identifier — a globally unique subject ID across the entire study (usually `{STUDYID}-{SITEID}-{SUBJID}`). It's the primary key that joins every SDTM domain back to a single patient. In our CDDE, `source_loader` merges DM + EX + DS + SV on USUBJID to build the per-subject row that ADSL derivations operate on.

### Q1.4 — What's the difference between a SDTM variable and a Supplemental Qualifier (SUPP--)?

**A:** Core SDTM domains have a fixed set of columns defined by the CDISC IG. Anything sponsor-specific that doesn't fit the standard goes into a `SUPP<DOMAIN>` dataset as key-value pairs. E.g., a custom "prior anti-dementia medication" flag on Alzheimer's trial subjects would live in SUPPDM, not DM itself. Our prototype ignores SUPP-- for scope reasons — it's a known limitation.

### Q1.5 — Why is SDTM in "tall" format while ADaM is usually "wide"?

**A:** SDTM is record-per-event — one row per lab test, one row per adverse event, one row per visit — because you don't know ahead of time how many events a subject will have. ADaM restructures this into analysis-ready forms: ADSL is one row per subject (subject-level summary), BDS (Basic Data Structure) is one row per subject-parameter-visit for longitudinal analysis. Different shapes serve different analyses.

---

## Section 2 — ADaM basics (core of what CDDE produces)

### Q2.1 — What is ADaM and how is it different from SDTM?

**A:** ADaM (Analysis Data Model) is the CDISC standard for analysis-ready datasets derived from SDTM. The key word is "derived": SDTM is raw collected data, ADaM is what the statistician actually runs analyses on. Every ADaM variable must be traceable back to SDTM via a documented derivation rule — this is the core regulatory requirement CDDE automates.

### Q2.2 — What is ADSL?

**A:** Subject-Level Analysis Dataset — one row per subject, containing the variables needed for any population-level analysis (age, sex, treatment, population flags, study dates). ADSL is the "index" ADaM dataset that every other ADaM references. CDDE's current prototype targets ADSL because it's bounded scope and the CDISC Pilot Study provides ground truth.

### Q2.3 — Explain AGEGR1, TRT01P, SAFFL.

**A:** AGEGR1 = Age Group 1, a categorical bucketing of subject age (e.g., `<65`, `65-75`, `>75`). TRT01P = Planned Treatment for Period 1 — the treatment arm the subject was randomized into. SAFFL = Safety Population Flag (Y/N) — whether the subject received at least one dose and should be included in safety analyses. These three cover the three types of ADaM derivations: categorical bucketing, direct mapping with recode, and boolean flag with business rule.

### Q2.4 — What is BDS (Basic Data Structure)?

**A:** A longitudinal ADaM structure — one row per subject-parameter-visit. Used for efficacy analyses where you need to track a measurement over time (e.g., ADLB for labs, ADAE for adverse events, ADVS for vital signs). Our prototype does ADSL only — BDS is the obvious next phase because the pipeline is already shape-agnostic; only the derivation rules change.

### Q2.5 — What's an "analysis value" vs an "original value" in ADaM?

**A:** Most ADaM datasets keep both — e.g., `AVAL` is the analysis-ready numeric value and `AVALC` is the character representation. A lab result might have an original SDTM value of "< 1.0 IU/L" which becomes `AVAL=0.5` (imputed) and `AVALC="< 1.0"` for traceability. This dual-representation is regulatory traceability baked into the data model.

---

## Section 3 — CDISC IG and regulatory concepts

### Q3.1 — What is the CDISC Implementation Guide (IG)?

**A:** The CDISC IG is the normative spec for what each SDTM / ADaM variable means, what type it should be, controlled vocabulary (e.g., `SEX` can only be "M", "F", "U", "UNDIFFERENTIATED"), and how derivations should be documented. It's ~500+ pages per standard. Production CDDE would RAG against the IG to ground the Spec Interpreter agent — we treat that as future work.

### Q3.2 — What is ICH E6?

**A:** International Conference on Harmonisation Good Clinical Practice guideline. E6 is the overall GCP umbrella. Relevant to CDDE: E6 R2 introduced the risk-based quality management framework, which is why double programming of derived variables is an industry norm — two independent implementations catch single-programmer errors.

### Q3.3 — What is 21 CFR Part 11?

**A:** FDA regulation on electronic records and electronic signatures for any system used in FDA-regulated industries. Key subsections CDDE addresses: §11.10(e) secure time-stamped audit trails (→ `audit/trail.py`), §11.10(f) operational system checks for permitted sequencing (→ `PipelineFSM`), §11.10(h) authority checks — NOT implemented in the prototype, this would need SSO/LDAP in production.

### Q3.4 — What is Pinnacle 21?

**A:** The industry-standard CDISC conformance validator. Runs ~1,000 checks against SDTM and ADaM datasets to verify they comply with the IG — variable types, controlled vocabulary, derivation traceability. We don't integrate Pinnacle 21 in the prototype; it would be a post-export validation step in production. Listed as a known limitation on my slides.

### Q3.5 — Why does pharma care so much about traceability?

**A:** Because a wrong derivation can change the outcome of a drug approval decision — that's billions of dollars and potentially patient safety at stake. If a reviewer in 3 years' time asks "why is this subject's AGEGR1 value `>75` when their recorded age is 74?", you need to reconstruct the exact derivation rule, input data, intermediate computations, and any human overrides that were applied. CDDE's append-only audit trail exists to make that reconstruction possible in seconds instead of weeks.

### Q3.6 — What is "double programming"?

**A:** Two programmers independently implement the same derivation from the same specification, then compare the outputs programmatically. If outputs match, the derivation is verified. If they diverge, either the spec is ambiguous or one programmer made a mistake. It's the single most important QC practice in clinical data programming and is baked into CDDE as the Coder agent + QC Programmer agent pattern.

---

## Section 4 — CDDE architecture

### Q4.1 — Why 5 agents specifically? Why not 1 or 10?

**A:** Each agent has a single cognitive responsibility that the others shouldn't interfere with. Spec Interpreter needs document understanding; Coder needs code generation; QC needs independent re-implementation without seeing the primary; Debugger needs post-mortem reasoning; Auditor needs compliance review. Collapsing any two means one context pollutes the other. More than 5 would be subdividing the same cognitive task, which adds LLM calls without adding independence.

### Q4.2 — Why must the QC agent be isolated from the Coder's output?

**A:** Regulatory requirement. The whole point of double programming is independent verification. If the QC agent sees the Coder's code, it can subconsciously anchor on that approach and miss an entire class of errors. CDDE enforces this by spawning Coder and QC in separate `asyncio.gather` tasks with fresh conversation contexts. The comparator is the only place where both outputs meet.

### Q4.3 — What happens when Coder and QC both produce identical code?

**A:** The programmatic comparator runs an AST similarity check. If similarity is >80%, the verdict is `TOO_SIMILAR` — which means the two agents didn't actually think independently, just produced the same approach. The system re-runs QC with a different prompt variant (e.g., "use a different pandas idiom") to force true independence. If it's still too similar, the human reviewer is the final gate.

### Q4.4 — Why custom orchestration instead of CrewAI or LangChain?

**A:** We tried CrewAI first. It has known bugs on `async_execution` (PR #2466), `human_input` is CLI-only, and structured output is bolted-on rather than native. PydanticAI gives us typed agent I/O as a first-class feature, which is what we need for regulatory audit trails. The orchestration layer itself (when to parallelize, when to escalate, when to pause for HITL) is domain logic that belongs in our code, not in a generic framework.

### Q4.5 — Walk me through one derivation from spec to output.

**A:** YAML spec declares `AGEGR1` with logic "1=>=65, 0=<65" and source column `AGE`. Spec Interpreter reads it, flags any ambiguity. DAG builder places AGEGR1 at layer 0 (depends only on AGE from DM). Coder agent generates `df['AGEGR1'] = np.where(df['AGE']>=65, '>=65', '<65')`. QC agent independently generates the same thing using `pd.cut`. Comparator runs both on the real DataFrame, compares row-by-row; match → auto-approve. Auditor writes an AuditRecord with both codes, verdict, and source columns. Human approves or rejects via the HITL gate.

### Q4.6 — How does CDDE handle ambiguous specs?

**A:** The Spec Interpreter agent has a dedicated output field for "ambiguities detected" and is prompted to flag underspecified rules rather than guessing. In our CDISC pilot test, `DURDIS` (Duration of Disease) is flagged because it requires the MH (Medical History) domain which isn't in our demo source. The workflow proceeds, that one variable ends up in DEBUG_FAILED state, and the human reviewer sees it immediately in the DAG view.

### Q4.7 — What is the "dual-dataset" architecture?

**A:** Agents (which talk to the LLM) never see real patient data. The LLM prompt contains schema metadata — column names, dtypes, null counts, value ranges — plus a synthetic reference dataset (10-20 fake rows with the same structure). Actual data access happens only through local tools (`inspect_data`, `execute_code`) which run on the real DataFrame and return aggregates, never raw rows. This is a regulatory pattern: you get the agent's code-generation benefit without any PHI ever leaving the secure environment.

---

## Section 5 — HITL design

### Q5.1 — Why did you choose ONE deep HITL gate instead of multiple?

**A:** Every HITL gate is a reviewer context switch, and clinical SMEs are the scarcest resource in the process. A single rich dialog where the reviewer scans all variables at once, checks/unchecks them in bulk, and confirms — is much cheaper to operate than 4 separate interruptions. The enterprise pipeline YAML has 3 gates for 21 CFR Part 11 deployments where regulation mandates separated sign-off points — same engine, different YAML.

### Q5.2 — What can a reviewer do at the HITL gate?

**A:** Three actions: (1) **Approve with feedback** — per-variable checkboxes, tick/untick each, optional free-text reason. (2) **Reject with reason** — workflow fails cleanly, FSM transitions to `failed`, feedback row captures the reason. (3) **Override code** — edit any variable's generated code in-place, the new code is re-executed on the real DataFrame before being committed.

### Q5.3 — What happens to human feedback after approval?

**A:** It's written to the `feedback` table in the database and becomes retrievable by the `query_feedback` tool that the Coder agent calls on future runs. So if a reviewer rejects a `RISK_SCORE` derivation today with reason "handle empty inputs", next time the Coder generates `RISK_SCORE` for any study, it sees that feedback in its prompt context. This is the long-term memory loop — Phase 17.1 of the project, which closed a code-review-surfaced gap.

### Q5.4 — What if the human reviewer is wrong?

**A:** The audit trail captures every human override with reason and timestamp. A later reviewer (or the regulator) can see exactly what the agent generated, what the human changed it to, and why. The override doesn't overwrite the original — both are preserved. If the override turns out to be wrong, that's detectable via downstream QC or regulatory review, and the chain of evidence is intact.

---

## Section 6 — Memory design

### Q6.1 — What's stored in short-term memory vs long-term memory?

**A:** Short-term = single-run workflow state (DAG snapshot, in-progress DataFrames, FSM state, pending approvals). Persisted to `workflow_states` table per step so runs can resume from the last checkpoint after a crash or restart. Long-term = cross-run knowledge: validated patterns (`patterns` table), human feedback (`feedback` table), QC verdict history (`qc_history` table). LTM persists and grows across runs.

### Q6.2 — How does the Coder agent access long-term memory?

**A:** Three PydanticAI tools, each surfacing a distinct signal with its own authority level: `query_feedback(variable)` surfaces human reviewer decisions (strongest signal), `query_qc_history(variable)` surfaces past coder/QC verdict pairs, `query_patterns(variable_type)` surfaces prior validated implementations. The coder's system prompt instructs it to query all three and weigh by authority: human > debugger > prior agent.

### Q6.3 — Why three separate tools instead of one "get all lessons" tool?

**A:** Provenance preservation. When the LLM sees results from three distinct tools, it can reason about which source to trust. Collapsing into one blob would erase source identity and force flat evidence weighing. The numbered list in the system prompt teaches priority order through prompt structure — no meta-reasoning required from the model.

### Q6.4 — When does memory get written?

**A:** LTM writes happen at two points. (1) After the HITL gate approves, a `save_patterns` builtin step runs and persists every approved DAG node to `patterns`, plus QC verdict pairs to `qc_history`. (2) Every human action at the HITL dialog writes a `feedback` row immediately (approve, reject, override all produce rows). This ordering matters: patterns only persist AFTER human review, so LTM never learns from un-verified work.

### Q6.5 — What if memory conflicts — e.g., feedback says "approve" but qc_history says "mismatch"?

**A:** The system prompt instructs the LLM to prefer human > debugger > prior agent, so a human approval overrides a past QC mismatch. This is intentional: the human is the authority. In practice, such conflicts are rare because feedback writes come from the same workflow that produced the QC history. But if they occur across runs (different specs same variable name), the hierarchy resolves it.

---

## Section 7 — Traceability and audit

### Q7.1 — What's in an audit record?

**A:** Timestamp, agent name, action type (coder_proposed, qc_verdict, debugger_resolved, human_approved, etc.), input hash, output hash, the rule being applied, QC result, and any human intervention context. Append-only — records are never modified or deleted. Stored in memory during the workflow then serialized to JSON for persistence and HTML for human review.

### Q7.2 — Three layers of tracing — explain each.

**A:** (1) **Agent trajectory** — AgentLens (OpenTelemetry proxy) captures every LLM call, tool invocation, and response. This is the full conversational trajectory. (2) **Orchestration logging** — loguru captures workflow-level state transitions, DAG progress, HITL gate events. (3) **Functional audit trail** — custom `audit/trail.py` captures business-level events (lineage, provenance, approvals, QC results). Different concerns, different tools, different retention policies.

### Q7.3 — Can I reconstruct a derivation 6 months later?

**A:** Yes — every variable's DAG node carries `source_columns`, `coder_code`, `qc_code`, `approved_code`, and `qc_verdict`. Combined with the input hash in the audit record, you can rebuild exactly what code ran, on what data, and with what human approvals. The pattern matches the "e-record reconstruction" requirement in 21 CFR Part 11 §11.10(e).

### Q7.4 — What does the audit export look like?

**A:** Two formats: JSON for programmatic analysis (machine-readable, one AuditRecord per line, hashable for diffing), and HTML via AgentLens for presentation (human-readable, nested structure showing agent trajectories). Production systems would also emit OpenTelemetry spans for SIEM integration.

---

## Section 8 — DAG and dependencies

### Q8.1 — Why a DAG and not just a list of derivations?

**A:** Derivations have dependencies. EFFFL (Efficacy Flag) depends on ITTFL (Intent-to-Treat Flag) AND SAFFL (Safety Flag), both of which are themselves derived. If you compute EFFFL before ITTFL/SAFFL, you get wrong results or a crash. The DAG guarantees topological order: compute everything at layer 0 first (source columns only), then layer 1 (depends on layer 0), etc. This is also how we parallelize — all variables at the same layer can run concurrently.

### Q8.2 — What if there's a cycle?

**A:** Networkx detects it in `DerivationDAG.__init__` and raises `networkx.NetworkXUnfeasible` with the cycle path. CDDE fails loudly at DAG build time, before any agent is spawned. Cycles mean the spec itself is self-referential which is always a spec bug, never a runtime issue.

### Q8.3 — How do you know which variables depend on which?

**A:** The transformation YAML declares `source_columns` for each derivation. The DAG builder cross-references: if `source_columns` includes a name that's also a derived variable, that's a dependency edge. For CDISC ADSL, `EFFFL` declares `source_columns: [ITTFL, SAFFL]` so it's placed after both in the topological order.

### Q8.4 — What if the Coder uses a column it didn't declare?

**A:** The sandboxed `execute_code` tool would either find the column (if it's in the synthetic reference data) or raise NameError. We don't currently enforce "only use declared source_columns" at the prompt level — it's an honor system. Production hardening would add an AST walker that validates column references against the declared list before execution. Known gap.

---

## Section 9 — Failure modes

### Q9.1 — What's the worst-case failure?

**A:** Coder and QC agents both generating the same WRONG code — a correlated failure that double programming can't catch. Our defense is the AST similarity check plus the Comparator's verdict being `TOO_SIMILAR`, which forces a re-run with a different prompt variant. Ultimately the human reviewer is the last line of defense; the system is designed to surface uncertainty, not hide it.

### Q9.2 — What happens if the LLM hallucinates a column name?

**A:** `inspect_data` tool returns the actual schema; the agent's system prompt requires grounding in that schema before generating code. If the LLM still hallucinates, `execute_code` raises `NameError` at runtime. That exception propagates to the Comparator which marks the variable as `FAILED` and triggers the Debugger agent, which is a separate agent whose job is to diagnose the failure and propose a fix.

### Q9.3 — What if the backend crashes mid-workflow?

**A:** The `PipelineInterpreter` persists FSM state + ctx snapshot after every step to the `workflow_states` table. Restart the backend, hit `POST /workflows/{id}/rerun`, and the run resumes from the last checkpoint. This is Phase 15 work — we added it after realizing uvicorn's `--reload` was destroying in-progress runs during dev.

### Q9.4 — What happens if the ground truth comparison disagrees with the human-approved code?

**A:** Excellent question — the current prototype doesn't re-open the workflow if ground truth surfaces a late mismatch. The audit trail captures both outcomes (human approval + ground truth divergence), and the workflow completes with a note. Production extension would either re-route to another human review round or tag the workflow as "needs secondary QC" in a separate queue. This is a known scope limitation.

### Q9.5 — What about LLM rate limits?

**A:** PydanticAI handles retries on malformed responses, but rate-limit errors from the upstream provider bubble up as HTTP errors. The AgentLens proxy layer is where we'd add rate-limit handling in production (token bucket, exponential backoff, circuit breaker). Currently the proxy sits between agents and the LLM provider, so adding the rate-limit logic there wouldn't require engine changes.

---

## Section 10 — Technical stack and scaling

### Q10.1 — Why PydanticAI?

**A:** First-class typed agent I/O — every agent declares input and output types as Pydantic models, and PydanticAI handles the LLM call, validation, retry-on-malformed-response loop. This is exactly what a regulatory workflow needs: you want the agent to return `DerivationCode` (with `python_code`, `approach`, `variable_name` fields), not free-form text. Plus it's framework-light, so the orchestration layer is our code and we understand what's under the hood.

### Q10.2 — Why FastAPI instead of Flask/Django?

**A:** Async-native. Our workflows are IO-bound (LLM calls + DB writes) and the natural abstraction is `asyncio` — spawn agents with `asyncio.gather`, await tool calls, yield to the event loop while LLMs are thinking. FastAPI + `uvicorn` gives us async out of the box, plus OpenAPI schema generation for free, plus native MCP transport via FastMCP 3.0. Flask would require Gunicorn + async extensions and still lack the schema story.

### Q10.3 — How does CDDE scale horizontally?

**A:** Backend is stateless. All persistent state lives in PostgreSQL (workflow_states, patterns, feedback, qc_history). To add capacity you add replicas behind nginx, each replica serves independent workflows, the DB is the shared state. LLM rate limits are the real bottleneck — you'd need per-tenant rate limit pools managed at the AgentLens proxy layer.

### Q10.4 — What database do you use and why?

**A:** SQLite for local dev, PostgreSQL for team/enterprise deployments. Same SQLAlchemy async models work against both — swap DATABASE_URL env var and the stack works unchanged. SQLite gives us zero-friction local dev; PostgreSQL gives us real concurrency, row-level locks, and production-grade reliability when the story matters.

### Q10.5 — What about authentication?

**A:** Not implemented in the prototype. HITL approvals are anonymous. Production would integrate with Sanofi's existing SSO (Azure AD / LDAP) via middleware on the FastAPI app, and every `/approve`, `/reject`, `/override` endpoint would write the authenticated user ID into the `FeedbackRow`. This is the 21 CFR Part 11 §11.10(h) authority check requirement — it's a production extension, not a prototype concern.

---

## Section 11 — Platform / Lead-candidate questions (HOMEWORK.md §11)

### Q11.1 — How does this scale across studies?

**A:** Same engine, different YAML configs. Each study gets its own spec file in `specs/` and optionally its own pipeline YAML in `config/pipelines/`. LTM is scoped by `study_id` in the database so one study's patterns don't pollute another's. A production system would add tenant isolation at the DB schema level (one schema per study or per sponsor) and per-tenant LLM API keys managed at the proxy.

### Q11.2 — What are the main trade-offs you made?

**A:** (1) Depth over count on HITL gates — one rich review vs four shallow. (2) LLM generation + deterministic verification vs pure LLM or pure rules — we chose hybrid. (3) Custom orchestration vs a framework — custom gave us control; framework would have been faster to prototype but harder to audit. (4) Single-study scope vs multi-tenant — we designed for multi-tenant but only demo single-study. (5) Anonymous HITL vs authenticated — deliberate prototype simplification.

### Q11.3 — What would you do differently given another week?

**A:** (1) Run the full CDISC Pilot end-to-end against the official ground truth and ship the comparison report as the strongest validation artifact. (2) Integrate Pinnacle 21 as a post-export conformance check. (3) Add SSO / authenticated HITL to close the 21 CFR Part 11 §11.10(h) gap. (4) Build a Spec Interpreter UI so clinical SMEs can author YAML specs without touching the filesystem.

### Q11.4 — How do you handle multi-modality? (e.g., imaging, genomics data)

**A:** Not in prototype scope — ADSL is tabular. For imaging, the agent would need a different tool interface (thumbnail + feature extraction rather than `inspect_data` + `execute_code`), but the orchestration layer (DAG, HITL, audit) would be unchanged. Genomics data is typically processed upstream of SDTM/ADaM and enters as derived features in LB or custom domains. Same engine works; tools evolve.

### Q11.5 — How does this integrate with existing validated clinical systems?

**A:** CDDE outputs are CSV / Parquet ADaM datasets and JSON audit trails. Both are consumable by any downstream statistical analysis tool (SAS, R, Python). The HITL approval layer could emit events to existing QMS (Quality Management Systems) via webhooks. The audit trail JSON format is designed to be ingested into enterprise audit stores (Splunk, Elasticsearch). Nothing about CDDE requires replacing existing tools — it slots in as the "SDTM → ADaM derivation step" within a larger pipeline.

---

## Section 12 — Questions YOU should ask the panel (5 to pick from)

Having questions ready shows engagement and that you're evaluating the role, not just being evaluated. Pick 2-3 of these and adapt:

1. **"What's the current state of SDTM → ADaM tooling at Sanofi? Is there an existing internal system this would complement or replace, or would this be greenfield?"** — reveals whether you'd be building from scratch or integrating into a mature ecosystem.

2. **"How many clinical programmers does Sanofi employ on SDTM/ADaM work today, and what's the ratio of senior to junior? I'm curious where AI-assisted derivation would have the biggest leverage — helping senior programmers move faster, or raising the floor for junior work."** — shows you think about where AI augments vs. replaces.

3. **"What's your position on LLM-generated code in validated systems? Specifically: does the QA framework at Sanofi have a posture on AI-generated artifacts entering regulated pipelines, or is that something this role would help establish?"** — positions you as a platform thinker, not just an implementer.

4. **"How does Sanofi currently handle the handoff between Biostats and Data Management when specs are ambiguous? I'm asking because my Spec Interpreter agent flags ambiguities explicitly, and I'm curious whether that's solving a real pain point or just moving it."** — shows you want the product-market fit conversation.

5. **"If I joined, what would success look like in the first 90 days? Is there a specific pilot study or a specific team you'd want this approach tested on first?"** — standard but useful, signals execution orientation.

6. **"What's the relationship between the AI/ML team and the regulatory affairs team? The trickiest part of this prototype was translating 21 CFR Part 11 requirements into code — I want to know how that cross-functional work happens at Sanofi."** — shows you understand regulatory AI isn't just about models.

---

## Crib sheet — 10 things to remember under pressure

If you draw a blank, these are the 10 one-liners that rescue you:

1. **SDTM = raw collected, ADaM = analysis-ready derived.** Everything else flows from this distinction.
2. **Double programming is regulatory, not just QA.** ICH E6 expects independent verification.
3. **PHI never leaves the local environment.** LLM sees synthetic data + schema; real data stays in tools.
4. **One HITL gate, three actions.** Approve (per-variable), reject (with reason), override (edit code in place).
5. **Three LTM tools, authority-ranked.** Human > debugger > prior agent. Phase 17.1 fix.
6. **The DAG is execution + audit + debugging in one structure.** Every node carries source, code, verdict, approval.
7. **Append-only audit trail.** Records are never modified or deleted.
8. **Stateless backend, stateful database.** Horizontal scale = add replicas; all state in PostgreSQL.
9. **PydanticAI, not CrewAI or LangChain.** Typed I/O, framework-light, understood end-to-end.
10. **Not production — prototype with production patterns.** Auth, Pinnacle 21, BDS, PDF spec parsing are known future work.

---

## One-paragraph "why I did this" for opening remarks

If they open with "tell me about your homework": "I built a multi-agent system for SDTM → ADaM derivation because that step sits right at the intersection of what LLMs are good at — generating code from specs — and what regulated pharma needs — independent verification, traceability, human oversight. I'm not a pharma expert; I'm an engineer who studied the CDISC standards for a week to make sure I understood the problem well enough to make the right technical trade-offs. The prototype runs on the CDISC pilot study ADSL derivations, has a single deep human review gate with per-variable approval, and exports a complete audit trail. I'll walk you through the architecture, show a live demo, and then we can dig into trade-offs."

That's ~90 seconds and sets the frame: you're a systems thinker who understood the pharma requirements well enough to ship something honest.
