## Code Review

### Code organization

#### Structure

from ARCHITECTURE.md, outdated

```
homework/
├── CLAUDE.md
├── ARCHITECTURE.md            # This file
├── decisions.md
├── pyproject.toml
├── uv.lock
├── .github/workflows/ci.yml
├── docs/
│   ├── homework.md            # Original assignment
│   ├── REQUIREMENTS.md        # Problem framing & decisions
│   └── design.md              # Deliverable design document
├── data/
│   ├── sdtm/cdiscpilot01/     # SDTM input (XPT)
│   └── adam/cdiscpilot01/     # ADaM ground truth (XPT)
├── specs/                     # Transformation specs (YAML)
├── src/
│   ├── __init__.py
│   ├── factory.py                 # DI factory for orchestrator
│   ├── config/                    # Infrastructure configuration
│   │   ├── __init__.py
│   │   ├── constants.py           # Shared defaults (DATABASE_URL, LLM_BASE_URL)
│   │   ├── llm_gateway.py         # LLM model construction (AgentLens proxy)
│   │   └── logging.py             # loguru configuration
│   ├── domain/                    # Pure domain: models, DAG, FSM, spec parsing
│   │   ├── __init__.py
│   │   ├── models.py              # DerivationRule, DAGNode, DerivationRunResult, etc.
│   │   ├── exceptions.py          # CDDEError, WorkflowStateError, DerivationError, etc.
│   │   ├── dag.py                 # DAG construction, topological sort, apply_run_result
│   │   ├── spec_parser.py         # YAML spec → DerivationRule objects
│   │   ├── executor.py            # Safe code execution + result comparison
│   │   ├── source_loader.py       # CSV/XPT file loading
│   │   ├── synthetic.py           # Privacy-safe synthetic data generation
│   │   ├── workflow_fsm.py        # Workflow state machine (python-statemachine)
│   │   └── workflow_models.py     # WorkflowState, WorkflowResult
│   ├── agents/                    # PydanticAI agent definitions
│   │   ├── __init__.py
│   │   ├── deps.py                # Shared CoderDeps dependency container
│   │   ├── tools/                 # Agent tools (split by responsibility)
│   │   │   ├── __init__.py        # Re-exports: inspect_data, execute_code
│   │   │   ├── sandbox.py         # Safe builtins, blocked tokens, namespace builder
│   │   │   ├── inspect_data.py    # Data inspection tool (schema, nulls, ranges)
│   │   │   ├── execute_code.py    # Sandboxed code execution tool
│   │   │   └── tracing.py         # @traced_tool decorator for observability
│   │   ├── spec_interpreter.py
│   │   ├── derivation_coder.py
│   │   ├── qc_programmer.py
│   │   ├── debugger.py
│   │   └── auditor.py
│   ├── engine/                    # Orchestration layer
│   │   ├── __init__.py
│   │   ├── orchestrator.py        # Workflow controller, agent dispatch
│   │   └── derivation_runner.py   # Per-variable coder+QC+verify+debug loop
│   ├── verification/              # QC / double programming
│   │   ├── __init__.py
│   │   └── comparator.py
│   ├── audit/                     # Traceability
│   │   ├── __init__.py
│   │   └── trail.py
│   └── persistence/               # Database layer
│       ├── __init__.py            # Re-exports all repos
│       ├── database.py            # Engine + session factory
│       ├── orm_models.py          # SQLAlchemy table definitions
│       ├── base_repo.py           # BaseRepository with error wrapping
│       ├── pattern_repo.py        # PatternRepository
│       ├── feedback_repo.py       # FeedbackRepository
│       ├── qc_history_repo.py     # QCHistoryRepository
│       └── workflow_state_repo.py # WorkflowStateRepository

├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_dag.py
│   │   ├── test_spec_parser.py
│   │   ├── test_agents.py
│   │   ├── test_executor.py
│   │   ├── test_comparator.py
│   │   ├── test_orchestrator.py
│   │   ├── test_memory.py
│   │   └── test_audit.py
│   └── integration/
│       └── test_workflow.py
└── presentation/
```

### Env

missing dev only loadenv

.env contains the variables for 
- DATABASE_URL
- LLM_BASE_URL
- LLM_API_KEY
- LLM_MODEL

### Code details

#### Main entry points

(for my understanding, not a review)
- `api.app.py`: FastAPI and FastMCP entry point

- `src.factory`: Factory pattern for the orchestrator => create_orchestrator(spec, llm, output, db) using DerivationOrchestrator() with DI to inject repo based in db session thru SQLAlchemy to get sessoin_Factory

