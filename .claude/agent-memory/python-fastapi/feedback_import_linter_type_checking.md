---
name: import-linter flags TYPE_CHECKING imports
description: import-linter v2.11 counts TYPE_CHECKING block imports as real imports — use ignore_imports to whitelist them per contract
type: feedback
---

`import-linter` (v2.11) does NOT exclude `TYPE_CHECKING` block imports when evaluating forbidden contracts. Even if the import is inside `if TYPE_CHECKING:`, it will trigger a broken contract.

**Why:** The linter analyses the static import graph, not the runtime behavior. TYPE_CHECKING imports are still present in the AST.

**How to apply:** When a forbidden contract would be broken only by a TYPE_CHECKING import (i.e., the import is annotation-only and the architectural boundary is maintained at runtime), add an `ignore_imports` clause to the specific contract in `.importlinter`:

```ini
[importlinter:contract:engine-no-persistence]
name = Engine cannot import Persistence directly (use DI)
type = forbidden
source_modules = src.engine
forbidden_modules = src.persistence
# TYPE_CHECKING-only import: annotation-only, never executed at runtime
ignore_imports =
    src.engine.orchestrator -> src.persistence.repositories
```

This whitelist approach is more explicit than removing the TYPE_CHECKING import, because it documents WHY the exception exists and keeps the architectural intent clear.
