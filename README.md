# SOC Incident Assistant

RAG backend для помощи SOC-аналитику при анализе security incidents. Приложение
хранит справочные документы, находит близкие по смыслу материалы и передаёт
отобранный контекст OpenAI-compatible LLM для структурированного анализа.

Portfolio project для позиции Machine Learning Technology Engineer.
Текущий этап: RAG API с проверками типов, GitHub Actions / GitLab CI и базовой эксплуатационной
диагностикой. Результат анализа требует проверки специалистом.

## Features

- Async FastAPI REST API для документов, поиска и анализа инцидентов.
- PostgreSQL, async SQLAlchemy и явные Alembic migrations.
- Sentence Transformer embeddings и semantic search через pgvector.
- RAG retrieval, ограничение контекста и проверка structured incident analysis через Pydantic.
- OpenAI-compatible LLM integration через `httpx.AsyncClient`.
- Liveness, database readiness, request ID и логи запросов.
- Unit/API и PostgreSQL integration tests, Ruff и mypy.
- Docker Compose, non-root API image, GitHub Actions и GitLab CI configuration.

## Architecture

```text
Client
  |
FastAPI (request ID / request logging)
  |
  +-- Documents API --> DocumentService --> DocumentRepository
  |                         +-- EmbeddingService
  |
  +-- Search API ----> SearchService ------> pgvector retrieval
  |                         +-- EmbeddingService
  |
  +-- Analyze API ---> AnalysisService
  |                         +-- EmbeddingService
  |                         +-- pgvector retrieval
  |                         +-- Prompt Builder
  |                         +-- LLMService --> external provider
  |
  +-- /health (liveness)
  +-- /ready  (SELECT 1 through the existing session factory)

DocumentRepository --> AsyncSession --> PostgreSQL + pgvector
```

API отвечает за HTTP и dependency wiring; service — за сценарий работы;
repository — за SQL. Repository вызывает `flush`, а транзакцией записи владеет
service (`session.begin()`). Embedding создаётся до начала транзакции записи.
Сессии используют `expire_on_commit=False`.

Engine, session factory, одна embedding model и один HTTP client создаются внутри
FastAPI lifespan. Session factory и сервисы сохраняются в `app.state`.
При shutdown закрывается HTTP client и освобождается engine, даже если закрытие
клиента завершилось ошибкой. При ошибке загрузки модели engine также освобождается.

## RAG flow

```text
incident -> embedding -> top-k semantic search -> grounded prompt
         -> LLM -> validated structured response + application-owned sources
```

Поиск исключает legacy `NULL` embeddings, сортирует по cosine distance
(при равенстве — по ID), возвращает `similarity = 1 - distance`.
Контекст ограничен `RAG_MAX_CONTEXT_CHARS`; последний документ может обрезаться.
`sources` включает только документы, реально попавшие в prompt.
Без доступного контекста API возвращает 409 и не вызывает LLM.

Incident и документы обозначены в prompt как недоверенные данные. Ответ LLM
должен соответствовать JSON schema: `summary`, `severity`, `likely_attack_type`,
`recommended_actions`. Приложение добавляет `sources`: ID, title, category и similarity.
Модель не определяет список источников.

## Tech stack

Python 3.12 (пакет допускает >=3.12), FastAPI, Pydantic / pydantic-settings,
SQLAlchemy async, asyncpg, PostgreSQL 17, Alembic, pgvector,
Sentence Transformers (`all-MiniLM-L6-v2`, 384 dimensions), httpx,
pytest / AnyIO, Ruff, mypy, Docker Compose, GitHub Actions, GitLab CI.

## API

| Method | Path | Назначение |
| --- | --- | --- |
| GET | `/health` | 200 `{"status":"ok"}`; без проверки зависимостей |
| GET | `/ready` | PostgreSQL `SELECT 1`: 200 `{"status":"ready"}` или 503 `{"status":"not_ready"}` |
| POST | `/api/v1/documents` | Создать документ и embedding, ответ 201 |
| GET | `/api/v1/documents` | Список с `limit` (1–100) и `offset` |
| GET | `/api/v1/documents/{id}` | Получить документ |
| POST | `/api/v1/search` | Semantic search: `query`, `limit` (1–20, default 5) |
| POST | `/api/v1/analyze` | RAG: `incident` (10–10000 символов), `top_k` (1–10, default 5) |

