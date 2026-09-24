# Развертка Telegram + WhatsApp

Минимальная production-инструкция для запуска проекта через Docker Compose. Nginx работает на сервере отдельно от Docker и проксирует HTTPS-запросы в FastAPI.

## 1. Подготовьте данные

Нужны:

- сервер с доменом;
- `git`, `docker`, `docker compose`;
- Telegram-аккаунт для userbot;
- `api_id` и `api_hash` с https://my.telegram.org/apps;
- рабочий WhatsApp-номер;
- API-ключ OpenRouter;
- Google Sheet с первой строкой-заголовками и колонкой телефона.

Пишите только лидам, которые дали согласие на связь. WhatsApp работает через неофициальную автоматизацию WhatsApp Web, поэтому используйте отдельный рабочий номер и не запускайте массовую рассылку.

## 2. Скачайте проект

```bash
git clone https://github.com/haldaniko/tg-wa-automatization.git
cd tg-wa-automatization
```

## 3. Создайте `.env`

```bash
cp .env.sample .env
openssl rand -hex 32
openssl rand -hex 32
nano .env
```

Заполните значения. Первую случайную строку используйте для `WEBHOOK_SECRET`, вторую - для `WHATSAPP_API_TOKEN`:

```text
WEBHOOK_SECRET=длинная-случайная-строка
APP_HOST=0.0.0.0
APP_PORT=8000
DATABASE_PATH=/app/data/leads.sqlite3
DRY_RUN=false

LEAD_PHONE_FIELD=Телефон

TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_SESSION_NAME=/app/sessions/userbot
TELEGRAM_SESSION_STRING=
TELEGRAM_DELETE_IMPORTED_CONTACT=false

WHATSAPP_API_TOKEN=другая-длинная-случайная-строка
WHATSAPP_SERVICE_URL=http://whatsapp:3000
WHATSAPP_CLIENT_ID=leads
WHATSAPP_SESSION_PATH=/app/session

OPENROUTER_API_KEY=sk-or-v1-your-key
OPENROUTER_MODEL=~openai/gpt-sol-latest
OPENROUTER_TEMPERATURE=0.7
OPENROUTER_MAX_TOKENS=220
OPENROUTER_HTTP_REFERER=https://your-domain.example
OPENROUTER_APP_TITLE=Lead Messenger Bot

OPENROUTER_SYSTEM_PROMPT=You write short, warm, compliant first-touch sales messages. Do not invent facts. Do not mention that you are AI.
OPENROUTER_USER_PROMPT=Сгенерируй короткое приветственное сообщение в мессенджере для нового лида. Пиши на языке лида, если он понятен из данных. Не добавляй вымышленных скидок, сроков или обещаний. Данные лида: {lead_json}
```

`LEAD_PHONE_FIELD` должен совпадать с названием колонки телефона в Google Sheets. Телефоны указывайте в международном формате: `+491701234567` или `491701234567`.

Если для WhatsApp нужны отдельные правила, можно дополнительно задать `OPENROUTER_WHATSAPP_SYSTEM_PROMPT` и `OPENROUTER_WHATSAPP_USER_PROMPT`. Если их нет, WhatsApp использует общие `OPENROUTER_SYSTEM_PROMPT` и `OPENROUTER_USER_PROMPT`.

## 4. Авторизуйте Telegram

```bash
docker compose --profile whatsapp build
docker compose --profile whatsapp run --rm app python scripts/login_telegram.py
```

Введите номер Telegram-аккаунта, код из Telegram и 2FA-пароль, если он включен. Сессия сохранится в volume `telegram_sessions`.

## 5. Запустите проект

