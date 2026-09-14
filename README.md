# Google Sheets to Telegram Userbot

Минимальный пайплайн:

1. Google Sheets Apps Script отправляет новые строки в `POST /webhooks/google-sheets`.
2. FastAPI-приложение проверяет `X-Webhook-Secret`.
3. OpenRouter генерирует короткое приветствие из промпта в `.env`.
4. Telethon-юзербот ищет Telegram-пользователя по номеру и отправляет сообщение.
5. SQLite хранит статус строки, чтобы не отправлять одно и то же сообщение дважды.

Подробная настройка: [docs/SETUP_PIPELINE_RU.md](docs/SETUP_PIPELINE_RU.md).
Docker production setup: [docs/DOCKER_PROD_RU.md](docs/DOCKER_PROD_RU.md).

## Быстрый старт

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.sample .env
```

Заполните `.env`, затем авторизуйте Telegram:

```powershell
python scripts/login_telegram.py
```

Запуск сервиса:

```powershell
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Публичный webhook URL должен указывать на:

```text
https://your-domain.example/webhooks/google-sheets
```

## Docker

```powershell
Copy-Item .env.sample .env
docker compose build
docker compose run --rm app python scripts/login_telegram.py
docker compose up -d
```
