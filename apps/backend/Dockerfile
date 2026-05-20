FROM python:3.12-slim

WORKDIR /app

# Системные зависимости для asyncpg (libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Зависимости отдельным слоем для кеша
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

EXPOSE 8000

# По умолчанию запускаем uvicorn в dev-режиме с автоперезагрузкой.
# В проде заменишь на `uvicorn solvix_chronometry.main:app --host 0.0.0.0 --port 8000 --workers 4`
CMD ["uvicorn", "solvix_chronometry.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
