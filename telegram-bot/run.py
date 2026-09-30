import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

NOMBRE, EDAD, GENERO, FOTO = range(4)

def init_db():
    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            age INTEGER,
            gender TEXT,
            photo_id TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS likes (
            from_user INTEGER,
            to_user INTEGER,
            PRIMARY KEY (from_user, to_user)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return ConversationHandler.END
        
    user_id = update.effective_user.id
    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        await update.message.reply_text("¡Bienvenido de nuevo! Usa /descubrir para ver candidatos.")
        return ConversationHandler.END
    else:
        await update.message.reply_text("¡Bienvenido al Bot de Citas! Vamos a crear tu perfil.\n\n¿Cuál es tu nombre?")
        return NOMBRE

async def get_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return NOMBRE
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Genial. ¿Cuántos años tienes?")
    return EDAD

async def get_edad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return EDAD
    try:
        age = int(update.message.text)
        context.user_data['age'] = age
        keyboard = [
            [
                InlineKeyboardButton("Hombre 👨", callback_data="Hombre"),
                InlineKeyboardButton("Mujer 👩", callback_data="Mujer")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("¿Cuál es tu género?", reply_markup=reply_markup)
        return GENERO
    except ValueError:
        await update.message.reply_text("Por favor, ingresa un número válido para tu edad.")
        return EDAD

async def get_genero(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return GENERO
    await query.answer()
    context.user_data['gender'] = query.data
    await query.edit_message_text(text=f"Género seleccionado: {query.data}.\nAhora envía una foto para tu perfil.")
    return FOTO

async def get_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo or not update.effective_user:
        return FOTO
        
    user_id = update.effective_user.id
    photo_file = update.message.photo[-1].file_id
    
    name = context.user_data.get('name', 'Usuario')
    age = context.user_data.get('age', 18)
    gender = context.user_data.get('gender', 'No especificado')

    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO users (user_id, name, age, gender, photo_id) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, age, gender, photo_file)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        "¡Tu perfil ha sido registrado con éxito! 🎉\n\nUsa /descubrir para buscar personas."
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Registro cancelado.")
    return ConversationHandler.END

async def descubrir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    current_user = update.effective_user.id
    
    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, name, age, gender, photo_id FROM users 
        WHERE user_id != ? AND user_id NOT IN (
            SELECT to_user FROM likes WHERE from_user = ?
        ) LIMIT 1
    ''', (current_user, current_user))
    
    candidate = cursor.fetchone()
    conn.close()

    if candidate:
        cand_id, name, age, gender, photo_id = candidate
        caption = f"👤 {name}, {age} años\n🚻 {gender}"
        
        keyboard = [
            [
                InlineKeyboardButton("❌ Dislike", callback_data=f"dislike_{cand_id}"),
                InlineKeyboardButton("❤️ Like", callback_data=f"like_{cand_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_photo(
                photo=photo_id, caption=caption, reply_markup=reply_markup
            )
        elif update.message:
            await update.message.reply_photo(
                photo=photo_id, caption=caption, reply_markup=reply_markup
            )
    else:
        msg = "No hay más perfiles disponibles en este momento."
        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text(msg)
        elif update.message:
            await update.message.reply_text(msg)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data or not update.effective_user:
        return
        
    await query.answer()
    data = query.data
    from_user = update.effective_user.id

    if data.startswith("like_") or data.startswith("dislike_"):
        action, to_user_str = data.split("_")
        to_user = int(to_user_str)
        
        if action == "like":
            conn = sqlite3.connect("dating_bot.db")
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO likes (from_user, to_user) VALUES (?, ?)", (from_user, to_user))
            conn.commit()
            
            cursor.execute("SELECT * FROM likes WHERE from_user = ? AND to_user = ?", (to_user, from_user))
            match = cursor.fetchone()
            conn.close()

            if match:
                if query.message:
                    await query.message.reply_text("🔥 ¡ES UN MATCH! Ambos se gustaron.")
                try:
                    await context.bot.send_message(
                        chat_id=to_user, 
                        text="🔥 ¡Tienes un nuevo MATCH! Entra al bot para conversar."
                    )
                except Exception:
                    pass

        if query.message:
            await query.message.delete()
        await descubrir(update, context)

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("Error: No se encontró la variable BOT_TOKEN en Secrets.")
        return

    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nombre)],
            EDAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_edad)],
            GENERO: [CallbackQueryHandler(get_genero)],
            FOTO: [MessageHandler(filters.PHOTO, get_foto)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("descubrir", descubrir))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot activo en Replit...")
    app.run_polling()

if __name__ == "__main__":
    main()
