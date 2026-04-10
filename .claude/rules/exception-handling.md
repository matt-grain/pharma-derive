---
paths: "src/**/*.py"
---

# Exception Handling — Catch Specific, Never Swallow

## The Mistake
Three `except Exception as exc:` blocks silently converted errors into result objects (`ExecutionResult(success=False)`, `self._state.errors.append(...)`) without re-raising or logging. This hides the traceback permanently — when something unexpected breaks, you get a generic "failed" status with no clue why.

## Rules

1. **Never `except Exception:` without either re-raising or logging the traceback.** At minimum: `logger.exception("context")` before absorbing.

2. **Catch the narrowest set of exceptions you actually expect.** For `eval()`/`exec()` sandboxes: `(SyntaxError, NameError, TypeError, ValueError, ArithmeticError, AttributeError)`. Not `Exception` which catches `MemoryError`, `RecursionError`, `SystemExit`.

3. **Use `raise NewError(...) from exc`** when converting exceptions to domain errors. This preserves the chain for debugging.

4. **Result-type conversion is OK, but log first.** If you convert an exception to `ExecutionResult(success=False, error=str(exc))`, still log at ERROR level so the traceback exists somewhere.

5. **No bare `except:` ever.** This project uses ruff rule `B001` to enforce this, but also watch for `except Exception:` which is technically not bare but equally dangerous when it swallows.

## How to Apply
When writing a try/except block, list the specific exceptions you're guarding against. If you can't name them, you don't understand the failure mode — investigate before catching.
