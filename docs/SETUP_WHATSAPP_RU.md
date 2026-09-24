# Подключение WhatsApp после Telegram

Эта инструкция продолжает `SETUP_PIPELINE_RU.md`. Выполняйте её после того, как Telegram-автоматизация уже запущена и новые лиды успешно обрабатываются.

WhatsApp работает отдельным Docker-сервисом на базе `whatsapp-web.js`. Он авторизуется через QR-код как связанное устройство, хранит сессию в Docker volume и доступен только основному приложению внутри Docker-сети. Nginx остаётся на сервере вне Docker.

Важно: `whatsapp-web.js` использует неофициальную автоматизацию WhatsApp Web. WhatsApp не гарантирует её стабильность, а за массовые или нежелательные сообщения аккаунт может быть ограничен. Используйте отдельный рабочий номер, пишите только лидам с согласием на связь и не запускайте массовую рассылку.

## 1. Обновите проект

На сервере откройте каталог проекта и получите новую версию:

```bash
cd ~/websites/tg-wa-automatization
git pull
```

## 2. Добавьте настройки WhatsApp в `.env`

Сгенерируйте отдельный внутренний токен:

```bash
openssl rand -hex 32
```

Откройте `.env`:

```bash
nano .env
```

Добавьте настройки, подставив сгенерированный токен:

```text
WHATSAPP_API_TOKEN=вставьте-сгенерированный-токен
WHATSAPP_SERVICE_URL=http://whatsapp:3000
WHATSAPP_CLIENT_ID=leads
WHATSAPP_SESSION_PATH=/app/session

OPENROUTER_WHATSAPP_SYSTEM_PROMPT=You write short, warm, compliant first-touch WhatsApp messages. Do not invent facts. Do not mention that you are AI.
OPENROUTER_WHATSAPP_USER_PROMPT=Сгенерируй короткое приветственное сообщение в WhatsApp для нового лида. Цель: поздороваться, представиться и предложить обсудить детали. Пиши на языке лида, если он понятен из данных. Не добавляй вымышленных скидок, сроков или обещаний. Данные лида: {lead_json}
```

`WHATSAPP_API_TOKEN` защищает внутренний HTTP-интерфейс WhatsApp-сервиса. Он должен быть длинным, случайным и отличаться от `WEBHOOK_SECRET`.

В prompt можно использовать `{lead_json}`, `{payload_json}`, `{phone}`, `{sheet_name}`, `{spreadsheet_id}` и `{row_number}`.

## 3. Соберите и запустите WhatsApp-сервис

WhatsApp вынесен в опциональный Compose-профиль, поэтому запускайте проект с профилем `whatsapp`:

```bash
docker compose --profile whatsapp build
docker compose --profile whatsapp up -d
```

Проверьте контейнеры:

```bash
docker compose --profile whatsapp ps
```

Основное приложение `app` должно быть `healthy`. WhatsApp-контейнер может быть `healthy` ещё до авторизации: его реальный статус проверяется на следующем шаге.

## 4. Привяжите WhatsApp по QR-коду

Откройте поток логов:

```bash
docker compose --profile whatsapp logs -f whatsapp
```

В терминале появится QR-код. На телефоне откройте WhatsApp, перейдите в `Настройки` -> `Связанные устройства` -> `Привязка устройства` и отсканируйте его.

После успешного входа в логах появится:

```text
WhatsApp bridge is ready.
```

Завершите просмотр логов сочетанием `Ctrl+C`. Контейнер продолжит работать. Сессия хранится в volume `whatsapp_sessions`, поэтому при обычном обновлении повторный QR-код не понадобится.

Проверить внутренний статус можно так:

```bash
docker compose --profile whatsapp exec whatsapp node -e "fetch('http://127.0.0.1:3000/health').then(r => r.text()).then(console.log)"
```

Ожидаемый результат содержит `"status":"ready"` и `"ready":true`.

## 5. Расширьте существующий Nginx-конфиг

Откройте уже работающий конфиг сайта:

```bash
sudo nano /etc/nginx/sites-available/denisprotarget
```

В существующий HTTPS-блок `server`, рядом с Telegram webhook и до общего `location /`, добавьте второй точный маршрут:

В `proxy_pass` укажите тот же локальный порт, который уже используется в рабочем Telegram-маршруте. Ниже показан порт `8000`; если Telegram у вас проксируется на `127.0.0.1:8017`, здесь также должен быть `8017`.

