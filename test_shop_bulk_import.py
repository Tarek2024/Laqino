# اختبارات استيراد أصناف المحلات من Excel — قاعدة بيانات مؤقتة ومعزولة.
import os, json, threading, urllib.request, urllib.error, tempfile, time, sqlite3, base64, io, zipfile
os.environ["LAQINO_DB"] = tempfile.mktemp(suffix=".db")
os.environ["LAQINO_UPLOADS"] = tempfile.mkdtemp()
import server, bulk_import, shop_bulk_import
from http.server import ThreadingHTTPServer

server.init("01000000000", "AdminPass123")
PORT = 8973
BASE = "http://127.0.0.1:%d" % PORT
DB = os.environ["LAQINO_DB"]
threading.Thread(target=ThreadingHTTPServer(( "127.0.0.1", PORT), server.H).serve_forever, daemon=True).start()
time.sleep(.3)

def call(method, path, data=None, token=None):
    req = urllib.request.Request(BASE + "/api" + path,
        json.dumps(data).encode() if data is not None else None,
        {"Content-Type":"application/json", **({"Authorization":"Bearer "+token} if token else {})},
        method=method)
    try:
        r = urllib.request.urlopen(req)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def sql(query, *args):
    c=sqlite3.connect(DB); out=c.execute(query,args).fetchall(); c.commit(); c.close(); return out

def ok(label, condition):
    print(("PASS " if condition else "FAIL ")+label)
    if not condition: raise SystemExit(1)

def user(phone):
    call("POST","/register",{"phone":phone,"name":"u"+phone[-3:],"password":"password1"})
    token=call("POST","/login",{"phone":phone,"password":"password1"})[1]["token"]
    return token

def xlsx(rows):
    ct=('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
    root=('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    wb=('<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="الأصناف" sheetId="1" r:id="rId1"/></sheets></workbook>')
    rels=('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",ct); z.writestr("_rels/.rels",root); z.writestr("xl/workbook.xml",wb)
        z.writestr("xl/_rels/workbook.xml.rels",rels)
        z.writestr("xl/worksheets/sheet1.xml",bulk_import._sheet_xml(rows,[24,14,30,12]))
    return base64.b64encode(b.getvalue()).decode()

admin=call("POST","/login",{"phone":"01000000000","password":"AdminPass123"})[1]["token"]
owner=user("01080000001")
customer=user("01080000002")
region=call("GET","/regions?parent_id=3")[1][0]["id"]
call("POST","/admin/shops-settings",{"enabled":True},admin)
shop=call("POST","/shops/apply",{"type_id":1,"name_ar":"مطعم الاستيراد","address":"شارع النصر","phone":"01012345678","region_id":region},owner)[1]["id"]
call("POST",f"/admin/shops/{shop}/review",{"status":"approved"},admin)
prefix="/admin/shops/items-import"
rows=[["اسم الصنف","السعر","الوصف","متاح"]]+[["صنف تجريبي %03d"%i, str(i+1)+".50", "وصف "+str(i), "نعم" if i%2 else "لا"] for i in range(100)]
data=xlsx(rows)
ok("staff/customer cannot import", call("POST",prefix+"/preview",{"shop_id":shop,"data":data},customer)[0]==403)
ok("template endpoint returns xlsx", call("GET",prefix+"/template",None,admin)[0]==200 and call("GET",prefix+"/template",None,admin)[1]["name"].endswith(".xlsx"))
status, preview=call("POST",prefix+"/preview",{"shop_id":shop,"data":data},admin)
ok("100 Arabic rows preview as new without writing", status==200 and preview["summary"]["new"]==100 and sql("SELECT COUNT(*) FROM shop_items WHERE shop_id=?",(shop)[0][0]==0)
status, done=call("POST",prefix+"/commit",{"shop_id":shop,"data":data},admin)
ok("commit inserts all 100 items", status==200 and done["done"]["inserted"]==100 and sql("SELECT COUNT(*) FROM shop_items WHERE shop_id=? AND status='active'",shop)[0][0]==100)
items=call("GET",f"/owner/shops/{shop}/items",None,owner)[1]["items"]
first=items[0]
ok("imported items use the owner's normal edit endpoint", call("POST",f"/owner/shops/{shop}/items/{first['id']}/edit",{"name_ar":"صنف تم تعديله","price":77},owner)[0]==200 and call("GET",f"/owner/shops/{shop}/items",None,owner)[1]["items"][0]["name_ar"]=="صنف تم تعديله")
ok("old imported rows remain and are not overwritten by another import", call("POST",prefix+"/commit",{"shop_id":shop,"data":xlsx([["اسم الصنف","السعر"],["صنف تجريبي 000","999"]])},admin)[0]==409 and sql("SELECT COUNT(*) FROM shop_items WHERE shop_id=? AND status='active'",shop)[0][0]==100)
mixed=xlsx([["اسم الصنف","السعر","الوصف","متاح"],["صنف جديد","15.75","وصف","نعم"],["صنف جديد","20","","نعم"],["سعر خاطئ","abc","","نعم"]])
status, p=call("POST",prefix+"/preview",{"shop_id":shop,"data":mixed},admin)
ok("preview reports within-file duplicates and invalid prices", status==200 and p["summary"]=={"new":1,"duplicate":1,"error":1})
ok("existing records are not deleted or modified by a new import", call("POST",prefix+"/commit",{"shop_id":shop,"data":mixed},admin)[0]==200 and sql("SELECT COUNT(*) FROM shop_items WHERE shop_id=? AND status='active'",shop)[0][0]==101)
# Type 2 has require_image enabled in this isolated database; imports must not bypass that rule.
sql("UPDATE shop_types SET require_image=1 WHERE id=2")
shop2=call("POST","/shops/apply",{"type_id":2,"name_ar":"سوبر ماركت الصور","address":"شارع النصر","phone":"01012345678","region_id":region},owner)[1]["id"]
call("POST",f"/admin/shops/{shop2}/review",{"status":"approved"},admin)
status,p=call("POST",prefix+"/preview",{"shop_id":shop2,"data":xlsx([["اسم الصنف","السعر"],["زيت","50"]])},admin)
ok("require_image shop rejects image-less Excel rows",status==200 and p["require_image"] is True and p["summary"]["error"]==1)
ok("audit records bulk import",sql("SELECT COUNT(*) FROM audit_log WHERE action='shopitem.bulk_import'")[0][0]>=2)
print("ALL PASS")
