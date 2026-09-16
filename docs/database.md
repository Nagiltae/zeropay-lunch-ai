# Database

## Current decision

MySQL is the application system of record. Docker Compose defines a local MySQL 8.4 service.

No application schema exists yet. Entity tables, relationships, constraints, and indexes will be designed during Phase 2 for these initial domains:

- User
- Restaurant
- User preference
- Meal history

The choice between Spring Data JPA and MyBatis remains open. It will be made from the query patterns and transaction needs before adding a persistence dependency.

External API payloads and application-owned data must remain distinguishable. Derived vector embeddings will not be treated as the authoritative restaurant record.

