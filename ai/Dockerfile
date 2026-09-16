FROM python:3.11-slim AS build

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1

WORKDIR /app

RUN pip install --no-cache-dir poetry==2.4.3

COPY pyproject.toml poetry.lock poetry.toml ./
RUN poetry install --only main --no-root

FROM python:3.11-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN groupadd --system app \
    && useradd --system --gid app app

WORKDIR /app

COPY --from=build --chown=app:app /app/.venv .venv
COPY --chown=app:app app app

USER app

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
