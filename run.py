import os
import logging
import math
import sqlite3
import threading
import time
from flask import Flask, render_template, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

print("--- INICIANDO SERVIDOR Y BOT DE CITAS (LIMPIO) ---")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_NAME = "dating_bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Limpia datos anteriores para empezar completamente de cero
    c.execute('DROP TABLE IF EXISTS users')
    c.execute('DROP TABLE IF EXISTS likes')
    c.execute('DROP TABLE IF EXISTS messages')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            age INTEGER,
            photo_url TEXT,
            lat REAL,
            lon REAL,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS likes (
            from_user INTEGER,
            to_user INTEGER,
            action TEXT,
            PRIMARY KEY (from_user, to_user)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user INTEGER,
            to_user INTEGER,
            text TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def calculate_distance(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)

app = Flask(__name__)

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/ping', methods=['POST'])
def ping():
    data = request.json or {}
    user_id = data.get('user_id')
    lat = data.get('lat')
    lon = data.get('lon')
    if user_id:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('''
            UPDATE users 
            SET last_seen = CURRENT_TIMESTAMP, lat = COALESCE(?, lat), lon = COALESCE(?, lon)
            WHERE user_id = ?
        ''', (lat, lon, user_id))
        conn.commit()
        conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/user', methods=['GET'])
def get_user():
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return jsonify({"user": None})
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT user_id, name, age, photo_url FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return jsonify({
            "user": {
                "user_id": row[0],
                "name": row[1],
                "age": row[2] or 25,
                "photo_url": row[3] or "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=500"
            }
        })
    return jsonify({"user": None})

@app.route('/api/profiles', methods=['GET'])
def get_profiles():
    user_id = request.args.get('user_id', type=int)
    min_age = request.args.get('min_age', default=18, type=int)
    max_age = request.args.get('max_age', default=150, type=int)

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT lat, lon FROM users WHERE user_id = ?', (user_id,))
    my_location = c.fetchone()
    my_lat, my_lon = my_location if my_location else (None, None)

    query = '''
        SELECT user_id, name, age, photo_url, lat, lon,
               (strftime('%s', 'now') - strftime('%s', last_seen)) < 300 as is_online
        FROM users 
        WHERE user_id != ? 
          AND age BETWEEN ? AND ?
          AND user_id NOT IN (SELECT to_user FROM likes WHERE from_user = ?)
        LIMIT 1
    '''
    c.execute(query, (user_id, min_age, max_age, user_id))
    row = c.fetchone()
    conn.close()

    if row:
        candidate_id, name, age, photo_url, c_lat, c_lon, is_online = row
        dist = calculate_distance(my_lat, my_lon, c_lat, c_lon)
        return jsonify({
            "candidate": {
                "user_id": candidate_id,
                "name": name,
                "age": age,
                "photo_url": photo_url or "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=500",
                "is_online": bool(is_online),
                "distancia": dist
            }
        })
    return jsonify({"candidate": None})

@app.route('/api/like', methods=['POST'])
def like_user():
    data = request.json or {}
    from_user = data.get('from_user')
    to_user = data.get('to_user')
    action = data.get('action')

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO likes (from_user, to_user, action) VALUES (?, ?, ?)', (from_user, to_user, action))
    
    is_match = False
    if action == 'like':
        c.execute('SELECT action FROM likes WHERE from_user = ? AND to_user = ?', (to_user, from_user))
        other_action = c.fetchone()
        if other_action and other_action[0] == 'like':
            is_match = True

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "match": is_match})

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO users (user_id, name, age, photo_url)
        VALUES (?, ?, ?, ?)
    ''', (user.id, user.first_name, 25, "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=500"))
    conn.commit()
    conn.close()

    base_url = os.environ.get("WEBAPP_URL", "https://telegram-citas-bot-production.up.railway.app")
    timestamp_version = int(time.time())
    web_app_url = f"{base_url}?v={timestamp_version}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Abrir Citas", web_app_url=WebAppInfo(url=web_app_url))]
    ])
    await update.message.reply_text(
        f"¡Hola {user.first_name}! Toca el botón para entrar a la aplicación de citas:",
        reply_markup=keyboard
    )

def run_bot():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        application = Application.builder().token(token).build()
        application.add_handler(CommandHandler("start", start))
        application.run_polling(drop_pending_updates=True, stop_signals=None)

if __name__ == '__main__':
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
