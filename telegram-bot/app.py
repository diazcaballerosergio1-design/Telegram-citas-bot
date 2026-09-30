import os
import asyncio
import sqlite3
import uvicorn
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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

# --- BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            user1 INTEGER,
            user2 INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user1, user2)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
tg_app_global = None

# --- OBTENER URL DE FOTO ---
def get_file_url(file_id: str) -> str:
    if not BOT_TOKEN or not file_id:
        return ""
    try:
        res = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}").json()
        if res.get("ok"):
            file_path = res["result"]["file_path"]
            return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    except Exception:
        pass
    return ""

# --- FASTAPI (MINI APP BACKEND) ---
app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def read_index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>index.html no encontrado</h1>"

@app.get("/api/candidate")
async def get_candidate(user_id: int):
    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id, name, age, gender, photo_id FROM users 
        WHERE user_id != ? AND user_id NOT IN (
            SELECT to_user FROM likes WHERE from_user = ?
        ) LIMIT 1
    ''', (user_id, user_id))
    row = cursor.fetchone()
    conn.close()

    if row:
        c_id, name, age, gender, photo_id = row
        photo_url = get_file_url(photo_id)
        return {"candidate": {"id": c_id, "name": name, "age": age, "gender": gender, "photo_url": photo_url}}
    return {"candidate": None}

async def notify_match(user1_id: int, user2_id: int):
    if not tg_app_global:
        return
    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, name, username FROM users WHERE user_id IN (?, ?)", (user1_id, user2_id))
    rows = cursor.fetchall()
    conn.close()

    if len(rows) < 2:
        return

    u1 = rows[0] if rows[0][0] == user1_id else rows[1]
    u2 = rows[1] if rows[1][0] == user2_id else rows[0]

    # Crear botones de contacto si tienen username
    btn1 = [InlineKeyboardButton(f"Hablar con {u2[1]} 💬", url=f"https://t.me/{u2[2]}")] if u2[2] else []
    btn2 = [InlineKeyboardButton(f"Hablar con {u1[1]} 💬", url=f"https://t.me/{u1[2]}")] if u1[2] else []

    try:
        await tg_app_global.bot.send_message(
            chat_id=user1_id,
            text=f"🔥 **¡NUEVO MATCH!** 🔥\n\n¡A **{u2[1]}** también le gustas! Ya pueden comenzar a conversar.",
            reply_markup=InlineKeyboardMarkup([btn1]) if btn1 else None,
            parse_mode="Markdown"
        )
        await tg_app_global.bot.send_message(
            chat_id=user2_id,
            text=f"🔥 **¡NUEVO MATCH!** 🔥\n\n¡A **{u1[1]}** también le gustas! Ya pueden comenzar a conversar.",
            reply_markup=InlineKeyboardMarkup([btn2]) if btn2 else None,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Error al enviar notificación de match: {e}")

@app.post("/api/action")
async def handle_action(request: Request):
    data = await request.json()
    from_user = data.get("from_user")
    target_id = data.get("target_id")
    action = data.get("action")

    if not from_user or not target_id:
        return {"status": "error", "message": "Datos incompletos"}

    if action == "like":
        conn = sqlite3.connect("dating_bot.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO likes (from_user, to_user) VALUES (?, ?)", (from_user, target_id))
        
        # Verificar si hay match mutuo
        cursor.execute("SELECT * FROM likes WHERE from_user = ? AND to_user = ?", (target_id, from_user))
        mutual = cursor.fetchone()
        
        is_match = False
        if mutual:
            is_match = True
            cursor.execute("INSERT OR IGNORE INTO matches (user1, user2) VALUES (?, ?)", (min(from_user, target_id), max(from_user, target_id)))
        
        conn.commit()
        conn.close()

        if is_match:
            asyncio.create_task(notify_match(from_user, target_id))
            return {"status": "ok", "match": True}

    return {"status": "ok", "match": False}

# --- TELEGRAM BOT LOGIC ---
NOMBRE, EDAD, GENERO, FOTO = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return ConversationHandler.END
    user_id = update.effective_user.id
    username = update.effective_user.username or ""

    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if user:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        conn.commit()
    conn.close()

    if user:
        await update.message.reply_text("¡Bienvenido de nuevo! Toca el botón '🔥 Abrir Citas' abajo para buscar personas.")
        return ConversationHandler.END
    else:
        context.user_data['username'] = username
        await update.message.reply_text("¡Bienvenido a Citas Amigos! 💖\nVamos a crear tu perfil.\n\n¿Cuál es tu nombre?")
        return NOMBRE

async def get_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return NOMBRE
    context.user_data['name'] = update.message.text
    await update.message.reply_text("¿Cuántos años tienes?")
    return EDAD

async def get_edad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return EDAD
    try:
        age = int(update.message.text)
        context.user_data['age'] = age
        keyboard = [[InlineKeyboardButton("Hombre 👨", callback_data="Hombre"), InlineKeyboardButton("Mujer 👩", callback_data="Mujer")]]
        await update.message.reply_text("¿Cuál es tu género?", reply_markup=InlineKeyboardMarkup(keyboard))
        return GENERO
    except ValueError:
        await update.message.reply_text("Ingresa un número válido para tu edad.")
        return EDAD

async def get_genero(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return GENERO
    await query.answer()
    context.user_data['gender'] = query.data
    await query.edit_message_text(text=f"Género: {query.data}.\nAhora envía tu foto de perfil.")
    return FOTO

async def get_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo or not update.effective_user:
        return FOTO
    user_id = update.effective_user.id
    username = context.user_data.get('username', update.effective_user.username or "")
    photo_file = update.message.photo[-1].file_id
    name = context.user_data.get('name', 'Usuario')
    age = context.user_data.get('age', 18)
    gender = context.user_data.get('gender', 'No especificado')

    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, username, name, age, gender, photo_id) VALUES (?, ?, ?, ?, ?, ?)", 
                   (user_id, username, name, age, gender, photo_file))
    conn.commit()
    conn.close()

    await update.message.reply_text("¡Perfil guardado con éxito! 🎉\n\nPresiona el botón '🔥 Abrir Citas' abajo para empezar a descubrir personas.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Registro cancelado.")
    return ConversationHandler.END

async def start_telegram_bot():
    global tg_app_global
    if not BOT_TOKEN:
        print("Error: Sin BOT_TOKEN")
        return
    tg_app = Application.builder().token(BOT_TOKEN).build()
    tg_app_global = tg_app
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
    tg_app.add_handler(conv_handler)
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling()

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(start_telegram_bot())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
