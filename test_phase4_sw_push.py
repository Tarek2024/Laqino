# المرحلة 4: منطق Web Push في static/sw.js (تنبيه المندوب لا يتغير + فرع المحادثة). يشغّل معالجات sw.js الحقيقية في vm؛ ليس متصفحًا ولا خدمة Push حقيقية.
import os, json, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); HAR = os.path.join(HERE, "test_sw_push_harness.js")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n) or (c or exit(1))
vis = lambda p: [{"visibilityState": "visible", "url": "https://app.example" + p}]
SC = [{"name": "order", "state": {"pending": 2, "chat": 0, "courier": True}},
      {"name": "order_wins_over_chat", "state": {"pending": 1, "chat": 3, "courier": True}},
      {"name": "idle", "state": {"pending": 0, "chat": 0, "courier": True}},
      {"name": "chat", "state": {"pending": 0, "chat": 1, "courier": False}},
      {"name": "chat_many", "state": {"pending": 0, "chat": 4, "courier": False}},
      {"name": "chat_market_visible", "state": {"pending": 0, "chat": 2, "courier": False}, "windows": vis("/market.html")},
      {"name": "courier_page_visible", "state": {"pending": 3, "chat": 0, "courier": True}, "windows": vis("/courier.html")},
      {"name": "offline_default", "state": "fail"},
      {"name": "offline_known_courier", "state": "fail", "meta": {"courier": True}},
      {"name": "offline_known_not_courier", "state": "fail", "meta": {"courier": False}},
      {"name": "no_subscription", "state": {"pending": 0, "chat": 0}, "noSub": True},
      {"name": "old_server_no_chat_field", "state": {"pending": 0}},
      {"name": "click_chat", "click": {"url": "/market.html#/chats"}},
      {"name": "click_default", "click": {"x": 1}}]
r = subprocess.run(["node", HAR, json.dumps(SC)], capture_output=True, text=True, timeout=60)
if r.returncode: print(r.stderr[:800])
R = {x["name"]: x for x in json.loads(r.stdout)}
one = lambda n: R[n]["shown"][0]
ok("order alert unchanged: loud, requireInteraction, courier url", one("order")["title"] == "لاقينو — طلب توصيل جديد" and one("order")["requireInteraction"] and one("order")["url"] == "/courier.html" and one("order")["tag"] == "laqino-order")
ok("order alert wins when there are also chat messages", len(R["order_wins_over_chat"]["shown"]) == 1 and one("order_wins_over_chat")["tag"] == "laqino-order")
ok("idle (nothing pending, no chat): silent note then cleared (unchanged)", len(R["idle"]["shown"]) == 1 and one("idle")["silent"] and R["idle"]["closed"] >= 1)
ok("chat only: plain chat notification, opens the chats page, not an order alert", len(R["chat"]["shown"]) == 1 and one("chat")["tag"] == "laqino-chat" and one("chat")["url"] == "/market.html#/chats" and not one("chat")["requireInteraction"] and "طلب توصيل" not in one("chat")["title"])
ok("several unread chat messages -> plural wording", "رسائل" in one("chat_many")["title"])
ok("chat push while the market page is on screen shows nothing", R["chat_market_visible"]["shown"] == [])
ok("courier page on screen: no notification (unchanged)", R["courier_page_visible"]["shown"] == [])
ok("offline with no hint: fails OPEN with the order alert (unchanged)", one("offline_default")["tag"] == "laqino-order")
ok("offline on a known courier: order alert", one("offline_known_courier")["tag"] == "laqino-order")
ok("offline on a known NON-courier: never a courier alert", one("offline_known_not_courier")["tag"] == "laqino-chat")
ok("no subscription behaves as before (fail-open order alert); old server without chat field behaves as idle", one("no_subscription")["tag"] == "laqino-order" and one("old_server_no_chat_field")["silent"])
ok("notification click opens the url carried by the notification (default courier page)", R["click_chat"]["opened"] == "/market.html#/chats" and R["click_default"]["opened"] == "/courier.html")
print("ALL PASSED")
