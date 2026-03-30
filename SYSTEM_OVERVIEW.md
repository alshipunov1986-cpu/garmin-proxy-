# Garmin Health Proxy — Техническое описание системы

> Дата: 2026-03-30 | Версия: актуальная

---

## 1. АРХИТЕКТУРА СИСТЕМЫ

### Схема потока данных

```
┌─────────────────┐
│  Garmin Connect │  (облако Garmin)
│  (API серверы)  │
└────────┬────────┘
         │ HTTPS / OAuth2 Bearer token
         │ библиотека garminconnect (Python)
         ▼
┌─────────────────────────────────────────────────────┐
│  Flask-прокси  (garmin-proxy)                       │
│                                                     │
│  💻 ОСНОВНОЙ: Локально (Lenovo ноутбук)             │
│  URL: http://localhost:5001                         │
│  URL: https://lenovo-15.tail1309d4.ts.net (Tailscale│
│       Funnel — публичный HTTPS, стабильный URL)     │
│                                                     │
│  🌐 РЕЗЕРВНЫЙ: Render.com                           │
│  URL: https://garmin-proxy-nuw1.onrender.com        │
│  (Garmin блокирует API с Render IP — не для данных) │
│  (UptimeRobot пингует каждые 5 мин — не засыпает)   │
└──┬──────────────────┬─────────────────┬────────────┘
   │                  │                 │
   │ /all-today       │ /sheets/save-day│ /food/*
   │ /sheets/history  │                 │
   ▼                  ▼                 ▼
┌──────────┐   ┌─────────────────┐  ┌─────────────────┐
│   n8n    │   │  Google Sheets  │  │  Food PWA       │
│ (cloud)  │   │  (база данных)  │  │  (телефон)      │
│alj.app.  │   │  30+ дней       │  │  Open Food Facts│
│n8n.cloud │   │  истории        │  │                 │
└────┬─────┘   └─────────────────┘  └─────────────────┘
     │
     │ Claude API (Anthropic)
     ▼
┌──────────────────┐
│  Claude Haiku /  │
│  Sonnet          │
│  Анализ данных   │
└────────┬─────────┘
         │ Telegram Bot API
         ▼
┌──────────────────┐
│  Telegram        │
│  (уведомления)   │
└──────────────────┘
```

### Где хостится каждый компонент

| Компонент | Хостинг | URL / расположение |
|-----------|---------|-------------------|
| Flask-прокси (ОСНОВНОЙ) | **Lenovo ноутбук** | `https://lenovo-15.tail1309d4.ts.net` (Tailscale Funnel) |
| Flask-прокси (резервный) | **Render.com** | `https://garmin-proxy-nuw1.onrender.com` (Garmin блокирует IP) |
| Flask-прокси (local) | **Lenovo ноутбук** | `http://localhost:5001` |
| Tailscale Funnel | **Lenovo ноутбук** | `https://lenovo-15.tail1309d4.ts.net` (стабильный URL) |
| UptimeRobot | **Облако** | Пингует Render каждые 5 мин, status: `stats.uptimerobot.com/nEequzkBjZ` |
| n8n воркфлоу | **n8n Cloud** | `https://alj.app.n8n.cloud` |
| Google Sheets | **Google Drive** | ID: `1bGEHnrvpCL6C_lwayP55W3oggNE4CKZQONOSeJLDCEc` |
| Garmin Connect | **Облако Garmin** | `connectapi.garmin.com` |
| Telegram Bot | **Telegram** | через Bot API |

### Авторизация в Garmin Connect

- **Библиотека**: `garminconnect==0.2.40` (Python), использует `garth` под капотом
- **Метод**: OAuth 2.0 с Bearer-токенами (не логин/пароль напрямую)
- **Токены**: base64-строка, внутри JSON-массив `[oauth1_dict, oauth2_dict]`
- **Хранение локально**: файл `GARMIN_TOKENS.txt` (в `.gitignore`)
- **Хранение на Render**: переменная окружения `GARMIN_TOKENS`
- **Хранение garth**: папка `.garth/` — `oauth1_token.json`, `oauth2_token.json`
- **Срок жизни**: access token ~25 часов, refresh token ~30 дней. `garth` обновляет автоматически при API-вызове.
- **Инициализация**: `client.garth.loads(GARMIN_TOKENS)` → восстанавливает сессию без ввода пароля
- **Важная особенность**: `client.display_name` берётся из `garth.profile` (нужен некоторым API-методам)
- **ВАЖНО**: `.garth/oauth2_token.json` требует **целочисленные** `expires_at` и `refresh_token_expires_at` (не float!)
- **ВАЖНО**: Garmin блокирует API-запросы с Render IP (AWS datacenter). Основной путь — через Tailscale Funnel (домашний IP).

