# ZeroPay Lunch AI

ZeroPay Lunch AI recommends nearby restaurants from a natural-language request, user preferences, budget, recent meal history, location, and situational context.

The service uses a monorepo and keeps Spring Boot as the single application entry point:

```text
React -> Spring Boot -> FastAPI
```

## Current status

This repository is at the Phase 1 skeleton stage.

| Area | Status |
| --- | --- |
| Frontend | Minimal React + TypeScript + Vite app created |
| Main backend | Directory and Spring Initializr guide created; project generation pending |
| AI server | Minimal FastAPI health endpoint and test created |
| MySQL | Local Docker Compose service defined |
| Contracts and architecture | Initial documents created |

## Repository layout

```text
zeropay-lunch-ai/
├── frontend/    # React application
├── backend/     # Spring Boot application (pending generation)
├── ai/          # FastAPI AI server
├── docs/        # Architecture and contracts
└── scripts/     # Local validation commands
```

## Local setup

Copy the local environment template before starting infrastructure:

```bash
cp .env.example .env
docker compose up -d mysql
```

Frontend requires Node.js 20.19 or newer:

```bash
cd frontend
npm install
npm run dev
```

AI server requires Python 3.11+ and Poetry:

```bash
cd ai
poetry install
poetry run uvicorn app.main:app --reload --port 8001
```

See `backend/README.md` before generating the Spring Boot project.

Run all available checks from the repository root:

```bash
./scripts/check-all.sh
```

