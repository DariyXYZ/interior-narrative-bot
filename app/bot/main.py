from __future__ import annotations

import asyncio
import html
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, MenuButtonCommands, Message

from app.bot.keyboards import app_keyboard
from app.core.config import get_settings

COMMANDS = [
    BotCommand(command="start", description="О боте и тестах"),
    BotCommand(command="app", description="Открыть приложение"),
    BotCommand(command="help", description="Если что-то не работает"),
    BotCommand(command="privacy", description="Какие данные сохраняются"),
]

SUPPORT_CONTACT = "@ded_indigo"

# Приветствие несёт то, что раньше пряталось в /info: без него первое сообщение
# не объясняло, зачем бот нужен.
WELCOME = (
    "Привет, {name}.\n\n"
    "Это внутренний инструмент дизайнеров интерьеров IND. Два независимых теста:\n\n"
    "01 · <b>Какой вы тип дизайнера</b> — определяет ваш авторский профиль: "
    "как вы находите идею, строите пространство и принимаете проектные решения. "
    "30 вопросов, около 10 минут.\n\n"
    "02 · <b>Нарратив проекта</b> — по полному брифу подбирает основной и два "
    "альтернативных нарратива, аргументацию для заказчика, визуальный язык "
    "и проекты-референсы. 35 вопросов, 10–15 минут.\n\n"
    "Результаты сохраняются в вашей истории — тесты можно проходить заново, "
    "а прерванный тест продолжится с того же вопроса.\n\n"
    "<b>Команды</b>\n"
    "/app — открыть приложение\n"
    "/help — если что-то не работает\n"
    "/privacy — какие данные сохраняются"
)

HELP = (
    "<b>Если что-то не работает</b>\n\n"
    "<b>«Открыто вне Telegram»</b> — Telegram не передал ваш профиль. Так бывает, "
    "когда приложение открыли ссылкой, а не кнопкой. Нажмите «Открыть приложение» "
    "под полем ввода; если кнопки нет — отправьте /start. "
    "С интернетом и VPN это не связано.\n\n"
    "<b>«Не получается связаться с сервером», код СЕТЬ-2</b> — приложение не "
    "достучалось до сервера. Проверьте интернет и повторите через пару минут: "
    "сервер иногда ненадолго уходит и поднимается сам.\n\n"
    "<b>«Сервер не ответил за 15 секунд», СЕТЬ-3</b> — медленная связь, "
    "нажмите «Попробовать ещё раз».\n\n"
    "<b>«Telegram не подтвердил вход», ВХОД-1</b> — закройте приложение и откройте "
    "заново кнопкой. Не помогло — отправьте /start, кнопка обновится.\n\n"
    "<b>Тест прервался</b> — ничего не потеряно: ответы сохраняются по ходу. "
    "Откройте тест снова и продолжите с того же вопроса.\n\n"
    f"Не починилось — напишите {SUPPORT_CONTACT}, приложите код ошибки и скриншот."
)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    token = settings.require_bot_token()
    webapp_url = settings.require_webapp_url()
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        name = html.escape(message.from_user.first_name or "коллега")
        await message.answer(WELCOME.format(name=name), reply_markup=app_keyboard(webapp_url))

    @dp.message(Command("app"))
    async def open_app(message: Message) -> None:
        await message.answer("Откройте приложение кнопкой ниже.", reply_markup=app_keyboard(webapp_url))

    @dp.message(Command("help"))
    async def help_message(message: Message) -> None:
        await message.answer(HELP, reply_markup=app_keyboard(webapp_url))

    @dp.message(Command("privacy"))
    async def privacy(message: Message) -> None:
        await message.answer(
            "Сохраняются Telegram ID, актуальный username, ответы и результаты тестов. "
            "Для проектов используются только внутренние коды или условные названия — без реальных названий заказчиков."
        )

    await bot.set_my_commands(COMMANDS)
    # Боковая кнопка — список команд, а не Web App: иначе команды доступны только
    # набором «/» вручную. Приложение открывается крупной кнопкой reply-клавиатуры
    # (app_keyboard), так что вход в него никуда не девается.
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logging.info("Interior Narrative Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
