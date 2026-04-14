# Phase 16.3.0 — Frontend Test Infrastructure Setup

**Agent:** `vite-react`
**Depends on:** None (runs before Phase 16.3 component work)
**Scope:** Very narrow — only installs test deps and configures Vitest. No product code changes.

## Goal

The existing `frontend/package.json` has NO `vitest`, NO `@testing-library/*`, and NO test script. Phase 16.3 assumes component tests are runnable. This phase installs the infrastructure so those tests can exist.

This is an isolated setup phase. Nothing downstream works without it, and it has no dependency on any other Phase 16 work.

---

## Files to create

### `frontend/vitest.config.ts` (NEW)
**Purpose:** Vitest configuration integrated with Vite.
**Content:**
```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test-setup.ts',
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
```
**Constraints:**
- `globals: true` so test files can use `describe`/`it`/`expect` without imports.
- `jsdom` environment for React component tests.
- Path alias must match the existing `tsconfig.app.json` alias `@/* → src/*`.

### `frontend/src/test-setup.ts` (NEW)
**Purpose:** Global test setup — imports jest-dom custom matchers for better assertion messages.
**Content:**
```typescript
import '@testing-library/jest-dom/vitest'
```
**Constraints:** Must be listed in `vitest.config.ts` `setupFiles` (it is).

---

## Files to modify

### `frontend/package.json` (MOD)
**Change 1 — install dev dependencies:**
```bash
cd frontend
pnpm add -D vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom @vitest/ui
```

**Change 2 — add scripts:**
In the `scripts` block, add:
```json
"test": "vitest run",
"test:watch": "vitest",
"test:ui": "vitest --ui"
```

### `frontend/tsconfig.app.json` (MOD — may not be needed)
**Change:** If `pnpm tsc --noEmit` reports errors after install (e.g., "Cannot find name 'describe'"), add `"vitest/globals"` and `"@testing-library/jest-dom"` to the `types` array under `compilerOptions`.
**Exact change (only if needed):**
```json
"compilerOptions": {
  "types": ["vitest/globals", "@testing-library/jest-dom"]
}
```
**Constraints:**
- Verify first by running `pnpm tsc --noEmit` after installing deps. If it's already clean, DO NOT modify this file.
- Do not broaden the `types` array to include other packages — keep the change surgical.

---

## Tooling gate

```bash
cd frontend
pnpm install  # or pnpm i
pnpm tsc --noEmit
pnpm eslint .
pnpm test  # should report "No test files found" with exit 0 — that's fine, no tests yet
pnpm vite build
```

## Acceptance criteria

1. ✅ `vitest`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`, `jsdom`, `@vitest/ui` appear in `package.json` devDependencies and in `pnpm-lock.yaml`.
2. ✅ `frontend/vitest.config.ts` exists and is valid TypeScript.
3. ✅ `frontend/src/test-setup.ts` exists and imports jest-dom.
4. ✅ `pnpm test` executes (even with zero test files — reports "No test files found" or equivalent, but exits cleanly).
5. ✅ `pnpm tsc --noEmit` is clean (no new TS errors from adding test deps).
6. ✅ `pnpm vite build` still succeeds.
7. ✅ No product code files modified.
