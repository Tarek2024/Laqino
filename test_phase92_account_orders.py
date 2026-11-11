"""Phase 92: account order history grouping must not change delivery lifecycle."""
import pathlib
import subprocess

root = pathlib.Path(__file__).resolve().parent
source = (root / "static" / "index.html").read_text(encoding="utf-8")

assert "api('/delivery/orders')" in source, "customer account must keep using the existing unified delivery API"
assert "window.rt=run(async id=>{await api('/delivery/orders/'+id+'/rate'" in source, "rating action/API must remain available"
assert "const deliveryOrderBuckets=o=>" in source, "account order buckets helper is missing"
assert "render(groups.current)" in source and "render(groups.previous)" in source, "both account sections must render delivery cards"

helper_start = source.index("const deliveryOrderBuckets=o=>")
helper_end = source.index("\nasync function mine()", helper_start)
helper = source[helper_start:helper_end]
pord_start = source.index("const pordCards=l=>")
pord_end = source.index("\nasync function prods()", pord_start)
pord = source[pord_start:pord_end]

program = r"""
const esc = x => String(x == null ? '' : x);
const money = x => String(x == null ? '' : x);
const pcls = x => x;
const PL = {completed:'تم التسليم', cancelled:'ملغي'};
const STEP = {};
const ST = {completed:'تم التسليم', cancelled:'ملغي'};
const sc3 = () => '';
const shopTrk = () => '';
const shopBill = () => '';
const cpm = () => '';
const IC = {rcpt:'', moto:'', bag:''};
const empty = () => '<div class="empty"></div>';
const LIVE = ['searching','assigned','heading_pickup','picked_up','heading_customer','arrived','awaiting_confirmation'];
const window = {_bp:{}};
""" + helper + "\n" + pord + r"""
const rows = [
 {id:1,status:'searching',origin_type:null},
 {id:2,status:'assigned',origin_type:'shop_order'},
 {id:3,status:'picked_up',origin_type:'product_order'},
 {id:4,status:'awaiting_confirmation',origin_type:'provider_pickup'},
 {id:5,status:'disputed',origin_type:null,medical_source:'prescription'},
 {id:6,status:'completed',origin_type:null,medical_source:'inquiry',rated:false},
 {id:7,status:'completed',origin_type:'product_order',rated:true},
 {id:8,status:'cancelled',origin_type:'shop_order'}
];
const groups = deliveryOrderBuckets(rows);
if (groups.current.map(x=>x.id).join(',') !== '1,2,3,4,5') throw new Error('current bucket lost or misclassified a live/disputed source');
if (groups.previous.map(x=>x.id).join(',') !== '6,7,8') throw new Error('completed/cancelled bucket is incorrect');
const pendingRating = deliveryOrderCard({id:6,status:'completed',rated:false});
const rated = deliveryOrderCard({id:7,status:'completed',rated:true});
const cancelled = deliveryOrderCard({id:8,status:'cancelled',rated:false});
if (!pendingRating.includes('قيّم المندوب')) throw new Error('completed unrated order must keep its rating action in history');
if (rated.includes('قيّم المندوب')) throw new Error('already-rated order must not show a second rating action');
if (!cancelled.includes('ملغي')) throw new Error('cancelled order must retain its cancelled status');
const pharmacy = pordCards([
 {id:11,status:'new',pharmacy:'صيدلية أ',items:[],items_total:0},
 {id:12,status:'rejected',pharmacy:'صيدلية ب',items:[],items_total:0},
 {id:13,status:'cancelled',pharmacy:'صيدلية ج',items:[],items_total:0}
]);
if (!pharmacy.includes('طلبات الصيدليات الحالية') || !pharmacy.includes('طلبات الصيدليات السابقة')) throw new Error('pre-delivery pharmacy orders must also be separated');
if (!pharmacy.includes('إلغاء الطلب') || !pharmacy.includes('الصيدلية اعتذرت') || !pharmacy.includes('ملغي')) throw new Error('pharmacy order actions/statuses were lost');
console.log('PASS account current/history grouping across direct, shop, pharmacy-product, prescription-linked orders');
console.log('PASS completed unrated orders remain rateable from history');
console.log('PASS cancelled orders remain labelled in history');
console.log('PASS pre-delivery pharmacy product orders are grouped separately');
"""
run = subprocess.run(["node", "-e", program], cwd=root, capture_output=True, text=True)
if run.returncode:
    raise SystemExit(run.stdout + run.stderr)
print(run.stdout, end="")
