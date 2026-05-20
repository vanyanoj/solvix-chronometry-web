# Backend — Edge

FastAPI + SQLAlchemy (async) + Alembic + asyncpg.

## Структура

```
src/solvix_chronometry/
  main.py           FastAPI app + lifespan + /health
  config.py         настройки через env
  db.py             async engine + session
  uuid_v7.py        своя реализация UUID v7 (Решение №53)
  models/
    base.py         DeclarativeBase + helpers
    enums.py        PartStatus, EventType, ...
    hierarchy.py    Site / Workshop / Line / Station
    parts.py        Part / Batch
    processes.py    Process (+ anomaly_threshold_pct)
    people.py       User / NfcBadge / Shift
    break_reasons.py
    events.py
alembic/
  env.py            async-конфиг для миграций
  versions/         генерируются автоматически
```

## Запуск

См. `../../docs/PHASE_0_SETUP.md` — там полный пошаговый план первого запуска.

Кратко (если уже всё установлено):

```bash
cd ../../infra && docker compose up -d
cd ../apps/backend && alembic revision --autogenerate -m "initial schema" && alembic upgrade head
```

Healthcheck: <http://localhost:8000/health>
