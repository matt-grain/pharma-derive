---
paths: "src/agents/**/*.py"
---

# LLM Gateway — Single Point of Model Construction

## The Mistake
All 5 agent files constructed their own `OpenAIChatModel` + `OpenAIProvider` at module level with hardcoded `base_url="http://localhost:8650/v1"` and `api_key="not-needed-for-mailbox"`. The `llm_gateway.create_llm()` existed but was completely bypassed. This means:
- Changing the LLM endpoint requires editing 5 files
- Hardcoded credentials in source code (even dummy ones set a bad pattern)
- Tests import agent modules and trigger real HTTP client construction

## Rules

1. **`src/engine/llm_gateway.py` is the ONLY place that constructs LLM model objects.** No `OpenAIChatModel()`, `OpenAIProvider()`, or `anthropic.Client()` anywhere else.

2. **Agent modules must NOT instantiate models at module level.** Define agents with `model=None` or accept the model as a parameter. The orchestrator injects the model at call time via `agent.run(..., model=llm)`.

3. **No hardcoded URLs or API keys in agent files.** All configuration flows through `llm_gateway.py` which reads from environment variables with sensible defaults.

4. **The gateway is the integration point for observability.** If we swap AgentLens for another proxy, only `llm_gateway.py` changes.

## How to Apply
When creating a new agent, define it with `Agent(model=None, ...)` or a placeholder. The orchestrator calls `create_llm()` once and passes the model to all agent runs.
