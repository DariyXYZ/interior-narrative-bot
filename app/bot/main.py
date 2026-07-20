from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, MenuButtonWebApp, Message, WebAppInfo

from app.bot.keyboards import app_keyboard
from app.core.config import get_settings

COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="app", description="Открыть приложение"),
    BotCommand(command="results", description="Мои результаты"),
    BotCommand(command="help", description="Как пользоваться"),
    BotCommand(command="privacy", description="Какие данные сохраняются"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    token = settings.require_bot_token()
    webapp_url = settings.require_webapp_url()
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        name = message.from_user.first_name or "коллега"
        await message.answer(
            f"Привет, {name}.\n\n"
            "Здесь два инструмента: профиль вашего проектного мышления и подбор нарратива для конкретного брифа.",
            reply_markup=app_keyboard(webapp_url),
        )

    @dp.message(Command("app"))
    async def open_app(message: Message) -> None:
        await message.answer("Откройте приложение кнопкой ниже.", reply_markup=app_keyboard(webapp_url))

    @dp.message(Command("results"))
    async def open_results(message: Message) -> None:
        await message.answer("История прохождений откроется в приложении.", reply_markup=app_keyboard(webapp_url, "results"))

    @dp.message(Command("help"))
    async def help_message(message: Message) -> None:
        await message.answer(
            "<b>Как пользоваться</b>\n\n"
            "1. Откройте приложение.\n"
            "2. Выберите один из двух независимых тестов.\n"
            "3. Результат сохранится в вашей внутренней истории."
        )

    @dp.message(Command("privacy"))
    async def privacy(message: Message) -> None:
        await message.answer(
            "Сохраняются Telegram ID, актуальный username, ответы и результаты тестов. "
            "Для проектов используются только внутренние коды или условные названия — без реальных названий заказчиков."
        )

    await bot.set_my_commands(COMMANDS)
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Открыть приложение",
            web_app=WebAppInfo(url=webapp_url),
        )
    )
    logging.info("Interior Narrative Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
