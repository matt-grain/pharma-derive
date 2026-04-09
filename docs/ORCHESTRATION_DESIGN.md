# Orchestration Design — Architectural Rationale

## The Core Question: Where Does the Orchestrator Fit?

In a traditional layered architecture (Fowler, *Patterns of Enterprise Application Architecture*, 2002), the stack is:

```
Presentation → Application Service → Domain → Repository → Database
```

The **Application Service** coordinates domain operations without containing domain logic itself. In an agentic system, the orchestrator fills this role — but with a critical difference: it is **stateful**. It manages a workflow lifecycle (FSM), not a stateless request-response cycle.

This places the orchestrator closer to a **Process Manager** (Hohpe & Woolf, *Enterprise Integration Patterns*, 2003) or a **Saga Coordinator** (Garcia-Molina & Salem, 1987) than a traditional service.

## Why No Separate Service Layer

A common reflex is to insert a service layer between the orchestrator and repositories:

```
Orchestrator → PatternService → PatternRepository → DB
                    ↑
              (what goes here?)
```

The service layer earns its existence when it contains **business rules that don't belong in the domain or the coordinator**. In CDDE, the relevant business rules are:

| Rule | Where It Lives | Why |
|------|---------------|-----|
| "Store pattern after QC pass" | Orchestrator workflow | It's a workflow decision, not a pattern-management rule |
| "Query patterns before derivation" | Orchestrator workflow | It's context injection for agent prompts |
| "Record audit on every transition" | FSM callbacks | It's a cross-cutting concern handled declaratively |
| "Compare coder vs QC outputs" | Verification layer | It's domain logic (independent of persistence) |

None of these rules would live in a `PatternService`. A service layer here would be pure pass-through — calling `repo.store()` and returning the result. This violates YAGNI and adds cognitive load without value.

**Reference:** Martin Fowler, "Anemic Domain Model" (2003) — warns against service layers that contain no logic and merely delegate. The inverse applies here: don't create a service layer when the coordinator already IS the application service.

## The Orchestrator as Application Service + Process Manager

The orchestrator combines two Fowler patterns:

### 1. Application Service (PoEAA, Chapter 9)

> "An Application Service defines the jobs the software is supposed to do and directs the expressive domain objects to work out problems."

The orchestrator does exactly this:
- Parses specs (directs `spec_parser`)
- Builds DAGs (directs `DerivationDAG`)
- Dispatches agents (directs PydanticAI agents)
- Runs verification (directs `comparator`)
- Manages persistence (uses repositories)

It contains no domain logic itself — that lives in `domain/`.

### 2. Process Manager (Enterprise Integration Patterns, Chapter 7)

> "A Process Manager maintains the state of the sequence and determines the next processing step based on intermediate results."

The FSM (`WorkflowFSM`) is the literal implementation of this pattern:
- Maintains state: `created → spec_review → dag_built → deriving → ...`
- Determines next step: FSM transitions based on verification results
- Handles exceptions: `fail()` from any state → `failed`

The statefulness is the key differentiator from a pure Application Service. A traditional service is stateless (one request, one response). The orchestrator manages a multi-step workflow where each step depends on prior results.

## Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│ API / UI (future)                                    │
│ FastAPI endpoints or Streamlit pages                 │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│ Orchestrator (engine/)                               │
│ = Application Service + Process Manager              │
│                                                      │
│ - WorkflowFSM: state machine (python-statemachine)   │
│ - DerivationOrchestrator: workflow coordinator        │
│ - DerivationRunner: per-variable agent dispatch       │
│                                                      │
│ Depends on: domain/, agents/, repositories (injected) │
│ Contains: workflow coordination logic ONLY            │
│ Does NOT contain: domain rules, SQL, agent internals  │
└──────────────────────┬──────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼──────┐ ┌─────▼──────┐ ┌────▼──────────┐
│ Domain       │ │ Agents     │ │ Verification   │
│ (domain/)    │ │ (agents/)  │ │ (verification/)│
│              │ │            │ │                │
│ - models     │ │ - PydanticAI│ │ - comparator  │
│ - DAG        │ │   agents   │ │ - AST analysis│
│ - executor   │ │ - tools    │ │               │
│ - spec parser│ │            │ │ Depends on:   │
│              │ │ Depends on:│ │ domain/ only  │
│ Depends on:  │ │ domain/    │ │               │
│ nothing      │ │ only       │ │               │
└──────────────┘ └────────────┘ └───────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│ Persistence (persistence/)                           │
│                                                      │
│ - repositories.py: query interfaces (return domain   │
│   models, never ORM rows)                            │
│ - orm_models.py: SQLAlchemy table definitions        │
│ - database.py: engine + session factory              │
│                                                      │
│ Depends on: domain/ (for return types), SQLAlchemy   │
│ Exposes: repository classes accepting AsyncSession    │
└──────────────────────┬──────────────────────────────┘
                       │
              ┌────────▼────────┐
              │ Database        │
              │ SQLite (local)  │
              │ PostgreSQL (prod)│
              └─────────────────┘