---

## 2. ВСЕ ENDPOINTS ПРОКСИ (app.py)

### Авторизация

Большинство эндпоинтов требуют заголовок:
```
X-API-Key: myhealthkey2026
```
Эндпоинты без авторизации: `/`, `/fatsecret/update`, `/fatsecret/update-form`, `/fatsecret/auth/start`, `/fatsecret/auth/callback`, `/food`, `/food/search`, `/food/cards`, `/food/diary`, `/food/diary/delete`

---

### Garmin Connect — данные за день

| Метод | Эндпоинт | Параметры | Возвращает |
|-------|----------|-----------|-----------|
| GET | `/` | — | Список всех эндпоинтов |
| GET | `/sleep` | `?date=YYYY-MM-DD` (default: сегодня) | Полные данные сна из Garmin (dailySleepDTO + HRV + температура кожи) |
| GET | `/hrv` | `?date=YYYY-MM-DD` (default: сегодня) | HRV данные: ночное среднее, 5-мин максимум, недельная норма |
| GET | `/body-battery` | `?start=`, `?end=` (default: вчера–сегодня) | Сырые данные Body Battery за период |
| GET | `/activities` | `?start=`, `?end=`, `?limit=10` | Список тренировок с типом, длительностью, HR, калориями |
| GET | `/stats` | `?date=YYYY-MM-DD` (default: вчера) | Дневная статистика: шаги, калории, стресс, HR покоя, этажи |
| GET | `/steps` | `?date=YYYY-MM-DD` (default: сегодня) | Пошаговые данные за день |
| GET | `/stress` | `?date=YYYY-MM-DD` (default: сегодня) | Временной ряд стресса за день |
| GET | `/respiration` | `?date=YYYY-MM-DD` (default: сегодня) | Данные дыхания |
| GET | `/spo2` | `?date=YYYY-MM-DD` (default: сегодня) | Пульсоксиметрия (SpO2) |
| GET | `/heart-rate` | `?date=YYYY-MM-DD` (default: сегодня) | Пульс в течение дня |
| GET | `/weekly-stats` | — | Статистика за последние 7 дней (шаги, калории, стресс, HR) |

> **Особенность Garmin**: сон хранится под датой **пробуждения** (не засыпания). Т.е. чтобы получить сон прошлой ночи — запрашивай с датой **сегодня**.

---

