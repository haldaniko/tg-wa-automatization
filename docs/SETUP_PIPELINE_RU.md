# Настройка пайплайна Google Sheets -> OpenRouter -> Telegram

Документ описывает рабочую схему для этого проекта: новая строка в Google Sheets отправляется в локальное/серверное FastAPI-приложение, приложение генерирует сообщение через OpenRouter и отправляет его через ваш Telegram-аккаунт с помощью Telethon.

## 1. Что понадобится

- Python 3.11+.
- Аккаунт Telegram, который будет работать как юзербот.
- `api_id` и `api_hash` Telegram с https://my.telegram.org/apps.
- API-ключ OpenRouter.
- Google Sheet с заголовками в первой строке и колонкой телефона, например `phone` или `Телефон`.
- Публичный HTTPS-адрес для приложения: VPS, Render/Fly/Railway, Cloudflare Tunnel, ngrok или другой туннель.

Важно: отправляйте сообщения только лидам, которые дали согласие на связь. У Telegram есть лимиты и антиспам-механизмы; массовые холодные рассылки могут привести к ограничениям аккаунта. Поиск по телефону также сработает не всегда: у пользователя должен быть Telegram, и его настройки приватности должны позволять вашему аккаунту найти его по номеру.

## 2. Установка приложения

В папке проекта выполните:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.sample .env
```

Откройте `.env` и заполните значения.

Главные переменные:

- `WEBHOOK_SECRET` - длинная случайная строка. Такое же значение будет в Google Apps Script.
- `LEAD_PHONE_FIELD` - название колонки с телефоном в таблице, например `Телефон`.
- `DEFAULT_PHONE_REGION` - страна для номеров без `+`, например `US`, `DE`.
- `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` - данные приложения Telegram.
- `TELEGRAM_SESSION_NAME` - путь к session-файлу, обычно `sessions/userbot`.
- `OPENROUTER_API_KEY` - ключ OpenRouter.
- `OPENROUTER_MODEL` - модель OpenRouter.
- `OPENROUTER_SYSTEM_PROMPT` и `OPENROUTER_USER_PROMPT` - инструкция для генерации сообщения.

В `OPENROUTER_USER_PROMPT` можно использовать плейсхолдеры:

- `{lead_json}` - данные строки таблицы как JSON.
- `{payload_json}` - весь payload из Google Sheets.
- `{phone}` - нормализованный телефон.
- `{sheet_name}` - имя листа.
- `{row_number}` - номер строки.

## 3. Авторизация Telegram userbot

В активированном виртуальном окружении запустите:

```powershell
python scripts/login_telegram.py
```

Telethon попросит номер телефона, код из Telegram и, если включена двухфакторная защита, пароль. После успешной авторизации появится файл `sessions/userbot.session`. Не публикуйте его: это фактически доступ к вашему Telegram-аккаунту.

## 4. Запуск сервиса

Локально:

```powershell
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Проверка:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Для Google нужен публичный HTTPS URL. Варианты:

- VPS с Nginx/Caddy и TLS.
- Cloudflare Tunnel.
- ngrok для тестов.
- Render/Fly/Railway или похожий хостинг.

Webhook endpoint:

```text
https://your-domain.example/webhooks/google-sheets
```

Для production-запуска в Docker используйте отдельную инструкцию: [DOCKER_PROD_RU.md](DOCKER_PROD_RU.md).

## 5. Настройка Google Sheets

1. Откройте вашу Google таблицу.
2. Выберите `Extensions` -> `Apps Script`.
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

Если нужно использовать активный лист вместо конкретного имени, можно не задавать `SHEET_NAME`.

6. В редакторе Apps Script выберите функцию `installLeadWebhookTriggers` и нажмите `Run`.
7. Разрешите доступы, которые попросит Google.

Скрипт создаст триггеры `onEdit`, `onChange` и таймер раз в минуту. Таймер нужен как страховка: некоторые интеграции добавляют строки не как обычное ручное редактирование. Apps Script отправляет только строки с пустой колонкой `Webhook status`; после попытки ставит `OK ...` или `ERR ...`. Чтобы повторить ошибочную строку, очистите статус в этой строке.

## 6. Формат строки в Google Sheets

Первая строка должна содержать заголовки. Пример:

```text
name | phone | source | comment
Ivan | +15551234567 | Instagram | interested in demo
```

Если колонка называется по-русски:

```text
Имя | Телефон | Источник | Комментарий
```

тогда в `.env` укажите:

```text
LEAD_PHONE_FIELD=Телефон
```

## 7. Тестовый режим

Перед реальной отправкой можно включить:

```text
DRY_RUN=true
```

Сервис будет генерировать сообщение и записывать статус в SQLite, но не отправит его в Telegram. Для повторного реального теста после `DRY_RUN=false` удалите тестовую запись из `data/leads.sqlite3` или добавьте новую строку в таблицу.

## 8. Диагностика

- `401 Invalid webhook secret` - разные `WEBHOOK_SECRET` в `.env` и Apps Script.
- `422 Phone number was not found` - неверный `LEAD_PHONE_FIELD` или пустая ячейка телефона.
- `422 Invalid phone number` - номер не распознан; используйте международный формат `+...`.
- `404 Telegram user was not found` - по этому телефону пользователь Telegram не найден или скрыт приватностью.
- `502 OpenRouter HTTP ...` - ошибка ключа, модели, лимитов или баланса OpenRouter.
- Строка в Sheets получила `ERR ...` - исправьте причину и очистите ячейку `Webhook status`, чтобы отправить повторно.

## 9. Использованные официальные источники

- OpenRouter: chat completions endpoint `https://openrouter.ai/api/v1/chat/completions`, заголовок `Authorization: Bearer ...`, параметры `model`, `messages`, `temperature`, `max_tokens`: https://openrouter.ai/docs/api-reference/chat-completion
- Google Apps Script: installable triggers для Sheets и URL Fetch service: https://developers.google.com/apps-script/guides/triggers/installable и https://developers.google.com/apps-script/reference/url-fetch/url-fetch-app
- Telethon: `TelegramClient` и `send_message`: https://docs.telethon.dev/en/stable/modules/client.html
