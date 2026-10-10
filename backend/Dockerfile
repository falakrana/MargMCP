FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY agentops_backend ./agentops_backend
COPY migrations ./migrations
RUN pip install --no-cache-dir .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
# Apply migrations, then start the API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn agentops_backend.main:app_factory --factory --host 0.0.0.0 --port 8000"]
