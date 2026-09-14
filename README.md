# Google Sheets to Telegram Userbot

Проект автоматизирует первый контакт с лидами из Google Sheets:

1. Google Sheets Apps Script отправляет новые строки в `POST /webhooks/google-sheets`.
2. FastAPI-приложение проверяет `X-Webhook-Secret`.
3. OpenRouter генерирует короткое приветствие из промпта в `.env`.
4. Telethon-юзербот ищет Telegram-пользователя по номеру и отправляет сообщение.
5. SQLite хранит статус строки, чтобы не отправлять одно и то же сообщение дважды.

Единая пошаговая инструкция по production-запуску через Docker: [docs/SETUP_PIPELINE_RU.md](docs/SETUP_PIPELINE_RU.md).
