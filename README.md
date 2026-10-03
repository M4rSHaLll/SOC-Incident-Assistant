# SOC Incident Assistant

Pet-проект для портфолио на позицию Machine Learning Technology Engineer.
Текущее состояние: **RAG incident analysis** — документы knowledge base, локальные
embeddings, semantic search и структурированный анализ через совместимый LLM API.

Стек: Python >=3.12, FastAPI, Pydantic v2 / pydantic-settings,
SQLAlchemy 2.x (async API), asyncpg, PostgreSQL, Alembic, pgvector,
Sentence Transformers, httpx для async LLM HTTP-запросов.
Docker-образ использует Python 3.12.

## Требования

- Python >=3.12 и pip для локального запуска.
- PostgreSQL 17 с pgvector; Compose использует `pgvector/pgvector:pg17`.
- Docker с Compose для запуска контейнеров.
- Доступ к Hugging Face при первой загрузке модели и место для PyTorch/model cache.

## Конфигурация

При необходимости скопируйте `.env.example` в `.env`. Переменные окружения имеют
приоритет над `.env`, который читается из текущей рабочей директории.

| Переменная | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `APP_NAME` | `SOC Incident Assistant` | Название в OpenAPI |
| `APP_ENV` | `development` | `development`, `test` или `production`; пока не переключает поведение |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` или `CRITICAL`; пока не применяется к logging |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/soc_assistant` | URL PostgreSQL для asyncpg при запуске с хоста |
| `TEST_DATABASE_URL` | Не задан | URL отдельной мигрированной PostgreSQL БД для integration tests |
| `EMBEDDING_MODEL_NAME` | `sentence-transformers/all-MiniLM-L6-v2` | Модель для документов и запросов |
| `EMBEDDING_DIMENSION` | `384` | Должна совпадать с моделью и схемой `VECTOR(384)` |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Base URL OpenAI-compatible Chat Completions API, включая `/v1` |
| `LLM_API_KEY` | Не задан | Bearer API key; нужен только для анализа через LLM |
| `LLM_MODEL` | `gpt-4.1-mini` | Имя модели у выбранного провайдера |
| `LLM_TIMEOUT_SECONDS` | `30` | Положительное значение HTTP timeout |
| `RAG_MAX_CONTEXT_CHARS` | `12000` | Максимум символов knowledge context, включая заголовки документов |

Значения `postgres:postgres` предназначены только для локальной разработки.
Реальные credentials задавайте через окружение, не сохраняйте их в Git.
Адрес подключения зависит от места запуска:

| Сценарий | Адрес PostgreSQL | DATABASE_URL |
| --- | --- | --- |
| Python / Alembic на хосте | `127.0.0.1:55432` | `postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/soc_assistant` |
| API внутри Docker Compose | `postgres:5432` | `postgresql+asyncpg://postgres:postgres@postgres:5432/soc_assistant` |

Default в Settings и `.env.example` рассчитаны на локальный запуск с хоста.
Compose передаёт API собственный URL через environment: контейнеры используют
Docker network и внутренний порт 5432. Публикация порта остаётся `55432:5432`.
Уровень серверных логов Uvicorn
настраивается отдельно параметром `--log-level`.

Embeddings и retrieval работают локально. Для `/analyze` задайте LLM provider
и API key в окружении или локальном `.env` (он игнорируется Git). Пустой ключ не
мешает запуску API, созданию документов и `/search`; при попытке вызвать LLM
анализ вернёт 503. После изменения LLM settings перезапустите API.
Incident и отобранные фрагменты документов отправляются настроенному провайдеру.

## Запуск через Docker Compose

Из корня репозитория:

```sh
docker compose up --build -d
docker compose exec api python -m alembic upgrade head
```

API доступен на порту 8000, PostgreSQL — на host-порту 55432. API запускается после
успешного healthcheck PostgreSQL. Данные сохраняются в именованном Docker volume.