### Сводный эндпоинт

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/all-today` | **Главный эндпоинт для n8n.** Возвращает одним запросом: сон, HRV, дневную статистику, body battery (с `current_level` и `net_used_since_wake`), стресс, дыхание, SpO2, последние 3 активности, данные питания из `fatsecret_diary.json` |

**Структура ответа `/all-today`:**
```json
{
  "sleep": { "score": 72, "duration_seconds": 27180, "deep_seconds": 4320,
             "rem_seconds": 5400, "avg_overnight_hrv": 48, "avg_skin_temp_deviation_c": 0.1 },
  "hrv": { "weekly_avg": 52, "last_night_avg": 48, "status": "BALANCED" },
  "daily_stats": { "steps": 8240, "active_calories": 420, "resting_hr": 58,
                   "resting_hr_7day_avg": 60, "avg_stress": 28, "max_stress": 65,
                   "body_battery_wake": 85 },
  "body_battery": { "charged": 42, "drained": 38, "current_level": 72,
                    "net_used_since_wake": 13 },
  "recent_activities": [{ "name": "Running", "type": "running", "avg_hr": 145 }],
  "nutrition": { "date": "2026-03-29", "total": {"calories": 1840, "protein": 142} }
}
```

---

### FatSecret — питание

| Метод | Эндпоинт | Auth | Описание |
|-------|----------|------|----------|
| GET | `/fatsecret/auth/start` | — | Редирект на OAuth2-авторизацию FatSecret |
| GET | `/fatsecret/auth/callback` | — | Callback OAuth2, сохраняет токен в `fatsecret_token.json` |
| GET | `/fatsecret/food-entries` | ✅ | Записи дневника питания за текущий месяц (через FatSecret API) |
| GET | `/fatsecret/search` | ✅ | Поиск в базе продуктов FatSecret `?q=курица` |
| GET | `/fatsecret/sync` | ✅ | Скрапинг дневника с сайта FatSecret (логин по паролю), сохраняет в файл |
| GET | `/fatsecret/diary` | ✅ | Возвращает сохранённые данные из `fatsecret_diary.json` |
| POST | `/fatsecret/update` | — | Принять JSON с данными питания от букмарклета/расширения, сохранить в файл |
| POST | `/fatsecret/update-form` | — | То же, но через HTML form submit (обход CSP) |

---

### Food PWA — дневник питания

| Метод | Эндпоинт | Auth | Описание |
|-------|----------|------|----------|
| GET | `/food` | — | Отдаёт `food_app/index.html` — мобильное PWA-приложение |
| GET | `/food/search` | — | Поиск продуктов в Open Food Facts `?q=гречка`. Возвращает `[{name, brand, per100: {calories, protein, fat, carbs}}]` |
| GET/POST/DELETE | `/food/cards` | — | CRUD личных карточек продуктов. Хранятся в `food_cards.json` |
| GET/POST | `/food/diary` | — | GET: дневник питания за дату. POST: добавить запись `{name, grams, per100}`, пересчитывает итоги |
| POST | `/food/diary/delete` | — | Удалить запись по индексу `{index: N}` |

---

### Google Sheets

| Метод | Эндпоинт | Auth | Описание |
|-------|----------|------|----------|
| GET/POST | `/sheets/save-day` | ✅ | Собирает данные Garmin за `?date=YYYY-MM-DD` и записывает/обновляет строку в Google Sheets |
| GET | `/sheets/history` | ✅ | Возвращает последние N дней из Sheets `?days=30`. Используется n8n для анализа трендов |

---

### Служебные

| Метод | Эндпоинт | Auth | Описание |
|-------|----------|------|----------|
| GET | `/debug-token` | ✅ | Показывает статус Garmin токена: длину, срок истечения, делает тестовый запрос к API |

---

## 3. N8N ВОРКФЛОУ

n8n Cloud: `https://alj.app.n8n.cloud`

### Воркфлоу 1: Morning Report (ID: `EeFTKchjUjXvtAwX`)

**Триггер**: каждый день в 08:30

```
Schedule 08:30
    ↓
Fetch All Health Data
    HTTP GET https://lenovo-15.tail1309d4.ts.net/all-today
    Header: X-API-Key: ***
    ↓
Fetch History
    HTTP GET https://lenovo-15.tail1309d4.ts.net/sheets/history?days=14
    Header: X-API-Key: ***
    ↓
Health Analysis Agent (Claude)
    Модель: Claude Sonnet (claude-chat-model)
    Вход: { today: <данные /all-today>, history: <данные /sheets/history> }
    Промпт: сформировать краткий утренний отчёт (≤10 строк)
            + тренды из history если есть реальный 3+ дневный тренд
    ↓
Send to Telegram
    Бот → личный чат
```

**Системный промпт**: Утренний формат. Шаги вчера, Body Battery, HRV, тренировки за вчера, одна рекомендация на день. Тренды из history только при реальном отклонении 3+ дня.

---

### Воркфлоу 2: Evening Report (ID: `EIShUgQHHJzVkyGr`)

**Триггер**: каждый день в 23:01

```
Daily 23:01 Trigger
    ↓
Fetch Health Data
    HTTP GET https://lenovo-15.tail1309d4.ts.net/all-today
    Header: X-API-Key: ***
    ↓
Fetch History
    HTTP GET https://lenovo-15.tail1309d4.ts.net/sheets/history?days=14
    Header: X-API-Key: ***
    ↓
Health Analysis Agent (Claude)
    Модель: Claude Haiku
    Вход: { today: <данные /all-today>, history: <данные /sheets/history> }
    Промпт: вечерний итог дня с анализом трендов
    ↓
Send to Telegram
    Бот → личный чат
```

**Системный промпт**: Полный вечерний формат. Активность, тренировки, Body Battery, сон прошлой ночи, HRV, советы.
- **Правило сна**: Блок 🛏️ *Сегодня ночью* писать **только** если `sleep_score < 60` или сон `< 5 часов`
- **Правило трендов**: упоминать только при реальном тренде 3+ дня подряд

