from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo


def _with_query(url: str, **params: str) -> str:
    """Добавляет query-параметры, не ломая уже имеющиеся в url (например ?v=)."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.update(params)
    return urlunsplit(parts._replace(query=urlencode(query)))


def app_keyboard(webapp_url: str, screen: str | None = None) -> ReplyKeyboardMarkup:
    url = _with_query(webapp_url, screen=screen) if screen else webapp_url
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=url))],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите команду или откройте приложение",
    )

