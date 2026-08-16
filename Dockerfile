FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --uid 10001 remoteops

COPY pyproject.toml README.md ./
COPY remoteops ./remoteops
COPY alembic.ini ./
COPY migrations ./migrations

RUN python -m pip install --no-cache-dir .

USER remoteops
EXPOSE 8000

CMD ["uvicorn", "remoteops.main:app", "--host", "0.0.0.0", "--port", "8000"]
