# phase-83 / خطوة 1: المحل يطلب مندوب عبر static/pdelivery.js المشترك (إعداد data-pd=shop) — بدون تكرار الكود. فحص ثابت + تشغيل المكتبة في node (DOM وهمي، ليس متصفحًا حقيقيًا).
import os, re, json, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); rd = lambda *p: open(os.path.join(HERE, *p), encoding="utf-8").read()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
shop, pd, sw = rd("static", "shop.html"), rd("static", "pdelivery.js"), rd("static", "sw.js")
ok("shop.html loads shared pdelivery.js with data-pd=shop before its inline script", re.search(r'<script src="/pdelivery\.js" data-pd="shop"></script><script>', shop) is not None)
ok("shop.html has no duplicated delivery card/rows code", not re.search(r"const (dlrows|dltrk|dltxt|dlmin)=|const DLS=", shop) and "PDL.card(" in shop)
ok("pharmacy.html still loads pdelivery.js without data-pd", '<script src="/pdelivery.js"></script>' in rd("static", "pharmacy.html"))
ok("version bumped to phase-83 / laqino-v126", "release=phase-83" in rd("VERSION") and "cache=laqino-v126" in rd("VERSION") and 'laqino-v126' in sw)
JS = r"""
const fs=require('fs'),vm=require('vm');const src=fs.readFileSync(process.argv[1],'utf8');
const run=shop=>{const ctx={document:{currentScript:shop?{dataset:{pd:'shop'}}:null,getElementById:()=>({}),addEventListener(){},hidden:false},esc:x=>String(x),api:async()=>({enabled:false,items:[]}),T:'t',MutationObserver:class{observe(){}},setInterval:()=>0,navigator:{},console};ctx.window=ctx;vm.createContext(ctx);vm.runInContext(src,ctx);return ctx};
const row={id:7,status:'assigned',courier_name:'أحمد',courier_phone:'01011112222',created_at:1,accepted_at:5};
const out={};for(const k of ['shop','pharm']){const c=run(k=='shop');out[k]={has:!!c.PDL,dl:typeof c.dlsend,card:c.PDL.card({items:[]},{dlp:'0100',dlm:'5',dln:'x'}),rows:c.PDL.rows([row]),txt:c.PDL.txt([row])}}
console.log(JSON.stringify(out));"""
r = subprocess.run(["node", "-e", JS, os.path.join(HERE, "static", "pdelivery.js")], capture_output=True, text=True, timeout=30)
if r.returncode: print(r.stderr[:500])
o = json.loads(r.stdout); S, P = o["shop"], o["pharm"]
ok("shop mode: library only (no pharmacy poll/dlsend injected)", S["has"] and S["dl"] == "undefined")
ok("pharmacy mode: unchanged (dlsend defined, text says صيدليتك)", P["dl"] == "function" and "من صيدليتك" in P["card"] and "للصيدلية" in P["rows"])
ok("shop texts say المحل / للمحل", "من محلك" in S["card"] and "للمحل" in S["rows"] and "صيدليتك" not in S["card"])
ok("courier name and phone show with acceptance (both modes)", all("أحمد" in x["rows"] and "tel:01011112222" in x["rows"] and "أحمد" in x["txt"] for x in (S, P)))
ok("card keeps typed values when re-rendered (shop passes TXF)", 'value="0100"' in S["card"] and 'value="5"' in S["card"])
