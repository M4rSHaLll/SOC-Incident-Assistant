# SOC Incident Assistant

Небольшой pet-проект для портфолио на позицию Machine Learning Technology Engineer.
В дальнейшем приложение будет помогать анализировать SOC-инциденты.

Текущее состояние: **foundation / initial API setup**. Реализованы только
FastAPI-приложение, конфигурация и `GET /health`. База данных и ML/LLM-функции
пока отсутствуют.

## Требования

- Python 3.12 и pip.
- Docker — опционально, для запуска в контейнере.

## Локальный запуск

Все команды выполняются из корня репозитория.

```sh
python -m venv .venv
```

Активируйте окружение в PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Или в Linux/macOS:

```sh
source .venv/bin/activate
```

Установите приложение и зависимости для разработки:

```sh
python -m pip install -e ".[dev]"
```

При необходимости скопируйте `.env.example` в `.env` и измените значения.
Без `.env` используются значения по умолчанию:

| Переменная | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `APP_NAME` | `SOC Incident Assistant` | Название приложения в OpenAPI |
| `APP_ENV` | `development` | Имя окружения; пока не меняет поведение приложения |
| `LOG_LEVEL` | `INFO` | Уровень стандартного Python logging |

Переменные окружения имеют приоритет над `.env`. Файл `.env` читается из текущей
рабочей директории. Uvicorn настраивает свои серверные логи отдельно через
параметр `--log-level`.

```sh
python -m uvicorn app.main:app --reload --port 8000
```

Документация API: [Swagger UI](http://127.0.0.1:8000/docs).

## Проверки

```sh
python -m pytest
python -m ruff check .
```

Пример запроса (в PowerShell можно использовать `curl.exe`):

```sh
curl -i http://127.0.0.1:8000/health
```

Ожидаемый ответ: HTTP 200, JSON:

```json
{"status": "ok"}
```

Endpoint подтверждает, что API отвечает; внешние зависимости пока не проверяются.

## Docker

```sh
docker build -t soc-incident-assistant .
docker run --rm -p 8000:8000 soc-incident-assistant
```

Для передачи настроек можно добавить `--env-file .env` перед именем образа
в команде `docker run`. В образ устанавливаются только runtime-зависимости.

## Структура

- `app/main.py` — фабрика `create_app()` и ASGI-приложение `app` для Uvicorn.
- `app/api/health.py` — отдельный router для `/health`.
- `app/core/config.py` — настройки через `pydantic-settings`.
- `tests/test_health.py` — проверка HTTP-статуса и JSON через TestClient.

## Planned features

- PostgreSQL
- pgvector
- embeddings
- semantic search
- LLM-based incident analysis
