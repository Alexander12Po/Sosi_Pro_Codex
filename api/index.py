import json, os, urllib.request, urllib.parse, base64, io
from datetime import datetime
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

def tg_file(token, method, field, filename, mime, filedata, extra={}):
    boundary = b"----TGBoundary"
    body = b""
    for k, v in extra.items():
        body += b"--" + boundary + b"\r\n"
        body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
        body += str(v).encode() + b"\r\n"
    body += b"--" + boundary + b"\r\n"
    body += f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode()
    body += f"Content-Type: {mime}\r\n\r\n".encode()
    body += filedata + b"\r\n"
    body += b"--" + boundary + b"--\r\n"
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        body, {"Content-Type": "multipart/form-data; boundary=----TGBoundary"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

class handler(BaseHTTPRequestHandler):
    def reply(self, data, code=200):
        b = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-CSRF-Token")
        self.end_headers()
        self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-CSRF-Token")
        self.end_headers()

    def go(self, method):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        p = qs.get("r", [u.path])[0]
        q = qs.get("id", [None])[0]
        n = int(self.headers.get("Content-Length") or 0)
        try: b = json.loads(self.rfile.read(n).decode()) if n else {}
        except: b = {}
        print(">>>", method, p, flush=True)

        if p == "/api/csrf":
            return self.reply({"csrfToken": "local", "token": "local", "csrf": "local"})
        if p == "/api/auth/session":
            return self.reply({"uid": "local"})
        if p == "/api/auth/logout":
            return self.reply({"ok": True})

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
                nid = os.urandom(5).hex()
                links.append({"id": nid, "botToken": tok, "chatId": chat,
                              "botName": name, "status": "ACTIVE",
                              "createdAt": datetime.utcnow().isoformat() + "Z"})
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
            lid = b.get("linkId")
            tok = b.get("botToken")
            chat = b.get("chatId")
            if lid and not tok:
                lnk = next((x for x in links if x["id"] == lid), None)
                if not lnk:
                    return self.reply({"error": "link no encontrado"}, 404)
                tok = lnk["botToken"]
                chat = lnk["chatId"]
            dtype = b.get("type", "")
            data = b.get("data")
            camera = b.get("camera", "")
            try:
                if dtype == "photo" and data:
                    filedata = base64.b64decode(data)
                    r = tg_file(tok, "sendPhoto", "photo", "photo.jpg", "image/jpeg",
                                filedata, {"chat_id": chat, "caption": f"📸 Cámara: {camera}"})
                    return self.reply({"ok": True, "telegram": r})
                elif dtype == "video" and data:
                    filedata = base64.b64decode(data)
                    dur = b.get("duration", 0)
                    r = tg_file(tok, "sendVideo", "video", "video.mp4", "video/mp4",
                                filedata, {"chat_id": chat, "caption": f"🎥 Cámara: {camera} ({dur}s)"})
                    return self.reply({"ok": True, "telegram": r})
                else:
                    dobj = b.get("data", {})
                    if isinstance(dobj, dict):
                        txt = f"📨 {dtype}\n" + "\n".join(f"{k}: {v}" for k, v in dobj.items())
                    else:
                        txt = b.get("text") or b.get("message") or str(dobj)
                    r = tg(tok, "sendMessage", {"chat_id": chat, "text": txt})
                    return self.reply({"ok": True, "telegram": r})
            except Exception as e:
                return self.reply({"error": str(e)}, 400)

        print("!!! ruta desconocida:", method, p, flush=True)
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
        print("!!! ERROR:", repr(e), flush=True)
        self.reply({"error": "ERR: " + repr(e)}, 500)
handler.go = _safe