Модель загружается при startup API, а не при Docker build. Первый запуск требует
сети и может быть долгим; до завершения startup API не обслуживает запросы.
Каждый процесс Uvicorn владеет своей моделью. Hugging Face использует свой cache
(путь можно переопределить через `HF_HOME`); модель не включается в образ.

Существующий volume автоматически не удаляется. Если volume от обычного postgres
image несовместим с новым окружением, может потребоваться его ручное пересоздание
после резервного копирования. Это удаляет локальные данные; не выполняйте очистку
volume как обычный шаг обновления.

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
или `.env`, что и приложение. При запуске Alembic с хоста адрес — `127.0.0.1:55432`.
Credentials в `alembic.ini` не хранятся. `app.main` не импортируется:
Alembic создаёт собственный async engine вне lifespan и вызывает `run_sync`.
Metadata берётся из существующего `Base`, модель `Document` импортируется явно.

Revision `0001` создаёт `documents` и не изменена. Revision `0002` включает
extension `vector`, добавляет `embedding VECTOR(384)` и ограничение новых записей.
Пользователь БД для миграций должен иметь право устанавливать extension.
Проверка после миграции:

```sh
docker compose exec postgres psql -U postgres -d soc_assistant -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"
```

Команда отката одного шага:

```sh
alembic downgrade -1
```

С `0002` это удаляет embedding column и её CHECK, сохраняя документы. Extension
`vector` остаётся, поскольку им могут пользоваться другие таблицы.
`alembic downgrade base` удаляет таблицу documents вместе с данными.
После учебной проверки отката
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
| POST | `/api/v1/search` | 200, query и top-k документов с similarity |
| POST | `/api/v1/analyze` | 200, структурированный SOC analysis и source metadata |

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

## Semantic search

При создании документа: `content → SentenceTransformer → 384-dimensional embedding
→ pgvector`. Вектор вычисляется до начала транзакции записи; при ошибке модели
документ не сохраняется. GET/POST documents не возвращают embedding в HTTP response.

При поиске: `query → embedding → cosine distance → top-k documents`.
Repository использует SQLAlchemy `cosine_distance`, исключает старые строки с
NULL embedding и сортирует по возрастанию distance (при равенстве — по ID).
SearchService возвращает `similarity = 1 - cosine_distance`: выше — ближе.
Cosine similarity лежит примерно в диапазоне [-1, 1]; это не вероятность.
Поиск точный, без HNSW/IVFFlat и без порога релевантности.

```sh
curl -i -X POST http://127.0.0.1:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"multiple failed ssh login attempts","limit":5}'
```

PowerShell:

```powershell
$body = @{ query = 'multiple failed ssh login attempts'; limit = 5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/search -ContentType 'application/json' -Body $body
```

Ответ: `{"query":"...","results":[{"document_id":1,"title":"...","content":"...",
"category":"...","similarity":0.87}]}`. Если подходящих записей нет в БД, results —
пустой список. Query обрезается по краям и не может быть пустой; limit — 1–20,
default 5. Некорректные значения получают 422.

