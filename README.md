# SOC Incident Assistant

Pet-проект для портфолио на позицию Machine Learning Technology Engineer.
Текущее состояние: **Documents + PostgreSQL + Alembic** — создание и чтение
документов knowledge base через FastAPI → Service → Repository → PostgreSQL,
миграции схемы и integration tests repository.

Стек: Python >=3.12, FastAPI, Pydantic v2 / pydantic-settings,
SQLAlchemy 2.x (async API), asyncpg, PostgreSQL, Alembic.
Docker-образ использует Python 3.12.
Embeddings, semantic search и LLM/RAG пока не реализованы.

## Требования

- Python >=3.12 и pip для локального запуска.
- PostgreSQL; в Docker Compose используется официальный образ `postgres:17`.
- Docker с Compose для запуска контейнеров.

## Конфигурация

При необходимости скопируйте `.env.example` в `.env`. Переменные окружения имеют
приоритет над `.env`, который читается из текущей рабочей директории.

| Переменная | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `APP_NAME` | `SOC Incident Assistant` | Название в OpenAPI |
| `APP_ENV` | `development` | `development`, `test` или `production`; пока не переключает поведение |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` или `CRITICAL`; пока не применяется к logging |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/soc_assistant` | URL PostgreSQL для asyncpg |
| `TEST_DATABASE_URL` | Не задан | URL отдельной мигрированной PostgreSQL БД для integration tests |

Значения `postgres:postgres` предназначены только для локальной разработки.
Реальные credentials задавайте через окружение, не сохраняйте их в Git.
Compose передаёт API собственный `DATABASE_URL` с hostname `postgres`; для запуска
Python на хосте используется `localhost`. Уровень серверных логов Uvicorn
настраивается отдельно параметром `--log-level`.

## Запуск через Docker Compose

Из корня репозитория:

```sh
docker compose up --build -d
docker compose exec api python -m alembic upgrade head
```

API доступен на порту 8000, PostgreSQL — на `127.0.0.1:5432`. API запускается после
успешного healthcheck PostgreSQL. Данные сохраняются в именованном Docker volume.

**Миграции выполняются явно, отдельно от старта API.** Приложение не создаёт
таблицы при старте. До применения миграций `/health` отвечает, но запросы
к documents завершаются ошибкой БД. Отдельного migration container нет.

## Database migrations

В активированном локальном Python окружении с установленным проектом выполните
из корня репозитория:

```sh
docker compose up -d postgres
alembic upgrade head
alembic current
```

Alembic использует `Settings().database_url`: тот же `DATABASE_URL` из окружения
или `.env`, что и приложение. Для локального запуска hostname — `localhost`.
Credentials в `alembic.ini` не хранятся. `app.main` не импортируется:
Alembic создаёт собственный async engine вне lifespan и вызывает `run_sync`.
Metadata берётся из существующего `Base`, модель `Document` импортируется явно.

Первая revision — `0001`, она создаёт `documents`. Команда отката одного шага:

```sh
alembic downgrade -1
```

Сейчас это удаляет `documents` вместе с данными. `alembic downgrade base` также
возвращает схему к состоянию до первой миграции. После учебной проверки отката
выполните `alembic upgrade head`, прежде чем запускать API.
Любую команду `alembic ...` можно записать как `python -m alembic ...`.

Если таблица была создана вручную на предыдущем этапе, `upgrade head` не будет
автоматически принимать её под управление. Сначала проверьте полное соответствие
существующей схемы revision `0001`; только для уже соответствующей схемы можно
выполнить `alembic stamp 0001`. Эта команда записывает версию, но не изменяет схему.
Не удаляйте существующие данные ради первоначального запуска миграций.

## Локальный запуск API

Создайте виртуальное окружение из корня репозитория:

```sh
python -m venv .venv
```

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```sh
source .venv/bin/activate
```

Установите приложение и зависимости разработки:

```sh
python -m pip install -e ".[dev]"
```

Запустите только PostgreSQL, если ещё не используете собственную БД:

```sh
docker compose up -d postgres
```

Задайте `DATABASE_URL` в окружении или `.env`, примените миграции и запустите API
(порт 8000 должен быть свободен):

```sh
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Документация: [Swagger UI](http://127.0.0.1:8000/docs).

## Endpoints

| Метод | Путь | Результат |
| --- | --- | --- |
| GET | `/health` | 200, `{"status":"ok"}`; доступность БД не проверяет |
| POST | `/api/v1/documents` | 201, созданный документ |
| GET | `/api/v1/documents?limit=20&offset=0` | 200, список документов по возрастанию ID |
| GET | `/api/v1/documents/{document_id}` | 200, документ; 404, если не найден |

`title`: 1–255 символов после удаления пробелов по краям.
`content`: непустой текст после удаления пробельных символов по краям;
форматирование внутри текста сохраняется.
`category`: необязательная строка до 100 символов либо `null`.
`limit`: 1–100, по умолчанию 20; `offset`: от 0, по умолчанию 0.
ID должен быть положительным целым числом. Некорректный запрос получает 422.
Обновление и удаление документов в этот этап не входят.

Пример POST в shell Linux/macOS:

```sh
curl -i -X POST http://127.0.0.1:8000/api/v1/documents \
  -H 'Content-Type: application/json' \
  -d '{"title":"Phishing playbook","content":"Inspect the sender and attachments.","category":"phishing"}'
