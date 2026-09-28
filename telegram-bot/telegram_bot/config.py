"""Configuración del bot tomada del entorno."""

import os


def get_bot_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError(
            "Falta TELEGRAM_BOT_TOKEN. Añade el token del bot en Replit Secrets "
            "antes de iniciar el programa."
        )
    return token