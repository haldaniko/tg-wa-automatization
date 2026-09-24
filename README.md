# Google Sheets to Telegram and WhatsApp

Проект автоматизирует первый контакт с лидами из Google Sheets:

1. Google Sheets Apps Script отправляет новые строки в Telegram и WhatsApp webhook endpoints.
2. FastAPI-приложение проверяет `X-Webhook-Secret`.
3. OpenRouter генерирует отдельные приветствия из Telegram и WhatsApp prompts в `.env`.
4. Telethon-юзербот ищет Telegram-пользователя по номеру и отправляет сообщение.
5. WhatsApp Web-сервис отправляет сообщение по тому же международному номеру.
6. SQLite хранит независимые статусы каналов, чтобы не отправлять сообщения дважды.

Единая пошаговая инструкция по production-запуску Telegram и WhatsApp через Docker: [docs/SETUP_PIPELINE_RU.md](docs/SETUP_PIPELINE_RU.md).
