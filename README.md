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
3. Запустить весь runtime: `./start_runtime.ps1`.
4. Один раз выполнить `./register_autostart.ps1`, чтобы runtime запускался при входе в Windows без админских прав.

`start_runtime.ps1` поднимает бота, Interior API на `127.0.0.1:8010`, общий gateway на `127.0.0.1:8090` и ngrok. Каждый долгоживущий процесс защищён mutex от дублей, перезапускается после сбоя и ротирует error log после 5 MB.

Mini App публикуется на GitHub Pages. Постоянный ngrok-домен ведёт на общий gateway: старый `poprobui` остаётся на корневых маршрутах, а Interior API доступен под `/interior-api`. URL API задаётся в `webapp/config.js`. `WEBAPP_URL` указывает на GitHub Pages, а `ALLOWED_ORIGINS` разрешает только origin GitHub Pages.

После изменения `webapp/` ветка `gh-pages` обновляется автоматически. Если GitHub Actions временно недоступен, после коммита можно выполнить `./deploy_pages.ps1` вручную.

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
