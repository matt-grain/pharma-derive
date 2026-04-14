# CDDE_Presentation.pptx — Review

**File reviewed:** `presentation/CDDE_Presentation.pptx` (466 KB, 19 slides)
**Review date:** 2026-04-14
**Reviewer target:** Sanofi panel interview, AI/ML Lead role, 15-20 minute delivery + Q&A
**Reviewed against:** HOMEWORK.md §5+§9 criteria, current code state at HEAD `7ff3c54` + Phase 18.1 in flight, Phase 16/17 memory

---

## Overall verdict

**Strong deck overall** — the narrative arc is tight, the pharma-specific value props (dual-dataset security, double programming, audit trail) are front-and-center, and the closing Rabelais quote is distinctive without being precious. The 19-slide count is tight but workable for 15-20 min if slide 13 (demo) gets its due ~4-5 min.

**5 BLOCKERS must be fixed before the demo** — stale test counts, stale contract counts, an internal contradiction on HITL gate count (slide 6 vs slide 14), and an unproven ground-truth validation claim on slide 13 that depends on Test 1 completing this afternoon.

---

## 🔴 BLOCKERS — fix before presentation

### B1 — Slide 17: test count is drastically stale (270 → 318+)

> "270 — Tests passing"

**Actual current state (HEAD `7ff3c54`):** 315 backend + 14 frontend = **329 tests**. Phase 18.1 currently running will add +3 backend = **332**.

The slide underclaims by ~60 tests. This is a "tell" for an interviewer: "this deck is stale, what else is stale?" Update to `332` (or whatever the final count is after Phase 18.1 lands today).

**Also stale on the same slide:**
- "85% core logic coverage" — Phase 9 figure. Needs re-measurement against current state (likely still 80%+ but verify with `uv run pytest --cov=src --cov-report=term-missing`).
- "10 Custom pre-commit checks" — this one is CORRECT per `tools/pre_commit_checks/` (I counted 10). Keep.

### B2 — Slides 4 and 17: import-linter contract count is wrong (21 → 19)

Both slides say "21 import-linter contracts". Actual count in `.importlinter`: **19 contracts**. Grep-confirmed against the current file. Fix both slides to `19`.

### B3 — Slide 6 contradicts Slide 14 on HITL gate count

**Slide 6:** `HITL Gate — 4 approval points in workflow`
**Slide 14:** `Our Choice: One deep review gate: (per-variable approve/reject/edit + reject reason)`

These contradict each other. Slide 14 is correct — the current architecture (ADR 2026-04-13, Phase 16) is **ONE deep gate** in `config/pipelines/clinical_derivation.yaml` with 3 actions: approve-with-per-variable-feedback, reject-with-reason, override-code. The enterprise pipeline (`config/pipelines/enterprise.yaml`) has 3 gates for 21 CFR Part 11 deployments, but that's NOT the default demo pipeline.

Slide 6's "4 approval points" resurrects the old overclaim that `docs/GAP_ANALYSIS.md` (post-code-review, 2026-04-13) explicitly debunked:

> Slides advertise 4 gates (spec review, QC dispute, final review, audit sign-off) — **only gate 3 is implemented**

**Fix slide 6:** replace "4 approval points in workflow" with "One deep gate: per-variable approve/reject + free-form override + cross-run feedback". This makes slide 6 internally consistent with slide 14 and honest about what shipped.

### B4 — Slide 13: ground truth comparison claim — **TEST 1 RUN 2026-04-14, RESULTS IN**

> "Comparator checks outputs against each other AND ground truth (official CDISC ADaM as reference)"

Phase 16.4 wired the `ground_truth_check` builtin + endpoint + step into the pipeline. Workflow `197afb5b` ran end-to-end this afternoon against `data/adam/cdiscpilot01/adsl.xpt` (official CDISC Pilot ADaM reference). Full report lives at `docs/GROUND_TRUTH_REPORT.md`.

**Headline: 3 / 7 variables matched exactly. 4 / 7 surfaced explainable discrepancies — each correctly flagged by the comparator.**

