# مساعد الاختبارات: تقديم طلب مندوب مع مستندات (الاعتماد يتطلب صورتي البطاقة).
import os, base64, tempfile, server
if not os.environ.get("LAQINO_UPLOADS"): server.UP = tempfile.mkdtemp()
if not os.environ.get("LAQINO_TEST_PRESENCE"): server.PRESENCE_ENFORCED = False  # legacy tests predate heartbeat; new presence tests set LAQINO_TEST_PRESENCE=1 before importing
from imgutil import png
def apply_docs(call, token, region=3, selfie=False):
    ids = {k: call("POST", "/files", {"data": png()}, token)[1]["id"] for k in (("id_front_file_id", "id_back_file_id") + (("selfie_file_id",) if selfie else ()))}
    return call("POST", "/couriers/apply", {"region_id": region, **ids}, token)

def fare_ok(oid):
    """اختصار للاختبارات القديمة التي لا تختبر الأجرة: يعتبر العميل وافق على أجرة الطلب كي يبدأ التوصيل. مسار الاقتراح/الموافقة/الرفض الحقيقي مغطّى في test_phase25_fare.py."""
    import sqlite3; c = sqlite3.connect(os.environ["LAQINO_DB"]); c.execute("UPDATE delivery_orders SET fare_status='approved' WHERE id=?", (oid,)); c.commit(); c.close()
def server_fee(oid):
    """الأجرة المخزّنة على الطلب (لا تُعرض للعميل قبل اقتراح المندوب)."""
    import sqlite3; c = sqlite3.connect(os.environ["LAQINO_DB"]); r = c.execute("SELECT fee FROM delivery_orders WHERE id=?", (oid,)).fetchone(); c.close(); return r[0]