```

То же в PowerShell:

```powershell
$body = @{ title = 'Phishing playbook'; content = 'Inspect the sender and attachments.'; category = 'phishing' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/documents -ContentType 'application/json' -Body $body
```

Ответ содержит `id`, `title`, `content`, `category`, `created_at`.
`created_at` заполняется PostgreSQL и включает часовой пояс.
Для GET используйте ID из ответа POST:

```sh
curl -i http://127.0.0.1:8000/api/v1/documents/1
curl -i 'http://127.0.0.1:8000/api/v1/documents?limit=20&offset=0'
curl -i http://127.0.0.1:8000/health
```

В PowerShell вместо `curl` можно использовать `curl.exe`.

## Архитектура и транзакции

- `app/main.py` — фабрика приложения, routers, lifespan для engine и session factory.
- `app/api/documents.py` — HTTP-контракты, Depends и преобразование domain error в 404.
- `app/schemas/document.py` — валидация запросов и сериализация ORM через `from_attributes`.
- `app/services/document_service.py` — сценарии, ошибка отсутствующего документа и транзакции.
- `app/repositories/document_repository.py` — запросы SQLAlchemy без HTTP-логики и commit.
- `app/models/document.py` — ORM-модель.
- `app/db/database.py` — DeclarativeBase, async engine, async_sessionmaker, сессия на запрос.

Service создаёт документ внутри `async with session.begin()`: успешный выход
делает commit, исключение приводит к rollback. Repository использует `flush`,
чтобы получить ID и серверный `created_at` до commit. `expire_on_commit=False`
позволяет сериализовать результат без дополнительного запроса после commit.
Сессия закрывается после запроса; engine освобождает пул при остановке приложения.
Создание engine не открывает соединение: `/health` и API-тесты с подменённым service
работают без запущенной БД. Глобальных engine/session/service singleton нет.

`sqlalchemy[asyncio]` включает `greenlet`, необходимый для async API SQLAlchemy.
Отдельный DI framework и базовые CRUD/service/repository классы не используются.

## Проверки

```sh
python -m pytest -v
python -m ruff check .
docker compose config
```

API-тесты подменяют `get_document_service` через `dependency_overrides`.
Проверяются создание, чтение, список, 404, валидация тела и пагинации;
внутренности SQLAlchemy не мокируются. Это не интеграционные тесты PostgreSQL:
работа SQL-запросов и транзакций с реальной БД ими не проверяется.

## Integration tests

Тесты в `tests/integration/` работают только с настоящим PostgreSQL и уже
мигрированной отдельной БД. Создайте её один раз, например через Compose:

```sh
docker compose up -d postgres
docker compose exec postgres createdb -U postgres soc_assistant_test
```

Если PostgreSQL работает вне Docker, используйте `createdb` с параметрами
подключения вашего сервера. Создание БД не выполняется на каждый тест.

Linux/macOS:

```sh
export TEST_DATABASE_URL='postgresql+asyncpg://postgres:postgres@localhost:5432/soc_assistant_test'
DATABASE_URL="$TEST_DATABASE_URL" python -m alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" python -m alembic current
python -m pytest -m integration -v
```

PowerShell:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://postgres:postgres@localhost:5432/soc_assistant_test'
$previousDatabaseUrl = $env:DATABASE_URL
try {
    $env:DATABASE_URL = $env:TEST_DATABASE_URL
    python -m alembic upgrade head
    python -m alembic current
} finally {
    $env:DATABASE_URL = $previousDatabaseUrl
}
python -m pytest -m integration -v
```

Alembic всегда читает `DATABASE_URL`, поэтому для миграции тестовой БД он
переопределяется временно. Перед pytest нужно вернуть обычный `DATABASE_URL`.
Сам `TEST_DATABASE_URL` никогда не меняет БД приложения или Alembic автоматически.
Его также можно задать в локальном `.env`.

Без `TEST_DATABASE_URL` integration tests пропускаются с понятной причиной,
остальные тесты продолжают выполняться. Неверный URL, недоступная БД или
отсутствующая таблица при заданном URL приводят к ошибке, а не скрытому skip.
Для защиты тесты требуют драйвер `postgresql+asyncpg`, имя БД с суффиксом `_test`
и имя, отличное от БД в `DATABASE_URL`. Fallback на development URL отсутствует.

Каждый тест открывает своё соединение и внешнюю транзакцию. `AsyncSession`
использует `join_transaction_mode="create_savepoint"`: commit/rollback сессии
работают внутри SAVEPOINT. После теста внешняя транзакция всегда откатывается,
сессия и соединение закрываются, engine освобождается. Тесты не выполняют
DROP/TRUNCATE и не создают таблицы. PostgreSQL sequence может продвинуться даже
после rollback, поэтому тесты не предполагают последовательные ID без пропусков.
Используйте отдельную БД без параллельных записей из других процессов.

Проверяются создание, чтение существующего/отсутствующего документа, сортировка
и пагинация списка, откат записи при исключении. Async-тесты запускает pytest
plugin AnyIO, уже установленный вместе с FastAPI/httpx; backend — `asyncio`.

## Planned features

- pgvector
- embeddings
- semantic search
- LLM-based incident analysis
