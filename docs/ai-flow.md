# AI Workflow

## Target flow

```text
User query
  -> intent parsing
  -> user context lookup
  -> restaurant candidate lookup
  -> hard filters
  -> semantic retrieval
  -> deterministic ranking
  -> optional constraint relaxation
  -> recommendation explanation
  -> response validation
```

## Responsibility rule

Distance, price, opening status, ZeroPay availability, recent history, exact filters, and final numeric ranking belong to application code and the database. The LLM interprets ambiguous natural language and generates explanations from already selected candidates.

LLM output must use a validated structured schema whenever it feeds program logic. Free-form model output must not directly control exact filters or ranking.

## Current implementation

Only the FastAPI service and its health endpoint exist. Intent parsing, recommendation schemas, retrieval, ranking, LangGraph, LLM providers, and fallback behavior are planned features.