```

### Dependency Rules

| Layer | Can Import From | Cannot Import From |
|-------|----------------|-------------------|
| **domain/** | stdlib, pydantic, networkx, pandas | agents, engine, verification, persistence |
| **agents/** | domain/ | engine, verification, persistence |
| **verification/** | domain/ | agents, engine, persistence |
| **engine/** | domain/, agents/, verification/ | persistence (only via injected repos) |
| **persistence/** | domain/ (return types), SQLAlchemy | agents, engine, verification |

The critical rule: **engine/ never imports from persistence/**. Repositories are injected via constructor parameters. This means:

```python
# In engine/orchestrator.py — CORRECT
class DerivationOrchestrator:
    def __init__(self, pattern_repo: PatternRepository | None = None):
        self._pattern_repo = pattern_repo  # injected, not imported

# In main.py or API layer — wiring happens here
session = await get_session(session_factory)
repo = PatternRepository(session)
orchestrator = DerivationOrchestrator(pattern_repo=repo)
```

This inversion means:
- Unit tests run without a database (pass `None`)
- Integration tests use SQLite in-memory (same code path)
- Production uses PostgreSQL (same code path, different connection string)

## Why Not a Saga?

Sagas (Garcia-Molina & Salem, 1987) handle distributed transactions with compensating actions. Our workflow is **not distributed** — all operations happen within a single process and database. The FSM is simpler and more appropriate:

- Sagas need compensation (undo step N if step N+1 fails). We don't — a failed derivation doesn't need to "undo" the spec parsing.
- Sagas coordinate across services/databases. We coordinate within a single process.
- The FSM provides the state management benefits of a saga without the distributed complexity.

If CDDE evolves to distributed microservices (e.g., separate derivation workers), the FSM-based orchestrator could be refactored into a saga coordinator. The current architecture doesn't preclude this.

## Why python-statemachine (Not Hand-Rolled)

See `decisions.md` for the full ADR. Summary:

The clinical workflow has 10 states and 19 transitions. A hand-rolled `dict[State, set[State]]` with a `transition()` function works (~15 lines) but requires manual logging and audit recording after every transition call. `python-statemachine` v3.0 provides:

1. **Declarative transitions** — the FSM definition IS the documentation
2. **`after_transition` callback** — automatic audit trail on every state change (21 CFR Part 11 traceability)
3. **`TransitionNotAllowed` exception** — type-safe invalid transition handling
4. **`.graph()` export** — generates state diagram for the panel presentation

Cost: one small dependency (pure Python, no transitive deps). Value: every transition is automatically logged and audited without the orchestrator needing to remember.

## Comparison with Agent Framework Orchestration

We evaluated built-in orchestration from agent frameworks:

| Framework | Orchestration | Why We Didn't Use It |
|-----------|--------------|---------------------|
| **CrewAI** | `Process.sequential` / `Process.hierarchical` | `async_execution` has known bugs (PR #2466). `hierarchical` is unpredictable. No FSM — just a loop. |
| **LangGraph** | Graph-based state machine | Heavy LangChain dependency. Graph-first paradigm fights our domain-specific workflow rules. |
| **AutoGen** | Chat-based multi-agent | Conversation-oriented, not workflow-oriented. No structured output validation. |
| **PydanticAI** | None (by design) | PydanticAI provides agent abstractions, not orchestration. Composition is the intended model. |

PydanticAI's design philosophy (confirmed by the docs) is: agents are building blocks, composition is your responsibility. This aligns with our need for domain-specific workflow rules (DAG-ordered execution, double-programming verification, HITL gates) that no generic framework handles correctly.

**Our approach:** PydanticAI for agent abstractions (typed I/O, tool binding, validation) + custom orchestration for clinical workflow rules (FSM, DAG execution, verification, audit). Neither layer is "custom framework" — it's standard Python async patterns composed with domain-specific rules.

## References

1. Fowler, M. (2002). *Patterns of Enterprise Application Architecture*. Addison-Wesley.
   - Chapter 9: Service Layer
   - Chapter 11: Unit of Work, Repository
   - "Anemic Domain Model" (martinfowler.com, 2003)

2. Hohpe, G. & Woolf, B. (2003). *Enterprise Integration Patterns*. Addison-Wesley.
   - Chapter 7: Process Manager pattern

3. Garcia-Molina, H. & Salem, K. (1987). "Sagas." *ACM SIGMOD Record*, 16(3), 249-259.

4. Vernon, V. (2013). *Implementing Domain-Driven Design*. Addison-Wesley.
   - Chapter 8: Application Services
   - Chapter 13: Integrating Bounded Contexts (process managers)

5. Martin, R.C. (2017). *Clean Architecture*. Prentice Hall.
   - Chapter 22: The Clean Architecture — use cases as application-specific business rules

6. PydanticAI Documentation — "Agents are not workflows. Compose them." (ai.pydantic.dev)
