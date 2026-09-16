# Project Instructions

Before modifying the project, read:

- `docs/architecture.md`
- `docs/api-contract.md`
- `docs/database.md`
- `docs/ai-flow.md`
- `docs/conventions.md`

Rules:

1. React calls Spring Boot only. It must not call FastAPI directly.
2. Spring Boot is the main application backend and service entry point.
3. FastAPI owns AI-specific workflows and LLM integration.
4. Keep deterministic filtering and ranking in normal code and the database.
5. Use validated structured output for AI responses where possible.
6. Do not change the architecture, database, frameworks, authentication, or API contracts without discussing the decision first.
7. Add dependencies only when existing project capabilities are insufficient.
8. Update the relevant documentation when APIs, architecture, database schema, AI workflow, or conventions change.
9. Run the relevant checks after changes and review the final Git diff.
10. Report changed files, reasons, validation results, and remaining concerns.

