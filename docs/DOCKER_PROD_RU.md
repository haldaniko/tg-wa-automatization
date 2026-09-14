# Docker production setup

Этот вариант запускает приложение в контейнере с одним `uvicorn` worker. Для Telegram userbot не стоит включать несколько workers: один аккаунт, один session-файл и одна очередь отправки должны жить в одном процессе.

## 1. Подготовьте `.env`

```bash
cp .env.sample .env
```

Заполните `.env`. Для Docker Compose можно оставить эти значения как в примере ниже, потому что `docker-compose.yml` переопределяет пути внутри контейнера:

```text
DATABASE_PATH=/app/data/leads.sqlite3
TELEGRAM_SESSION_NAME=/app/sessions/userbot
APP_HOST=0.0.0.0
APP_PORT=8000
```

## 2. Соберите образ

```bash
docker compose build
```

## 3. Авторизуйте Telegram session внутри volume

Перед первым запуском сервиса выполните:

```bash
docker compose run --rm app python scripts/login_telegram.py
```

Telethon попросит номер телефона, код из Telegram и 2FA-пароль, если он включен. Session сохранится в Docker volume `telegram_sessions`.

## 4. Запустите сервис

```bash
docker compose up -d
```

Проверка:

```bash
docker compose ps
curl http://localhost:8000/health
```

Логи:

```bash
docker compose logs -f app
```

Остановка:

```bash
docker compose down
```

Команда `docker compose down` не удаляет volumes. Чтобы удалить базу и Telegram session, нужна отдельная команда `docker compose down -v`; используйте ее только если точно хотите стереть состояние.

## 5. Публичный HTTPS endpoint

Google Apps Script должен отправлять запросы на публичный HTTPS URL:

```text
https://your-domain.example/webhooks/google-sheets
```

На VPS обычно ставят reverse proxy перед контейнером:

- Caddy или Nginx слушает `443`.
- Proxy передает трафик на `127.0.0.1:8000`.
- TLS-сертификат выпускается на ваш домен.

Пример Caddyfile:

```caddyfile
your-domain.example {
  reverse_proxy 127.0.0.1:8000
}
```

После этого в Apps Script properties укажите:

```text
WEBHOOK_URL=https://your-domain.example/webhooks/google-sheets
WEBHOOK_SECRET=то-же-значение-что-в-.env
```

## 6. Обновление контейнера

После изменения кода:

```bash
docker compose build
docker compose up -d
```

Volumes `lead_data` и `telegram_sessions` сохранятся.
