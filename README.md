# garmin-proxy

Flask-сервер для получения данных из Garmin Connect. Деплоится на Render.com.

## Эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/sleep` | Сон за вчера |
| GET | `/hrv` | HRV за вчера |
| GET | `/body-battery` | Body Battery за вчера и сегодня |
| GET | `/activities` | Активности за 7 дней |
| GET | `/weekly-stats` | Шаги, калории, стресс за 7 дней |

Все эндпоинты требуют заголовок `X-API-Key: <ваш ключ>`.

---

## Настройка (обязательные шаги)

### Шаг 1 — Получи токены локально

Garmin блокирует авторизацию по логину/паролю с облачных серверов.
Поэтому нужно один раз войти локально и сохранить OAuth-токены.

**Установи зависимости локально:**
```bash
pip install garminconnect
```

**Запусти скрипт** (Git Bash / macOS / Linux):
```bash
GARMIN_EMAIL=your@email.com GARMIN_PASSWORD=yourpassword python get_tokens.py
```

**Windows PowerShell:**
```powershell
$env:GARMIN_EMAIL="your@email.com"
$env:GARMIN_PASSWORD="yourpassword"
python get_tokens.py
```

Скрипт выведет содержимое токенов и сохранит их в `tokens.json`.

---

### Шаг 2 — Добавь переменные окружения на Render

В разделе **Environment Variables** добавь:

| Переменная | Значение |
|------------|----------|
| `GARMIN_TOKENS` | Вставь содержимое файла `tokens.json` (всю строку целиком) |
| `API_KEY` | Любая секретная строка, например `myhealthkey2026` |

> `GARMIN_EMAIL` и `GARMIN_PASSWORD` на Render **не нужны**.

---

### Шаг 3 — Задеплой и проверь

После деплоя проверь через браузер или Postman:
```
GET https://garmin-proxy-xxxx.onrender.com/sleep
Headers: X-API-Key: myhealthkey2026
```

---

## Обновление токенов

Токены Garmin живут долго, но если получишь ошибку 401 от Garmin — просто
запусти `get_tokens.py` снова локально и обнови `GARMIN_TOKENS` на Render.