Используется [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
с собственной размерностью 384. EmbeddingService проверяет размерность при
загрузке модели и каждого результата; нулевые и нечисловые/бесконечные векторы
отклоняются. Загрузка и `encode()` выполняются через `asyncio.to_thread` на CPU.
Модель создаётся один раз в lifespan и доступна через `app.state` / Depends.
На import модель не создаётся. SQLAlchemy VECTOR сам сериализует векторы;
дополнительный asyncpg registration для одиночной VECTOR-колонки не нужен.

На этом этапе один документ получает один вектор: длинный текст обрезается
по token limit модели, chunking отсутствует. При замене модели даже с той же
размерностью нужно пересчитать все векторы; другая размерность требует отдельной
миграции. Произвольное изменение EMBEDDING_DIMENSION при текущей схеме отклоняется.

## Архитектура и транзакции

- `app/main.py` — фабрика приложения, routers, lifespan для engine и session factory.
- `app/api/documents.py` — HTTP-контракты, Depends и преобразование domain error в 404.
- `app/schemas/document.py` — валидация запросов и сериализация ORM через `from_attributes`.
- `app/services/document_service.py` — сценарии, ошибка отсутствующего документа и транзакции.
- `app/repositories/document_repository.py` — запросы SQLAlchemy без HTTP-логики и commit.
- `app/models/document.py` — ORM-модель.
- `app/db/database.py` — DeclarativeBase, async engine, async_sessionmaker, сессия на запрос.
- `app/services/embedding_service.py` — lifecycle модели и кодирование текста.
- `app/services/search_service.py` — query embedding и преобразование distance в similarity.
- `app/api/search.py`, `app/schemas/search.py` — контракт semantic search.
- `app/services/analysis_service.py` — retrieval → prompt → LLM → response с sources.
- `app/services/prompt_builder.py` — инструкции и ограниченный knowledge context.
- `app/services/llm_service.py` — async HTTP, обработка ошибок и проверка JSON.
- `app/api/analysis.py`, `app/schemas/analysis.py` — контракт анализа инцидента.

Service создаёт документ внутри `async with session.begin()`: успешный выход
делает commit, исключение приводит к rollback. Repository использует `flush`,
чтобы получить ID и серверный `created_at` до commit. `expire_on_commit=False`
позволяет сериализовать результат без дополнительного запроса после commit.
Сессия закрывается после запроса; engine освобождает пул при остановке приложения.
Создание engine не открывает соединение: `/health` и API-тесты с подменённым service
работают без запущенной БД; в тестах модель также подменена. На реальном startup
модель должна успешно загрузиться. Глобальных engine/session/service singleton нет.

`sqlalchemy[asyncio]` включает `greenlet`, необходимый для async API SQLAlchemy.
Отдельный DI framework и базовые CRUD/service/repository классы не используются.

В lifespan после загрузки embedding-модели создаётся один `httpx.AsyncClient` и
`LLMService`, доступный через `app.state` / Depends. HTTP client закрывается через
`aclose()` перед освобождением engine; вложенные `finally` обеспечивают освобождение
БД также при ошибке startup или закрытия HTTP client. HTTP client не создаётся
на import или заново на каждый запрос. Глобальная logging configuration не меняется.

## RAG incident analysis

```text
Incident → EmbeddingService → pgvector retrieval → top-k context
         → LLMService / Chat Completions → validated SOC analysis + sources
```

AnalysisService напрямую использует EmbeddingService и DocumentRepository;
SearchService для этого не вызывается. Схема БД не менялась, Alembic head — `0002`.

Запрос к провайдеру: `POST {LLM_BASE_URL}/chat/completions`, Bearer Authorization,
configured `model`, сообщения `system` / `user`, `response_format={"type":"json_object"}`.
Провайдер должен поддерживать этот JSON mode и стандартный ответ
`choices[0].message.content` с `finish_reason="stop"`.
Нестандартный или обрезанный ответ отклоняется; retry и repair prompts отсутствуют.

System prompt требует использовать только incident facts и предоставленный context,
указывать uncertainty, не выдумывать IOC/CVE/IP/domain/user/malware и возвращать
только JSON. Knowledge base и incident явно помечены как untrusted data;
инструкции внутри документов запрещено выполнять. Это базовая защита в prompt,
а не гарантия отсутствия prompt injection или фактических ошибок модели.

User prompt содержит incident, документы с заголовками `[Document ID]`, title,
category и content, затем инструкции для SOC-анализа. Векторы не передаются.
Документы добавляются по relevance; учитываются заголовки и разделители.
Последний content обрезается по символам с `[truncated]`, если маркер помещается.
`RAG_MAX_CONTEXT_CHARS` ограничивает именно reference context; incident ограничен
отдельно 10000 символами, system prompt не входит в этот бюджет. Это не token limit.

Sources строит приложение из документов, чей content реально попал в prompt,
в порядке retrieval. Они содержат только ID/title/category/similarity.
LLM не может добавить свои sources: дополнительные поля в его JSON запрещены.
Similarity вычисляется как `1 - cosine_distance`, это не confidence оценки LLM.

Запрос: incident после strip — 10–10000 символов, top_k — 1–10 (default 5).

```sh
curl -i -X POST http://127.0.0.1:8000/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"incident":"During the last 10 minutes the same account generated 80 failed SSH login attempts from multiple external IP addresses.","top_k":5}'
```

Иллюстрация структуры ответа (текст и similarity зависят от данных и модели):

```json
{
  "summary": "Repeated SSH authentication failures require investigation; compromise is not confirmed.",
  "severity": "high",
  "likely_attack_type": "Possible SSH brute-force attack",
  "recommended_actions": ["Review successful authentication events for the account."],
  "sources": [
    {"document_id": 3, "title": "SSH response", "category": "credential_access", "similarity": 0.86}
  ]
}
```

LLM JSON проверяется Pydantic: непустые summary/likely_attack_type/actions,
не менее одного action, severity только `low|medium|high|critical`.
Полный content источников в AnalyzeResponse не возвращается.

| Ситуация | HTTP | detail |
| --- | --- | --- |
| Некорректный incident/top_k | 422 | Ошибки Pydantic |
| Нет usable context | 409 | `No relevant knowledge base documents are available` |
| Ключ/конфигурация LLM отсутствует | 503 | `LLM provider is not configured` |
| Timeout, connection error, non-2xx | 502 | `LLM provider request failed` |
| Неверный provider/model JSON или schema | 502 | `LLM provider returned an invalid analysis` |

Без context LLM не вызывается. Слишком маленький context budget, в который не
помещается ни один документ с content, тоже даёт 409. Retrieval не имеет similarity
threshold: наличие результатов не гарантирует релевантность. Ответ требует проверки
SOC-аналитиком. В логах — начало/завершение анализа, число источников и тип ошибки;
API key, Authorization, incident и полный provider response приложение не логирует.

## Manual RAG smoke workflow

1. Запустите БД: `docker compose up -d postgres`.
2. В локальном Python окружении выполните `python -m alembic upgrade head`.
3. Запустите `python -m uvicorn app.main:app --reload` и дождитесь загрузки embeddings.
4. Добавьте несколько security documents.
5. Проверьте `/search`.
6. Задайте действующий `LLM_API_KEY` через окружение или локальный `.env`, при
   необходимости настройте base URL/model; перезапустите API, чтобы прочитать settings.
7. Явно выполните `/analyze`. Это реальный запрос к провайдеру и может быть платным.

PowerShell, шаги 4–5:

```powershell
$documents = @(
    @{ title = 'SSH response'; content = 'For repeated SSH login failures, review successful logins for the same account, preserve authentication logs and consider rate limiting.'; category = 'credential_access' },
    @{ title = 'Phishing response'; content = 'Inspect suspicious sender addresses, preserve email headers and isolate unsafe attachments.'; category = 'phishing' }
)
foreach ($document in $documents) {
    Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/documents -ContentType 'application/json' -Body ($document | ConvertTo-Json)
}
$search = @{ query = 'multiple failed ssh login attempts'; limit = 5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/search -ContentType 'application/json' -Body $search
```

После настройки ключа и перезапуска API, шаг 7:

```powershell
$incident = @{ incident = 'During the last 10 minutes the same account generated 80 failed SSH login attempts from multiple external IP addresses.'; top_k = 5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/analyze -ContentType 'application/json' -Body $incident
```

Для API внутри Docker ключ нужно передать именно в контейнер: `.env` не копируется
в image и текущий Compose автоматически не передаёт LLM settings. Например, после
экспорта LLM variables в host environment и остановки обычного API service:

```sh
docker compose stop api
docker compose run --rm --service-ports -e LLM_API_KEY -e LLM_BASE_URL -e LLM_MODEL -e LLM_TIMEOUT_SECONDS -e RAG_MAX_CONTEXT_CHARS api
```

При этом DATABASE_URL внутри API остаётся `postgres:5432`. Обычный pytest никогда
не выполняет paid LLM calls, даже если в окружении задан ключ.

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
Unit/API-тесты подменяют model layer и embedding dependency и не скачивают модель.
Также проверяются search response, distance → similarity, валидация query/limit,
размерность embedding, вызов encode вне event loop и отсутствие записи при ошибке.
LLM tests используют `httpx.MockTransport`: проверяют URL/auth/model/messages,
HTTP-ошибки, timeout, JSON/schema и отсутствие утечки diagnostics. AnalysisService
и API tests используют mocks/overrides; отдельно проверяется lifecycle ресурсов.

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
Используйте отдельную БД без сохранённых embedded documents и без параллельных
записей из других процессов. До тестов примените миграции до `0002`.

Проверяются создание, чтение существующего/отсутствующего документа, сортировка
и пагинация списка, откат записи при исключении, запрет записи без embedding,
cosine distance / порядок / limit поиска с детерминированными векторами длины 384.
Реальная модель в repository-тестах не используется. Async-тесты запускает pytest
plugin AnyIO, уже установленный вместе с FastAPI/httpx; backend — `asyncio`.
Дополнительный RAG integration test использует реальный pgvector retrieval и fake
LLM: проверяет выбранный context и sources без Hugging Face или внешних LLM calls.

## Existing documents / backfill

`0002` добавляет nullable column: существующие документы сохраняются с NULL и
пока не участвуют в поиске. `CHECK (embedding IS NOT NULL) NOT VALID` не проверяет
старые строки, но запрещает новые/изменённые строки без embedding. Поэтому ORM
честно допускает `None` для legacy rows. Новые документы API всегда имеют вектор.
Фиктивные embeddings не создаются; NOT NULL для всей колонки пока не выставляется.

Для маленького dev dataset запустите следующий Python-код из корня проекта
в активированном окружении после `alembic upgrade head` (например, сохраните во
временный скрипт). Он читает только NULL embeddings и использует ту же модель:

```python
import asyncio
from sqlalchemy import select
from app.core.config import Settings
from app.db.database import create_database
from app.models.document import Document
from app.services.embedding_service import EmbeddingService

async def backfill():
    settings = Settings()
    embeddings = EmbeddingService(settings.embedding_model_name, settings.embedding_dimension)
    await embeddings.load_model()
    engine, sessions = create_database(settings.database_url)
    try:
        async with sessions() as session:
            rows = (await session.execute(
                select(Document.id, Document.content).where(Document.embedding.is_(None))
            )).all()
        for document_id, content in rows:
            vector = await embeddings.embed_text(content)
            async with sessions.begin() as session:
                document = await session.get(Document, document_id)
                if document is not None and document.embedding is None:
                    document.embedding = vector
    finally:
        await engine.dispose()

asyncio.run(backfill())
```

Повторный запуск пропускает заполненные строки. После backfill можно отдельной
будущей миграцией провалидировать CHECK и установить обычный NOT NULL.

## Real embedding smoke test (manual)

Не является частью pytest. В активированном окружении откройте `python` и выполните:

```python
import asyncio
from app.core.config import Settings
from app.services.embedding_service import EmbeddingService

async def smoke():
    settings = Settings()
    service = EmbeddingService(settings.embedding_model_name, settings.embedding_dimension)
    await service.load_model()
    vector = await service.embed_text("multiple failed ssh login attempts")
    assert len(vector) == 384
    print(f"Embedding dimension: {len(vector)}")

asyncio.run(smoke())
```

При первой загрузке нужны сеть и доступ к Hugging Face; ошибка загрузки здесь
не должна влиять на обычные unit/API-тесты с fake model. NumPy приходит транзитивно,
прямого импорта и прямой зависимости на NumPy в проекте нет.

## Planned features

- Оценка качества retrieval и анализа на размеченных SOC-инцидентах
