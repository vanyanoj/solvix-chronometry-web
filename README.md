# solvix-chronometry-web

Веб-часть системы хронометража Solvix. Монорепо: backend + 3 фронта для ролей.

Прошивка ESP32 живёт отдельно: `solvix-chronometry-firmware`.

## Структура

```
apps/
  backend/         FastAPI + SQLAlchemy + Alembic (бэкенд Edge-сервера)
  warehouse/       фронт кладовщика  (placeholder, пока пусто)
  distributor/     фронт распределителя (placeholder, пока пусто)
  supervisor/      фронт старшего смены (placeholder, пока пусто)
packages/
  ui/              общая дизайн-система Solvix (placeholder)
  types/           общие TS-типы / API-контракт (placeholder)
  config/          общий eslint / prettier / tsconfig (placeholder)
infra/
  docker-compose.yml   локальный стек: postgres + mosquitto + backend
docs/
  PHASE_0_SETUP.md     как запустить фазу 0
```

## Фаза 0 — что в этом скелете

- Структура монорепо
- Бэкенд: FastAPI-приложение, конфиг через env, подключение к PostgreSQL (async)
- SQLAlchemy-модели всех таблиц по [[Модель данных]] из Обсидиана
- Первая Alembic-миграция (создаёт схему)
- `docker-compose.yml` с Postgres, Mosquitto и backend
- Заготовки UUID v7 (своя имплементация, без внешних зависимостей)

**Что ещё не входит** (по дизайну, всё ещё открыто):
- Эндпоинты API (вопрос №16)
- Watchdog аномалий (логика решена, ждёт MQTT и потока событий)
- MQTT-handler (топики и формат — вопрос №11)
- Фронты (UI не нарисован — №7, №13-15)

## Запуск

См. `docs/PHASE_0_SETUP.md`.

## Стек

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2.x (async), Alembic, asyncpg, Pydantic v2
- **БД:** PostgreSQL 16+
- **Брокер:** Mosquitto MQTT
- **Деплой:** Docker Compose (Edge-сервер в цеху)
- **Frontend (на будущее):** React + TS + Vite + Tailwind + shadcn/ui + TanStack