---

### Воркфлоу 3: Hourly Monitor (ID: `cKjo6HKAaLeNDNLB`)

**Триггер**: каждый час

```
Hourly Trigger
    ↓
Fetch Health Data (retry: 3x, пауза 5 сек)
    HTTP GET https://lenovo-15.tail1309d4.ts.net/all-today
    Header: X-API-Key: ***
    ↓
Health Analysis Agent (Claude)
    ↓
Send to Telegram (если есть что сообщить)
```

**Назначение**: мониторинг в течение дня, алерты при аномалиях.

---

### Воркфлоу 4: Auto Save to Sheets (если настроен)

> Ещё не создан как отдельный воркфлоу. Пока `/sheets/save-day` вызывается вручную через `load_history.py`.

**Рекомендуется добавить**: триггер в 23:45 → HTTP POST `/sheets/save-day` (без параметра, сохранит вчера).

---

### Retry-настройка HTTP-нод (добавлено 2026-03-30)

Все HTTP-ноды во всех воркфлоу настроены с retry:

| Воркфлоу | Ноды с retry | Попыток | Пауза |
|----------|-------------|---------|-------|
| Morning Report | Fetch All Health Data, Fetch History | 3 | 5 сек |
| Evening Report | Sync FatSecret, Fetch Health Data, Fetch History | 3 | 5 сек |
| Hourly Monitor | Fetch Health Data | 3 | 5 сек |

Причина: Tailscale Funnel иногда даёт `connection reset` для внешних серверов n8n Cloud — retry решает проблему нестабильности без дополнительной инфраструктуры.

---

### Передача данных между нодами

- Нода **Fetch History** передаёт данные в `$json.data` → следующая нода берёт `$json.data`
- Агент получает объединённый JSON: `{ today: $('Fetch Health Data').item.json, history: $json.data }`
- История содержит массив объектов с полями таблицы Sheets (на русском: "Дата", "Шаги", "HRV (мс)" и т.д.)

---

## 4. GOOGLE SHEETS

### Таблица

- **ID**: `1bGEHnrvpCL6C_lwayP55W3oggNE4CKZQONOSeJLDCEc`
- **Лист**: `Health Data`
- **Сервис-аккаунт**: `garmin-sheets@elaborate-scope-491716-m2.iam.gserviceaccount.com`
- **Доступ**: таблица расшарена на сервис-аккаунт с правами редактора

### Структура (19 столбцов, колонки A–S)

| Колонка | Поле | Источник |
|---------|------|----------|
| A | Дата | date_str (YYYY-MM-DD) |
| B | Сон (ч) | sleepTimeSeconds / 3600 |
| C | Оценка сна | sleepScores.overall.value |
| D | Глубокий сон (мин) | deepSleepSeconds / 60 |
| E | REM (мин) | remSleepSeconds / 60 |
| F | HRV (мс) | hrvSummary.lastNight |
| G | HRV норма недели | hrvSummary.weeklyAvg |
| H | Пульс покоя | restingHeartRate |
| I | Пульс норма 7д | lastSevenDaysAvgRestingHeartRate |
| J | Body Battery утром | bodyBatteryAtWakeTime |
| K | Body Battery вечером | последнее значение bodyBatteryStatList |
| L | Израсходовано BB | BB утром − BB вечером (>0 = потрачено) |
| M | Стресс средний | averageStressLevel |
| N | Стресс пик | maxStressLevel |
| O | Шаги | totalSteps |
| P | Активные калории | activeKilocalories |
| Q | Температура кожи | avgSkinTempDeviationC |
| R | Тренировки | типы активностей через запятую |
| S | SpO2 | averageSpo2 |

### Как записываются данные

1. **Ручная загрузка истории**: скрипт `load_history.py` — POST `/sheets/save-day?date=YYYY-MM-DD` для каждого дня
2. **Автоматически**: будущий n8n триггер в 23:45 (пока не создан)
3. **Логика записи**: если дата уже есть — обновляет строку (`update`), если нет — добавляет (`append_row`)

### Как читаются данные

- n8n вызывает `GET /sheets/history?days=14` перед каждым отчётом
- Flask возвращает все строки начиная с `(today - N days)`
- Claude видит историю как массив объектов `[{"Дата": "2026-03-15", "Шаги": 9240, ...}, ...]`

