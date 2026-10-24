FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY marg_backend ./marg_backend
COPY migrations ./migrations
RUN pip install --no-cache-dir .

RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live')" || exit 1

# Apply migrations, then start the API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn marg_backend.main:app_factory --factory --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2}"]