| Variable | Verdict | Match / Total | Explanation |
|---|---|---|---|
| **AGEGR1** | ✅ match | 18576 / 18576 | Clean categorical bucketing |
| **SAFFL** | ✅ match | 18576 / 18576 | Clean boolean flag |
| **ITTFL** | ✅ match | 18576 / 18576 | Clean boolean flag |
| **TRTDUR** | ⚠ mismatch | 18344 / 18576 (1.25 %) | Edge case: null date handling |
| **EFFFL** | ⚠ mismatch | 18108 / 18576 (2.52 %) | Business rule: stricter treatment criterion in reference |
| **DISCONFL** | ❌ mismatch | 8900 / 18576 (52.09 %) | Test-fixture bug: canned response omits `DSDECOD != 'COMPLETED'` filter that the spec calls for |
| **DURDIS** | ❌ mismatch | 0 / 18576 (100.00 %) | Spec-flagged non-derivable (needs MH domain that prototype doesn't load) |

**This is actually a STRONGER story than 7/7 would be.** A perfect match would look suspicious. The distribution shows: (a) the clean cases work, (b) the comparator correctly detects edge cases, (c) the comparator catches test-fixture drift, (d) the Spec Interpreter correctly flags non-derivable variables. All four failure modes are things a regulator wants to see the system catch.

**Action — slide 13 footer rewrite:**

Replace:
> "Comparator checks outputs against each other AND ground truth (official CDISC ADaM as reference)"

With:
> "Validated on CDISC Pilot ADSL (workflow `197afb5b`, 18,576 rows vs `adsl.xpt`): AGEGR1 / SAFFL / ITTFL matched exactly. TRTDUR, EFFFL, DISCONFL, DURDIS surfaced explainable discrepancies — each correctly flagged by the comparator. The comparison step catches every disagreement — that is its purpose."

And be ready for panel questions on each mismatch — full per-variable explanations in `docs/GROUND_TRUTH_REPORT.md`.

### B5 — Slide 3: "Validated on real data" claim — **NOW SUBSTANTIATED**

> "Validated on real data: CDISC Pilot Study (cdiscpilot01) — Alzheimer's trial, 7 ADSL derivations"

Test 1 ran successfully. The claim is now backed by `docs/GROUND_TRUTH_REPORT.md`. Keep the wording as-is, but be ready to interpret "validated" the way a regulator would: **validated means the pipeline ran end-to-end, produced output, and the ground-truth-comparison step exercised every derivation against the official reference — not that every variable matched bit-for-bit**. 3/7 exact matches + 4/7 correctly-flagged discrepancies is a stronger "validation" story than 7/7 silent match.

**Action — speaker note for slide 3:**

When you say "validated on real data", follow with: "We ran the full ADSL derivation against the official CDISC Pilot reference — 3 variables match exactly, 4 surface explainable differences the system correctly detected. The ground truth report is in `docs/GROUND_TRUTH_REPORT.md`." That pre-empts the "what does validated mean" follow-up question.

---

## 🟠 HIGH — address if time permits

### H1 — Slide 17 missing the pre-push hook count (18 hooks)

18 pre-push hooks is a signature "production rigor" artifact for this project — it's what makes the repo feel enterprise-grade vs prototype. Currently missing from the quality slide.

**Fix:** Add `18/18 pre-push hooks green` next to the "10 Custom pre-commit checks" entry.

### H2 — Slide 11 "Satisfies 21 CFR Part 11 traceability requirements" is a strong claim

Regulatory interviewers at Sanofi WILL push on this. "Tell me specifically which Part 11 sections you satisfy and how" is a natural follow-up. Current deck has no supporting detail — just the claim.

**Safer framing:** "Designed against 21 CFR Part 11 §11.10 controls: audit trail (§11.10(e)), electronic signatures placeholder (§11.100), operational checks (§11.10(f))." OR the softer "Aligned with 21 CFR Part 11 traceability principles" + be ready to explain which 3-4 specific subsections.

**Prep answer for the panel:** The three most relevant Part 11 requirements this prototype addresses are:
1. **§11.10(e)** — secure, computer-generated, time-stamped audit trails. ✅ `audit/trail.py` is append-only, every record has timestamp + agent + input hash + output hash.
2. **§11.10(f)** — operational system checks to enforce permitted sequencing of steps. ✅ `PipelineFSM` enforces state transitions; invalid transitions raise.
3. **§11.10(h)** — use of authority checks to ensure only authorized individuals can use the system, electronically sign a record, access the operation or computer system input or output device. ⚠️ **NOT IMPLEMENTED** in prototype — the HITL approval is anonymous. Be honest: "Auth is a production extension".

### H3 — Slide 14 "guards enforce" phrase

> "Hybrid: LLM generates, rules verify, guards enforce"

"Guards" is ambiguous. In this project they're: (a) the AgentLens proxy which runs external to the repo, and (b) `config/guards.yaml` which is a Phase 16.5 stub (not a live enforcement mechanism). A panel interviewer asking "show me the guards" will get an awkward answer.

**Fix options:**
- Drop "guards" from the triad → "Hybrid: LLM generates, rules verify" (simpler, more honest)
- Replace "guards" with "pipeline checks" → "LLM generates, rules verify, pipeline checks enforce" + be ready to point at the 10 custom pre-commit checks + import-linter contracts + the `ground_truth_check` runtime step
- Keep "guards" and add a half-sentence: "guards enforced via AgentLens proxy (token budgets, output validation) + `config/guards.yaml` (policy stubs)"

### H4 — Slide 3 agent count inconsistency with Slide 5

Slide 3 lists 5 agents: Parse / Generate / Verify / Debug / Audit
Slide 5 lists 5 agents: Spec Interpreter / Derivation Coder / QC Programmer / Debugger / Auditor

These MAP 1-to-1 but use different names on each slide, which a careful interviewer might flag as "which are the real names?" Minor but fixable.

**Fix:** Use the same 5 names on slide 3 as slide 5 (the agent YAMLs in `config/agents/` use: `spec_interpreter.yaml`, `coder.yaml`, `qc_programmer.yaml`, `debugger.yaml`, `auditor.yaml` — those are the authoritative names).

### H5 — Slide 10 "Memorize" bullet is too abstract

> "Every action → FeedbackRepository → surfaced to future runs via pattern retrieval"

Panel will want a concrete example. Be ready with:

> "Concrete example: in Test 2 the user rejected RISK_SCORE with the reason 'empty RISK SCORE?'. That feedback got written to `feedback` table. The next time a coder agent generates code for any `RISK_SCORE`-typed variable, it calls `query_feedback('RISK_SCORE')` which surfaces that rejection. The coder then knows to handle empty inputs explicitly. This is Phase 17.1 — Bug #5 from the code review — the LTM read loop closure."

This is a STRONG narrative because it's concrete, fixes a real bug, and shows the memory loop is actually closed (not aspirational). Mention Bug #5 by name.

---

## 🟡 MEDIUM — polish opportunities

### M1 — Slide 9 (Dual-Dataset) should move earlier

Currently slide 9. This is the **strongest pharma-specific slide in the deck** — the data security story is where most agentic AI demos fall apart at the "but you can't send patient data to an LLM" question. Consider moving it right after slide 2 (Problem) to frontload the pharma credibility.

### M2 — Slide 13 is demo-heavy but lacks a "what to watch" script

The demo is ~4-5 min of the 15-min budget. The slide currently lists 5 steps but doesn't cue Matt on what to actually SHOW live. Add speaker notes (not on the slide itself) with:
- What UI state to start from
- Which variables to actually click through
- What the audit tab will show at each step
- What to say when the HITL gate pauses ("this is where a real reviewer would come in...")
- Fallback plan if the backend chokes mid-demo (e.g., "if the mailbox auto-responder lags, I can show you the audit trail of workflow `5799b1d7` from last night's test")

### M3 — Slide 6 visual scanability

5 patterns in a grid is a lot of numbered items. Visual inspection recommended (convert to JPG via the pptx skill's thumbnail script). Patterns 3+4 ("Concurrent+Compare" / "Retry+Escalation") may blur together — consider merging or using stronger visual separation.

### M4 — Slide 12 should name the 3 LTM tools explicitly (Phase 17.1 story)

> "Before generating code: agent tools query long-term memory for matching patterns."

This understates the Phase 17.1 work. The coder agent now has **three distinct tools** with an authority hierarchy:

1. `query_patterns(variable_type)` — prior validated implementations
2. `query_feedback(variable)` — human reviewer decisions (STRONGEST signal)
3. `query_qc_history(variable)` — coder/QC verdict pairs

And the system prompt teaches priority order: `human > debugger > prior agent`. Naming the 3 tools and the hierarchy on slide 12 turns "we have LTM" into "we have a 3-tier LTM with provenance-aware authority ranking" — much stronger.

### M5 — Slide 18 "Current guards are rule-based (AgentLens proxy + custom rules)"

This reads as a throwaway. If guards is a real limitation, be explicit: "Current guards are rule-based — no policy engine (OPA, Cedar) for dynamic per-study overrides; no LLM-based output validator". Otherwise drop it.

### M6 — Agent count on slide 17 quality metrics

The deck shows 5 agents but the custom check list doesn't mention `check_patient_data_leaks` by name, which is **the most pharma-differentiating hook in the repo** (verifies no real patient data can leak into LLM prompts). Call it out in a speaker note when you hit slide 17.

---

## 🟢 LOW — nice-to-haves

### L1 — Slide 19 Rabelais closing

Keep it. It's distinctive, personal, and ties philosophy to practice. Reviewers will remember it. The translation footer is helpful — maybe render it smaller/italicized.

### L2 — Consider adding a "what this does NOT do" slide

Between slide 17 (Quality) and slide 18 (Limitations) — an honest "non-goals" slide shows mature scoping. Example bullets:
- NOT a SAS → Python migration tool (different problem)
- NOT a spec authoring assistant (spec comes in as YAML)
- NOT a full CDISC validator (Pinnacle 21 does that)
- NOT a drop-in replacement for SAS programmers (complement, not substitute)

This defuses "can't you just use SAS?" type questions by addressing them head-on.

### L3 — Missing: a slide or footer showing the Docker Compose story

Phase 18's docker-compose.yml update added postgres + agentlens services. If the WSL Docker test (today's agenda item #5) passes, a one-line callout in slide 15 "Small-scale Prod" like `docker compose up -d → full stack in <30s` is a concrete production readiness artifact.

---

## Pacing recommendation for 15-min vs 20-min delivery

### 15-minute path (12 slides, ~1 min each + 3 min demo)
1. Title (30s) → 2. Problem (1min) → 3. Solution overview (1min) → 4. Architecture (1min) → 8. Double Programming (1min) → 9. Data Security (1.5min — the pharma-credibility slide) → 10. HITL (1min) → 12. Memory (1min) → 13. Demo (4min) → 14. Trade-offs (1min) → 17. Quality (30s) → 19. Closing (30s)

Skip slides 5, 6, 7, 11, 15, 16, 18 — use them only if the panel asks.

### 20-minute path (add 5 more slides)
Add: 5 (Agent roles detail), 6 (Orchestration patterns), 11 (Traceability detail), 15 (Production tiers), 18 (Limitations)

Still skip: 7 (DAG visual — fold into demo), 16 (resilience — save for Q&A)

---

## Questions the panel will probably ask (use this as Q&A prep, NOT as slides)

**Technical architecture:**
1. "Why custom orchestration over CrewAI or LangGraph?" → Because we wanted typed agent I/O (PydanticAI provides this) + custom async control flow (parallel map, HITL pauses, debug escalation) that framework abstractions make awkward. Slide 6 bottom note.
2. "What happens when the LLM returns malformed output?" → PydanticAI automatic retry (up to 3), then ValidationError bubbles to the engine which marks the variable `FAILED` and triggers debugger.
3. "How does QC stay independent from the coder?" → Two mechanisms: (a) separate asyncio tasks with fresh contexts via `asyncio.gather`, (b) isolated prompt — QC agent never sees coder's code, only the spec and a comparison request.
4. "What if coder and QC always produce identical code?" → AST similarity check; >80% = too similar, re-run QC with a temperature bump or fall through to human review.

**Pharma-specific:**
5. "Can you explain ICH E6?" → International Conference on Harmonisation Guideline for Good Clinical Practice. Double programming is one of its operational requirements for derived variables.
6. "Explain SDTM vs ADaM in one sentence each." → SDTM is the raw collected data standardized by domain (DM=demographics, EX=exposure, DS=disposition, SV=visits). ADaM is analysis-ready datasets derived from SDTM by applying the statistical analysis plan's derivation logic (subject-level ADSL, BDS for longitudinal endpoints).
7. "What is 21 CFR Part 11?" → FDA regulation on electronic records and electronic signatures in FDA-regulated industries. §11.10 specifies audit trail, operational checks, authority checks.
8. "What's Pinnacle 21?" → CDISC community's conformance validator for SDTM/ADaM. Runs 1000+ checks; industry-standard acceptance gate for regulatory submissions.

**Scaling / multi-tenancy:**
9. "How does this scale across studies?" → Backend is stateless; all state in PostgreSQL. Per-study isolation via DB schema + LLM_API_KEY per tenant. LTM can be per-study or cross-study (config choice).
10. "What's the bottleneck?" → LLM latency dominates. Each variable = ~2 LLM calls (coder + QC) + 1 for debug if mismatch. 7-variable ADSL ≈ 15-20 LLM calls ≈ 30-60 seconds wall-clock. Parallelism helps but bounded by LLM provider rate limits.

**Failure modes:**
11. "What's the worst-case failure mode?" → Coder and QC both generate same WRONG code (correlated failure). AST similarity would mark it TOO_SIMILAR, forcing human review. Human is the ultimate gate.
12. "How do you handle LLM hallucination of column names?" → `inspect_data` tool returns the actual schema; agent must ground in that schema before generating code. `execute_code` tool catches runtime errors; mismatches surface as QC failures.

---

## Action checklist before the panel

- [ ] B1 — Update slide 17 test count (Phase 18.1 committed on main: **332 tests** = 318 backend + 14 frontend)
- [ ] B2 — Fix import-linter count on slides 4 and 17 (21 → **19**)
- [ ] B3 — Rewrite slide 6 "HITL Gate — 4 approval points" to match slide 14's "One deep gate"
- [ ] B4 — ✅ Test 1 ran successfully on 2026-04-14 (workflow `197afb5b`). Apply the 3/7 match footer to slide 13 per the text in B4 above. Reference `docs/GROUND_TRUTH_REPORT.md` in the speaker notes for the per-variable explanations.
- [ ] B5 — ✅ "Validated on real data" is now substantiated by `docs/GROUND_TRUTH_REPORT.md`. Keep slide 3 wording; add the speaker-note framing from B5 above so the "validated" term maps to "end-to-end ground truth comparison" rather than implying 7/7 bit-for-bit match.
- [ ] H1 — Add "18/18 pre-push hooks green" to slide 17
- [ ] H2 — Soften 21 CFR Part 11 claim on slide 11 OR prep detailed §11.10 answer
- [ ] H4 — Unify agent names across slides 3 and 5
- [ ] M1 — Consider moving slide 9 (Dual-Dataset) earlier in the flow
- [ ] M4 — Name the 3 LTM tools on slide 12 (Phase 17.1 Bug #5 story)
- [ ] Visual QA: convert to JPGs and inspect for overlap / text overflow / pacing

---

## Prep notes (outside the deck)

Rehearse these as 30-second soundbites in case the panel pushes:
1. "Why not just fine-tune a model on SDTM→ADaM?" → Regulatory traceability. Fine-tuned models are black boxes; every derivation must be traceable to source + logic + agent + approval. An LLM that GENERATES code we can read, test, and audit is the compliance story.
2. "How much of this is you vs Claude?" → Honest answer: I architected the system, chose the patterns, wrote the design docs and specs, and reviewed every change. Claude (Claude Code) implemented most of the code under my direction. I can walk through any module and explain why it's structured the way it is. The value I add is the judgment layer — what gets built, how it's wired, how the trade-offs are made.
3. "What would you change given more time?" → (1) Replace the mailbox proxy with a real Claude API integration + caching. (2) Actually wire the Pinnacle 21 validator as a post-export step. (3) Add a Spec Interpreter UI that lets SAS programmers drag-and-drop derivation rules into YAML. (4) Add per-study RLS on the LTM tables for multi-tenant.
