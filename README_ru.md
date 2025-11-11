# MCP-сервер для Битрикс24

Сервер на базе FastAPI, реализующий Model Context Protocol (MCP) и предоставляющий LLM-агентам доступ к данным и действиям в CRM Битрикс24. Сервер преобразует вызовы ресурсов и инструментов MCP в запросы к REST API Битрикс24.

## Возможности

- Ресурсы MCP для получения списков сделок, лидов, контактов, пользователей и задач
- Инструменты MCP для получения сущностей CRM (сделок, лидов, контактов, пользователей, задач)
- Локализованные подсказки для MCP (русский язык), включая structuredContent и предупреждения о пропущенных аргументах
- Ответы инструментов соответствуют CallToolResult (поля `content`, `structuredContent`, `isError`) совместимому с fastmcp
- Единообразные предупреждения и рекомендованные фильтры дат для всех инструментов, позволяющие клиентам автоматически повторять запросы с корректировками
- Настройка через переменные окружения (`.env`)
- Клиент для Битрикс24 на базе HTTPX с поддержкой повторных запросов и backoff
- Асинхронное FastAPI-приложение, готовое к запуску в Docker или локально
- Набор тестов Pytest с заглушками для клиента Битрикс24, работающими в памяти
- Stdio-прокси для Claude Desktop (`mcp_stdio_proxy.py`) с настраиваемым URL и тайм-аутом через переменные окружения

## Подсказки MCP и шпаргалки

- Все тексты подсказок, описания инструментов и готовые payload'ы хранятся в `mcp_server/app/docs/prompts_ru.md`. При изменении файла сервер автоматически подхватывает новые инструкции без правок в коде.
- Ответ `initialize` содержит `structuredInstructions` и `instructionNotes` с примерами: как получить свежие лиды (`order = {"DATE_MODIFY": "DESC"}`) и как задавать диапазоны дат через `>=DATE_CREATE`, `<=DATE_CREATE`.
- MCP-инструменты возвращают `structuredContent` с полным ответом Bitrix24 и предупреждениями. При отсутствии диапазона по дате любой инструмент (`getDeals`, `getLeads`, `getContacts`, `getUsers`, `getTasks`) добавляет сообщение, рекомендуемые фильтры и `suggestedFix`, что позволяет fastmcp/SGR автоматически повторить запрос.
- Доступен ресурс `bitrix24_leads_guide`, который отдаёт шпаргалку с типовыми сценариями (свежие лиды, выборка за сегодня, фильтр по статусу) и правилами комбинирования фильтров.
- Структура `prompts_ru.md` предусматривает локализацию: для новой локали достаточно добавить файл `prompts_<locale>.md` и обновить настройки.

## Формат ответа инструментов (CallToolResult)

- MCP инструменты (`/mcp/tool/call`, JSON-RPC `tools/call`, WebSocket/SSE) возвращают словарь формата:

```json
{
  "content": [
    {"type": "text", "text": "crm/leads: получено 42 записей. Полный ответ в structuredContent.result."}, 
    {"type": "text", "text": "Внимание: Добавьте фильтры диапазона ..."} // опционально
  ],
  "structuredContent": {
    "metadata": {"provider": "bitrix24", "tool": "getLeads", "resource": "crm/leads"},
    "request": {"order": {"DATE_MODIFY": "DESC"}, "filter": {...}},
    "result": {...},            // исходный ответ Битрикс24
    "warnings": [...]           // опционально
  },
  "isError": false
}
```

- Поле `structuredContent` хранит исходный REST payload, поэтому клиенты могут продолжать использовать `metadata` и `result`.
- Предупреждения о пропущенных датах и других критичных аргументах добавляются в `structuredContent.warnings`, а конкретные фильтры и сортировки, которые стоит применить, доступны в `structuredContent.suggestedFix.filters`.
- SSE/WebSocket трансляции используют тот же CallToolResult, что исключает ошибки валидатора fastmcp.

## Структура проекта

```
mcp_server/
  app/
    main.py            # Фабрика приложения FastAPI и управление жизненным циклом
    settings.py        # Настройки Pydantic, загружаемые из окружения
    bitrix_client.py   # Асинхронная обертка HTTP-клиента для REST API Битрикс24
    exceptions.py      # Общие типы исключений для ответов MCP
    dependencies.py    # Зависимости FastAPI для реестров ресурсов/инструментов
    mcp/
      schemas.py       # Модели Pydantic для запросов/ответов MCP
      resources.py     # Реестр ресурсов (crm/deals, crm/leads, ...)
      tools.py         # Реестр инструментов (getDeals, getLeads, ...)
      routes.py        # Эндпоинты MCP (`/mcp/index`, `/mcp/resource/query`, `/mcp/tool/call`)
tests/
  test_resources.py    # Тесты запросов к ресурсам
  test_tools.py        # Тесты вызовов инструментов
  conftest.py          # Общие фикстуры и переопределения настроек
```

