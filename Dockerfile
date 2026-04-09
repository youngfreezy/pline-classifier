FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        "fastapi>=0.115.0" \
        "uvicorn>=0.34.0" \
        "pydantic>=2.10.0" \
        "sqlalchemy>=2.0.0" \
        "psycopg2-binary>=2.9.0" \
        "openai>=1.60.0" \
        "anthropic>=0.42.0" \
        "python-dotenv>=1.0.0"

COPY app ./app
COPY scripts ./scripts
COPY data ./data

EXPOSE 8000

CMD ["bash", "-c", "python scripts/seed.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