```bash
docker compose --profile whatsapp up -d
docker compose --profile whatsapp ps
curl http://127.0.0.1:8017/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

## 6. Авторизуйте WhatsApp

```bash
docker compose --profile whatsapp logs -f whatsapp
```

Отсканируйте QR-код в WhatsApp: `Настройки` -> `Связанные устройства` -> `Привязка устройства`.

После успешного входа в логах появится:

```text
WhatsApp bridge is ready.
```

Остановите просмотр логов через `Ctrl+C`. Контейнер продолжит работать. Сессия сохранится в volume `whatsapp_sessions`.

Проверка:

```bash
docker compose --profile whatsapp exec whatsapp node -e "fetch('http://127.0.0.1:3000/health').then(r => r.text()).then(console.log)"
```

В ответе должно быть `"status":"ready"` и `"ready":true`.

## 7. Настройте Nginx и HTTPS

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
sudo nano /etc/nginx/sites-available/tg-wa-automatization
```

Конфиг:

```nginx
server {
    listen 80;
    server_name your-domain.example;

    location = /webhooks/google-sheets {
        proxy_pass http://127.0.0.1:8017;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location = /webhooks/google-sheets/whatsapp {
        proxy_pass http://127.0.0.1:8017;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;
    }

    location / {
        proxy_pass http://127.0.0.1:8017;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/tg-wa-automatization /etc/nginx/sites-enabled/tg-wa-automatization
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.example
curl https://your-domain.example/health
```

Webhook URLs:

```text
https://your-domain.example/webhooks/google-sheets
https://your-domain.example/webhooks/google-sheets/whatsapp
```

## 8. Настройте Google Sheets

1. Откройте Google Sheets с лидами.
2. Перейдите в `Extensions` -> `Apps Script`.
3. Вставьте код из `google_apps_script/Code.gs`.
4. Откройте `Project Settings` -> `Script properties`.
5. Добавьте свойства:

```text
WEBHOOK_URL=https://your-domain.example/webhooks/google-sheets
WHATSAPP_WEBHOOK_URL=https://your-domain.example/webhooks/google-sheets/whatsapp
WEBHOOK_SECRET=то-же-значение-что-в-.env
SHEET_NAME=Leads
STATUS_COLUMN_NAME=Webhook status
WHATSAPP_STATUS_COLUMN_NAME=WhatsApp status
START_ROW=2
```

Если нужно использовать активный лист, не задавайте `SHEET_NAME`.

6. Выберите функцию `installLeadWebhookTriggers`.
7. Нажмите `Run` и подтвердите доступы.

Скрипт создаст две колонки статусов и будет отправлять каждую новую строку в Telegram и WhatsApp. Для повторной отправки очистите статус нужного канала.

## 9. Проверьте отправку

Добавьте новую строку с тестовым номером, владелец которого согласен получить сообщение:

```text
Имя | Телефон | Источник | Комментарий
Ivan | +15551234567 | Instagram | interested in demo
```

Проверьте:

- в `Webhook status` появился `OK ...`;
- в `WhatsApp status` появился `OK ...`;
- сообщения ушли в Telegram и WhatsApp;
- в логах нет ошибок.

```bash
docker compose --profile whatsapp logs --tail=200 app whatsapp
```

## 10. Обновление

```bash
git pull
docker compose --profile whatsapp build
docker compose --profile whatsapp up -d
```

Volumes `lead_data`, `telegram_sessions` и `whatsapp_sessions` сохраняются между пересборками. Не используйте `docker compose down -v`, если не хотите удалить базу статусов и обе сессии.

## 11. Диагностика

- `401 Invalid webhook secret` - `WEBHOOK_SECRET` отличается в `.env` и Apps Script.
- `422 Phone number was not found` - неверный `LEAD_PHONE_FIELD` или пустая колонка телефона.
- `404 Telegram user was not found` - пользователь не найден по номеру или скрыт настройками приватности.
- `503 WhatsApp is not ready` - откройте логи `whatsapp` и отсканируйте новый QR-код.
- `404 No WhatsApp account was found` - на номере нет WhatsApp или номер неверен.
- `401 Invalid API token` - `WHATSAPP_API_TOKEN` не совпадает в `app` и `whatsapp`; выполните `docker compose --profile whatsapp up -d --force-recreate`.
- `502 OpenRouter HTTP ...` - проблема с ключом, моделью, лимитами или балансом OpenRouter.
- `ERR ...` в таблице - исправьте причину и очистите статус нужного канала.

Остановить сервисы:

```bash
docker compose --profile whatsapp down
```