## Начало работы

### 1. Настройте окружение

Создайте файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Обновите следующие значения:

- `BITRIX_BASE_URL`: ваш REST эндпоинт Битрикс24 (обычно `<portal>/rest`)
- `BITRIX_TOKEN`: ключ веб-хука или токен доступа OAuth
- `BITRIX_INSTANCE_NAME` (опционально): идентификатор, используемый в метаданных MCP
- `SERVER_*`: при необходимости настройте хост/порт/уровень логирования локального сервера

### 2. Установите зависимости

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### 3. Запустите сервер (локально)

```bash
uvicorn mcp_server.app.main:app --reload
```

Проверка состояния:

```bash
curl http://localhost:8000/healthz
```

Обнаружение MCP:

```bash
curl http://localhost:8000/mcp/index
```

### 4. Запустите тесты

```bash
pytest
```

### 5. Запустите с помощью Docker (опционально)

```bash
docker build -t b24-mcp .
docker run --rm -p 8000:8000 --env-file .env b24-mcp
```

> **Примечание:** Указанный файл `.env` монтируется как переменные окружения внутри контейнера. Перед запуском контейнера убедитесь, что он содержит действительные учетные данные Битрикс24.

## Требования к токену Битрикс24

- Сервер аутентифицирует запросы к Битрикс24 с помощью переменной окружения `BITRIX_TOKEN`.
- Вы можете предоставить:
  - **Ключ входящего веб-хука** (рекомендуется для сервисных интеграций) — создайте его в Битрикс24 и убедитесь, что у него есть доступ к сущностям CRM (сделки, лиды, контакты) и задачам.
  - **Токен доступа OAuth** — убедитесь, что права доступа приложения охватывают как минимум `crm`, `task` и доступ к справочнику пользователей.
- Токен должен оставаться секретным. Храните его только в `.env`, секретах CI или защищенных хранилищах секретов; никогда не добавляйте его в систему контроля версий.
- При смене токена просто обновите значение в `.env` или в используемом источнике секретов и перезапустите MCP-сервер.

## Эндпоинты MCP

| Эндпоинт | Метод | Описание |
|----------|--------|-------------|
| `/mcp/index` | GET | Список доступных ресурсов и инструментов |
| `/mcp/resource/query` | POST | Запрос к ресурсу (`crm/deals`, `crm/leads`, `crm/contacts`, `crm/users`, `crm/tasks`) |
| `/mcp/tool/call` | POST | Выполнение инструмента (`getDeals`, `getLeads`, `getContacts`, `getUsers`, `getTasks`) |

### Пример запроса к ресурсу

```bash
curl -X POST http://localhost:8000/mcp/resource/query \
  -H "Content-Type: application/json" \
  -d '{"resource": "crm/deals", "params": {"select": ["ID", "TITLE"], "filter": {">OPPORTUNITY": 10000}}}'
```

### Пример вызова инструмента

```bash
curl -X POST http://localhost:8000/mcp/tool/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "getDeals", "params": {"select": ["ID", "TITLE"], "filter": {">OPPORTUNITY": 10000}}}'
```

## Замечания по развертыванию

- Используйте Docker или менеджер процессов (systemd, supervisord) для хостинга FastAPI-приложения.
- Убедитесь, что файл `.env` хранится безопасно и не добавлен в систему контроля версий.
- Для производственной среды настройте HTTPS-терминацию и при необходимости добавьте аутентификацию перед MCP-сервером.

## Локальное тестирование WebSocket / CORS

- Во время локальной разработки MCP-сервер принимает WebSocket-соединения по адресу `ws://<host>:<port>/mcp`.
- По умолчанию приложение настроено на прием запросов с origin `http://localhost` и `http://127.0.0.1`.
- Если вы видите ошибку `403 Forbidden` при попытке открыть WebSocket, попробуйте передать явный заголовок `Origin` с вашим клиентом (например, `Origin: http://localhost`) или обновите настройку `allow_origins` в `mcp_server/app/main.py`.

Примеры для тестирования:

```bash
# быстрая проверка индекса по HTTP
curl -sS http://127.0.0.1:8000/mcp/index | jq .

# JSON-RPC handshake через HTTP GET
curl -sS http://127.0.0.1:8000/mcp | jq .

# websocat с явным заголовком Origin (рекомендуется при отладке CORS)
websocat -H 'Origin: http://localhost' ws://127.0.0.1:8000/mcp

# FastMCP CLI (если установлен) для проверки MCP handshake
python -m fastmcp.cli connect ws://127.0.0.1:8000/mcp
```

