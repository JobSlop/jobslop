"""Phone access: a second server on the home network, PIN protected, off by default."""

import secrets
import socket
import sys
import threading
from http.server import ThreadingHTTPServer

from jobslop.settings import load_settings, update_settings

# ---------------------------------------------------------------- phone access (same Wi-Fi, PIN protected)
# A second, separate server that listens on your home network so your phone can use jobslop
# while it runs on this computer. Off by default. Every request needs a session from the PIN;
# PC-only actions (opening programs, clipboard, keys, the extension) are blocked from the phone.

PHONE_PORT = 47322
phone = {"server": None, "fails": []}
PHONE_BLOCKED = {"/api/open", "/api/linkedin/link", "/api/update", "/api/update/status", "/api/openfolder", "/api/ext/setup", "/api/ext/status", "/api/copy", "/api/export",
                 "/api/apply", "/api/phone", "/api/settings", "/api/prefs"}


def lan_ip():
    """This computer's address on the home network (no data is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def phone_settings():
    return load_settings().get("phone", {})


def new_pin():
    pin = f"{secrets.randbelow(1000000):06d}"
    update_settings(lambda s: s.setdefault("phone", {}).update(pin=pin, sessions=[]))   # new PIN signs phones out
    return pin


def start_phone_server():
    if phone["server"]:
        return True
    from jobslop.server.phone_handler import PhoneHandler  # here, not at the top: it imports this module
    try:
        host = "127.0.0.1" if "--phone-local" in sys.argv else "0.0.0.0"   # --phone-local: for testing only
        srv = ThreadingHTTPServer((host, PHONE_PORT), PhoneHandler)
    except OSError:
        return False
    phone["server"] = srv
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return True


def stop_phone_server():
    srv, phone["server"] = phone["server"], None
    if srv:
        threading.Thread(target=lambda: (srv.shutdown(), srv.server_close()), daemon=True).start()


def phone_status():
    p = phone_settings()
    ip = lan_ip()
    return {"enabled": bool(p.get("enabled")), "running": bool(phone["server"]), "pin": p.get("pin", ""),
            "url": f"http://{ip}:{PHONE_PORT}", "ip": ip, "phones": len(p.get("sessions", []))}


PHONE_LOGIN = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>jobslop</title><style>
@font-face{font-family:Italiana;src:url(/static/Italiana-Regular.ttf)}@font-face{font-family:Manrope;src:url(/static/Manrope.ttf);font-weight:200 800}
body{margin:0;min-height:100vh;display:grid;place-items:center;font:15px/1.5 Manrope,system-ui,sans-serif;color:#f4efe6;
background:radial-gradient(500px 300px at 85% 0%,rgba(155,123,85,.45),transparent 70%),linear-gradient(160deg,#2a2620,#141210)}
.box{width:min(340px,88vw);text-align:center}h1{font-family:Italiana,serif;font-weight:400;font-size:40px;margin:14px 0 4px}
p{color:rgba(244,239,230,.7);margin:0 0 20px}input{width:100%;box-sizing:border-box;font:600 26px Consolas,monospace;letter-spacing:10px;text-align:center;
padding:14px;border-radius:16px;border:1px solid rgba(255,255,255,.25);background:rgba(255,255,255,.08);color:#fff;outline:none}
input:focus{border-color:#c9a57a}button{margin-top:14px;width:100%;font:600 15px Manrope,sans-serif;padding:13px;border:0;border-radius:999px;background:#f4efe6;color:#1d1b18}
.err{color:#e0a040;min-height:22px;margin-top:10px;font-size:14px}</style></head><body><form class="box" id="f">
<svg viewBox="0 0 64 64" width="56" height="56"><rect width="64" height="64" rx="16" fill="#f4efe6"/><text x="32" y="45" text-anchor="middle" font-family="Italiana,serif" font-size="38" fill="#1d1b18">jF</text></svg>
<h1>jobslop</h1><p>Enter the PIN shown in jobslop on your computer<br>(⚙ Settings → Phone access)</p>
<input id="pin" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="••••••" autofocus>
<button>Open jobslop</button><div class="err" id="err"></div></form>
<script>document.getElementById("f").onsubmit=async e=>{e.preventDefault();const r=await fetch("/phone/login",{method:"POST",headers:{"Content-Type":"application/json"},
body:JSON.stringify({pin:document.getElementById("pin").value.trim()})});if(r.ok)location.reload();else{const d=await r.json().catch(()=>({}));
document.getElementById("err").textContent=d.error||"That PIN didn't work";document.getElementById("pin").value=""}}</script></body></html>"""
