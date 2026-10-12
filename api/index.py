import json, os, urllib.request
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler

RU = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
RT = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")

def rd(*cmd):
    req = urllib.request.Request(RU, json.dumps(list(cmd)).encode(),
        {"Authorization": "Bearer " + RT, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["result"]

def load():
    v = rd("GET", "links")
    return json.loads(v) if v else []

def save(l): rd("SET", "links", json.dumps(l))

def tg(token, method, data=None):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        json.dumps(data or {}).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

class handler(BaseHTTPRequestHandler):
    def reply(self, data, code=200):
        b = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def go(self, method):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        p = qs.get("r", [u.path])[0]
        q = qs.get("id", [None])[0]
        n = int(self.headers.get("Content-Length") or 0)
        try: b = json.loads(self.rfile.read(n).decode()) if n else {}
        except: b = {}

        if p == "/api/csrf":
            return self.reply({"csrfToken": "local", "token": "local", "csrf": "local"})
        if p == "/api/auth/session":
            return self.reply({"uid": "local"})
        if p == "/api/auth/logout":
            return self.reply({"ok": True})

        if p == "/api/debug":
            return self.reply({"env": [k for k in os.environ if any(x in k for x in ("KV","REDIS","UPSTASH","STORAGE"))]})
        links = load()
        if p == "/api/links/list":
            return self.reply(links)

        if p in ("/api/links/create", "/api/links/update"):
            tok = b.get("botToken", "").strip()
            chat = b.get("chatId", "").strip()
            try:
                name = tg(tok, "getMe")["result"]["username"]
            except Exception as e:
                return self.reply({"error": "❌ Token inválido: " + str(e)}, 400)
            if p.endswith("create"):
                nid = str(max([int(l["id"]) for l in links] + [0]) + 1)
                links.append({"id": nid, "botToken": tok, "chatId": chat,
                              "botName": name, "status": "active"})
            else:
                for l in links:
                    if l["id"] == q:
                        l.update({"botToken": tok, "chatId": chat, "botName": name})
            save(links)
            return self.reply({"ok": True})

        if p == "/api/links/delete":
            links[:] = [l for l in links if l["id"] != q]
            save(links)
            return self.reply({"ok": True})

        if p == "/api/send":
            txt = b.get("text") or b.get("message") or ""
            try:
                return self.reply({"ok": True, "telegram": tg(
                    b.get("botToken"), "sendMessage",
                    {"chat_id": b.get("chatId"), "text": txt})})
            except Exception as e:
                return self.reply({"error": str(e)}, 400)

        self.reply({"error": "ruta desconocida"}, 404)

    def do_GET(self): self.go("GET")
    def do_POST(self): self.go("POST")
    def do_PUT(self): self.go("PUT")
    def do_DELETE(self): self.go("DELETE")

_orig = handler.go
def _safe(self, m):
    try:
        _orig(self, m)
    except Exception as e:
        self.reply({"error": "ERR: " + repr(e)}, 500)
handler.go = _safe
