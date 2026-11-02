"""What the phone server answers: the app's endpoints minus PC-only ones."""

import json
import re
import secrets
import time
import urllib.parse
from pathlib import Path

from jobslop.config import RES_DIR
from jobslop.server.handler import Handler, load_page
from jobslop.server.phone import PHONE_BLOCKED, PHONE_LOGIN, phone, phone_settings
from jobslop.settings import update_settings


class PhoneHandler(Handler):
    """Serves the app to phones on the home network. Everything needs a PIN session."""

    def _session(self):
        m = re.search(r"(?:^|;\s*)jfs=([\w-]+)", self.headers.get("Cookie", ""))
        return bool(m) and m[1] in phone_settings().get("sessions", [])

    def app_ok(self):
        origin = self.headers.get("Origin")
        same = origin is None or origin == f"http://{self.headers.get('Host', '')}"
        return self._session() and same

    def ext_ok(self):
        return False                                   # the extension only talks to this computer

    def _blocked(self):
        path = urllib.parse.urlparse(self.path).path
        return path in PHONE_BLOCKED or path.startswith("/ext/") or path.startswith("/api/phone")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/static/") and re.fullmatch(r"/static/[\w.-]+\.(ttf|png|svg)", path):
            f = RES_DIR / "static" / Path(path).name   # fonts/logo for the PIN page (no sign-in needed)
            if f.is_file():
                data = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", {"ttf": "font/ttf", "png": "image/png", "svg": "image/svg+xml"}[path.rsplit(".", 1)[1]])
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            return self.send('{"error":"not found"}', code=404)
        if not self._session():
            if path == "/":
                return self.send(PHONE_LOGIN, "text/html")
            return self.send('{"error":"sign in with the PIN first"}', code=401)
        if path == "/":
            page = load_page().replace("<head>", "<head><script>window.JF_PHONE=true</script>", 1)
            return self.send(page, "text/html")
        if self._blocked():
            return self.send('{"error":"not available from a phone"}', code=403)
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/phone/login":
            now = time.time()
            phone["fails"] = [t for t in phone["fails"] if now - t < 300]
            if len(phone["fails"]) >= 5:
                return self.send('{"error":"Too many tries - wait 5 minutes"}', code=429)
            try:
                body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 1000)) or b"{}")
            except ValueError:
                body = {}
            pin = phone_settings().get("pin", "")
            if not pin or not secrets.compare_digest(str(body.get("pin", "")), pin):
                phone["fails"].append(now)
                return self.send('{"error":"That PIN didn\'t work"}', code=403)
            token = secrets.token_urlsafe(24)
            update_settings(lambda s: s.setdefault("phone", {}).update(
                sessions=(s.get("phone", {}).get("sessions", []) + [token])[-10:]))
            data = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Set-Cookie", f"jfs={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000")
            self.end_headers()
            self.wfile.write(data)
            return
        if not self._session():
            return self.send('{"error":"sign in with the PIN first"}', code=401)
        if self._blocked():
            return self.send('{"error":"not available from a phone"}', code=403)
        return super().do_POST()