---

## 5. УЯЗВИМЫЕ МЕСТА

### Что зависит от локального компьютера (КРИТИЧНО — основной путь через Tailscale!)

| Зависимость | Что произойдёт если ноут выключен/недоступен |
|-------------|---------------------------------------------|
| Flask-прокси | **n8n отчёты НЕ придут** — n8n обращается к Tailscale URL |
| Tailscale Funnel | `lenovo-15.tail1309d4.ts.net` недоступен → n8n не получит данные |
| `GARMIN_TOKENS.txt` | Нужен для запуска прокси. Render тоже имеет копию в env var |
| `fatsecret_diary.json` | Данные питания **не будут в отчёте** — файл локальный |
| `food_cards.json` | Личные карточки продуктов — файл локальный |
| Food PWA `/food/*` | Работает только на локальном прокси |

### Автозагрузка (Windows Services — NSSM)

С 2026-03-30 прокси и Tailscale Funnel работают как **Windows-сервисы через NSSM** (Non-Sucking Service Manager). VBS-скрипты из Startup удалены.

| Сервис | Имя в NSSM | Что делает | Auto-restart |
|--------|-----------|-----------|-------------|
| `GarminProxy` | `GarminProxy` | Flask-прокси на порту 5001 | ✅ через 5 сек |
| `TailscaleFunnel` | `TailscaleFunnel` | `tailscale funnel 5001` | ✅ через 5 сек |

**Управление сервисами** (PowerShell от администратора):
```powershell
# Статус
Get-Service GarminProxy, TailscaleFunnel

# Перезапуск
Restart-Service GarminProxy

# Логи NSSM
nssm status GarminProxy
```

**Установочный скрипт**: `install_services.ps1` / `install_services2.ps1`

**Проверка после kill-теста**: `Stop-Process -Name python -Force` → через 5 сек `Get-Service GarminProxy` показывает `Running` ✅

### Что произойдёт при смене Wi-Fi или IP

- **Tailscale Funnel**: работает на любом Wi-Fi (VPN поверх интернета) ✅
- **n8n**: не зависит от IP, работает всегда ✅
- **UptimeRobot**: пингует Render каждые 5 мин независимо ✅
- **localhost:5001**: недоступен извне, только локально

### Что произойдёт при перезагрузке компьютера

- Flask + Tailscale Funnel **запускаются автоматически** как Windows-сервисы (NSSM, `SERVICE_AUTO_START`) ✅
- Если прокси упадёт — NSSM перезапустит через 5 сек ✅
- Tailscale сервис стартует автоматически (Windows service) ✅
- Render продолжает работать независимо (но Garmin API с него не работает)

### Другие уязвимые места

| Проблема | Описание | Симптом |
|----------|----------|---------|
| **Garmin токен истёк** | Refresh token (30 дней) протух | `/all-today` → 401. Решение: `garth.resume()` + API вызов (если refresh жив) или `get_tokens.py` |
| **Garmin блокирует Render IP** | Datacenter IP заблокирован | Render отдаёт 401 на все Garmin-эндпоинты. Решение: использовать Tailscale (домашний IP) |
| **Render засыпает** | Бесплатный план засыпает через 15 мин | UptimeRobot пингует каждые 5 мин — **решено** |
| **Garmin SSO 429** | Слишком частые попытки логина | Подождать 30-60 мин или использовать AdsPower с итальянским прокси |
| **Ноутбук выключен** | n8n не получит данные через Tailscale | Отчёты не придут до включения ноута |
| **Google Sheets квота** | 60 запросов/мин бесплатно | При быстрой загрузке истории — throttle |
| **FatSecret OAuth** | Refresh token может протухнуть | `/fatsecret/diary` вернёт ошибку auth |

---

## 6. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ

### На Render (production)

