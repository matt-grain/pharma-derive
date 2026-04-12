## Code Review

### Code organization

#### Structure

from ARCHITECTURE.md, outdated

```
homework/
├── specs/                     # Transformation specs (YAML)
├── src/
│   ├── __init__.py
│   ├── domain/                # Pure domain: models, DAG, spec parsing, code execution
│   │   ├── __init__.py
│   │   ├── models.py          # DerivationRule, DAGNode, AuditRecord, etc.
│   │   ├── dag.py             # DAG construction, topological sort
│   │   ├── spec_parser.py     # YAML spec → DerivationRule objects
│   │   └── executor.py        # Safe code execution + result comparison
│   ├── agents/                # PydanticAI agent definitions
│   │   ├── __init__.py
│   │   ├── tools.py           # Shared tools: inspect_data, execute_code
│   │   ├── spec_interpreter.py
│   │   ├── derivation_coder.py
│   │   ├── qc_programmer.py
│   │   ├── debugger.py
│   │   └── auditor.py
│   ├── engine/                # Orchestration layer
│   │   ├── __init__.py
│   │   ├── orchestrator.py    # Workflow FSM, agent dispatch
│   │   ├── llm_gateway.py     # LLM abstraction (AgentLens mailbox)
│   │   └── logging.py         # loguru configuration
│   ├── verification/          # QC / double programming
│   │   ├── __init__.py
│   │   └── comparator.py      # Compare primary vs QC outputs, AST similarity
│   ├── audit/                 # Traceability
│   │   ├── __init__.py
│   │   └── trail.py           # Audit trail management + JSON export
│   ├── memory/                # Short-term + long-term memory
│   │   ├── __init__.py
│   │   ├── short_term.py      # Workflow state (JSON per run)
│   │   └── long_term.py       # Validated patterns (SQLite)
│   └── ui/                    # Streamlit HITL
│       ├── __init__.py
│       ├── app.py             # Main entry point
│       └── pages/             # Streamlit multi-page
│           ├── 1_spec_review.py
│           ├── 2_derivation_review.py
│           ├── 3_qc_results.py
│           └── 4_audit_trail.py
├── tests
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
- `ui.app.py`: start the Streamlit server (`PYTHONPATH="." uv run streamlit run src/ui/app.py`)

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