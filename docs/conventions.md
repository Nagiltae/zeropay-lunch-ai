# Conventions

## General

- Prefer clear feature-oriented code over speculative abstractions.
- Keep service responsibilities aligned with `architecture.md`.
- Validate data at API boundaries.
- Update documentation in the same change when a contract or architectural decision changes.
- Do not commit secrets, local environment files, generated output, or IDE metadata.

## Frontend

- Use React function components and TypeScript strict mode.
- Keep all server communication behind a dedicated API layer when API integration begins.
- Configure the API base URL for Spring Boot only.

## Backend

- Use Java 21 and Spring Boot.
- Make transaction boundaries explicit around business use cases.
- Map external API and AI server failures into stable application errors.
- Add tests for validation, business rules, persistence behavior, and service integration where they provide meaningful coverage.

## AI server

- Use type hints and Pydantic models at request, response, and LLM-output boundaries.
- Keep deterministic filters and ranking independent from prompts.
- Add framework and model-provider dependencies only with the feature that needs them.
- Test parsing, validation, workflow branching, fallback, and response contracts.

## Validation

Run the focused script for the changed service or run `./scripts/check-all.sh` for the repository. If a required runtime or generated project is missing, report it rather than claiming the check passed.

