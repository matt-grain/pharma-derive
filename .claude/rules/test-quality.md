---
paths: "tests/**/*.py"
---

# Test Quality — Coverage, Precision, Readability

## The Mistake
The core execution engine (`derivation_runner.py`) had zero tests despite being the most complex module. FSM transitions were partially tested (happy path only, not all fail transitions). `pytest.raises(Exception)` was used twice — so broad it would pass on any error, making the test meaningless. AAA markers were inconsistent.

## Rules

1. **Every new source module gets a test file in the same commit.** If you create `src/engine/foo.py`, `tests/unit/test_foo.py` must exist before the PR. No "I'll add tests later."

2. **Every public function: 1 happy path + 1 error path minimum.** For FSMs: test every valid transition AND every invalid transition that should raise.

3. **Never `pytest.raises(Exception)`.** Always catch the specific exception: `pytest.raises(ValidationError)`, `pytest.raises(TransitionNotAllowed)`. If you don't know what the code raises, read it first.

4. **AAA markers in every test body.** Use `# Arrange`, `# Act`, `# Assert` comments. For trivial one-liner tests, `# Act & Assert` is acceptable.

5. **`asyncio_mode = "auto"` means no `@pytest.mark.asyncio`.** The project configures auto mode in `pyproject.toml`. Adding the decorator is redundant noise.

6. **Mock at boundaries, not internals.** Mock LLM calls (via `TestModel`/`FunctionModel`), mock DB sessions (via `sqlite:///:memory:`). Never mock domain logic — that's the code under test.

7. **No magic constants in assertions.** If a test asserts `== 4`, it should be clear WHY 4. Use named constants or derive from test data: `assert len(result) == len(input_rules)`.

## How to Apply
Before marking a module as "done," check: does every public function have at least 2 tests? Are all FSM transitions (including failure paths) covered? Are assertions specific?
