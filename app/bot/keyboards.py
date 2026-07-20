from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo


def app_keyboard(webapp_url: str, screen: str | None = None) -> ReplyKeyboardMarkup:
    url = webapp_url if not screen else f"{webapp_url}?screen={screen}"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=url))],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите команду или откройте приложение",
    )

