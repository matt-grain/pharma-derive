---
paths: "src/**/*.py"
---

# Enum Discipline — No Raw Strings for Fixed Sets

## The Mistake
Sonnet defined Pydantic model fields as `str` with inline comments listing valid values (e.g., `correct_implementation: str  # "coder", "qc", "neither"`). This creates hidden enums — the type system can't catch invalid values, comparisons use raw strings, and refactoring misses references.

## Rules

1. **If a field has a fixed set of valid values, it MUST be a `StrEnum`.** No exceptions. A comment listing values is a code smell that screams "this should be an enum."

2. **Compare enum members directly — never unwrap `.value`.** `vr.verdict == QCVerdict.MATCH` not `vr.verdict.value == "match"`. StrEnum supports direct equality.

3. **Repository method parameters that correspond to enums must accept the enum type**, not `str`. Convert to `.value` only at the ORM boundary (the `mapped_column` level).

4. **All domain enums live in `src/domain/models.py`** (or `src/domain/enums.py` if the file grows). Never define enums in `engine/` or `agents/` — those layers import from domain.

5. **FSM state checks use enum members.** Never `self._fsm.current_state_value == "completed"` — use `WorkflowStep.COMPLETED`.

6. **No string sentinels in dicts or defaults.** If you write `"pending"` as a fallback value, that's a missing enum member.

## How to Apply
Before writing any `str` field on a Pydantic model, ask: "Can this field hold arbitrary text, or is it one of N known values?" If the latter, define a StrEnum first, then use it as the field type.
