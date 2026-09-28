"""Comandos del bot."""

from telegram import Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde al comando /start."""
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "¡Hola! Soy tu bot de Telegram. Ya estoy listo para recibir comandos."
        )