| Переменная | Значение | Описание |
|------------|----------|----------|
| `GARMIN_TOKENS` | JSON строка (base64) | OAuth2 токены Garmin Connect. Получаются скриптом `get_tokens.py` |
| `API_KEY` | `myhealthkey2026` | Ключ для защиты эндпоинтов прокси (заголовок `X-API-Key`) |
| `GOOGLE_CREDENTIALS` | JSON сервис-аккаунта | Credentials для Google Sheets API (`elaborate-scope-491716-m2` проект) |
| `FATSECRET_CLIENT_ID` | ID из FatSecret Developer | OAuth2 client_id для FatSecret API |
| `FATSECRET_CLIENT_SECRET` | Secret из FatSecret Developer | OAuth2 client_secret для FatSecret API |
| `FATSECRET_USER` | email аккаунта FatSecret | Для scraping через `_fs_scrape()` |
| `FATSECRET_PASS` | пароль FatSecret | Для scraping через `_fs_scrape()` |
| `PYTHON_VERSION` | `3.11.11` | Версия Python на Render |

### Локально (start-local.bat)

| Переменная | Источник | Описание |
|------------|----------|----------|
| `GARMIN_TOKENS` | читается из `GARMIN_TOKENS.txt` | Токены, обновляются вручную при протухании |
| `API_KEY` | захардкожен в `.bat` | `myhealthkey2026` |
| `PORT` | захардкожен в `.bat` | `5001` |

### Файлы с секретами (локальные, в .gitignore)

| Файл | Содержит |
|------|----------|
| `GARMIN_TOKENS.txt` | Garmin OAuth токены |
| `google_credentials.json` | Google сервис-аккаунт JSON key |
| `tokens.json` | Дополнительные OAuth токены (garth) |
| `fatsecret_token.json` | FatSecret OAuth2 access+refresh токены |
| `elaborate-scope-491716-m2-c177bcb966ca.json` | Старый вариант google credentials |

---

## 7. КАК ВОССТАНОВИТЬ ЕСЛИ ЧТО-ТО СЛОМАЛОСЬ

### 🔴 Garmin API не работает (401 / нет данных)

```
1. Проверить: curl https://lenovo-15.tail1309d4.ts.net/all-today -H "X-API-Key: myhealthkey2026"

2. Если 401 с Tailscale (домашний IP):
   a. Проверить refresh token: посмотреть .garth/oauth2_token.json → refresh_token_expires_at
   b. Если refresh token жив (< 30 дней):
      - Исправить float→int в .garth/oauth2_token.json (expires_at, refresh_token_expires_at)
      - Запустить: python -c "import garth; garth.resume('.garth'); from garminconnect import Garmin; c=Garmin(); c.garth.loads(c.garth.dumps())"
      - garth автоматически обновит access token при API-вызове
   c. Если refresh token тоже истёк:
      - python get_tokens.py (если не 429)
      - Или через AdsPower: python get_tokens_adspower.py
   d. Скопировать garth.dumps() → GARMIN_TOKENS.txt и на Render

3. Если 401 только с Render (а через Tailscale работает):
   → Garmin блокирует Render IP. Это нормально — используй Tailscale.
```

### 🔴 n8n отчёты не приходят

```
1. Открыть https://alj.app.n8n.cloud → проверить последние выполнения
2. Если ошибка в ноде "Fetch Health Data" или "Fetch History":
   → проверить что ноутбук включён и NSSM-сервис работает:
     Get-Service GarminProxy, TailscaleFunnel   (PowerShell)
   → если сервис Stopped — перезапустить:
     Start-Service GarminProxy
     Start-Service TailscaleFunnel
   → проверить прокси напрямую:
     curl https://lenovo-15.tail1309d4.ts.net/ -H "X-API-Key: myhealthkey2026"
   → если прокси работает, но n8n не достучивается — это нестабильность Tailscale Funnel.
     retry (3 попытки по 5 сек) должен решить автоматически.
     Можно принудительно перезапустить Funnel:
     Restart-Service TailscaleFunnel
3. Если ошибка в Claude агенте:
   → проверить API ключ Anthropic в n8n Credentials
4. Если ошибка в Telegram:
   → проверить Bot Token и Chat ID в n8n Credentials
5. n8n URL-ы должны быть: https://lenovo-15.tail1309d4.ts.net/all-today
   (НЕ garmin-proxy-nuw1.onrender.com — Garmin блокирует Render IP)
```

### 🔴 Google Sheets не пишется / не читается