OpenAPI UI: [localhost:8000/docs](http://127.0.0.1:8000/docs).
Каждый ответ получает `X-Request-ID`: входное значение либо новый UUID.
Readiness использует существующую DB session; probe ограничен тремя секундами.
Он проверяет доступность БД, но не наличие миграций, inference или LLM provider.

Известные application errors имеют тело `{"detail":"..."}`:
404 — документ отсутствует; 409 — нет RAG context; 502 — timeout, connection error,
non-2xx или неверный ответ LLM; 503 — LLM не настроен; 422 — request validation.
Readiness 503 использует указанное выше тело `status`.
Неожиданная ошибка возвращает 500 с общим сообщением без внутренних diagnostics.

Примеры для POSIX shell (в Windows также можно использовать OpenAPI UI):

```sh
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -H 'Content-Type: application/json' \
  -d '{"title":"SSH triage","content":"Review successful logins after repeated SSH failures. Preserve authentication logs.","category":"credential_access"}'
curl -X POST http://127.0.0.1:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"multiple failed SSH login attempts","limit":5}'
```

Ручной вызов после настройки provider/key и перезапуска API:

```sh
curl -X POST http://127.0.0.1:8000/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"incident":"80 failed SSH login attempts for the same account in 10 minutes.","top_k":5}'
```

Этот вызов отправляет incident и выбранный контекст внешнему провайдеру и может
быть платным. Тесты и CI реальных LLM-запросов не выполняют.

## Local development

Нужны Python 3.12, pip и PostgreSQL с pgvector (удобно через Docker Compose).
При первой загрузке embedding model нужны доступ к Hugging Face и место для cache.

```sh
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# PowerShell вместо предыдущей команды:
# .\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
cp .env.example .env
# PowerShell: Copy-Item .env.example .env
docker compose up -d postgres
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --no-access-log
```

Команды выполняются из корня репозитория. API обслуживает запросы после загрузки
модели. Каждый процесс Uvicorn владеет отдельной моделью. `/health`, документы
и поиск не требуют LLM key. При `/analyze` отсутствие контекста даёт 409;
если контекст найден, отсутствие ключа даёт controlled 503.

| Сценарий | Адрес PostgreSQL | DATABASE_URL |
| --- | --- | --- |
| Local Python / Alembic с хоста | `127.0.0.1:55432` | `postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/soc_assistant` |
| API внутри Docker Compose | `postgres:5432` | `postgresql+asyncpg://postgres:postgres@postgres:5432/soc_assistant` |

Compose публикует `55432:5432`. Default Settings и `.env.example` рассчитаны на хост;
Compose передаёт API собственный URL для Docker network.

## Migrations

```sh
python -m alembic upgrade head
python -m alembic current
```

Ожидаемый head — `0002`. Alembic читает `Settings().database_url`; приложение
не создаёт таблицы и не запускает миграции автоматически. `/ready` не подтверждает
актуальность схемы. Пользователю миграций нужны права на создание extension `vector`.

`0001` создаёт documents; `0002` добавляет `VECTOR(384)` и
`CHECK (embedding IS NOT NULL) NOT VALID`. Старые строки сохраняют `NULL` и
исключаются из поиска; новые и изменяемые строки должны иметь embedding.
Для legacy документов нужен отдельный ручной backfill той же моделью:
прочитать строки с `NULL`, вычислить вектор вне транзакции записи, сохранить его
в короткой транзакции. Автоматический backfill не реализован.
Не меняйте модель для существующего набора векторов без пересчёта embeddings.

## Tests

```sh
python -m pytest -v
python -m pytest -m "not integration" -v
python -m ruff check .
python -m mypy app
git diff --check
```

Unit/API tests используют fake embeddings, dependency overrides и
`httpx.MockTransport`. Они проверяют API, retrieval orchestration, prompt budget,
JSON validation, public errors, LLM timeout, resource cleanup, Settings,
readiness и request logging. Реальная модель не скачивается; ключ не нужен.

Integration tests требуют отдельную предварительно мигрированную БД. Создайте
её один раз, если она ещё не существует:

```sh
docker compose exec postgres createdb -U postgres soc_assistant_test
```

POSIX shell:

```sh
export TEST_DATABASE_URL='postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/soc_assistant_test'
DATABASE_URL="$TEST_DATABASE_URL" python -m alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" python -m alembic current
python -m pytest -m integration -v
```

PowerShell:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/soc_assistant_test'
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

Перед pytest обычный `DATABASE_URL` должен быть восстановлен. Тесты требуют
имя БД с суффиксом `_test`, отличное от application database, и драйвер asyncpg.
Без `TEST_DATABASE_URL` integration tests пропускаются; неверная конфигурация
или недоступная явно заданная БД приводит к ошибке.

Используйте тестовую БД без сохранённых embedded documents и параллельных записей.
Каждый тест работает во внешней транзакции с SAVEPOINT и rollback; данные не
удаляются через DROP/TRUNCATE. Проверяются repository, транзакции, pgvector cosine
ordering и RAG retrieval с fake LLM и детерминированными векторами размерности 384.

## Docker

```sh
docker compose config
docker compose build api
docker compose up -d
docker compose exec api python -m alembic upgrade head
docker compose ps
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

API image использует `python:3.12-slim`, только runtime dependencies и пользователя
`appuser` (UID 10001). HEALTHCHECK обращается к `/health` через Python stdlib.
Модель не скачивается при build: она загружается при startup в доступный пользователю
cache (`HF_HOME` можно переопределить). Первый запуск может быть долгим; cache
в контейнере теряется при его пересоздании, отдельного model volume пока нет.

Compose сохраняет PostgreSQL в именованном volume, ждёт его healthcheck и использует
`restart: unless-stopped`. Source code bind mount отсутствует. API публикуется на
8000, PostgreSQL — на 55432. Это конфигурация для разработки с dev credentials.

`.env` не попадает в image. Для ручного анализа через Docker экспортируйте LLM
variables в окружение хоста и явно передайте их контейнеру:

```sh
docker compose stop api
docker compose run --rm --service-ports -e LLM_API_KEY -e LLM_BASE_URL -e LLM_MODEL api
```

Показанная команда предполагает, что все три переменные заданы. Внутренний
`DATABASE_URL` остаётся `postgres:5432`. Секреты не записываются в Compose.

## CI

GitHub Actions настроен в `.github/workflows/ci.yml`: запускается при `push`,
`pull_request` и вручную через `workflow_dispatch`. После успешного `lint`
параллельно выполняются `unit` и `integration`. Workflow имеет только
`contents: read`, ограничение времени jobs и кеш pip по `pyproject.toml`.

GitLab CI настроен отдельно в `.gitlab-ci.yml` со stages `lint` и `test`.
Обе конфигурации выполняют одинаковые проверки:

| Job | Проверки |
| --- | --- |
| `lint` | Ruff и `mypy app` |
| `unit` | `pytest -m "not integration" -v`, без PostgreSQL |
| `integration` | Миграции до head, затем `pytest -m integration -v` |

Каждый job использует `python:3.12-slim` и устанавливает `.[dev]`. Integration job
поднимает service `pgvector/pgvector:pg17` с alias `postgres`, БД
`soc_assistant_test` и одноразовыми credentials `postgres:postgres`.
`TEST_DATABASE_URL` использует `postgres:5432`; только команда Alembic временно
получает этот URL как `DATABASE_URL`, сохраняя защиту тестовой БД в pytest.

Кешируется только pip cache. `HF_HUB_OFFLINE=1` и `TRANSFORMERS_OFFLINE=1` запрещают
загрузку моделей; тесты используют mocks/manual vectors. LLM key не требуется.
В GitHub jobs работают в контейнере Python на `ubuntu-24.04`, поэтому PostgreSQL
доступен по имени service `postgres`, без публикации порта на runner.
Для GitLab нужен Runner с поддержкой container services. Deploy jobs отсутствуют.
Настройка services описана в документации
[GitHub Actions](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers)
и [GitLab](https://docs.gitlab.com/ci/services/postgres/).

CI config created and locally validated where possible. Реальный pipeline нужно
подтвердить запуском в GitHub/GitLab; локальные проверки не заменяют этот запуск.

## Configuration

`pydantic-settings` читает `.env` из текущей директории; environment variables имеют
приоритет. После изменения конфигурации перезапустите API.

| Variable | Default / поведение |
| --- | --- |
| `APP_NAME` | `SOC Incident Assistant` |
| `APP_ENV` | `development`; допустимы `development`, `test`, `production` |
| `LOG_LEVEL` | `INFO`; допустимы `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `DATABASE_URL` | Host URL из таблицы выше; в production задаётся явно |
| `TEST_DATABASE_URL` | Не задан; включает integration tests |
| `EMBEDDING_MODEL_NAME` | `sentence-transformers/all-MiniLM-L6-v2` |
| `EMBEDDING_DIMENSION` | `384`, должна совпадать с моделью и схемой |
| `LLM_BASE_URL` | `https://api.openai.com/v1`, валидный HTTP(S) URL |
| `LLM_MODEL` | `gpt-4.1-mini`, непустая строка |
| `LLM_API_KEY` | Не задан; не обязателен при startup |
| `LLM_TIMEOUT_SECONDS` | `30`, положительный HTTP timeout для операций httpx |
| `RAG_MAX_CONTEXT_CHARS` | `12000`, минимум 1, включая заголовки документов |

При `APP_ENV=production` отсутствие явно заданного `DATABASE_URL` вызывает ошибку
валидации до создания engine и загрузки модели. `.env` считается явной конфигурацией.
Пустые DATABASE_URL/LLM_MODEL и некорректный LLM_BASE_URL отклоняются также в development.
Это минимальная валидация, а не гарантия готовности к публичному production.
`.env` игнорируется Git; `.env.example` содержит только примеры и пустой LLM key.

Logging настраивается в lifespan, а не при импорте или `create_app()`.
Стандартный logging выводит timestamp, level, logger и message.
Request log содержит method, path, status, duration_ms и request_id. Тела, query
strings, Authorization, векторы и provider responses не логируются. Стандартный
Uvicorn access log отключён, чтобы не дублировать URL с query strings; HTTP client
logging ограничен уровнем WARNING. Неожиданные ошибки логируются без текста
исключения, который может содержать SQL values или credentials.

## Design decisions

- Простая orchestration вместо LangChain: retrieval, prompt и provider call видны
  напрямую и тестируются отдельно; дополнительные frameworks здесь не нужны.
- `asyncio.to_thread` выносит model loading и encode из event loop; одна модель
  переиспользуется в lifespan. Это не batching и не очередь inference.
- `httpx.AsyncClient` переиспользует соединения и даёт явные timeout/error handling
  без provider SDK. Automatic retries отсутствуют, чтобы не повторять платные вызовы.
- Application-owned sources связывают ответ с реально переданным контекстом.
- Fake embeddings и LLM в тестах делают проверки воспроизводимыми без сети и оплаты.
- pgvector хранит документы и векторы в PostgreSQL, без отдельной vector database.
- mypy проверяет аннотации приложения без максимального strict и массовых ignore.

## Limitations / planned improvements

- Нет auth, rate limiting, reranking, hybrid search и vector indexes; текущий поиск
  рассчитан на небольшой dataset.
- Нет automatic retries, conversational memory и истории анализов.
- Нет similarity threshold: top-k может содержать нерелевантные документы.
- JSON validation проверяет структуру, но не достоверность выводов модели.
- Startup требует доступной embedding model/cache; readiness проверяет только БД.
- Версии зависимостей ограничены диапазонами, отдельного lockfile пока нет.
- Возможное продолжение: размеченный evaluation dataset для оценки retrieval и анализа.

## What this project demonstrates

- Python async backend development и REST API design.
- PostgreSQL / SQLAlchemy, миграции и управление транзакциями.
- Semantic/vector retrieval и практическую RAG architecture.
- LLM API integration с валидируемым структурированным ответом.
- Unit/integration testing и static/type checks.
- Docker, lifecycle ресурсов, health/readiness и безопасные request logs.
- Основы CI/CD: автоматические проверки в GitHub Actions и GitLab CI (без deployment).
