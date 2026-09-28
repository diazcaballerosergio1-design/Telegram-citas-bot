# Bot de Telegram

Proyecto Python sencillo que responde al comando `/start` usando **long polling**.
No necesita servidor web ni base de datos.

## Preparación

1. Crea un bot con **@BotFather** en Telegram y copia el token que te entregue.
2. Añade un Secret en Replit con el nombre `TELEGRAM_BOT_TOKEN` y pega allí el token. No lo escribas en el código ni en `.env.example`.
3. Instala las dependencias desde esta carpeta:

   ```bash
   python3 -m pip install -r requirements.txt
   ```

4. Inicia el bot:

   ```bash
   python3 run.py
   ```

Abre el chat de tu bot en Telegram y envía `/start` para recibir un saludo.
Si falta el Secret, el proceso muestra un error claro y termina. Mantén el
proceso en ejecución para que reciba mensajes. No ejecutes dos instancias del
mismo bot por polling a la vez.

## Estructura

- `run.py`: punto de entrada.
- `telegram_bot/config.py`: lectura y validación del Secret.
- `telegram_bot/handlers.py`: comandos.
- `telegram_bot/app.py`: registro de comandos y ejecución.
- `requirements.txt`: dependencias Python.
- `.env.example`: nombre de la variable requerida, sin credenciales.