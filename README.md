<p align="center">
  <img src="docs/readme/cover.png" alt="Архетипы дизайнерского нарратива — тест для интерьерного отдела IND" width="100%">
</p>

<h1 align="center">IND Interior Bot</h1>

<p align="center">
  Telegram-бот и Mini App для дизайнеров интерьеров IND.<br>
  Два теста: авторский профиль дизайнера и нарратив конкретного проекта.
</p>

<p align="center">
  <a href="https://t.me/IND_interior_bot"><img alt="Telegram" src="https://img.shields.io/badge/Telegram-@IND__interior__bot-111827?logo=telegram&logoColor=white"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-111827?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-111827?logo=fastapi&logoColor=white">
  <img alt="aiogram" src="https://img.shields.io/badge/aiogram-3-111827">
  <img alt="Postgres" src="https://img.shields.io/badge/Postgres-Supabase-111827?logo=postgresql&logoColor=white">
</p>

---

## Что это

Внутренний инструмент интерьерного отдела. Вопросы и архетипы выросли из исследования 65 конкурсных офисных интерьеров и 18 премий: из него вышли 11 типов дизайнерского нарратива.

| | Тест | Что даёт |
|---|---|---|
| **01** | **Какой вы тип дизайнера** — 30 вопросов, ~10 минут | Ведущий архетип с разбором, сильные стороны и слепые зоны, колесо профиля по всем 11 архетипам |
| **02** | **Нарратив для проекта** — 35 вопросов, 10–15 минут | Рабочая гипотеза нарратива по брифу, две альтернативы, тезис и аргумент для заказчика, визуальный язык, риски |

Формулировки второго теста подстраиваются под типологию проекта: офис, ресторан, отель, МОП жилого комплекса, аэропорт, музей, спортивный комплекс. Незаконченный тест продолжается с того же вопроса, все результаты лежат в истории.

<p align="center">
  <img src="docs/readme/start.png" width="22%" alt="Главный экран">&nbsp;
  <img src="docs/readme/question.png" width="22%" alt="Вопрос">&nbsp;
  <img src="docs/readme/result.png" width="22%" alt="Результат">&nbsp;
  <img src="docs/readme/history.png" width="22%" alt="История">
</p>

## Архитектура

```mermaid
flowchart LR
    U["Дизайнер<br>в Telegram"] -->|Mini App| P["GitHub Pages<br>webapp/"]
    P -->|"/api/*"| X["Прокси Deno Deploy<br>proxy/main.ts"]
    X --> V["Vercel<br>FastAPI · api/index.py"]
    T["Telegram"] -->|webhook| V
    V --> S[("Supabase Postgres<br>схема interior")]
    G["GitHub Actions<br>keepalive"] -.->|"раз в день /health"| V
```

- **Фронт** — статический Mini App в `webapp/`, публикуется на GitHub Pages workflow-ом `pages.yml` при пуше в `main`.
- **API и бот** — одно FastAPI-приложение (`app/api/main.py`) как функция Vercel в регионе `dub1`, рядом с базой. Бот работает через webhook `POST /api/v1/telegram/webhook`, отдельного процесса нет.
- **Прокси** — `*.vercel.app` недоступен у части российских провайдеров (блок по IP), поэтому Mini App ходит в API через Deno Deploy. Webhook Telegram идёт на Vercel напрямую.
- **База** — Postgres в Supabase, схема `interior`. Бесплатный проект засыпает после недели без запросов: `/api/v1/health` делает `SELECT 1`, а `keepalive.yml` дёргает его раз в день.
- **Вход** — `initData` проверяется один раз в `POST /api/v1/auth/exchange` и меняется на сессионный токен; бот подписывает токен и в кнопку входа. Подробности — [docs/architecture.md](docs/architecture.md).

## Структура

```text
app/
  api/        FastAPI: эндпоинты, проверка initData, сессионные токены
  bot/        aiogram: /start, /app, /help, /privacy, клавиатуры
  core/       настройки из переменных окружения
  domain/     quiz_engine — подсчёт и сборка результата, без привязки к UI
  storage/    repository на asyncpg
api/index.py  точка входа Vercel
content/      вопросы, архетипы, банк формулировок результата (JSON, версии v1)
migrations/   схема базы
proxy/        прокси для Deno Deploy
scripts/      настройка бота, перенос данных, экспорт PDF презентации
tests/        pytest против настоящего Postgres (схема interior_test)
webapp/       Mini App и презентация для отдела (presentation.html)
```

## Локальный запуск

```bash
python -m pip install -r requirements-dev.txt
cp .env.example .env          # заполнить TELEGRAM_TOKEN, DATABASE_URL и остальное
uvicorn app.api.main:app --port 8010
```

API отдаёт и Mini App с корня: `http://127.0.0.1:8010/`. Чтобы фронт ходил в локальный API, в `webapp/config.js` поменяйте `API_URL`. Вне Telegram нет `initData`, поэтому для ручной проверки нужен сессионный токен в адресе (`?t=...`), его выдаёт бот.

```bash
pytest                        # ~3 минуты: тесты собирают схему interior_test в той же базе
```

### Переменные окружения

| Переменная | Зачем |
|---|---|
| `TELEGRAM_TOKEN` | токен бота; им же подписываются сессионные токены |
| `DATABASE_URL` | Postgres; для Supabase — transaction pooler, порт 6543 |
| `DB_SCHEMA` | схема базы, по умолчанию `interior` |
| `WEBHOOK_SECRET` | секрет в заголовке webhook от Telegram |
| `WEBAPP_URL` | адрес Mini App для кнопки бота (только https) |
| `ALLOWED_ORIGINS` | CORS: откуда фронту можно ходить в API |
| `INIT_DATA_MAX_AGE_SECONDS` | срок годности `initData` |

## Деплой

| Что | Как |
|---|---|
| Mini App | пуш в `main` с изменениями в `webapp/**` → `pages.yml` → ветка `gh-pages` |
| API и бот | пуш в `main` → Vercel собирает `api/index.py` |
| Прокси | код из `proxy/main.ts` вручную вставляется в playground на Deno Deploy |
| Настройки бота | `python scripts/setup_bot.py --webhook <https-адрес>` — webhook, команды, кнопка меню |
| PDF презентации | `python scripts/deck_pdf.py` — текст в PDF редактируется в Acrobat |

> Сейчас прод собирается из исходного репозитория. Перенос Vercel, GitHub Pages и адресов бота на этот репозиторий — отдельный шаг; дальше планируется переезд на сервер IND.

## Контент

Вопросы, веса и тексты лежат в `content/*.json` и меняются без правки кода.

- **Новая типология проекта:** `<option>` в `webapp/index.html` + ключ в `variants` у вопросов `content/project-narrative.v1.json` + запись в `TYPOLOGIES` теста.
- **Формулировки результата:** `content/result-phrases.v1.json`. Одно и то же прохождение всегда получает один и тот же текст, разные прохождения — разные формулировки одного вывода.

---

<p align="center">
  Разработан: Полина Ишукова · <a href="https://t.me/ded_indigo">@ded_indigo</a> · IND
</p>
