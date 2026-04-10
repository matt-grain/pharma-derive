---
paths: "src/**/*.py"
---

# Logging Instrumentation — Observable by Default

## The Mistake
loguru was configured (`setup_logging` exists, `workflow_fsm.py` uses it) but only 2 of 27 source files actually log anything. The orchestrator runs derivations, compares QC results, triggers debuggers, and transitions FSM states — all silently. When something goes wrong, the only evidence is a `WorkflowResult.status == "failed"` with no trail.

## Rules

1. **Every business-significant event gets an INFO log.** FSM transitions, derivation starts/completions, QC comparisons, audit trail exports.

2. **Every error path gets an ERROR log with context.** Not just `logger.error(str(exc))` — include the variable name, the step, and the exception chain.

3. **Import loguru in every module that does non-trivial work.** `from loguru import logger` at the top. The orchestrator, executor, derivation_runner, comparator, and repositories all qualify.

4. **Use structured fields, not f-strings in log messages.** `logger.info("Derivation complete", variable=var, status=status)` instead of `logger.info(f"Derivation {var} complete with status {status}")`. This enables log aggregation.

5. **No `print()` in production code.** ruff rule `T201` catches this, but also watch for `sys.stdout.write()`.

## How to Apply
When implementing a new step or module, add logging at entry (INFO), exit (INFO with result), and error (ERROR with exception). Think: "If this fails at 2am, what would I need in the logs to diagnose it?"
