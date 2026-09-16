# Architecture

## Fixed service boundary

```text
Browser
  -> React frontend
  -> Spring Boot main backend
  -> FastAPI AI server
```

React never calls FastAPI directly. Spring Boot is the public application API and owns authentication, business rules, persistence, external data integration, and AI request context assembly. FastAPI exposes internal AI capabilities to Spring Boot.

## Responsibilities

### Frontend

- Natural-language recommendation input
- Recommendation result presentation
- Preference, meal-history, and feedback user interfaces
- Calls only Spring Boot APIs

### Main backend

- Users, authentication, preferences, restaurants, meal history, and feedback
- Transaction boundaries and persistent data
- Exact filters such as distance, price, business hours, and ZeroPay availability
- Deterministic scoring and ranking
- External API integration and failure handling
- AI server request construction and response validation

### AI server

- Natural-language intent parsing into validated structured data
- Semantic retrieval and AI workflow orchestration
- LLM calls and recommendation explanation generation
- AI-specific retry, fallback, evaluation, and observability as features mature

## Current implementation boundary

The frontend shell and FastAPI health endpoint exist. The Spring Boot project is pending generation. Recommendation, persistence, external APIs, LLM integration, vector search, and LangGraph are planned and are not yet implemented.

## Data ownership

MySQL is the system of record for application data. A future vector database may store derived embeddings and retrieval metadata; it will not replace MySQL as the source of truth.

