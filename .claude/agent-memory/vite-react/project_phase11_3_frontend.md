---
name: Phase 11.3 — Vite+React Frontend
description: SPA frontend for CDDE built in frontend/ — build passes, dev server on :3000 proxying to :8000
type: project
---

Phase 11.3 complete. Vite+React SPA in `frontend/` sub-project.

**Why:** Replaces Streamlit UI with a production-grade React SPA for the panel presentation demo.

**How to apply:** When extending the frontend, follow the established structure: pages in `src/pages/`, shared components in `src/components/`, API hooks in `src/hooks/useWorkflows.ts`, status palette centralized in `src/lib/status.ts`.

Key decisions made:
- shadcn@latest with Tailwind v4 required tsconfig.json (root) to include `compilerOptions.paths` — not just tsconfig.app.json
- `ignoreDeprecations: "6.0"` needed for `baseUrl` in tsconfig with TS 5.x+
- Google Fonts `@import url(...)` must precede `@import "tailwindcss"` to avoid Vite CSS warning
- AuditTable extracted as shared component used in both WorkflowDetailPage and AuditPage
- reactflow `nodeTypes` must be defined outside the component (stable reference) — currently fine since DAGNodeContent is file-level
- Chunk size warning (~670 KB) is expected — reactflow+dagre are large; acceptable for internal tool
