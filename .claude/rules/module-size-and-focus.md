---
paths: "src/**/*.py"
---

# Module Size & Focus — Small Files, Single Purpose

## The Mistake
`orchestrator.py` grew to 237 lines with a 168-line class. `tools.py` mixed `CoderDeps` (a type) with tool implementations (business logic). `spec_parser.py` mixed YAML parsing, CSV loading, and synthetic data generation. These accumulated because each addition was "just one more function" — but the files lost their single purpose.

## Rules

1. **Files > 200 lines: split before adding more.** Don't wait for the review to catch it. Check `wc -l` before committing.

2. **Functions > 30 lines: extract helpers.** If a function has 3+ code paths (if/elif/else for different data types), extract each path into a named helper.

3. **Classes > 150 lines: extract collaborators.** The class is doing too much. Move step methods into a separate helper class or module.

4. **One responsibility per module.** A file named `spec_parser.py` should only parse specs. If it also loads CSVs and generates synthetic data, those are separate modules (`source_loader.py`, `synthetic_generator.py`).

5. **Types and implementations live apart.** A shared `CoderDeps` dataclass used by multiple agents should be in `deps.py`, not bundled with tool implementations in `tools.py`.

6. **Constants get `Final[T]` annotations.** Module-level constants without `Final` look like mutable variables and confuse readers. Unused constants (like `_MAX_DEBUG_RETRIES` that was never wired into retry logic) are misleading — implement or remove.

## How to Apply
Before adding code to an existing file, check: (a) does this belong to the file's stated purpose? (b) will this push the file over 200 lines? If either answer is no, create a new focused module.