- `DerivationOrchestrator` creates orchestrator for spec, llm, pattern/QCHist/workflowstate repos, output dir. 
  - run() entry point: _step_spec_review, _step_build_dag, _step_derive_all, _step_audit => kind of harcoded steps, maybe it can be configured (yaml) and probably each Step could be his own class

  _step_spec_review(): parse spec, load source data, generate synth data
  _step_build_dag(): DerivationDAG()
  _step_derive_all(): for each layer of DAG, _derive_variable()
  _derive_variable(): run_variable(), _record_derivation_outcome()
    engine.derivation_runner::run_variable() => _run_coder_and_qc()
    _record_derivation_outcome()

  _step_audit(): create_llm(), run(Generate audit summary with AuditorDeps)

#### Agents

- AuditorDeps => auditor agent definition with prompt, output type: AuditSummary, retries. Input: dag_summary, workflow_id, SpecMetadata

### Questions

1. execute_code =>  with redirect_stdout(stdout_buf):
            exec(code, globals_ns, local_ns)  # noqa: S102 — sandboxed exec: restricted builtins via _SAFE_BUILTINS, blocked tokens checked

is it usign system python? uv env ? specific virtualenv ?

2. where tools usage are logged and error traced? Can't we define a Tool class with some tracing capabilities, logging, error management rather than only async func ? Should Tool be D-injected as implem may change?

3. why src\domain\source_loader.py, src\domain\spec_parser.py, src\domain\synthetic.py in domain? They look like data tools

4. src\persistence\repositories.py, I did not see a lot of error mgt: connection, queries errors, retries, pooling... ?

5. can we make async def run(self) -> WorkflowResult: less hardcoded and configurable (steps, inherited by FSM ?)

6. what can go wrong, I did not see a lot of exceptions and their management, rollback?

7. How to export the dag? not needed

8. can we generate the sequence diagram for the orchestration uisng mermaid? (https://github.com/jeremylongshore/claude-code-plugins-plus-skills/tree/main/planned-skills/generated/18-visual-content/mermaid-sequence-diagram-creator)

9. can the fsm and transitions be generated from a yaml? and also use this yaml to build the orchestration sequence?

10. can we split the web UI and the Orchestrator to simplify docker / k8s / multiple instances deployment (=> expose API on orchestrator?)

### Bugs

- streamlit UI doesn't look great, I added some skills for frontend design, canvas design and brand guidelines. H
- current ppt using npm cli is not nice, how you created the PPTX for the interview was great: C:\Projects\Interviews\slides

### To fix

init_db(): 
url = database_url or os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///cdde.db") # duplicate 

_step_spec_review():
assert self._state.spec is not None # => !!! exceptions!
assert self._state.derived_df is not None

_step_audit():
llm = create_llm(base_url=self._llm_base_url) # => limit to only one LLM

AuditorDeps: externalize prompt and retries config, tools

DerivationOrchestrator:
self._audit_trail.record(
            variable="",
            action=AuditAction.AUDIT_COMPLETE,
            agent=AgentName.AUDITOR, # => can use AuditorDeps from run rather than harcoded value
            details={"auto_approved": str(result.output.auto_approved)},
        )

dag is updated manually using calls like dag.update_node(variable, coder_code=coder.python_code, qc_code=qc_code.python_code), cannot it be done automatically using a Run class? if the dag.update_node is missing or incorrect, dag is incorrect, dangerous

tools.py in agents, should be a specific folder with a class or function at least per tool

split repos in src\persistence\repositories.py by class with a BaseRepo to avoid code duplication

add docstrings for each func/method

llm_gateway.py, logging.py are not an engine, that factories

WorkflowFSM, workflow_models are not engines but models

### Quality

missing variables types hints:

```
    async def get_stats(self, variable: str | None = None) -> QCStats:
        base = select(func.count()).select_from(QCHistoryRow)
        match_stmt = select(func.count()).select_from(QCHistoryRow).where(QCHistoryRow.verdict == QCVerdict.MATCH.value)
        if variable:
            base = base.where(QCHistoryRow.variable == variable)
            match_stmt = match_stmt.where(QCHistoryRow.variable == variable)
        total_result = await self._session.execute(base)
        total = total_result.scalar() or 0
        match_result = await self._session.execute(match_stmt)
        matches = match_result.scalar() or 0
        return QCStats(
            total=total,
            matches=matches,
            mismatches=total - matches,
            match_rate=matches / total if total > 0 else 0.0,
        )
```        

classes/methods have docstrings:

    def _compute_layers(self) -> None:
        """Compute topological layers and assign layer index to each node."""

but single funcs have none:

```
    async def _derive_variable(self, variable: str) -> None:
        assert self._state.dag is not None
        assert self._state.derived_df is not None
        await run_variable(
            variable=variable,
            dag=self._state.dag,
            derived_df=self._state.derived_df,
            synthetic_csv=self._state.synthetic_csv,
            llm_base_url=self._llm_base_url,
        )
        await self._record_derivation_outcome(variable)
```        

Add rule CPY001 to ruff, use MIT license