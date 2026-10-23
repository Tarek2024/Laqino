"""Phase 15: medical notifications wake subscribed devices with generic, privacy-safe push."""
import os, tempfile, threading, time, json, urllib.request
DB=tempfile.mktemp(suffix='.db'); UP=tempfile.mkdtemp(prefix='laqino-p15-')
os.environ['LAQINO_DB']=DB; os.environ['LAQINO_UPLOADS']=UP
import server, rx, fcm
from http.server import ThreadingHTTPServer
server.init('01000000000','AdminPass123')
c=server.db()
try:
    now=int(time.time()); salt='34'*16
    uid=c.execute("INSERT INTO users(phone,name,pw_hash,salt,role,created_at) VALUES(?,?,?,?,?,?)",('01066667777','عميل',server.hp('password1',salt),salt,'customer',now)).lastrowid
    endpoint='https://fcm.googleapis.com/test-endpoint'
    c.execute("INSERT INTO push_subs(endpoint,user_id,created_at) VALUES(?,?,?)",(endpoint,uid,now))
    c.execute("INSERT INTO notifications(user_id,kind,title,body,link,ref_type,ref_id,created_at) VALUES(?,?,?,?,?,?,?,?)",(uid,'rx.claim_timeout','انتهت المهلة','روشتة #123','medical','prescription',123,now))
    c.commit()
finally: c.close()
# Public push state exposes counts only, keyed by the device endpoint.
srv=ThreadingHTTPServer(('127.0.0.1',0),server.H); threading.Thread(target=srv.serve_forever,daemon=True).start()
req=urllib.request.Request('http://127.0.0.1:%d/api/push/state'%srv.server_address[1],json.dumps({'endpoint':endpoint}).encode(),{'Content-Type':'application/json'},method='POST')
with urllib.request.urlopen(req,timeout=5) as resp: state=json.loads(resp.read())
assert state.get('medical')==1 and 'title' not in state and 'body' not in state, state
# Android push text is generic; no prescription id, medicine, price, or customer data.
msg=fcm.build_message('testtokenabcdefghijklmnopqrstuvwxyz','medical',3600)['message']
assert msg['notification']['body']=='عندك تحديث بخصوص طلبك الطبي' and msg['data']['kind']=='medical', msg
assert '123' not in json.dumps(msg) and 'روشتة' not in json.dumps(msg), msg
# rx notification callback is best-effort and receives only user id + generic notification kind.
seen=[]; old=rx.push_hook; rx.push_hook=lambda user_id,kind: seen.append((user_id,kind))
try:
    c=server.db()
    rx._notify(c,uid,'rx.quote','وصلك رد','راجع طلبك','medical',124)
    c.commit(); c.close()
finally: rx.push_hook=old
assert seen==[(uid,'rx.quote')], seen
print('PASS push state returns unread medical count only')
print('PASS FCM medical payload is generic and contains no prescription details')
print('PASS RX notification hook is called with minimal identifiers')
srv.shutdown(); srv.server_close()
