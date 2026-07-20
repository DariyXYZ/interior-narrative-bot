# Interior Narrative Bot

Внутренний Telegram-бот и Mini App для дизайнеров интерьера IND.

Текущий этап: архитектурный каркас. Вопросы, scoring и финальные формулировки результатов ещё не утверждены.

## Структура

```text
app/
  api/          FastAPI, Telegram initData auth, HTTP endpoints через ngrok
  bot/          aiogram-команды и кнопка Mini App
  core/         конфигурация
  domain/       scoring и сборка результата без привязки к UI
  storage/      SQLite schema и repository
content/        версионируемые нарративы, вопросы, фразы, референсы
docs/           архитектурные решения
tests/          unit-тесты доменной логики и авторизации
  webapp/         mobile-first Mini App для GitHub Pages
```

## Локальный запуск

1. Создать `.env` из `.env.example` и использовать новый токен бота.
2. Установить зависимости: `python -m pip install -r requirements-dev.txt`.
3. Запустить API: `./run_api.ps1`.
4. Запустить бота в другом терминале: `./run_bot.ps1`.

Mini App публикуется на GitHub Pages. Локальный API доступен снаружи через постоянный ngrok-домен; его URL задаётся в `webapp/config.js`. `WEBAPP_URL` указывает на GitHub Pages, а `ALLOWED_ORIGINS` разрешает только origin GitHub Pages.

## Команды первой версии

- `/start` — приветствие и основная кнопка;
- `/app` — открыть Mini App;
- `/results` — открыть историю результатов;
- `/help` — краткое описание;
- `/privacy` — правила хранения внутренних данных.

## Безопасность

- Telegram-пользователь определяется только через серверную проверку подписанного `initData`.
- `telegram_user_id` — постоянный идентификатор; username хранится как изменяемый снимок.
- токен Telegram не попадает в webapp, content или БД;
- реальные названия заказчиков не сохраняются — только код/условное имя проекта.

См. [архитектуру](docs/architecture.md).
