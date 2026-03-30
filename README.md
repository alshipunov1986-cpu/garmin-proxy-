# garmin-proxy

Flask-прокси для получения данных из Garmin Connect + FatSecret. Работает локально на ноутбуке, доступен через Tailscale Funnel. Резервный деплой на Render.com.

> Подробная техническая документация: **[SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md)**

---

## Архитектура

```
Garmin Connect API
      ↓
Flask-прокси (localhost:5001)
      ↓
Tailscale Funnel (https://lenovo-15.tail1309d4.ts.net)
      ↓
n8n Cloud → Claude AI → Telegram
      ↓
Google Sheets (история 30+ дней)
```

---

## Эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/` | Список всех эндпоинтов |
| GET | `/all-today` | **Главный**: сон, HRV, Body Battery, стресс, активности, питание |
| GET | `/sleep` | Сон за вчера/дату |
| GET | `/hrv` | HRV данные |
| GET | `/body-battery` | Body Battery |
| GET | `/activities` | Тренировки за 7 дней |
| GET | `/stats` | Дневная статистика |
| GET | `/steps` | Шаги |
| GET | `/stress` | Стресс |
| GET | `/respiration` | Дыхание |
| GET | `/spo2` | SpO2 |
| GET | `/heart-rate` | Пульс за день |
| GET | `/weekly-stats` | Статистика за 7 дней |
| GET/POST | `/sheets/save-day` | Сохранить день в Google Sheets |
| GET | `/sheets/history` | История из Google Sheets `?days=30` |
| GET | `/fatsecret/sync` | Скрапинг дневника FatSecret |
| GET | `/fatsecret/diary` | Данные питания из файла |
| GET | `/food` | Food PWA (мобильный дневник питания) |
| GET | `/debug-token` | Диагностика Garmin токена |

Все эндпоинты (кроме `/food/*` и `/fatsecret/update`) требуют заголовок:
```
X-API-Key: myhealthkey2026
```

---

## Локальный запуск

```bat
start-local.bat
```

Или через NSSM-сервис (автоматически при старте Windows):
```powershell
Get-Service GarminProxy, TailscaleFunnel
Start-Service GarminProxy
```

---

## Автозапуск (NSSM — Windows Service)

С 2026-03-30 прокси и Tailscale Funnel работают как Windows-сервисы:

| Сервис | Действие | Auto-restart |
|--------|---------|-------------|
| `GarminProxy` | Flask на порту 5001 | ✅ через 5 сек |
| `TailscaleFunnel` | `tailscale funnel 5001` | ✅ через 5 сек |

Установка: запустить `install_services.ps1` от администратора.

---

## Обновление токенов Garmin

Если `/all-today` возвращает 401:
```bash
python get_tokens.py
```
Скрипт сохранит токены в `GARMIN_TOKENS.txt`. Скопировать также в переменную `GARMIN_TOKENS` на Render.

---

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `GARMIN_TOKENS` | OAuth2 токены Garmin (из `GARMIN_TOKENS.txt`) |
| `API_KEY` | Ключ защиты эндпоинтов (`myhealthkey2026`) |
| `GOOGLE_CREDENTIALS` | JSON сервис-аккаунта для Google Sheets |
| `FATSECRET_CLIENT_ID` | OAuth client_id FatSecret |
| `FATSECRET_CLIENT_SECRET` | OAuth client_secret FatSecret |
| `FATSECRET_USER` | Email аккаунта FatSecret (для scraping) |
| `FATSECRET_PASS` | Пароль FatSecret (для scraping) |

Локально переменные читаются из `.env` файла (не в git).

---

## n8n Воркфлоу

| Воркфлоу | Триггер | Описание |
|----------|---------|----------|
| Morning Report | 08:30 | Утренний отчёт: сон, HRV, Body Battery, рекомендация |
| Evening Report | 23:01 | Вечерний итог дня + тренды |
| Hourly Monitor | Каждый час | Мониторинг в течение дня |

Все HTTP-ноды настроены с **retry: 3 попытки, пауза 5 сек** (решает нестабильность Tailscale Funnel).