```
1. Проверить что сервис-аккаунт имеет доступ к таблице:
   → открыть таблицу 1bGEHnrvpCL6C_lwayP55W3oggNE4CKZQONOSeJLDCEc
   → Поделиться → убедиться что garmin-sheets@elaborate-scope-491716-m2.iam.gserviceaccount.com есть с правами Editor

2. Проверить env var на Render:
   → GOOGLE_CREDENTIALS должна содержать корректный JSON (не пустую строку)
   → Формат: {"type":"service_account","project_id":"elaborate-scope-491716-m2",...}

3. Тест через curl:
   curl -X POST "https://garmin-proxy-nuw1.onrender.com/sheets/save-day?date=2026-03-28" \
     -H "X-API-Key: myhealthkey2026"
```

### 🔴 Локальный Flask не запускается

```
1. Открыть PowerShell / cmd в D:\Проэкты Клод\garmin-proxy
2. Запустить: start-local.bat
3. Если ошибка "порт занят":
   netstat -ano | findstr :5001
   taskkill /PID <номер> /F
4. Если ошибка импорта:
   .venv\Scripts\pip install -r requirements.txt
5. Проверить что GARMIN_TOKENS.txt существует и не пустой
6. Не забыть запустить Tailscale Funnel:
   tailscale funnel 5001
```

### 🔴 Данные питания не попадают в отчёт

```
Питание хранится в fatsecret_diary.json ЛОКАЛЬНО.
На Render этого файла нет — питание в вечернем отчёте работает только
если запрос идёт к ЛОКАЛЬНОМУ прокси через Tailscale.

Варианты:
a. Использовать Food PWA (/food на локальном сервере) — пишет в тот же файл
b. Использовать букмарклет FatSecret → POST /fatsecret/update на localhost
c. Переключить n8n воркфлоу на Tailscale URL вместо Render для all-today
```

### 🔴 Загрузить историю в Sheets повторно

```
# Локально (нужен запущенный Flask на 5001):
python load_history.py 30    # последние 30 дней
python load_history.py 7     # последние 7 дней

# Или через Render напрямую (медленнее, ~1.2 сек/запрос):
# Изменить BASE_URL в load_history.py на Render URL
```

### 🔴 Обновить n8n воркфлоу

```
1. Открыть https://alj.app.n8n.cloud
2. Найти воркфлоу по имени:
   - Morning: "Daily Garmin Health Analysis to Telegram" (EeFTKchjUjXvtAwX)
   - Evening: "Evening Report" (EIShUgQHHJzVkyGr)
3. Редактировать визуально или через Pinia API в консоли браузера
4. Ctrl+S для сохранения
```

### 🔴 Деплой новой версии на Render

```
# Локально:
git add app.py requirements.txt <другие файлы>
git commit -m "описание"
git push origin master:main    # Render следит за веткой main!

# Render автоматически задеплоит через ~2 мин
# Проверить: Render Dashboard → garmin-proxy → Deploys
```

---

## Дополнительно: файловая структура проекта

```
garmin-proxy/
├── app.py                  # Главный Flask-прокси
├── requirements.txt        # Python зависимости
├── render.yaml             # Конфигурация Render деплоя
├── start-local.bat         # Запуск локального сервера (порт 5001)
├── autostart-proxy.bat     # Обёртка для автозагрузки прокси
├── autostart-funnel.bat    # Обёртка для автозагрузки Tailscale Funnel
├── load_history.py         # Скрипт загрузки 30 дней истории в Sheets
├── get_tokens.py           # Получение Garmin токенов (логин/пароль)
├── get_tokens_adspower.py  # Получение через AdsPower (итальянский прокси)
├── extract_tokens_after_login.py  # Извлечение из браузера через CDP
├── SYSTEM_OVERVIEW.md      # Это описание системы
├── food_app/
│   └── index.html          # Food PWA (мобильное приложение питания)
├── .garth/                 # Garth OAuth токены (oauth1_token.json, oauth2_token.json)
├── food_cards.json         # Личные карточки продуктов (локально)
├── fatsecret_diary.json    # Данные питания (локально, обновляется букмарклетом)
├── GARMIN_TOKENS.txt       # Garmin OAuth токены base64 (gitignored)
├── GARMIN_TOKENS_NEW.txt   # Последний обновлённый токен (gitignored)
├── google_credentials.json # Google сервис-аккаунт (gitignored)
├── fatsecret_token.json    # FatSecret OAuth2 токены (gitignored)
├── tokens.json             # Garth-формат токенов {oauth1_token, oauth2_token}
└── n8n_prompt_patch.md     # Архив правок промптов n8n (применены 2026-03-30)
```
