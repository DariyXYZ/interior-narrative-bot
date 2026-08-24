from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo


def _with_query(url: str, **params: str) -> str:
    """Добавляет query-параметры, не ломая уже имеющиеся в url (например ?v=)."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.update(params)
    return urlunsplit(parts._replace(query=urlencode(query)))


def app_keyboard(webapp_url: str, screen: str | None = None, session_token: str | None = None) -> ReplyKeyboardMarkup:
    """Кнопка входа в мини-апп.

    session_token уходит в URL сознательно: Telegram-клиенты (особенно Desktop)
    периодически отдают мини-аппу пустой initData, и тогда приложение не может
    ни узнать человека, ни выменять токен — вход запирается насмерть. Токен из
    кнопки бота этого не зависит: бот и так знает, кто нажал. Ссылка видна только
    владельцу чата, а приложение вычищает параметр из адреса сразу после чтения."""
    params = {key: value for key, value in (("screen", screen), ("t", session_token)) if value}
    url = _with_query(webapp_url, **params) if params else webapp_url
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=url))],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите команду или откройте приложение",
    )

