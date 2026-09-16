FROM eclipse-temurin:21-jdk-alpine AS build

WORKDIR /workspace

COPY gradlew gradlew
COPY gradle gradle
COPY build.gradle settings.gradle ./
RUN chmod +x gradlew && ./gradlew --no-daemon dependencies

COPY src src
RUN ./gradlew --no-daemon bootJar

FROM eclipse-temurin:21-jre-alpine

RUN apk add --no-cache curl \
    && addgroup --system app \
    && adduser --system --ingroup app app

WORKDIR /app

COPY --from=build --chown=app:app /workspace/build/libs/backend-0.0.1-SNAPSHOT.jar app.jar

USER app

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=10 \
  CMD curl --fail --silent http://127.0.0.1:8080/actuator/health > /dev/null || exit 1

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