```nginx
location = /webhooks/google-sheets/whatsapp {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_connect_timeout 30s;
    proxy_send_timeout 60s;
    proxy_read_timeout 90s;
}
```

Итоговый HTTPS-блок должен содержать оба маршрута:

```nginx
location = /webhooks/google-sheets {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 60s;
}

location = /webhooks/google-sheets/whatsapp {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 90s;
}

location / {
    proxy_pass http://127.0.0.1:8002;
    # Остальные настройки существующего Django-сайта оставьте без изменений.
}
```

Проверьте и примените конфиг:

```bash
sudo nginx -t
sudo systemctl reload nginx
curl -i https://denisprotarget.com/webhooks/google-sheets/whatsapp
```

Для `GET` ожидается `405 Method Not Allowed`: это означает, что Nginx направил запрос в FastAPI, а endpoint ожидает `POST`. Ответ Django или `502 Bad Gateway` означает неправильную маршрутизацию.

## 6. Обновите Google Apps Script без рассылки старым лидам

Откройте таблицу, перейдите в `Extensions` -> `Apps Script` и замените код содержимым обновлённого `google_apps_script/Code.gs`.

Сначала защитите существующие строки от повторной рассылки:

1. Не добавляйте пока свойство `WHATSAPP_WEBHOOK_URL`.
2. В редакторе Apps Script выберите функцию `markExistingRowsSkippedForWhatsApp`.
3. Нажмите `Run` и подтвердите доступ.
4. Убедитесь, что появилась колонка `WhatsApp status`, а старые строки получили статус `SKIP existing ...`.

Если старых лидов в таблице нет, этот шаг всё равно безопасен. Не пропускайте его в рабочей таблице с историей: иначе WhatsApp-обработка начнётся со старых строк с пустым статусом.

Теперь откройте `Project Settings` -> `Script properties` и добавьте:

```text
WHATSAPP_WEBHOOK_URL=https://denisprotarget.com/webhooks/google-sheets/whatsapp
WHATSAPP_STATUS_COLUMN_NAME=WhatsApp status
```

Существующие свойства `WEBHOOK_URL`, `WEBHOOK_SECRET`, `SHEET_NAME`, `STATUS_COLUMN_NAME` и `START_ROW` оставьте без изменений.

Снова выберите `installLeadWebhookTriggers` и нажмите `Run`. Функция удалит старые триггеры `syncNewLeads` и создаст их заново.

Теперь для каждой новой строки скрипт независимо вызывает два endpoint:

- `Webhook status` показывает результат Telegram;
- `WhatsApp status` показывает результат WhatsApp.

Ошибка одного канала не вызывает повторную отправку в другом. Для ручного повтора очистите только статус нужного канала.

## 7. Проверьте новый пайплайн

Добавьте новую строку с вашим тестовым номером WhatsApp в международном формате: `+380...` или `380...`. Используйте номер, владелец которого согласен получить тестовое сообщение.

В течение минуты проверьте:

- в `Webhook status` появился `OK ...` для Telegram;
- в `WhatsApp status` появился `OK ...` для WhatsApp;
- сообщение пришло в WhatsApp;
- в логах нет ошибки отправки.

Логи обоих сервисов:

```bash
docker compose --profile whatsapp logs --tail=200 app whatsapp
```

## 8. Обновление и диагностика

Для последующих обновлений используйте:

```bash
git pull
docker compose --profile whatsapp build
docker compose --profile whatsapp up -d
```

Частые ошибки:

- `503 WhatsApp is not ready` — откройте `docker compose --profile whatsapp logs -f whatsapp` и отсканируйте новый QR-код.
- `404 No WhatsApp account was found` — на указанном номере нет WhatsApp либо номер неверен.
- `401 Invalid API token` — значения `WHATSAPP_API_TOKEN` в `app` и `whatsapp` различаются; пересоздайте оба контейнера командой `docker compose --profile whatsapp up -d --force-recreate`.
- `502 WhatsApp service request failed` — WhatsApp-контейнер не запущен или недоступен; проверьте `docker compose --profile whatsapp ps`.
- `ERR ...` в таблице — исправьте причину и очистите только ячейку `WhatsApp status`, чтобы повторить WhatsApp-отправку.
- QR-код появляется после каждого перезапуска — проверьте наличие volume командой `docker volume ls` и не используйте `docker compose down -v`.

Команда `docker compose down` сохраняет сессии. Команда `docker compose down -v` удалит базу дедупликации, Telegram-сессию и WhatsApp-сессию, после чего потребуется повторная авторизация.
