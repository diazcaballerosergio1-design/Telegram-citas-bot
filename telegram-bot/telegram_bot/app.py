"""Construcción y ejecución del bot mediante long polling."""

import logging

from telegram.ext import Application, CommandHandler

from telegram_bot.config import get_bot_token
from telegram_bot.handlers import start


def build_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    return application


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    token = get_bot_token()
    logging.getLogger(__name__).info("Iniciando bot de Telegram")
    build_application(token).run_polling()