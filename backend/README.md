# Backend bootstrap

The Spring Boot project has intentionally not been generated yet. Generate it into this `backend/` directory with Spring Initializr using these choices:

| Option | Value |
| --- | --- |
| Project | Gradle - Groovy |
| Language | Java |
| Spring Boot | Latest stable version compatible with Java 21 |
| Group | `com.zeropaylunch` |
| Artifact / Name | `backend` |
| Package name | `com.zeropaylunch.backend` |
| Packaging | Jar |
| Java | 21 |

Add only these dependencies for the Phase 1 health-check application:

- Spring Web
- Validation
- Spring Boot Actuator

Database access will be introduced in Phase 2 after deciding between Spring Data JPA and MyBatis. At that point, add the MySQL driver and the selected persistence dependency.

Extract the generated project so that `backend/gradlew`, `backend/build.gradle`, and `backend/src/` exist directly under this directory. Keep this README or merge its instructions into the root README after generation.

The first backend endpoint should act as the service-facing health check. FastAPI's internal health endpoint is documented separately and must only be called by Spring Boot.

