# Gemini Project Context

Use `AGENTS.md` as the entry point for project rules. Read the documents under `docs/` before reviewing architecture or code.

The core call path is fixed:

```text
React -> Spring Boot -> FastAPI
```

Spring Boot owns business data and deterministic business logic. FastAPI owns AI-specific parsing, retrieval workflows, LLM calls, and generated explanations.