Примечание: Для производственных развертываний ограничьте `allow_origins` до доверенных доменов и включите TLS (`wss://`).

### Потоковая передача Server-Sent Events (SSE)

Этот MCP-сервер предоставляет простой эндпоинт Server-Sent Events по адресу `/mcp/sse`.
Используйте SSE, когда вам нужен потоковый транспорт от сервера к клиенту. Сервер отправит начальный handshake-payload при подключении и будет транслировать результаты инструментов и ресурсов подключенным SSE-клиентам.

Как это работает:
- Подключите клиент к `GET /mcp/sse` для получения событий (Content-Type `text/event-stream`).
- Отправляйте JSON-RPC запросы через `POST /mcp` (сервер ответит на POST-запрос, а также транслирует результаты подписчикам SSE).
- Для локального тестирования используйте следующие команды:

```bash
# Просмотр HTTP-индекса
curl -sS http://127.0.0.1:8000/mcp/index | jq .

# Подключение к SSE (пример с использованием curl) — примечание: curl не будет красиво отображать непрерывный вывод SSE, но может использоваться для тестирования handshake
curl -v http://127.0.0.1:8000/mcp/sse

# Отправка initialize через HTTP JSON-RPC (вы также должны увидеть этот payload в SSE-соединении)
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | jq .

# Эндпоинт состояния
curl -sS http://127.0.0.1:8000/mcp/health | jq .
```

Для производственной среды замените curl на полноценный SSE-клиент (браузерный EventSource или библиотеку с поддержкой SSE) и защитите соединение с помощью TLS (`https`/`wss`).

## Настройка MCP-клиентов (Claude, Codex, Cursor)

Сервер может использоваться любым клиентом, поддерживающим MCP. Ниже приведены примеры быстрой настройки для наиболее распространенных десктопных клиентов. Укажите пути в соответствии с вашей операционной системой и перезапустите клиент после редактирования конфигурации.

### Claude Desktop

1. Запустите MCP-сервер (`uvicorn mcp_server.app.main:app --reload`).
2. При необходимости задайте переменные окружения для прокси (`MCP_PROXY_BASE_URL`, `MCP_PROXY_TIMEOUT`).
3. Отредактируйте `~/Library/Application Support/Claude/Settings/settings.json` (macOS) или `%AppData%\Claude\Settings\settings.json` (Windows) и добавьте запись в `mcpServers`:

```json
{
  "mcpServers": {
    "b24-mcp": {
      "command": "/Users/gregkisel/Documents/GitHub/b24-mcp/.venv/bin/python",
      "args": [
        "/Users/gregkisel/Documents/GitHub/b24-mcp/mcp_stdio_proxy.py"
      ],
      "cwd": "/Users/gregkisel/Documents/GitHub/b24-mcp",
      "env": {
        "MCP_PROXY_BASE_URL": "http://127.0.0.1:8000",
        "MCP_PROXY_TIMEOUT": "30"
      },
      "autoStart": false
    }
  }
}
```

При необходимости подправьте пути, если репозиторий расположен в другом каталоге или используется иной интерпретатор Python. После сохранения перезапустите Claude Desktop и выберите сервер `b24-mcp`. Stdio-прокси не отправляет ответы на JSON-RPC уведомления без `id`, поэтому всплывающие ошибки исчезнут, а ответы MCP будут передаваться без изменений.

### Codex CLI

1. Запустите MCP-сервер (`uvicorn mcp_server.app.main:app --reload`).
2. Обновите `~/.codex/config.toml` и добавьте запись под `[mcp_servers]`:

```toml
[mcp_servers.bitrix24]
url = "http://127.0.0.1:8000/mcp"
```

3. Перезапустите Codex CLI; выполните `codex mcp list` для проверки соединения.

### Cursor IDE

1. Запустите MCP-сервер локально.
2. Отредактируйте `~/.cursor/mcp.json` (Cursor создает файл автоматически после первого запуска) и добавьте новое определение сервера:

```jsonc
{
  "mcpServers": {
    "bitrix24": {
      "url": "http://127.0.0.1:8000/mcp",
      "timeout": 30000,
      "name": "Bitrix24 MCP"
    }
  }
}
```

После сохранения файла снова откройте Cursor. MCP-сервер Битрикс24 будет доступен в панели MCP и его можно будет включить для каждого проекта.

## Лицензия

Лицензия MIT. Подробности см. в файле [LICENSE](LICENSE).
