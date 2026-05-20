# Фаза 0 — поднять с нуля

Пошаговый план чтобы первый раз увидеть зелёный `/health` и `alembic upgrade head` без сюрпризов.

---

## Что должно быть установлено на Mac

| Инструмент | Зачем | Как поставить |
|------------|-------|---------------|
| Git | контроль версий | `brew install git` (если ещё нет) |
| Docker Desktop | крутить Postgres + Mosquitto | <https://www.docker.com/products/docker-desktop/> |
| Python 3.12+ | сам бэкенд | `brew install python@3.12` или через `uv` (см. ниже) |
| `uv` (опционально) | быстрый менеджер пакетов и виртуалок | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

> Можно жить и без `uv` (стандартный `python -m venv` + `pip` работают), но с `uv` быстрее и чище.

---

## 1. Положить скелет в репо

После распаковки zip:

```bash
cd ~/projects/solvix-chronometry-web   # или куда положил
git init
git add .
git commit -m "initial scaffold: phase 0 backend skeleton"
```

Создай **приватный** репо на GitHub `solvix-chronometry-web`. GitHub покажет команды — вторая часть:

```bash
git remote add origin git@github.com:<твой-логин>/solvix-chronometry-web.git
git branch -M main
git push -u origin main
```

---

## 2. Поднять инфру (Postgres + Mosquitto)

```bash
cd infra
cp ../apps/backend/.env.example .env   # настройки docker-compose
docker compose up -d postgres mosquitto
docker compose ps
```

Должны увидеть оба контейнера в статусе `running` / `healthy`.

Postgres проверить:

```bash
docker exec -it solvix-postgres psql -U solvix -d solvix_chronometry -c '\dt'
```

Пусто — это нормально, миграций ещё нет.

---

## 3. Поднять backend локально (вне docker-compose)

Удобно для разработки — авто-reload, IDE видит код напрямую.

```bash
cd apps/backend
cp .env.example .env

# Вариант А — через uv (быстрее)
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Вариант Б — через стандартный venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## 4. Сгенерировать первую миграцию

Модели уже описаны (`src/solvix_chronometry/models/`), но `alembic/versions/` пуст —
первую миграцию `autogenerate`-нём прямо из моделей. Это заодно проверит что
SQLAlchemy и Alembic-конфиг видят все таблицы.

```bash
cd apps/backend
alembic revision --autogenerate -m "initial schema"
```

В `alembic/versions/` появится файл вида `<id>_initial_schema.py`. **Открой и глазами пробеги** — там должны быть все 12 таблиц (sites, workshops, lines, stations, parts, batches, processes, users, nfc_badges, shifts, break_reasons, events) и постгресовые enum'ы.

Применяем:

```bash
alembic upgrade head
```

Проверяем что таблицы создались:

```bash
docker exec -it solvix-postgres psql -U solvix -d solvix_chronometry -c '\dt'
```

Должно быть 12 таблиц + служебная `alembic_version`.

---

## 5. Запустить бэкенд и убедиться что живой

```bash
cd apps/backend
uvicorn solvix_chronometry.main:app --reload
```

Открыть в браузере / curl:

- `http://localhost:8000/health` → `{"status":"ok","version":"0.1.0","env":"development"}`
- `http://localhost:8000/docs` → автогенерируемая Swagger-страница (пока с одним эндпоинтом)

---

## 6. Прогнать smoke-тесты

```bash
cd apps/backend
pytest
```

Все четыре теста зелёные = базовый каркас целый.

---

## 7. Закоммитить миграцию

```bash
cd ../..
git add apps/backend/alembic/versions/
git commit -m "phase 0: initial schema migration"
git push
```

---

## Что дальше

Фаза 0 готова. Можно идти в чат, разруливать оставшиеся открытые вопросы и писать фичи.

Ближайшие кандидаты, когда модели уже на месте:

- **№11 (MQTT-топики)** — без него ничего не приедет от ESP32
- **№16 (API-контракт)** — REST для веб-фронтов
- **Watchdog аномалий** — логика решена в №8, нужен запущенный поток событий + MQTT

---

## Если что-то падает

| Симптом | Скорее всего |
|---------|--------------|
| `alembic` не видит модели | проверь `PYTHONPATH=src` или что `pip install -e .` отработал |
| `connection refused` к Postgres | контейнер не поднят / другой порт / `.env` не подхватился |
| `port 5432 already in use` | у тебя уже крутится локальный Postgres — потуши или поменяй порт в `docker-compose.yml` |
| `enum already exists` при повторной миграции | откатывал не так — `alembic downgrade base` и попробуй заново |
