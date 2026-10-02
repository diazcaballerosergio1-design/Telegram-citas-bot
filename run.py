import os
import logging
import math
import sqlite3
import threading
from flask import Flask, render_template_string, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Base de Datos SQLite
DB_NAME = "dating_bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
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

HTML_TEMPLATE = """
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
        .filters input { width: 55px; background: #2a2a2a; border: 1px solid #444; color: #fff; padding: 5px; border-radius: 6px; text-align: center; }
        .card-container { margin-top: 10px; min-height: 400px; position: relative; }
        .card { background: #1e1e1e; border-radius: 16px; overflow: hidden; border: 1px solid #333; box-shadow: 0 8px 20px rgba(0,0,0,0.5); }
        .card-img { width: 100%; height: 320px; object-fit: cover; background: #2a2a2a; display: block; }
        .card-info { padding: 15px; }
        .status-badge { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #4caf50; box-shadow: 0 0 8px #4caf50; margin-left: 6px; }
        .offline-badge { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #888; margin-left: 6px; }
        .meta { font-size: 13px; color: #aaa; margin-top: 6px; }
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
        <div class="header"><h2>🔥 Descubrir</h2></div>
        <div class="filters">
            <span>Edad:</span>
            <input type="number" id="minAge" value="18" min="18" max="99" onchange="loadProfile()">
            <span>a</span>
            <input type="number" id="maxAge" value="50" min="18" max="99" onchange="loadProfile()">
            <span>años</span>
        </div>
        <div class="card-container" id="cardContainer"><div class="empty">Buscando perfiles...</div></div>
    </div>

    <div id="screenChats" class="screen">
        <div class="header"><h2>💬 Mis Matches</h2></div>
        <div id="chatsList" style="margin-top: 15px;"><div class="empty">Cargando conversaciones...</div></div>
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
        <button class="nav-btn active" id="navDiscover" onclick="showScreen('screenDiscover')"><span>🔥</span> Descubrir</button>
        <button class="nav-btn" id="navChats" onclick="showScreen('screenChats')"><span>💬</span> Chats</button>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        const userId = tg.initDataUnsafe?.user?.id || 123456;
        let userLat = null, userLon = null, currentCandidate = null, activeChatUserId = null, chatInterval = null;

        function updateLocation() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (p) => { userLat = p.coords.latitude; userLon = p.coords.longitude; sendPing(); loadProfile(); },
                    () => { sendPing(); loadProfile(); },
                    { enableHighAccuracy: true }
                );
            } else { sendPing(); loadProfile(); }
        }

        function showScreen(id) {
            document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(id).classList.add('active');
            if (id === 'screenDiscover') { document.getElementById('navDiscover').classList.add('active'); clearInterval(chatInterval); loadProfile(); }
            else if (id === 'screenChats') { document.getElementById('navChats').classList.add('active'); clearInterval(chatInterval); loadChats(); }
        }

        function sendPing() {
            fetch('/api/ping', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: userId, lat: userLat, lon: userLon }) });
        }
        setInterval(sendPing, 30000);

        async function loadProfile() {
            const minAge = document.getElementById('minAge').value;
            const maxAge = document.getElementById('maxAge').value;
            const res = await fetch(`/api/profiles?user_id=${userId}&min_age=${minAge}&max_age=${maxAge}`);
            const data = await res.json();
            const container = document.getElementById('cardContainer');
            if (data.candidate) {
                currentCandidate = data.candidate;
                const isOnline = currentCandidate.is_online;
                const distText = currentCandidate.distancia !== null ? `📍 A ${currentCandidate.distancia} km de ti` : '📍 Ubicación sin GPS';
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
                    </div>`;
            } else { container.innerHTML = `<div class="empty">🎉 ¡Has visto todos los perfiles disponibles!</div>`; }
        }

        async function handleAction(action) {
            if (!currentCandidate) return;
            const res = await fetch('/api/like', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ from_user: userId, to_user: currentCandidate.user_id, action: action }) });
            const result = await res.json();
            if (result.match) tg.showAlert("🔥 ¡ES UN MATCH!");
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
                        <div><strong>${m.name}</strong><div style="font-size:12px; color:#aaa;">Presiona para chatear</div></div>
                    </div>`).join('');
            } else { list.innerHTML = `<div class="empty">Aún no tienes matches.</div>`; }
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
            box.innerHTML = data.messages.map(m => `<div class="msg ${m.from_user === userId ? 'me' : 'other'}">${m.text}</div>`).join('');
            box.scrollTop = box.scrollHeight;
        }

        async function sendMessage() {
            const input = document.getElementById('msgInput');
            const text = input.value.trim();
            if (!text || !activeChatUserId) return;
            input.value = '';
            await fetch('/api/send_message', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ from_user: userId, to_user: activeChatUserId, text: text }) });
            fetchMessages();
        }

        updateLocation();
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

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

@app.route('/api/profiles', methods=['GET'])
def get_profiles():
    user_id = request.args.get('user_id', type=int)
    min_age = request.args.get('min_age', default=18, type=int)
    max_age = request.args.get('max_age', default=99, type=int)

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

@app.route('/api/matches', methods=['GET'])
def get_matches():
    user_id = request.args.get('user_id', type=int)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    query = '''
        SELECT u.user_id, u.name, u.photo_url
        FROM likes l1
        JOIN likes l2 ON l1.from_user = l2.to_user AND l1.to_user = l2.from_user
        JOIN users u ON l1.to_user = u.user_id
        WHERE l1.from_user = ? AND l1.action = 'like' AND l2.action = 'like'
    '''
    c.execute(query, (user_id,))
    matches = [{"user_id": r[0], "name": r[1], "photo_url": r[2]} for r in c.fetchall()]
    conn.close()
    return jsonify({"matches": matches})

@app.route('/api/messages', methods=['GET'])
def get_messages():
    user_id = request.args.get('user_id', type=int)
    other_id = request.args.get('other_id', type=int)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    query = '''
        SELECT from_user, to_user, text, timestamp
        FROM messages
        WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?)
        ORDER BY timestamp ASC
    '''
    c.execute(query, (user_id, other_id, other_id, user_id))
    messages = [{"from_user": r[0], "to_user": r[1], "text": r[2]} for r in c.fetchall()]
    conn.close()
    return jsonify({"messages": messages})

@app.route('/api/send_message', methods=['POST'])
def send_message():
    data = request.json or {}
    from_user = data.get('from_user')
    to_user = data.get('to_user')
    text = data.get('text')
    
    if from_user and to_user and text:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('INSERT INTO messages (from_user, to_user, text) VALUES (?, ?, ?)', (from_user, to_user, text))
        conn.commit()
        conn.close()
    return jsonify({"status": "ok"})

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO users (user_id, name, age, photo_url)
        VALUES (?, ?, ?, ?)
    ''', (user.id, user.first_name, 25, None))
    conn.commit()
    conn.close()

    web_app_url = os.environ.get("WEBAPP_URL", "https://telegram-citas-bot-production.up.railway.app")
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
