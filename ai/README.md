# AI server

This service owns AI-specific behavior such as natural-language intent parsing, semantic retrieval, workflow orchestration, LLM calls, and recommendation explanations.

Only Spring Boot may call this service in the application architecture. The frontend must never call it directly.

Current Phase 1 scope is limited to a health endpoint. LangGraph, LangChain, model SDKs, vector storage, and observability dependencies will be added only when their corresponding features are implemented.

```bash
poetry install
poetry run uvicorn app.main:app --reload --port 8001
poetry run ruff check .
poetry run pytest
```

