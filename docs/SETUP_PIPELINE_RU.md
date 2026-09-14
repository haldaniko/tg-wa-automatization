# Пошаговый запуск проекта в Docker

Эта инструкция описывает production-развертку проекта через Docker Compose. Nginx настраивается отдельно на сервере как reverse proxy и не добавляется в Docker.

## 1. Что понадобится

- Сервер с публичным IP и доменом, например `your-domain.example`.
- Установленные `git`, `docker` и `docker compose`.
- Аккаунт Telegram для userbot.
- `api_id` и `api_hash` Telegram с https://my.telegram.org/apps.
- API-ключ OpenRouter.
- Google Sheet с заголовками в первой строке и колонкой телефона.

Важно: отправляйте сообщения только лидам, которые дали согласие на связь. У Telegram есть антиспам-ограничения, а поиск по номеру может не сработать, если у пользователя нет Telegram или приватность скрывает его аккаунт.

## 2. Скачайте проект на сервер

```bash
git clone https://github.com/haldaniko/tg-wa-automatization.git
cd tg-wa-automatization
```

## 3. Создайте `.env`

```bash
cp .env.sample .env
nano .env
```

Заполните основные переменные:

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

OPENROUTER_API_KEY=sk-or-v1-your-key
OPENROUTER_MODEL=~openai/gpt-sol-latest
OPENROUTER_TEMPERATURE=0.7
OPENROUTER_MAX_TOKENS=220
OPENROUTER_HTTP_REFERER=https://your-domain.example
OPENROUTER_APP_TITLE=Lead Telegram Userbot
OPENROUTER_SYSTEM_PROMPT=You write short, warm, compliant first-touch sales messages. Do not invent facts. Do not mention that you are AI.
OPENROUTER_USER_PROMPT=Сгенерируй короткое приветственное сообщение в Telegram для нового лида. Цель: поздороваться, представиться и предложить обсудить детали. Пиши на языке лида, если он понятен из данных. Не добавляй вымышленных скидок, сроков или обещаний. Данные лида: {lead_json}
```

`LEAD_PHONE_FIELD` должен совпадать с названием колонки телефона в Google Sheets. Телефоны должны быть в международном формате: `+491701234567` или `491701234567`. Если `+` отсутствует, приложение добавит его автоматически.

## 4. Соберите Docker-образ

```bash
docker compose build
```

## 5. Авторизуйте Telegram userbot

Перед первым запуском нужно создать Telegram session внутри Docker volume:

```bash
docker compose run --rm app python scripts/login_telegram.py
```

Введите номер телефона Telegram-аккаунта, код из Telegram и 2FA-пароль, если он включен. Session сохранится в volume `telegram_sessions`. Не удаляйте этот volume без необходимости: в нем хранится доступ userbot к аккаунту.

## 6. Запустите приложение

```bash
docker compose up -d
```

Проверьте контейнер:

```bash
docker compose ps
curl http://127.0.0.1:8000/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

Логи:

```bash
docker compose logs -f app
```

## 7. Настройте Nginx как reverse proxy

Nginx должен стоять на сервере снаружи Docker и проксировать HTTPS-трафик на приложение, которое слушает локальный порт `8000`.

Установите Nginx:

```bash
sudo apt update
sudo apt install -y nginx
```

Создайте конфиг:

```bash
sudo nano /etc/nginx/sites-available/tg-wa-automatization
```

Пример конфига без TLS:

```nginx
server {
    listen 80;
    server_name your-domain.example;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 30s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

Активируйте сайт:

```bash
sudo ln -s /etc/nginx/sites-available/tg-wa-automatization /etc/nginx/sites-enabled/tg-wa-automatization
sudo nginx -t
sudo systemctl reload nginx
```

Для Google Apps Script нужен HTTPS. Самый простой вариант - выпустить сертификат через Certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.example
```

После выпуска сертификата проверьте:

```bash
curl https://your-domain.example/health
```

Webhook URL для Google Sheets:

```text
https://your-domain.example/webhooks/google-sheets
```

## 8. Настройте Google Sheets Apps Script

1. Откройте Google Sheets с лидами.
2. Перейдите в `Extensions` -> `Apps Script`.
3. Вставьте код из `google_apps_script/Code.gs`.
4. Откройте `Project Settings` -> `Script properties`.
5. Добавьте свойства:

```text
WEBHOOK_URL=https://your-domain.example/webhooks/google-sheets
WEBHOOK_SECRET=то-же-значение-что-в-.env
SHEET_NAME=Leads
STATUS_COLUMN_NAME=Webhook status
START_ROW=2
```

Если нужно использовать активный лист, не задавайте `SHEET_NAME`.

6. В Apps Script выберите функцию `installLeadWebhookTriggers`.
7. Нажмите `Run` и разрешите доступы.

Скрипт добавит колонку `Webhook status`, если ее нет. Новые строки с пустым статусом будут отправляться в webhook. После попытки скрипт запишет `OK ...` или `ERR ...`. Для повторной отправки строки очистите ее ячейку `Webhook status`.

## 9. Проверьте весь пайплайн

Добавьте тестовую строку в Google Sheets:

```text
Имя | Телефон | Источник | Комментарий
Ivan | +15551234567 | Instagram | interested in demo
```

Проверьте:

- В Google Sheets появился статус `OK ...`.
- В логах контейнера нет ошибок.
- Telegram userbot отправил сообщение найденному пользователю.

Если хотите протестировать генерацию без отправки в Telegram, временно поставьте:

```text
DRY_RUN=true
```

Затем перезапустите контейнер:

```bash
docker compose up -d
```

## 10. Обновление проекта

```bash
git pull
docker compose build
docker compose up -d
```

Volumes `lead_data` и `telegram_sessions` сохранятся между пересборками.

## 11. Диагностика

- `401 Invalid webhook secret` - `WEBHOOK_SECRET` отличается в `.env` и Apps Script.
- `422 Phone number was not found` - неверный `LEAD_PHONE_FIELD` или пустая колонка телефона.
- `422 Invalid phone number` - номер не распознан; используйте международный формат, например `+491701234567` или `491701234567`.
- `404 Telegram user was not found` - пользователь не найден по номеру или скрыт настройками приватности.
- `502 OpenRouter HTTP ...` - проблема с ключом, моделью, лимитами или балансом OpenRouter.
- `Telegram session is not authorized` - повторите шаг авторизации через `docker compose run --rm app python scripts/login_telegram.py`.

Остановить сервис:

```bash
docker compose down
```

Удалять volumes командой `docker compose down -v` стоит только если вы точно хотите стереть базу статусов и Telegram session.
