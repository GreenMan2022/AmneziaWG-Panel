#!/usr/bin/env python3
"""AmneziaWG Panel with Authentication"""

import subprocess, json, os, datetime, re, base64, hashlib, secrets, time, socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from html import escape as html_escape
import urllib.parse

HASH_SALT = os.environ.get("PANEL_HASH_SALT", "amnezia_panel_2026")
CLIENT_AUTH_SALT = os.environ.get("PANEL_CLIENT_AUTH_SALT", "amnezia_client_auth_2026")

CONF_FILE = "/root/awg/panel.conf"


def _load_conf():
    cfg = {}
    try:
        with open(CONF_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip()
    except OSError:
        pass
    return cfg


PANEL_CONF = _load_conf()


def conf_get(key, default=None):
    return PANEL_CONF.get(key, default)


def parse_config(text):
    """Разбирает .conf (Interface/Peer) в плоский словарь key -> value."""
    cfg = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('[') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        cfg[k.strip()] = v.strip()
    return cfg


# Секретный путь админ-панели: всё, кроме /client/, доступно только по этому
# пути. Корень "/" отдаёт 404, чтобы скрипт-сканеры не находили панель.
# Задаётся через env PANEL_ADMIN_PATH или admin_path в panel.conf; если не
# задан — генерируется случайно при первом запуске и сохраняется в panel.conf.
ADMIN_PATH = (os.environ.get("PANEL_ADMIN_PATH") or conf_get("admin_path") or "/1q2w3e4r")

if not os.environ.get("PANEL_ADMIN_PATH") and not conf_get("admin_path"):
    ADMIN_PATH = "/" + secrets.token_hex(8)
    try:
        with open(CONF_FILE, "a") as f:
            f.write(f"\nadmin_path={ADMIN_PATH}\n")
    except OSError:
        pass

PANEL_HOST = conf_get("host") or "0.0.0.0"
try:
    PANEL_PORT = int(conf_get("port") or 8000)
except ValueError:
    PANEL_PORT = 8000

AUTH_LOG = conf_get("auth_log") or "/var/log/awg/panel_auth.log"


def generate_client_password(length=10):
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# Программы для подключения (показываются на странице клиента).
# ВАЖНО: это AmneziaWG (AWG) — стандартное приложение WireGuard его НЕ
# поддерживает (в конфиге есть параметры обфускации Jc/Jmin/Jmax/S1-S4/H1-H4).
CONNECT_APPS = [
    {
        'name': 'AmneziaWG (Android)',
        'desc': 'Официальное нативное приложение для протокола AmneziaWG. Импорт .conf или QR-кода.',
        'platforms': 'Android',
        'url': 'https://play.google.com/store/apps/details?id=org.amnezia.awg',
        'color': '#238636',
        'icon': '🤖',
    },
    {
        'name': 'AmneziaWG (iOS)',
        'desc': 'Официальное нативное приложение AmneziaWG для iPhone/iPad.',
        'platforms': 'iOS',
        'url': 'https://apps.apple.com/app/amneziawg/id6478942365',
        'color': '#00838f',
        'icon': '🍎',
    },
    {
        'name': 'WG Tunnel (универсально)',
        'desc': 'Универсальный способ подключения с любого устройства: Android, iOS, Windows, macOS, Linux.',
        'platforms': 'Android · iOS · Windows · macOS · Linux',
        'url': 'https://wgtunnel.com/download',
        'color': '#ab47bc',
        'icon': '🔗',
    },
]

ADMIN_USERNAME = os.environ.get("PANEL_ADMIN_USER", "GreenMan")
ADMIN_PASSWORD = os.environ.get("PANEL_ADMIN_PASSWORD", "1Q2w3e4r!")

USERS_DB = {
    ADMIN_USERNAME: hashlib.sha256((ADMIN_PASSWORD + HASH_SALT).encode()).hexdigest()
}

SESSION_TIMEOUT = 3600
sessions = {}

def hash_password(password):
    return hashlib.sha256((password + HASH_SALT).encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

def create_session(username):
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {'username': username, 'created': time.time(), 'expires': time.time() + SESSION_TIMEOUT}
    return session_id

def validate_session(session_id):
    if session_id not in sessions:
        return None
    session = sessions[session_id]
    if time.time() > session['expires']:
        del sessions[session_id]
        return None
    session['expires'] = time.time() + SESSION_TIMEOUT
    return session['username']

def cleanup_sessions():
    now = time.time()
    expired = [sid for sid, session in sessions.items() if now > session['expires']]
    for sid in expired:
        del sessions[sid]

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    timeout = 30

    def log_message(self, fmt, *args):
        pass
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        # Клиентские страницы подключения доступны без секретного пути
        if path.startswith('/client/') or path.startswith('/static/'):
            self.handle_client_route(path)
            return

        # Всё остальное (админ-панель) — только по секретному пути
        if path == '/' or not path.startswith(ADMIN_PATH):
            self.send_response(404)
            self.end_headers()
            return

        if path == ADMIN_PATH:
            if not self.is_authenticated():
                self.send_response(302)
                self.send_header('Location', ADMIN_PATH + '/login')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(self.get_dashboard().encode())
        elif path == ADMIN_PATH + '/login':
            if self.is_authenticated():
                self.send_response(302)
                self.send_header('Location', ADMIN_PATH)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(self.get_login_page().encode())
        elif path == ADMIN_PATH + '/dns':
            if not self.is_authenticated():
                self.send_response(302)
                self.send_header('Location', ADMIN_PATH + '/login')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(self.get_dns_log().encode())
        elif path == ADMIN_PATH + '/logout':
            self.logout()
        elif path.startswith(ADMIN_PATH + '/config/'):
            self.serve_config(path.split('/')[-1])
        elif path.startswith(ADMIN_PATH + '/qr/'):
            self.serve_qr(path.split('/')[-1])
        elif path.startswith(ADMIN_PATH + '/json/'):
            self.serve_json(path.split('/')[-1])
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(content_length).decode()
        params = urllib.parse.parse_qs(data)
        path = self.path

        print(f"📨 POST request: {path}, data: {data}")  # Отладка

        if path.startswith('/client/') and path.endswith('/auth'):
            self.handle_client_auth(path, params)
        elif path == ADMIN_PATH + '/login':
            self.handle_login(params)
        elif path == ADMIN_PATH + '/add':
            self.handle_add_friend(params)
        elif path == ADMIN_PATH + '/delete':
            self.handle_delete_client(params)
        elif path == ADMIN_PATH + '/unblock':
            self.handle_unblock_client(params)
        elif path == ADMIN_PATH + '/extend':
            self.handle_extend_client(params)
        elif path == ADMIN_PATH + '/logout':
            self.logout()
        else:
            self.send_response(404)
            self.end_headers()
    
    def is_authenticated(self):
        cookie = self.headers.get('Cookie', '')
        if 'session=' in cookie:
            session_id = cookie.split('session=')[1].split(';')[0]
            if validate_session(session_id):
                return True
        return False
    
    def redirect_to_login(self):
        self.send_response(302)
        self.send_header('Location', ADMIN_PATH + '/login')
        self.end_headers()
    
    def set_session_cookie(self, session_id):
        self.send_header('Set-Cookie', f'session={session_id}; Path=/; HttpOnly; Max-Age={SESSION_TIMEOUT}; SameSite=Lax')
    
    def handle_login(self, params):
        username = params.get('username', [''])[0]
        password = params.get('password', [''])[0]
        client_ip = self.client_address[0] if self.client_address else '?'
        
        if username in USERS_DB and verify_password(password, USERS_DB[username]):
            session_id = create_session(username)
            self.send_response(302)
            self.set_session_cookie(session_id)
            self.send_header('Location', ADMIN_PATH)
            self.end_headers()
        else:
            try:
                with open(AUTH_LOG, "a") as f:
                    f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                            f"Failed login for user '{username}' from {client_ip}\n")
            except OSError:
                pass
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(self.get_login_page(error="Неверное имя пользователя или пароль").encode())
    
    def handle_add_friend(self, params):
        """Обработка добавления друга с произвольным сроком"""
        name = params.get('name', [''])[0].strip()
        expires_days = params.get('expires_days', ['7'])[0].strip()  # Изменено с expires на expires_days
        
        # Валидация
        if not name:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(self.get_dashboard(error="❌ Имя не может быть пустым").encode())
            return
        
        try:
            days = int(expires_days)
            if days < 1 or days > 365:
                raise ValueError("Дни должны быть от 1 до 365")
        except ValueError:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(self.get_dashboard(error="❌ Введите корректное число дней (1-365)").encode())
            return
        
        print(f"➕ Добавление друга: {name} на {days} дней")
        
        # Здесь вызывается твой скрипт добавления
        # Замени на реальную команду
        cmd = f'/root/awg/manage_amneziawg.sh add {name} --expires={days}d'
        # cmd = f'echo "Добавлен {name} на {days} дней"'  # Тестовая команда
        
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            print(f"➕ Результат команды: {result.stdout}")
            if result.stderr and result.returncode != 0:
                print(f"⚠️ Ошибки: {result.stderr}")
            
            if os.path.exists(f'/root/awg/{name}.conf'):
                self.ensure_client_password(name)
            
            # Перенаправляем обратно на панель с сообщением об успехе
            self.send_response(302)
            self.send_header('Location', f'{ADMIN_PATH}?success=added&name={urllib.parse.quote_plus(name)}&days={days}')
            self.end_headers()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(self.get_dashboard(error=f"❌ Ошибка при добавлении: {str(e)}").encode())
    
    def handle_delete_client(self, params):
        name = params.get('name', [''])[0].strip()
        if not name:
            self.send_response(302)
            self.send_header('Location', ADMIN_PATH)
            self.end_headers()
            return
        
        print(f"🗑 Удаление клиента: {name}", flush=True)
        cmd = f'/root/awg/manage_amneziawg.sh remove {name}'
        
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            print(f"🗑 Результат: {result.stdout}", flush=True)
            if result.returncode != 0:
                print(f"⚠️ Ошибки: {result.stderr}", flush=True)
            if result.returncode == 0:
                for ext in ('.password',):
                    p = f'/root/awg/{name}{ext}'
                    if os.path.exists(p):
                        try:
                            os.remove(p)
                        except OSError:
                            pass
                self.send_response(302)
                self.send_header('Location', ADMIN_PATH + '?success=deleted&name=' + urllib.parse.quote_plus(name))
            else:
                self.send_response(302)
                self.send_header('Location', ADMIN_PATH + '?error=delete_failed&name=' + urllib.parse.quote_plus(name))
            self.end_headers()
        except subprocess.TimeoutExpired:
            print(f"❌ Таймаут удаления {name}", flush=True)
            self.send_response(302)
            self.send_header('Location', ADMIN_PATH + '?error=delete_failed&name=' + urllib.parse.quote_plus(name))
            self.end_headers()
        except Exception as e:
            print(f"❌ Ошибка удаления: {e}", flush=True)
            self.send_response(302)
            self.send_header('Location', ADMIN_PATH + '?error=delete_failed')
            self.end_headers()
    
    def handle_extend_client(self, params):
        """Продление подписки клиента: добавляет дни к текущему сроку"""
        name = params.get('name', [''])[0].strip()
        add_days = params.get('add_days', [''])[0].strip()

        if not name:
            self.send_response(302)
            self.send_header('Location', ADMIN_PATH)
            self.end_headers()
            return

        try:
            days = int(add_days)
            if days < 1 or days > 365:
                raise ValueError("Дни должны быть от 1 до 365")
        except ValueError:
            self.send_response(302)
            self.send_header('Location', f'{ADMIN_PATH}?error=invalid_days&name={urllib.parse.quote_plus(name)}')
            self.end_headers()
            return

        print(f"➕ Продление {name} на {days} дней")
        cmd = f'/root/awg/manage_amneziawg.sh extend {name} --expires={days}d'
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.send_response(302)
                self.send_header('Location', f'{ADMIN_PATH}?success=extended&name={urllib.parse.quote_plus(name)}&days={days}')
            else:
                self.send_response(302)
                self.send_header('Location', f'{ADMIN_PATH}?error=extend_failed&name={urllib.parse.quote_plus(name)}')
            self.end_headers()
        except Exception as e:
            print(f"❌ Ошибка продления: {e}")
            self.send_response(302)
            self.send_header('Location', f'{ADMIN_PATH}?error=extend_failed')
            self.end_headers()

    def handle_unblock_client(self, params):
        """Разблокировка клиента, заблокированного за раздачу подключения"""
        name = params.get('name', [''])[0].strip()
        if not name:
            self.send_response(302)
            self.send_header('Location', ADMIN_PATH)
            self.end_headers()
            return

        print(f"🚫 Разблокировка клиента: {name}", flush=True)
        info = self.get_client_info(name)
        ip = info.get('ip')
        if ip:
            ip = ip.split('/')[0]
            ip_cidr = f'{ip}/32'
            subprocess.run(f'iptables -D FORWARD -s {ip_cidr} -j DROP', shell=True, capture_output=True)
            subprocess.run(f'iptables -D FORWARD -s {ip} -j DROP', shell=True, capture_output=True)

            blocked_path = '/var/log/awg/blocked_ips'
            try:
                lines = [ln.strip() for ln in open(blocked_path) if ln.strip()]
                kept = [ln for ln in lines if ln not in (ip, ip_cidr)]
                with open(blocked_path, 'w') as f:
                    f.write('\n'.join(kept) + ('\n' if kept else ''))
            except OSError:
                pass

        self.send_response(302)
        self.send_header('Location', f'{ADMIN_PATH}?success=unblocked&name={urllib.parse.quote_plus(name)}')
        self.end_headers()

    def logout(self):
        cleanup_sessions()
        self.send_response(302)
        self.send_header('Set-Cookie', 'session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT')
        self.send_header('Location', ADMIN_PATH + '/login')
        self.end_headers()
    
    def serve_config(self, name):
        name = name[:-5] if name.lower().endswith('.conf') else name
        path = f'/root/awg/{name}.conf'
        if os.path.exists(path):
            self.send_response(200)
            self.send_header('Content-type', 'application/octet-stream')
            self.send_header('Content-Disposition', f'attachment; filename="{name}.conf"')
            self.end_headers()
            with open(path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()
    
    def serve_qr(self, name):
        png_path = f'/root/awg/{name}.png'
        conf_path = f'/root/awg/{name}.conf'
        
        if os.path.exists(png_path):
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            
            with open(png_path, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode()
            
            conf_link = f"{ADMIN_PATH}/config/{name}/{name}.conf" if os.path.exists(conf_path) else ""
            share_link = f"/client/{name}"
            
            html = f'''
            <!DOCTYPE html>
            <html lang="ru">
            <head><meta charset="UTF-8"><title>QR-код {name}</title>
            <style>
                body{{background:#0d1117;color:#c9d1d9;font-family:sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}
                .card{{background:#161b22;border-radius:12px;padding:30px;text-align:center;max-width:500px;width:90%;box-shadow:0 8px 24px rgba(0,0,0,0.5)}}
                img{{max-width:100%;height:auto;border-radius:8px}}
                h2{{margin-top:0}}
                .btn{{display:inline-block;margin-top:15px;background:#238636;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold}}
                .btn:hover{{background:#2ea043}}
                .btn-see{{background:#1f6feb}}
                .btn-see:hover{{background:#2c89f0}}
                .back{{display:inline-block;margin-top:12px;color:#58a6ff;text-decoration:none}}
            </style>
            </head>
            <body>
            <div class="card">
                <h2>🔑 {name}</h2>
                <img src="data:image/png;base64,{img_data}" alt="QR">
                {f'<br><a href="{conf_link}" class="btn" download>📥 Скачать конфиг</a>' if conf_link else ''}
                <br><a href="{share_link}" class="btn btn-see">📱 Страница клиента</a>
                <br><a href="{ADMIN_PATH}" class="back">← На панель</a>
            </div>
            </body>
            </html>'''
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def serve_json(self, name):
        conf_path = f'/root/awg/{name}.conf'
        if os.path.exists(conf_path):
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            config = {}
            with open(conf_path) as f:
                config = dict(parse_config(f.read()))
            self.wfile.write(json.dumps(config, ensure_ascii=False, indent=2).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def format_bytes(self, b):
        if b == 0: return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while b >= 1024 and i < len(units) - 1:
            b /= 1024
            i += 1
        return f"{b:.1f} {units[i]}" if i > 0 else f"{int(b)} B"

    # ==========================================================================
    # Защита страницы клиента паролем
    # ==========================================================================

    def get_client_password(self, name):
        try:
            with open(f'/root/awg/{name}.password') as f:
                pwd = f.read().strip()
            return pwd or None
        except OSError:
            return None

    def ensure_client_password(self, name):
        pwd = self.get_client_password(name)
        if not pwd:
            pwd = generate_client_password()
            try:
                with open(f'/root/awg/{name}.password', 'w') as f:
                    f.write(pwd)
                os.chmod(f'/root/awg/{name}.password', 0o600)
            except OSError:
                pass
        return pwd

    def client_cookie_name(self, name):
        return 'client_' + hashlib.sha256(name.encode()).hexdigest()[:16]

    def client_token(self, name):
        pwd = self.get_client_password(name)
        if not pwd:
            return None
        return hashlib.sha256((name + ':' + pwd + ':' + CLIENT_AUTH_SALT).encode()).hexdigest()

    def is_client_authed(self, name):
        expected = self.client_token(name)
        if not expected:
            return False
        cookie_name = self.client_cookie_name(name)
        for part in self.headers.get('Cookie', '').split(';'):
            part = part.strip()
            if part.startswith(cookie_name + '='):
                return part[len(cookie_name) + 1:] == expected
        return False

    def serve_client_login(self, name, error=None):
        safe_name = html_escape(name)
        url_name = urllib.parse.quote(name)
        error_html = ''
        if error:
            error_html = f'<div style="background:#d32f2f;padding:10px 14px;border-radius:8px;color:#fff;margin-bottom:14px;font-size:13px">{html_escape(error)}</div>'
        html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Вход — {safe_name}</title>
<style>
    *{{box-sizing:border-box}}
    body{{background:#0a0e17;color:#e0e0e0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:16px;display:flex;justify-content:center;align-items:center;min-height:100vh}}
    .card{{background:#111b2b;border:1px solid #1a2a3a;border-radius:16px;padding:28px;max-width:360px;width:100%;text-align:center}}
    h1{{font-size:20px;margin:0 0 6px;color:#4fc3f7}}
    p{{color:#8899bb;font-size:14px;margin:0 0 18px}}
    input{{width:100%;padding:12px 14px;border-radius:8px;border:1px solid #2a3a5a;background:#0a1520;color:#e0e0e0;font-size:15px;margin-bottom:12px;box-sizing:border-box}}
    button{{width:100%;padding:12px;border:none;border-radius:8px;background:#1f6feb;color:#fff;font-size:15px;font-weight:600;cursor:pointer}}
    button:hover{{background:#2c89f0}}
</style>
</head>
<body>
<div class="card">
    <h1>🔒 {safe_name}</h1>
    <p>Страница подключения доступна по паролю</p>
    {error_html}
    <form method="POST" action="/client/{url_name}/auth">
        <input type="password" name="password" placeholder="Пароль" required autofocus>
        <button type="submit">Войти</button>
    </form>
</div>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(html.encode())

    def handle_client_auth(self, path, params):
        parts = [p for p in path.split('/') if p]
        name = parts[1] if len(parts) > 1 else ''
        pwd = params.get('password', [''])[0]
        if name and self.get_client_password(name) == pwd:
            self.send_response(302)
            self.send_header('Set-Cookie',
                             f'{self.client_cookie_name(name)}={self.client_token(name)}; Path=/; HttpOnly; Max-Age=2592000; SameSite=Lax')
            self.send_header('Location', '/client/' + urllib.parse.quote(name))
            self.end_headers()
        else:
            self.serve_client_login(name, error="Неверный пароль")

    # ==========================================================================
    # Страница клиента (публичная, доступна по ссылке без авторизации)
    # ==========================================================================

    def handle_client_route(self, path):
        parts = [p for p in path.split('/') if p]
        # parts[0] == 'client', parts[1] == name, parts[2] == action (optional)
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            return
        name = parts[1]
        if not os.path.exists(f'/root/awg/{name}.conf'):
            self.send_response(404)
            self.end_headers()
            return
        action = parts[2] if len(parts) > 2 else 'page'
        if action in ('auth', 'login'):
            self.serve_client_login(name)
            return
        if not self.is_client_authed(name):
            self.serve_client_login(name)
            return
        if action == 'conf':
            self.serve_client_file(name, 'conf', 'application/octet-stream')
        elif action == 'vpnuri':
            self.serve_client_file(name, 'vpnuri', 'application/octet-stream')
        elif action == 'qr.png':
            self.serve_client_qr(name)
        else:
            self.serve_client_page(name)

    def serve_client_file(self, name, ext, content_type):
        suffix = f'.{ext}'
        if name.lower().endswith(suffix):
            name = name[:-len(suffix)]
        path = f'/root/awg/{name}.{ext}'
        if os.path.exists(path):
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Disposition', f'attachment; filename="{name}.{ext}"')
            self.end_headers()
            with open(path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()

    def serve_client_qr(self, name):
        # Сначала отдаём QR обычного .conf (тот же, что в панели) — его понимают
        # и нативные клиенты AmneziaWG, и AmneziaVPN. vpn:// URI поддерживают
        # только отдельные приложения, поэтому он лишь как запасной вариант.
        for ext in ('png', 'vpnuri.png'):
            png_path = f'/root/awg/{name}.{ext}'
            if os.path.exists(png_path):
                self.send_response(200)
                self.send_header('Content-type', 'image/png')
                self.end_headers()
                with open(png_path, 'rb') as f:
                    self.wfile.write(f.read())
                return
        self.send_response(404)
        self.end_headers()

    def get_client_info(self, name):
        info = {
            'name': name,
            'exists': os.path.exists(f'/root/awg/{name}.conf'),
            'ip': None,
            'status': 'Неизвестно',
            'status_code': 'unknown',
            'rx': 0,
            'tx': 0,
            'last_handshake': None,
            'days_left': None,
            'expires_at': None,
            'qr': os.path.exists(f'/root/awg/{name}.vpnuri.png') or os.path.exists(f'/root/awg/{name}.png'),
            'conf': os.path.exists(f'/root/awg/{name}.conf'),
            'vpnuri': os.path.exists(f'/root/awg/{name}.vpnuri'),
        }
        for c in self.get_clients():
            if c.get('name') == name:
                info['ip'] = c.get('ip')
                info['status'] = c.get('status', 'Неизвестно')
                info['status_code'] = c.get('status_code', 'unknown')
                info['rx'] = int(c.get('rx') or 0)
                info['tx'] = int(c.get('tx') or 0)
                info['last_handshake'] = c.get('last_handshake')
                break
        expiry_path = f'/root/awg/expiry/{name}'
        if os.path.exists(expiry_path):
            try:
                exp_ts = int(open(expiry_path).read().strip())
                info['expires_at'] = exp_ts
                info['days_left'] = int((exp_ts - time.time()) / 86400)
            except (ValueError, OSError):
                pass
        return info

    def is_client_blocked(self, name):
        """Заблокирован ли клиент за раздачу подключения (туннельный IP в blocked_ips)."""
        try:
            with open('/var/log/awg/blocked_ips') as f:
                blocked = {line.strip() for line in f if line.strip()}
        except OSError:
            return False
        if not blocked:
            return False
        ip = self.get_client_info(name).get('ip')
        if not ip:
            return False
        ip_cidr = ip if '/' in ip else f'{ip}/32'
        return ip in blocked or ip_cidr in blocked

    def get_blocked_ips(self):
        """Список туннельных IP, заблокированных за раздачу подключения."""
        try:
            with open('/var/log/awg/blocked_ips') as f:
                return [line.strip() for line in f if line.strip()]
        except OSError:
            return []

    def serve_client_page(self, name):
        info = self.get_client_info(name)
        if not info['exists']:
            self.send_response(404)
            self.end_headers()
            return

        safe_name = html_escape(info['name'])
        is_blocked = self.is_client_blocked(name)

        if info['days_left'] is None:
            days_num = '∞'
            days_html_cls = 'days-infinite'
        elif info['days_left'] < 0:
            days_num = '0'
            days_html_cls = 'days-expired'
        elif info['days_left'] <= 3:
            days_num = str(info['days_left'])
            days_html_cls = 'days-warn'
        else:
            days_num = str(info['days_left'])
            days_html_cls = 'days-ok'

        status_color = '#66bb6a' if info['status'] == 'Активен' else '#ffa726' if info['status'] == 'Недавно' else '#8899bb'
        status_icon = '🟢' if info['status'] == 'Активен' else '🟡' if info['status'] == 'Недавно' else '⚪'

        expiry_line = ''
        if info['expires_at']:
            exp_date = datetime.datetime.fromtimestamp(info['expires_at']).strftime('%d.%m.%Y')
            if info['days_left'] is not None and info['days_left'] >= 0:
                expiry_line = f'<div class="info-row"><span class="info-label">📅 Подписка действует до</span><span class="info-value">{exp_date}</span></div>'
            else:
                expiry_line = f'<div class="info-row"><span class="info-label">📅 Подписка истекла</span><span class="info-value" style="color:#f85149">{exp_date}</span></div>'

        vpnuri_href = ''
        vpnuri_path = f'/root/awg/{name}.vpnuri'
        if os.path.exists(vpnuri_path):
            vpnuri_href = open(vpnuri_path).read().strip()

        vpnuri_open = ''
        if vpnuri_href:
            vpnuri_open = f'''
            <a href="{html_escape(vpnuri_href)}" class="option-btn option-primary">🚀 Открыть в приложении</a>
            <a href="/client/{name}/vpnuri" class="option-btn" download>📄 Скачать .vpnuri</a>
            '''

        apps_cards = '\n'.join(
            f'''<a href="{html_escape(app['url'])}" target="_blank" rel="noopener" class="app-card">
                <div class="app-icon" style="background:{app['color']}">{app['icon']}</div>
                <div class="app-body">
                    <div class="app-name">{app['name']}</div>
                    <div class="app-desc">{html_escape(app['desc'])}</div>
                    <div class="app-platforms">{app['platforms']}</div>
                </div>
                <div class="app-arrow">↗</div>
            </a>'''
            for app in CONNECT_APPS
        )

        if is_blocked:
            blocked_banner = '''
            <div class="blocked-banner">
                🚫 <strong>Подключение заблокировано</strong> — этот конфиг был замечен в использовании несколькими устройствами с разных сетей (раздача подключения). Доступ приостановлен. По вопросам восстановления обратитесь к администратору.
            </div>'''
        else:
            blocked_banner = ''

        share_warning = '''
        <div class="share-warning">🔒 <strong>Запрещено делиться этим подключением.</strong> Конфиг предназначен только для личного использования. При подключении с нескольких устройств одновременно или передаче настроек третьим лицам доступ будет заблокирован автоматически.</div>
        '''

        html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Подключение — {safe_name}</title>
<style>
    *{{box-sizing:border-box}}
    body{{background:#0a0e17;color:#e0e0e0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:16px}}
    .wrap{{max-width:560px;margin:0 auto}}
    .card{{background:#111b2b;border:1px solid #1a2a3a;border-radius:16px;padding:20px;margin-bottom:16px}}
    h1{{font-size:20px;margin:0;color:#4fc3f7;text-align:center}}
    .subtitle{{text-align:center;color:#8899bb;font-size:13px;margin:6px 0 0}}
    .qr-card{{text-align:center}}
    .qr-img{{width:min(260px,70vw);height:auto;border-radius:12px;background:#fff;padding:10px}}
    .qr-hint{{color:#8899bb;font-size:13px;margin-top:10px}}
    .step{{display:flex;gap:12px;margin-bottom:14px}}
    .step:last-child{{margin-bottom:0}}
    .step-num{{flex-shrink:0;width:28px;height:28px;border-radius:50%;background:#1f6feb;color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center;font-size:14px}}
    .step-body{{font-size:13.5px;line-height:1.55;color:#c9d1d9}}
    .step-body strong{{color:#e0e0e0}}
    .options{{display:flex;flex-direction:column;gap:8px;margin-top:14px}}
    .option-btn{{display:block;text-align:center;padding:12px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;background:#1a2a3a;color:#c9d1d9;transition:background .15s}}
    .option-btn:hover{{background:#243b52}}
    .option-primary{{background:#1f6feb;color:#fff}}
    .option-primary:hover{{background:#2c89f0}}
    .section-title{{color:#4fc3f7;font-size:15px;margin:0 0 12px}}
    .apps{{display:flex;flex-direction:column;gap:8px}}
    .app-card{{display:flex;align-items:center;gap:12px;background:#0a1520;border:1px solid #1a2a3a;border-radius:10px;padding:12px;text-decoration:none;color:inherit;transition:border-color .15s}}
    .app-card:hover{{border-color:#4fc3f7}}
    .app-icon{{width:38px;height:38px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:19px;flex-shrink:0}}
    .app-body{{flex:1;min-width:0}}
    .app-name{{font-weight:600;font-size:14px}}
    .app-desc{{color:#8899bb;font-size:12px;margin-top:2px}}
    .app-platforms{{color:#4fc3f7;font-size:11px;margin-top:4px}}
    .app-arrow{{color:#8899bb;flex-shrink:0}}
    .info-row{{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #1a2a3a}}
    .info-row:last-child{{border-bottom:none}}
    .info-label{{color:#8899bb;font-size:13px}}
    .info-value{{font-weight:600;font-size:14px}}
    .days-big{{font-size:22px;font-weight:700}}
    .days-infinite{{color:#66bb6a}}
    .days-expired{{color:#f85149}}
    .days-warn{{color:#ffa726}}
    .days-ok{{color:#66bb6a}}
    .traffic-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:4px}}
    .traffic-cell{{background:#0a1520;border-radius:8px;padding:10px;text-align:center}}
    .traffic-cell.down .traffic-num{{color:#42a5f5}}
    .traffic-cell.up .traffic-num{{color:#ab47bc}}
    .traffic-cell.total .traffic-num{{color:#4fc3f7}}
    .traffic-num{{font-size:15px;font-weight:700}}
    .traffic-label{{color:#8899bb;font-size:11px;margin-top:2px}}
    .status-badge{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;background:#0a1520;border:1px solid {status_color};color:{status_color}}}
    .warn{{background:#2d1b00;border:1px solid #b47c00;color:#ffd479;border-radius:10px;padding:12px 14px;font-size:13px;line-height:1.5;margin-bottom:16px}}
    .share-warning{{background:#0a1520;border:1px solid #b47c00;color:#ffd479;border-radius:10px;padding:12px 14px;font-size:13px;line-height:1.5;margin-bottom:16px}}
    .blocked-banner{{background:#3d0000;border:2px solid #f85149;color:#ff8b87;border-radius:10px;padding:14px 16px;font-size:14px;line-height:1.6;margin-bottom:16px;text-align:center}}
    .footer{{text-align:center;color:#667799;font-size:12px;margin:20px 0}}
    .back{{display:inline-block;margin-top:12px;color:#58a6ff;text-decoration:none;font-size:13px}}
</style>
</head>
<body>
<div class="wrap">
    <div class="warn">⚠️ <strong>Этот сервер использует AmneziaWG (AWG)</strong> — обычное приложение WireGuard его не поддерживает и не сможет подключиться. Используйте приложения из списка ниже.</div>
    {blocked_banner}
    {share_warning}
    <div class="card qr-card">
        <h1>🔑 Подключение VPN</h1>
        <div class="subtitle">Клиент: <strong>{safe_name}</strong></div>
        <img class="qr-img" src="/client/{safe_name}/qr.png" alt="QR-код подключения">
        <div class="qr-hint">Отсканируйте QR-код приложением AmneziaWG</div>
        <div class="options">
            <a href="/client/{safe_name}/conf/{safe_name}.conf" class="option-btn option-primary" download>📥 Скачать конфигурацию (.conf)</a>
            {vpnuri_open}
        </div>
    </div>

    <div class="card">
        <div class="section-title">📖 Как подключиться</div>
        <div class="step">
            <div class="step-num">1</div>
            <div class="step-body">Установите приложение <strong>AmneziaWG</strong> (Android/iOS) или используйте <strong>WG Tunnel</strong> — список ниже.</div>
        </div>
        <div class="step">
            <div class="step-num">2</div>
            <div class="step-body">Скачайте файл конфигурации <strong>.conf</strong> кнопкой выше либо <strong>отсканируйте QR-код</strong> камерой приложения.</div>
        </div>
        <div class="step">
            <div class="step-num">3</div>
            <div class="step-body">В приложении нажмите <strong>«+» / «Добавить»</strong> и выберите импорт конфигурации из файла или по QR-коду.</div>
        </div>
        <div class="step">
            <div class="step-num">4</div>
            <div class="step-body">Нажмите <strong>«Подключить»</strong> — соединение установится через протокол AmneziaWG.</div>
        </div>
    </div>

    <div class="card">
        <div class="section-title">🗂 Подключение через конфигурацию (.conf)</div>
        <div class="step">
            <div class="step-num">1</div>
            <div class="step-body">Скачайте файл <strong>.conf</strong> кнопкой «📥 Скачать конфигурацию» выше. В браузере он сохранится в папку «Загрузки».</div>
        </div>
        <div class="step">
            <div class="step-num">2</div>
            <div class="step-body">Откройте приложение и нажмите кнопку <strong>«+»</strong> (добавить конфигурацию / импортировать из файла).</div>
        </div>
        <div class="step">
            <div class="step-num">3</div>
            <div class="step-body">Укажите путь к скачанному файлу <strong>.conf</strong> — приложение само распознает и добавит профиль AmneziaWG.</div>
        </div>
        <div class="step">
            <div class="step-num">4</div>
            <div class="step-body">Нажмите <strong>«Подключить»</strong> у добавленного профиля. VPN готов к работе. ⚡</div>
        </div>
    </div>

    <div class="card">
        <div class="section-title">📊 Подписка и трафик</div>
        <div class="info-row">
            <span class="info-label">🕒 Осталось дней</span>
            <span class="info-value days-big {days_html_cls}">{days_num}</span>
        </div>
        {expiry_line}
        <div class="info-row">
            <span class="info-label">🔌 Статус подключения</span>
            <span class="info-value"><span class="status-badge">{status_icon} {html_escape(info['status'])}</span></span>
        </div>
        <div class="traffic-grid">
            <div class="traffic-cell down"><div class="traffic-num">⬇ {self.format_bytes(info['rx'])}</div><div class="traffic-label">Скачано</div></div>
            <div class="traffic-cell up"><div class="traffic-num">⬆ {self.format_bytes(info['tx'])}</div><div class="traffic-label">Отправлено</div></div>
        </div>
    </div>

    <div class="card">
        <div class="section-title">📲 Программы для подключения</div>
        <div class="apps">{apps_cards}</div>
    </div>
</div>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(html.encode())

    def get_clients(self):
        try:
            result = subprocess.run('/root/awg/manage_amneziawg.sh stats --json', shell=True, capture_output=True, timeout=5)
            output = result.stdout.strip()
            if not output:
                return []
            clients = json.loads(output)
            return clients if isinstance(clients, list) else []
        except json.JSONDecodeError:
            print(f"⚠️ Невалидный JSON от скрипта: {result.stdout}")
            return []
        except Exception as e:
            print(f"⚠️ Ошибка получения клиентов: {e}")
            return []
    
    def get_client_ip_map(self):
        ip_map = {}
        for f in os.listdir('/root/awg/'):
            if f.endswith('.conf') and f != 'panel.conf':
                name = f[:-5]
                path = os.path.join('/root/awg/', f)
                with open(path) as fh:
                    content = fh.read()
                m = re.search(r'Address\s*=\s*([0-9.]+)', content)
                if m:
                    ip_map[m.group(1)] = name
        return ip_map

    def get_days_left(self, name):
        expiry_path = f'/root/awg/expiry/{name}'
        if not os.path.exists(expiry_path):
            return None
        try:
            with open(expiry_path) as f:
                expiry_ts = int(f.read().strip())
        except (ValueError, OSError):
            return None
        return int((expiry_ts - time.time()) / 86400)

    def format_days_left(self, days_left):
        if days_left is None:
            return '<span style="color:#8899bb" title="Без ограничения">∞</span>'
        if days_left < 0:
            return '<span style="color:#f85149">⚠️ истёк</span>'
        if days_left <= 3:
            return f'<span style="color:#ffa726">⚠️ {days_left} дн.</span>'
        return f'<span style="color:#66bb6a">{days_left} дн.</span>'

    def get_dns_log(self):
        limit = 200
        log_file = '/var/log/dnsmasq.log'
        client_ips = self.get_client_ip_map()
        
        queries = {}
        replies = []
        if os.path.exists(log_file):
            with open(log_file) as f:
                lines = f.readlines()[-limit:]
            for line in lines:
                parts = line.strip().split()
                if len(parts) < 7:
                    continue
                ts = ' '.join(parts[0:3])
                action = parts[4]
                if action.startswith('query['):
                    domain = parts[5]
                    src_ip = parts[-1]
                    queries[domain] = {'ts': ts, 'src_ip': src_ip}
                elif action == 'reply' and len(parts) >= 7:
                    domain = parts[5]
                    ip = parts[7] if len(parts) > 7 else ''
                    if domain and ip:
                        replies.append((ts, domain, ip))
        
        seen = {}
        rows_parts = []
        for ts, domain, ip in reversed(replies):
            key = (domain, ip)
            if key in seen:
                continue
            seen[key] = True
            qinfo = queries.get(domain, {})
            src_ip = qinfo.get('src_ip', '')
            
            client_name = client_ips.get(src_ip, '')
            
            if client_name:
                who_query = f'<span style="color:#66bb6a">👤 {client_name}</span> <span style="color:#8899bb;font-size:11px">({src_ip})</span>'
            elif src_ip:
                who_query = f'<span style="color:#8899bb">{src_ip}</span>'
            else:
                who_query = '<span style="color:#667799">?</span>'
            
            ptr_name = ''
            if ip and not ip.startswith('10.') and not ip.startswith('172.16.') and not ip.startswith('192.168.'):
                try:
                    ptr_name = socket.gethostbyaddr(ip)[0]
                    if len(ptr_name) > 60:
                        ptr_name = ptr_name[:57] + '...'
                except:
                    pass
            
            if client_name:
                who = f'<span style="color:#66bb6a">👤 {client_name}</span>'
            elif ptr_name:
                who = f'<span style="color:#42a5f5">🌐 {ptr_name}</span>'
            else:
                who = f'<span style="color:#8899bb">{ip}</span>'
            
            rows_parts.append(f'<tr><td>{ts}</td><td><code>{domain}</code></td><td>{who}</td><td>{who_query}</td></tr>')
        
        rows = '\n'.join(rows_parts[:100]) if rows_parts else '<tr><td colspan="4" style="text-align:center;color:#667799;">Нет записей — клиенты ещё не переключились на DNS 10.9.9.1</td></tr>'
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>DNS логи - AmneziaWG Panel</title>
            <style>
                body{{background:#0a0e17;color:#e0e0e0;font-family:sans-serif;padding:20px}}
                .container{{max-width:1200px;margin:0 auto}}
                .header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:10px}}
                .header h1{{margin:0;color:#4fc3f7}}
                .card{{background:#111b2b;border-radius:12px;padding:20px;border:1px solid #1a2a3a;margin-bottom:20px}}
                table{{width:100%;border-collapse:collapse;font-size:13px}}
                th,td{{padding:8px 12px;border-bottom:1px solid #1a2a3a;text-align:left}}
                th{{color:#8899bb}}
                code{{color:#e6db74;font-size:12px}}
                .back{{color:#58a6ff;text-decoration:none}}
                .back:hover{{text-decoration:underline}}
                .info{{color:#8899bb;font-size:13px;margin-bottom:12px}}
                tr:hover td{{background:#152030}}
                .refresh{{background:#1f6feb;color:#fff;padding:8px 16px;border:none;border-radius:4px;cursor:pointer;text-decoration:none;font-size:14px}}
                .refresh:hover{{background:#2c89f0}}
            </style>
            <meta http-equiv="refresh" content="15">
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🌐 DNS логи — кто куда ходит</h1>
                    <div>
                        <a href="{ADMIN_PATH}/dns" class="refresh">🔄 Обновить</a>
                        <a href="{ADMIN_PATH}" class="back" style="margin-left:12px">← На панель</a>
                    </div>
                </div>
                <div class="card">
                    <div class="info">🟢 = клиент VPN &nbsp;|&nbsp; 🌐 = внешний сайт &nbsp;|&nbsp; автообновление каждые 15с</div>
                    <table>
                        <tr><th>Время</th><th>Запрошенный домен</th><th>Куда (сайт/клиент)</th><th>Кто запросил</th></tr>
                        {rows}
                    </table>
                </div>
            </div>
        </body>
        </html>'''
    
    def get_dashboard(self, error=None, success=None):
        clients = self.get_clients()
        cleanup_sessions()
        
        # Обработка сообщений
        query = urlparse(self.path).query
        params = parse_qs(query)
        if 'success' in params:
            _nm = params.get('name', [''])[0]
            _pwd = self.get_client_password(_nm)
            _days = params.get('days', [''])[0]
            if params.get('success', [''])[0] == 'extended':
                success = f"✅ Подписка {_nm} продлена на {_days} дней"
            elif params.get('success', [''])[0] == 'deleted':
                success = f"🗑 Клиент {_nm} удалён"
            elif params.get('success', [''])[0] == 'unblocked':
                success = f"🚫 Клиент {_nm} разблокирован"
            else:
                success = f"✅ Добавлен {_nm} на {_days} дней" + (f" · 🔑 Пароль страницы: <code>{html_escape(_pwd)}</code>" if _pwd else "")
        if 'error' in params:
            _er = params.get('error', [''])[0]
            if _er == 'invalid_days':
                error = "❌ Введите корректное число дней (1-365)"
            elif _er == 'extend_failed':
                error = "❌ Не удалось продлить подписку"
            elif _er == 'delete_failed':
                _nm = params.get('name', [''])[0]
                error = f"❌ Не удалось удалить клиента {_nm}"
        
        rows = ''
        total_rx = 0
        total_tx = 0
        for c in clients:
            name = c.get('name', 'unknown')
            ip = c.get('ip', '-')
            status = c.get('status', 'Неизвестно')
            status_color = '#66bb6a' if status == 'Активен' else '#ffa726' if status == 'Недавно' else '#ffa726'
            rx = c.get('rx', 0)
            tx = c.get('tx', 0)
            total_rx += rx
            total_tx += tx
            days_left = self.get_days_left(name)
            pwd = self.ensure_client_password(name)
            blocked_flag = self.is_client_blocked(name)
            name_badge = '<span class="blocked-badge" title="Заблокирован за раздачу">🚫</span> ' if blocked_flag else ''
            unblock_btn = f'''
                            <form method="POST" action="{ADMIN_PATH}/unblock" style="display:inline">
                                <input type="hidden" name="name" value="{name}">
                                <button type="submit" class="btn btn-unblock" title="Разблокировать" onclick="return confirm('Разблокировать {name}?')">🚫</button>
                            </form>''' if blocked_flag else ''
            
            rows += f'''
            <tr>
                <td><strong>{name_badge}{name}</strong></td>
                <td><code>{ip}</code></td>
                <td style="color:{status_color}">{status}</td>
                <td>{self.format_days_left(days_left)}</td>
                <td><span class="traffic-down">⬇ {self.format_bytes(rx)}</span></td>
                <td><span class="traffic-up">⬆ {self.format_bytes(tx)}</span></td>
                <td>
                    <code class="client-pwd" id="pwd_{html_escape(name)}" title="Пароль для страницы клиента">{pwd}</code>
                    <button type="button" class="btn btn-copy" onclick="copyPwd('{html_escape(name)}', this)">📋</button>
                </td>
                <td>
                    <span class="action-icons">
                        <a href="/client/{name}" class="btn btn-client btn-icon" target="_blank" title="Страница клиента">📱</a>
                        {unblock_btn}
                        <form method="POST" action="{ADMIN_PATH}/delete" style="display:inline">
                            <input type="hidden" name="name" value="{name}">
                            <button type="submit" class="btn btn-danger btn-icon" onclick="return confirm('Удалить {name}?')" title="Удалить">🗑</button>
                        </form>
                    </span>
                </td>
            </tr>
            '''
        
        if not rows:
            rows = '<tr><td colspan="8" style="text-align:center;color:#667799;">Нет клиентов</td></tr>'
        
        # Сообщения
        alert_html = ''
        if error:
            alert_html = f'<div style="background:#d32f2f;padding:12px;border-radius:6px;margin-bottom:16px;color:#fff;">{error}</div>'
        if success:
            alert_html = f'<div style="background:#238636;padding:12px;border-radius:6px;margin-bottom:16px;color:#fff;">{success}</div>'

        blocked_ips = self.get_blocked_ips()
        if blocked_ips:
            blocked_names = []
            for c in clients:
                if self.is_client_blocked(c.get('name', '')):
                    blocked_names.append(c.get('name', ''))
            names_html = ', '.join(f'<strong>{html_escape(n)}</strong>' for n in blocked_names) if blocked_names else 'несколько клиентов'
            alert_html += f'''<div class="blocked-alert">🚫 <strong>Заблокировано за раздачу подключения:</strong> {names_html} — доступ приостановлен. Снимите блок кнопкой 🚫 в списке.</div>'''
        
        total = len(clients)
        active = sum(1 for c in clients if c.get('status') == 'Активен')
        recent = sum(1 for c in clients if c.get('status') == 'Недавно')

        client_options = '\n'.join(
            f'<option value="{html_escape(c.get("name", ""))}">{html_escape(c.get("name", ""))}</option>'
            for c in clients
        )
        if not client_options:
            client_options = '<option value="">— нет клиентов —</option>'
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>AmneziaWG Panel</title>
            <style>
                body{{background:#0a0e17;color:#e0e0e0;font-family:sans-serif;padding:20px}}
                .header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:10px}}
                .header h1{{margin:0}}
                .user{{color:#c9d1d9}}
                .logout{{background:#da3633;color:#fff;padding:8px 16px;border:none;border-radius:4px;cursor:pointer}}
                .logout:hover{{background:#f44336}}
                .container{{max-width:1200px;margin:0 auto}}
                .card{{background:#111b2b;border-radius:12px;padding:20px;border:1px solid #1a2a3a;margin-bottom:20px}}
                h1{{color:#4fc3f7}}
                .stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:20px}}
                .stat{{background:#0a1520;border-radius:8px;padding:16px;text-align:center}}
                .stat .num{{font-size:28px;font-weight:700;color:#4fc3f7}}
                .stat .label{{color:#8899bb;font-size:13px}}
                table{{width:100%;border-collapse:collapse}}
                th,td{{padding:12px;border-bottom:1px solid #1a2a3a;text-align:left}}
                th{{color:#8899bb}}
                .btn{{padding:8px 12px;border:none;border-radius:4px;cursor:pointer;font-size:14px;text-decoration:none;display:inline-block;transition:background 0.2s;border:1px solid transparent}}
                .btn-client{{background:#00838f;color:#fff}}
                .btn-client:hover{{background:#00acc1}}
                .btn-icon{{padding:8px 12px}}
                .btn-dns{{background:#00838f;color:#fff}}
                .btn-dns:hover{{background:#00acc1}}
                .btn-danger{{background:#d32f2f;color:#fff}}
                .btn-danger:hover{{background:#f44336}}
                .btn-extend{{background:#1f6feb;color:#fff;padding:6px 10px;font-size:12px;border:none;border-radius:4px;cursor:pointer}}
                .btn-extend:hover{{background:#2c89f0}}
                .btn-unblock{{background:#b45309;color:#fff;padding:8px 12px;font-size:14px;border:none;border-radius:4px;cursor:pointer}}
                .btn-unblock:hover{{background:#d97706}}
                .blocked-badge{{color:#f85149;font-size:14px}}
                .blocked-alert{{background:#3d0000;border:2px solid #f85149;color:#ff8b87;padding:12px;border-radius:6px;margin-bottom:16px}}
                .action-icons{{display:inline-flex;gap:6px;align-items:center;white-space:nowrap}}
                .btn-copy{{background:#0a1520;color:#4fc3f7;padding:4px 8px;font-size:12px;border:1px solid #1a2a3a;cursor:pointer}}
                .btn-copy:hover{{background:#152030}}
                .client-pwd{{color:#4fc3f7;font-size:12px;background:#0a1520;padding:3px 6px;border-radius:4px;word-break:break-all}}
                .action-buttons{{display:flex;gap:8px;flex-wrap:wrap}}
                .add-panel{{background:#0a1520;border-radius:8px;padding:16px;text-align:center}}
                .btn-add{{background:#238636;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;border:none;cursor:pointer}}
                .btn-add:hover{{background:#2ea043}}
                .form-group{{margin:10px 0}}
                label{{display:block;margin-bottom:5px;color:#8899bb}}
                input,select{{width:100%;padding:10px;border-radius:4px;border:1px solid #1a2a3a;background:#0a1520;color:#fff;margin:5px 0;box-sizing:border-box}}
                input:focus{{outline:none;border-color:#4fc3f7}}
                tr:hover td{{background:#152030}}
                .traffic-down{{color:#42a5f5;font-size:13px}}
                .traffic-up{{color:#ab47bc;font-size:13px}}
                small{{color:#8899bb;font-size:12px;display:block;margin-top:4px}}
                .form-row{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
                @media (max-width:768px){{.form-row{{grid-template-columns:1fr}}}}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔐 AmneziaWG Panel</h1>
                    <span class="user">👤 <strong>GreenMan</strong></span>
                    <div style="display:flex;gap:8px;align-items:center">
                        <a href="{ADMIN_PATH}/dns" class="btn btn-dns">🌐 DNS логи</a>
                        <form method="POST" action="{ADMIN_PATH}/logout" style="display:inline">
                            <button type="submit" class="logout">🚪 Выход</button>
                        </form>
                    </div>
                </div>
                
                {alert_html}
                
                <div class="stats">
                    <div class="stat"><div class="num">{total}</div><div class="label">👥 Всего</div></div>
                    <div class="stat"><div class="num" style="color:#66bb6a">{active}</div><div class="label">🟢 Активных</div></div>
                    <div class="stat"><div class="num" style="color:#ffa726">{recent}</div><div class="label">🟡 Недавно</div></div>
                    <div class="stat"><div class="num" style="color:#42a5f5">{self.format_bytes(total_rx)}</div><div class="label">⬇ Всего скачано</div></div>
                    <div class="stat"><div class="num" style="color:#ab47bc">{self.format_bytes(total_tx)}</div><div class="label">⬆ Всего отправлено</div></div>
                </div>
                
                <div class="card">
                    <h2>➕ Добавить друга</h2>
                    <form method="POST" action="{ADMIN_PATH}/add">
                        <div class="form-row">
                            <div class="form-group">
                                <label>👤 Имя клиента</label>
                                <input type="text" name="name" placeholder="Например: friend_01" required>
                            </div>
                            <div class="form-group">
                                <label>📅 Срок действия (дни)</label>
                                <input type="number" name="expires_days" min="1" max="365" step="1" placeholder="Введите количество дней" value="7" required>
                                <small>Введите любое число от 1 до 365 дней</small>
                            </div>
                        </div>
                        <button type="submit" class="btn-add">➕ Добавить друга</button>
                    </form>
                </div>
                
                <div class="card">
                    <h2>⏳ Продлить подписку</h2>
                    <form method="POST" action="{ADMIN_PATH}/extend" class="extend-form">
                        <div class="form-row">
                            <div class="form-group">
                                <label>👤 Клиент</label>
                                <select name="name" required>{client_options}</select>
                            </div>
                            <div class="form-group">
                                <label>📅 Добавить дней</label>
                                <input type="number" name="add_days" min="1" max="365" step="1" value="30" required>
                                <small>Дни добавятся к текущему сроку</small>
                            </div>
                        </div>
                        <button type="submit" class="btn-add">➕ Продлить</button>
                    </form>
                </div>
                
                <div class="card">
                    <h2>👥 Список друзей</h2>
                    <table>
                        <tr>
                            <th>Имя</th>
                            <th>IP</th>
                            <th>Статус</th>
                            <th>Осталось дней</th>
                            <th>⬇ Скачано</th>
                            <th>⬆ Отправлено</th>
                            <th>🔑 Пароль</th>
                            <th>Действия</th>
                        </tr>
                        {rows}
                    </table>
                </div>
            </div>
            <script>
                function copyPwd(name, btn) {{
                    const el = document.getElementById('pwd_' + name);
                    const text = el ? el.textContent : name;
                    const done = function() {{ btn.textContent = '✅'; setTimeout(function() {{ btn.textContent = '📋'; }}, 1200); }};
                    if (navigator.clipboard && navigator.clipboard.writeText) {{
                        navigator.clipboard.writeText(text).then(done).catch(function() {{}});
                    }} else {{
                        const ta = document.createElement('textarea');
                        ta.value = text; document.body.appendChild(ta); ta.select();
                        try {{ document.execCommand('copy'); done(); }} catch(e) {{}}
                        document.body.removeChild(ta);
                    }}
                }}
            </script>
        </body>
        </html>'''
    
    def get_login_page(self, error=None):
        error_html = f'<div style="color:#f85149;margin:10px 0;padding:10px;background:#d32f2f;border-radius:4px">{error}</div>' if error else ''
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Вход в AmneziaWG Panel</title>
            <style>
                body{{background:#0a0e17;color:#e0e0e0;font-family:sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}
                .login{{background:#161b22;border-radius:12px;padding:40px;width:100%;max-width:400px}}
                h1{{color:#4fc3f7;text-align:center;margin-bottom:30px}}
                .form-group{{margin-bottom:20px}}
                label{{display:block;margin-bottom:5px;color:#8899bb}}
                input{{width:100%;padding:12px;border-radius:6px;border:1px solid #1a2a3a;background:#0a1520;color:#fff;font-size:16px;box-sizing:border-box}}
                input:focus{{outline:none;border-color:#1f6feb}}
                .btn{{width:100%;padding:12px;border:none;border-radius:6px;cursor:pointer;font-size:16px;font-weight:bold;margin-top:10px}}
                .btn-primary{{background:#1f6feb;color:#fff}}
                .btn-primary:hover{{background:#2c89f0}}
                .footer{{text-align:center;color:#8899bb;margin-top:20px;font-size:14px}}
            </style>
        </head>
        <body>
            <div class="login">
                <h1>🔐 AmneziaWG Panel</h1>
                {error_html}
                <form method="POST" action="{ADMIN_PATH}/login">
                    <div class="form-group">
                        <label for="username">Имя пользователя</label>
                        <input type="text" id="username" name="username" required placeholder="Логин">
                    </div>
                    <div class="form-group">
                        <label for="password">Пароль</label>
                        <input type="password" id="password" name="password" required placeholder="Пароль">
                    </div>
                    <button type="submit" class="btn btn-primary">Войти</button>
                </form>
                <p class="footer">AmneziaWG Panel v2.0</p>
            </div>
        </body>
        </html>'''

def main():
    print("✅ AmneziaWG Panel v2.0")
    print(f"📡 Running on http://{PANEL_HOST}:{PANEL_PORT}")
    print(f"🔑 Админ-путь: {ADMIN_PATH}")
    print("📅 Теперь можно указывать произвольный срок действия (1-365 дней)")
    
    ThreadingHTTPServer((PANEL_HOST, PANEL_PORT), Handler).serve_forever()

if __name__ == '__main__':
    main()