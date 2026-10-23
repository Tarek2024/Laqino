"""Phase 44 smoke tests: registration page is separate and legacy auth APIs remain compatible."""
import json, os, tempfile, threading, urllib.request, urllib.error
from http.server import ThreadingHTTPServer

os.environ['LAQINO_DB'] = tempfile.mktemp(suffix='.db')
os.environ['LAQINO_UPLOADS'] = tempfile.mkdtemp()
import server
server.init('01000000000', 'AdminPass123')
httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.H)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%s' % httpd.server_address[1]

def request(path, method='GET', data=None, token=None):
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read()
            return r.status, raw.decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')

def check(name, ok):
    print(('PASS ' if ok else 'FAIL ') + name)
    if not ok:
        raise SystemExit(1)

try:
    status, home = request('/')
    check('home page serves login-only form', status == 200 and 'تسجيل الدخول' in home and 'id="ph"' in home and 'href="/register.html"' in home)
    check('home auth form no longer includes registration name field', 'id="nm"' not in home and "auth('register')" not in home)
    status, regpage = request('/register.html')
    check('dedicated registration page serves required fields', status == 200 and 'id="name"' in regpage and 'id="phone"' in regpage and 'id="password2"' in regpage)
    check('registration reuses existing phone verification APIs', "'/verify/start'" in regpage and "'/verify/status'" in regpage and "'/register'" in regpage and "'/login'" in regpage)
    phone = '01055554444'
    st, body = request('/api/register', 'POST', {'name':'Phase44 Test','phone':phone,'password':'TestPass123'})
    check('existing registration API still creates an account', st == 201)
    st, body = request('/api/login', 'POST', {'phone':phone,'password':'TestPass123'})
    token = json.loads(body).get('token') if st == 200 else None
    check('existing login API accepts newly registered account', st == 200 and bool(token))
    st, me = request('/api/me', token=token)
    check('new session authenticates against existing /me endpoint', st == 200 and 'Phase44 Test' in me)
    st, _ = request('/api/logout', 'POST', {}, token)
    check('logout endpoint remains available', st == 200)
    st, _ = request('/api/me', token=token)
    check('logged-out session is rejected', st == 401)
finally:
    httpd.shutdown()
    try: os.unlink(os.environ['LAQINO_DB'])
    except OSError: pass
