import os
import math
import sqlite3
import threading
import requests
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# --- CONFIGURACIÓN Y SERVIDOR WEB (FLASK) ---
web_app = Flask(__name__)
BOT_TOKEN = os.environ.get("BOT_TOKEN")

def send_telegram_notification(chat_id, text):
    """Envía un mensaje de Telegram mediante la API HTTP limpia sin chocar con asyncio."""
    if not BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error al enviar notificación: {e}")

def calcular_distancia(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)

# --- PLANTILLA HTML DE LA MINI APP CON CHAT Y NAVEGACIÓN ---
MINI_APP_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Citas & Amigos</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #121212; color: #fff; padding-bottom: 70px; }
        
        .screen { display: none; padding: 15px; }
        .screen.active { display: block; }

        .header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 1px solid #2a2a2a; }
        .filters { margin: 15px 0; background: #1e1e1e; padding: 12px; border-radius: 12px; display: flex; gap: 10px; align-items: center; font-size: 14px; }
        .filters input { width: 50px; background: #2a2a2a; border: 1px solid #444; color: #fff; padding: 4px; border-radius: 6px; text-align: center; }

        .card-container { margin-top: 10px; min-height: 400px; position: relative; }
        .card { background: #1e1e1e; border-radius: 16px; overflow: hidden; border: 1px solid #333; box-shadow: 0 8px 20px rgba(0,0,0,0.5); }
        .card-img { width: 100%; height: 310px; object-fit: cover; background: #2a2a2a; display: block; }
        .card-info { padding: 15px; }
        .status-badge { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #4caf50; box-shadow: 0 0 8px #4caf50; }
        .offline-badge { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #888; }
        .meta { font-size: 13px; color: #aaa; margin-top: 4px; }
        .actions { display: flex; justify-content: space-around; margin-top: 15px; }
        .btn { width: 65px; height: 65px; border-radius: 50%; border: none; font-size: 26px; cursor: pointer; transition: transform 0.2s; display: flex; align-items: center; justify-content: center; }
        .btn:active { transform: scale(0.9); }
        .btn-dislike { background: #2a2a2a; color: #ff4d4d; border: 2px solid #ff4d4d; }
        .btn-like { background: #e91e63; color: #fff; box-shadow: 0 4px 15px rgba(233,30,99,0.4); }

        .chat-item { display: flex; align-items: center; gap: 12px; padding: 12px; background: #1e1e1e; border-radius: 12px; margin-bottom: 10px; cursor: pointer; border: 1px solid #2a2a2a; }
        .chat-avatar { width: 50px; height: 50px; border-radius: 50%; background: #e91e63; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 18px; }

        .chat-box { height: 350px; overflow-y: auto; background: #181818; border-radius: 12px; padding: 10px; display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; border: 1px solid #2a2a2a; }
        .msg { max-width: 75%; padding: 8px 12px; border-radius: 12px; font-size: 14px; }
        .msg.me { align-self: flex-end; background: #e91e63; color: #fff; }
        .msg.other { align-self: flex-start; background: #2a2a2a; color: #fff; }
        .send-form { display: flex; gap: 8px; }
        .send-form input { flex: 1; background: #2a2a2a; border: 1px solid #444; color: #fff; padding: 10px; border-radius: 8px; }
        .send-form button { background: #e91e63; color: #fff; border: none; padding: 0 15px; border-radius: 8px; font-weight: bold; cursor: pointer; }

        .nav-bar { position: fixed; bottom: 0; left: 0; right: 0; height: 60px; background: #1a1a1a; border-top: 1px solid #333; display: flex; justify-content: space-around; align-items: center; z-index: 100; }
        .nav-btn { background: none; border: none; color: #888; font-size: 12px; display: flex; flex-direction: column; align-items: center; gap: 3px; cursor: pointer; }
        .nav-btn.active { color: #e91e63; font-weight: bold; }
        .nav-btn span { font-size: 20px; }

        .empty { text-align: center; padding: 50px 20px; color: #aaa; }
    </style>
</head>
<body>

    <div id="screenDiscover" class="screen active">
        <div class="header">
            <h2>🔥 Descubrir</h2>
        </div>
        <div class="filters">
            <span>Edad:</span>
            <input type="number" id="minAge" value="18" min="18" max="99" onchange="loadProfile()">
            <span>a</span>
            <input type="number" id="maxAge" value="50" min="18" max="99" onchange="loadProfile()">
            <span>años</span>
        </div>
        <div class="card-container" id="cardContainer">
            <div class="empty">Cargando perfiles...</div>
        </div>
    </div>

    <div id="screenChats" class="screen">
        <div class="header">
            <h2>💬 Mis Matches</h2>
        </div>
        <div id="chatsList" style="margin-top: 15px;">
            <div class="empty">Cargando conversaciones...</div>
        </div>
    </div>

    <div id="screenConversation" class="screen">
        <div class="header">
            <button onclick="showScreen('screenChats')" style="background:none; border:none; color:#e91e63; font-size:16px; cursor:pointer;">← Volver</button>
            <h3 id="chatTitle">Chat</h3>
        </div>
        <div class="chat-box" id="chatMessages"></div>
        <div class="send-form">
            <input type="text" id="msgInput" placeholder="Escribe un mensaje...">
            <button onclick="sendMessage()">Enviar</button>
        </div>
    </div>

    <div class="nav-bar">
        <button class="nav-btn active" id="navDiscover" onclick="showScreen('screenDiscover')">
            <span>🔥</span> Descubrir
        </button>
        <button class="nav-btn" id="navChats" onclick="showScreen('screenChats')">
            <span>💬</span> Chats
        </button>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        const userId = tg.initDataUnsafe?.user?.id || 123456;

        let currentCandidate = null;
        let activeChatUserId = null;
        let chatInterval = null;

        function showScreen(screenId) {
            document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

            document.getElementById(screenId).classList.add('active');

            if (screenId === 'screenDiscover') {
                document.getElementById('navDiscover').classList.add('active');
                clearInterval(chatInterval);
                loadProfile();
            } else if (screenId === 'screenChats') {
                document.getElementById('navChats').classList.add('active');
                clearInterval(chatInterval);
                loadChats();
            }
        }

        function sendPing() {
            fetch('/api/ping', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId })
            });
        }
        setInterval(sendPing, 30000);
        sendPing();

        async function loadProfile() {
            const minAge = document.getElementById('minAge').value;
            const maxAge = document.getElementById('maxAge').value;

            const res = await fetch(`/api/profiles?user_id=${userId}&min_age=${minAge}&max_age=${maxAge}`);
            const data = await res.json();

            const container = document.getElementById('cardContainer');
            if (data.candidate) {
                currentCandidate = data.candidate;
                const isOnline = currentCandidate.is_online;
                const distText = currentCandidate.distancia !== null ? `📍 A ${currentCandidate.distancia} km` : '📍 Cerca de ti';

                container.innerHTML = `
                    <div class="card">
                        <img src="${currentCandidate.photo_url}" class="card-img">
                        <div class="card-info">
                            <h3>${currentCandidate.name}, ${currentCandidate.age} <span class="${isOnline ? 'status-badge' : 'offline-badge'}"></span></h3>
                            <div class="meta">${isOnline ? '🟢 En línea ahora' : '⚪ Reciente'} | ${distText}</div>
                        </div>
                    </div>
                    <div class="actions">
                        <button class="btn btn-dislike" onclick="handleAction('dislike')">❌</button>
                        <button class="btn btn-like" onclick="handleAction('like')">❤️</button>
                    </div>
                `;
            } else {
                container.innerHTML = `<div class="empty">🎉 ¡Has visto todos los perfiles disponibles!</div>`;
            }
        }

        async function handleAction(action) {
            if (!currentCandidate) return;

            const res = await fetch('/api/like', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ from_user: userId, to_user: currentCandidate.user_id, action: action })
            });

            const result = await res.json();
            if (result.match) {
                tg.showAlert("🔥 ¡ES UN MATCH! Ambos se han gustado.");
            }
            loadProfile();
        }

        async function loadChats() {
            const res = await fetch(`/api/matches?user_id=${userId}`);
            const data = await res.json();
            const list = document.getElementById('chatsList');

            if (data.matches && data.matches.length > 0) {
                list.innerHTML = data.matches.map(m => `
                    <div class="chat-item" onclick="openChat(${m.user_id}, '${m.name}')">
                        <div class="chat-avatar">${m.name.charAt(0)}</div>
                        <div>
                            <strong>${m.name}</strong>
                            <div style="font-size:12px; color:#aaa;">Presiona para abrir conversación</div>
                        </div>
                    </div>
                `).join('');
            } else {
                list.innerHTML = `<div class="empty">Aún no tienes matches. ¡Da Like en Descubrir!</div>`;
            }
        }

        function openChat(otherUserId, name) {
            activeChatUserId = otherUserId;
            document.getElementById('chatTitle').innerText = name;
            showScreen('screenConversation');
            fetchMessages();
            chatInterval = setInterval(fetchMessages, 3000);
        }

        async function fetchMessages() {
            if (!activeChatUserId) return;
            const res = await fetch(`/api/messages?user_id=${userId}&other_id=${activeChatUserId}`);
            const data = await res.json();
            const box = document.getElementById('chatMessages');

            box.innerHTML = data.messages.map(m => `
                <div class="msg ${m.from_user === userId ? 'me' : 'other'}">${m.text}</div>
            `).join('');
            box.scrollTop = box.scrollHeight;
        }

        async function sendMessage() {
            const input = document.getElementById('msgInput');
            const text = input.value.trim();
            if (!text || !activeChatUserId) return;

            input.value = '';
            await fetch('/api/send_message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ from_user: userId, to_user: activeChatUserId, text: text })
            });

            fetchMessages();
        }

        loadProfile();
    </script>
</body>
</html>
"""

@web_app.route('/')
def home():
    return render_template_string(MINI_APP_HTML)

@web_app.route('/api/ping', methods=['POST'])
def ping():
    data = request.json or {}
    user_id = data.get('user_id')
    if user_id:
        conn = sqlite3.connect("dating_bot.db")
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute("UPDATE users SET last_seen = ? WHERE user_id = ?", (now, user_id))
        conn.commit()
        conn.close()
    return jsonify({"status": "ok"})

@web_app.route('/api/profiles', methods=['GET'])
def get_profiles():
    user_id = request.args.get('user_id', type=int)
    min_age = request.args.get('min_age', default=18, type=int)
    max_age = request.args.get('max_age', default=50, type=int)

    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()

    cursor.execute("SELECT lat, lon FROM users WHERE user_id = ?", (user_id,))
    u_data = cursor.fetchone()
    u_lat, u_lon = (u_data[0], u_data[1]) if u_data else (None, None)

    cursor.execute('''
        SELECT user_id, name, age, gender, photo_id, lat, lon, last_seen FROM users 
        WHERE user_id != ? 
          AND age >= ? AND age <= ?
          AND user_id NOT IN (SELECT to_user FROM likes WHERE from_user = ?)
        LIMIT 1
    ''', (user_id, min_age, max_age, user_id))
    
    cand = cursor.fetchone()
    conn.close()

    if cand:
        c_id, name, age, gender, photo_id, c_lat, c_lon, last_seen = cand
        is_online = False
        if last_seen:
            last_dt = datetime.fromisoformat(last_seen)
            if datetime.utcnow() - last_dt < timedelta(minutes=2):
                is_online = True

        distancia = calcular_distancia(u_lat, u_lon, c_lat, c_lon)

        return jsonify({
            "candidate": {
                "user_id": c_id,
                "name": name,
                "age": age,
                "gender": gender,
                "is_online": is_online,
                "distancia": distancia,
                "photo_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=500&q=80"
            }
        })
    return jsonify({"candidate": None})

@web_app.route('/api/like', methods=['POST'])
def handle_like():
    data = request.json or {}
    from_user = data.get('from_user')
    to_user = data.get('to_user')
    action = data.get('action')

    if not from_user or not to_user:
        return jsonify({"error": "Parámetros inválidos"}), 400

    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO likes (from_user, to_user) VALUES (?, ?)", (from_user, to_user))
    conn.commit()

    is_match = False
    if action == "like":
        cursor.execute("SELECT * FROM likes WHERE from_user = ? AND to_user = ?", (to_user, from_user))
        if cursor.fetchone():
            is_match = True

    conn.close()

    if is_match:
        msg_text = "🔥 ¡TIENES UN NUEVO MATCH! Ambos se gustaron. Abre la Mini App para chatear."
        send_telegram_notification(from_user, msg_text)
        send_telegram_notification(to_user, msg_text)

    return jsonify({"success": True, "match": is_match})

@web_app.route('/api/matches', methods=['GET'])
def get_matches():
    user_id = request.args.get('user_id', type=int)
    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()

    cursor.execute('''
        SELECT u.user_id, u.name FROM users u
        WHERE u.user_id IN (
            SELECT l1.to_user FROM likes l1
            JOIN likes l2 ON l1.from_user = l2.to_user AND l1.to_user = l2.from_user
            WHERE l1.from_user = ?
        )
    ''', (user_id,))
    
    matches = [{"user_id": row[0], "name": row[1]} for row in cursor.fetchall()]
    conn.close()
    return jsonify({"matches": matches})

@web_app.route('/api/messages', methods=['GET'])
def get_messages():
    user_id = request.args.get('user_id', type=int)
    other_id = request.args.get('other_id', type=int)

    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    cursor.execute('''
        SELECT from_user, to_user, text FROM messages 
        WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?)
        ORDER BY id ASC
    ''', (user_id, other_id, other_id, user_id))

    messages = [{"from_user": r[0], "to_user": r[1], "text": r[2]} for r in cursor.fetchall()]
    conn.close()
    return jsonify({"messages": messages})

@web_app.route('/api/send_message', methods=['POST'])
def send_message():
    data = request.json or {}
    from_user = data.get('from_user')
    to_user = data.get('to_user')
    text = data.get('text')

    if from_user and to_user and text:
        conn = sqlite3.connect("dating_bot.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages (from_user, to_user, text) VALUES (?, ?, ?)", (from_user, to_user, text))
        conn.commit()
        conn.close()

        send_telegram_notification(to_user, "💬 Tienes un nuevo mensaje en el chat. Abre la Mini App para responder.")

    return jsonify({"status": "ok"})

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# --- BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            age INTEGER,
            gender TEXT,
            photo_id TEXT,
            lat REAL,
            lon REAL,
            last_seen TEXT
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
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user INTEGER,
            to_user INTEGER,
            text TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- LÓGICA BOT DE TELEGRAM ---
NOMBRE, EDAD, GENERO, FOTO = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("dating_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        await update.message.reply_text("¡Bienvenido! Abre la Mini App para interactuar con perfiles y chatear.")
        return ConversationHandler.END
    else:
        await update.message.reply_text("¡Bienvenido! Vamos a crear tu perfil.\n\n¿Cuál es tu nombre?")
        return NOMBRE

async def get_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Genial. ¿Cuántos años tienes?")
  
