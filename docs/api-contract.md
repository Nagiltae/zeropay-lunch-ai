# API Contract

This document separates implemented endpoints from planned contracts. Paths and payloads marked as planned are not available yet.

## Implemented: AI health

Internal endpoint called by Spring Boot or operational checks.

```http
GET /health
```

Response `200 OK`:

```json
{
  "status": "ok",
  "service": "ai"
}
```

## Planned: backend health

The exact public health path will be finalized when the Spring Boot project is generated. Spring Boot Actuator may expose operational health separately from an application-facing API.

## Planned: recommendation

Recommendation endpoints and DTOs will be designed in Phase 3. The external contract belongs to Spring Boot. Any Spring Boot-to-FastAPI contract will be documented as an internal API, with request and response validation on both sides.

