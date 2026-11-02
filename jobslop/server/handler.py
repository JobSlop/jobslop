"""The app's local web server: the page and its /api and /ext endpoints."""

import base64
import json
import os
import re
import secrets
import shutil
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from jobslop import config
from jobslop.boards.registry import BOARDS
from jobslop.config import FEEDBACK_EMAIL, RES_DIR
from jobslop.extension import active_job, extension_payload, install_extension, open_in_chrome, pairing_code
from jobslop.geo import osm
from jobslop.geo.cities import city_label, code_for_country_text, geocode_text, nearest_city, towns_in_box
from jobslop.geo.countries import COUNTRIES, country_info
from jobslop.geo.osm import place_summary
from jobslop.geo.places import resolve_where
from jobslop.plugins.points import POINTS
from jobslop.profile.cvparse import parse_cv
from jobslop.profile.linkedin_import import linkedin_import
from jobslop.profile.linkedin_link import li_link, linkedin_from_page, linkedin_link_status, linkedin_profile_url
from jobslop.profile.store import CV_DIR, EXT_DIR, PROFILE_FILE, cv_file, load_profile, save_cv, save_profile
from jobslop.rates import get_rates
from jobslop.runtime import state
from jobslop.search.engine import search
from jobslop.search.matching import match_groups
from jobslop.server import plugin_routes
from jobslop.server.phone import PHONE_PORT, new_pin, phone_settings, phone_status, start_phone_server, stop_phone_server
from jobslop.settings import KEY_NAMES, load_settings, public_settings, save_settings, update_settings
from jobslop.system import copy_to_clipboard, export_csv, open_path
from jobslop.tracker import APPLIED_STAGES, load_saved, lock, set_status, today, write_saved
from jobslop.updates import UPDATE_DIR, check_for_update, download_update, install_update, update_state

# ---------------------------------------------------------------- web server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body, ctype="application/json", code=200):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- security: only this app's own page and the paired Chrome extension may use the server
    def host_ok(self):
        port = state["port"]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def app_ok(self):
        port = state["port"]
        origin = self.headers.get("Origin")
        return self.host_ok() and origin in (None, f"http://127.0.0.1:{port}", f"http://localhost:{port}")

    def ext_ok(self):
        origin = self.headers.get("Origin") or ""
        key = (self.headers.get("X-JobFinder-Key") or "").strip().upper()
        good = self.host_ok() and (origin == "" or origin.startswith("chrome-extension://")) \
            and secrets.compare_digest(key, pairing_code())
        if good:
            state["ext_seen"] = time.time()
        return good

    def do_OPTIONS(self):
        origin = self.headers.get("Origin") or ""
        self.send_response(204)
        if origin.startswith("chrome-extension://") and self.path.startswith("/ext/"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "X-JobFinder-Key, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.end_headers()

    def handle_ext(self, method, body=None):
        if not self.ext_ok():
            return self.send('{"error":"bad-code"}', code=401)
        path = urllib.parse.urlparse(self.path).path
        if method == "GET" and path == "/ext/profile":
            return self.send(json.dumps(extension_payload()))
        if method == "GET" and path == "/ext/cv":
            f = cv_file()
            if not f:
                return self.send("{}")
            ext = f.suffix.lower()
            mime = {".pdf": "application/pdf", ".doc": "application/msword",
                    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ".txt": "text/plain", ".rtf": "application/rtf"}.get(ext, "application/octet-stream")
            return self.send(json.dumps({"name": f.name, "type": mime,
                                         "data": base64.b64encode(f.read_bytes()).decode()}))
        if method == "GET" and path == "/ext/linkedin/wanted":
            st = linkedin_link_status()
            return self.send(json.dumps({"url": st["url"] if st["waiting"] else ""}))
        if method == "POST" and path == "/ext/linkedin":
            if not linkedin_link_status()["waiting"]:
                return self.send('{"error":"not waiting"}', code=409)
            b = body or {}
            if b.get("error"):
                li_link["error"] = str(b["error"])[:200]
            else:
                try:
                    li_link["found"] = linkedin_from_page(b.get("page") or {})
                except Exception as e:
                    li_link["error"] = "Couldn't read that LinkedIn page (" + str(e)[:80] + ")"
            return self.send("{}")
        if method == "POST" and path == "/ext/applied":
            url = (body or {}).get("url") or (active_job() or {}).get("url")
            with lock:
                items = load_saved()
                for i in items:
                    if i.get("url") == url:
                        set_status(i, "Applied")
                write_saved(items)
            return self.send("{}")
        self.send('{"error":"not found"}', code=404)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path.startswith("/ext/"):
            return self.handle_ext("GET")
        if not self.app_ok():
            return self.send('{"error":"forbidden"}', code=403)
        if plugin_routes.ROUTES.get(self, u.path, p):
            return
        if u.path == "/api/linkedin/link":
            return self.send(json.dumps(linkedin_link_status()))
        if u.path == "/api/update":
            try:
                return self.send(json.dumps(check_for_update()))
            except Exception as e:
                return self.send(json.dumps({"enabled": bool(config.UPDATE_REPO), "current": config.APP_VERSION,
                                             "error": "Couldn't check for updates (" + str(e)[:80] + ")"}))
        if u.path == "/api/update/status":
            return self.send(json.dumps({k: update_state[k] for k in ("done", "total", "busy", "ready", "error")}))
        if u.path == "/api/profile":
            cv = cv_file()
            return self.send(json.dumps({
                "profile": load_profile(), "cv": {"name": cv.name, "size": cv.stat().st_size} if cv else None,
                "ext": {"code": pairing_code(), "folder": str(EXT_DIR),
                        "connected": time.time() - state["ext_seen"] < 7 * 24 * 3600 and state["ext_seen"] > 0}}))
        def num(key, default, lo, hi):
            try:
                return max(lo, min(hi, int(float(p.get(key, default) or default))))
            except ValueError:
                return default

        if u.path == "/":
            self.send(load_page(), "text/html")
        elif u.path == "/api/countries":
            self.send(json.dumps([{"code": c, "name": v[0], "adzuna": bool(v[2]), "currency": v[5]}
                                  for c, v in sorted(COUNTRIES.items(), key=lambda kv: kv[1][0])]))
        elif u.path == "/api/boards":
            s = load_settings()
            self.send(json.dumps([b.describe(s) for b in BOARDS]))
        elif u.path == "/api/rates":
            self.send(json.dumps(get_rates()))
        elif u.path == "/api/phone":
            self.send(json.dumps(phone_status()))
        elif u.path == "/api/geocode":
            # offline town list first; the online lookup is only a fallback for tiny places
            q = p.get("q", "")[:120]
            row = geocode_text(q, code_for_country_text(p.get("country", "")))
            if row:
                return self.send(json.dumps({"lat": row[1], "lon": row[2], "town": row[0], "country_code": row[3],
                                             "country": country_info(row[3])[0] if row[3] in COUNTRIES else row[3],
                                             "label": city_label(row), "offline": True}))
            loc = resolve_where(q, code_for_country_text(p.get("country", "")) or "GB")   # postcodes, addresses
            if loc and loc["found"] and loc["lat"] is not None:
                cc = loc["country_code"]
                return self.send(json.dumps({"lat": loc["lat"], "lon": loc["lon"], "town": loc["town"], "country_code": cc,
                                             "country": country_info(cc)[0] if cc in COUNTRIES else cc,
                                             "label": loc["label"]}))
            try:
                found = osm.nominatim("search", {"q": q, "limit": 1})
                self.send(json.dumps(place_summary(found[0]) if found else {"error": "Place not found"}))
            except Exception:
                self.send(json.dumps({"error": "Place not found"}))
        elif u.path == "/api/place":
            # what "Where?" means: a town, postcode or full address -> town, postcode, country
            loc = resolve_where(p.get("q", "")[:200], (p.get("country") or "GB").upper())
            self.send(json.dumps(loc or {"town": "", "label": "", "found": False}))
        elif u.path == "/api/reverse":
            try:
                row = nearest_city(float(p.get("lat")), float(p.get("lon")))
            except (TypeError, ValueError):
                row = None
            if not row:
                return self.send(json.dumps({"error": "No town here"}))
            self.send(json.dumps({"lat": row[1], "lon": row[2], "town": row[0], "country_code": row[3],
                                  "country": country_info(row[3])[0] if row[3] in COUNTRIES else row[3],
                                  "label": city_label(row), "offline": True}))
        elif u.path == "/api/match_terms":
            self.send(json.dumps(match_groups()))
        elif u.path == "/api/towns":
            try:
                box = [float(p[k]) for k in ("s", "w", "n", "e")]
                self.send(json.dumps(towns_in_box(*box, limit=num("limit", 60, 1, 300))))
            except (KeyError, ValueError):
                self.send("[]")
        elif u.path.startswith("/static/"):
            name = Path(u.path).name
            f = RES_DIR / "static" / name
            if not re.fullmatch(r"[\w.-]+\.(ttf|woff2?|png|svg|js|css|json)", name) or not f.is_file():
                return self.send('{"error":"not found"}', code=404)
            ctype = {"ttf": "font/ttf", "woff": "font/woff", "woff2": "font/woff2", "png": "image/png",
                     "svg": "image/svg+xml", "js": "text/javascript", "css": "text/css",
                     "json": "application/json"}[name.rsplit(".", 1)[1]]
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(data)
        elif u.path == "/api/prefs":
            self.send(json.dumps(load_settings().get("ui", {})))
        elif u.path == "/api/search":
            q = p.get("q", "")[:300]
            country = p.get("country", "GB").upper()
            # the screen's filters are applied by the screen itself; only "where" settings reach the boards
            opts = {"where": p.get("where", "").strip()[:200], "intern": p.get("intern") == "1",
                    "country": country if country in COUNTRIES else "GB",
                    "local": p.get("local", "1") == "1",
                    "strict": p.get("strict", "0") == "1",
                    "miles": num("miles", 15, 1, 100),
                    "posted": num("posted", 0, 0, 60),
                    "jtype": p.get("jtype", "") if p.get("jtype") in ("fulltime", "parttime", "contract", "internship") else "",
                    "remote": p.get("remote", "") if p.get("remote") in ("remote", "hybrid", "onsite") else "",
                    "salary_min": num("salary_min", 0, 0, 10_000_000)}
            srcs = p.get("sources", ",".join(BOARDS.names())).split(",")
            fresh = p.get("fresh", "0") == "1"
            any_job = p.get("any", "0") == "1"
            if not q.strip() and not any_job:
                return self.send(json.dumps({"results": [], "status": {}}))
            self.send(json.dumps(search("" if any_job else q, srcs, opts, fresh)))
        elif u.path == "/api/saved":
            self.send(json.dumps(load_saved()))
        elif u.path == "/api/settings":
            self.send(json.dumps(public_settings(setting_keys())))
        else:
            self.send('{"error":"not found"}', code=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 15 * 1024 * 1024:
            return self.send('{"error":"too big"}', code=413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self.send('{"error":"bad json"}', code=400)
        if self.path.startswith("/ext/"):
            return self.handle_ext("POST", body)
        if not self.app_ok():
            return self.send('{"error":"forbidden"}', code=403)
        if plugin_routes.ROUTES.post(self, urllib.parse.urlparse(self.path).path, body):
            return
        if self.path == "/api/profile":
            return self.send(json.dumps({"profile": save_profile(body.get("profile", {}))}))
        if self.path == "/api/prefs":
            # small screen preferences (theme, colours, currency) kept with the app's settings
            s = update_settings(lambda s: s.setdefault("ui", {}).update({str(k)[:30]: str(v)[:60] for k, v in body.items()}))
            return self.send(json.dumps(s.get("ui", {})))
        if self.path == "/api/profile/clear":
            PROFILE_FILE.unlink(missing_ok=True)
            if body.get("cv"):
                shutil.rmtree(CV_DIR, ignore_errors=True)
            return self.send(json.dumps({"profile": {}, "cv_removed": bool(body.get("cv"))}))
        if self.path == "/api/cv":
            try:
                if body.get("remove"):
                    shutil.rmtree(CV_DIR, ignore_errors=True)
                    return self.send(json.dumps({"cv": None}))
                name = save_cv(body.get("name", "cv.pdf"), body.get("data", ""))
                return self.send(json.dumps({"cv": {"name": name, "size": cv_file().stat().st_size}}))
            except Exception as e:
                return self.send(json.dumps({"error": str(e)[:120]}), code=400)
        if self.path == "/api/update":
            act = body.get("action")
            try:
                if act == "check":
                    return self.send(json.dumps(check_for_update(force=True)))
                if act == "off":
                    update_settings(lambda s: s.__setitem__("updates_off", bool(body.get("off"))))
                    if body.get("off"):
                        update_state.update(ready="", done=0, total=0)
                        (UPDATE_DIR / "jobslop-new.exe").unlink(missing_ok=True)
                    return self.send(json.dumps(check_for_update()))
                if act == "skip":
                    update_settings(lambda s: s.__setitem__("update_skip", str(body.get("version", ""))[:20]))
                    return self.send(json.dumps(check_for_update()))
                if act == "download":
                    if not update_state["busy"]:
                        threading.Thread(target=download_update, daemon=True).start()
                    return self.send('{"started":true}')
                if act == "install":
                    install_update()
                    return self.send('{"restarting":true}')
            except Exception as e:
                return self.send(json.dumps({"error": str(e)[:160]}), code=400)
            return self.send('{"error":"unknown action"}', code=400)
        if self.path == "/api/linkedin/link":
            if body.get("cancel"):
                li_link.update(url="", found=None, error="")
                return self.send(json.dumps(linkedin_link_status()))
            url = linkedin_profile_url(body.get("url", ""))
            if not url:
                return self.send(json.dumps({"error": "That isn't a LinkedIn profile link - it looks like "
                                                      "linkedin.com/in/your-name"}), code=400)
            li_link.update(url=url, at=time.time(), found=None, error="")
            connected = state["ext_seen"] > 0 and time.time() - state["ext_seen"] < 7 * 24 * 3600
            return self.send(json.dumps({"url": url, "chrome": open_in_chrome(url), "connected": connected}))
        if self.path == "/api/linkedin":
            try:
                return self.send(json.dumps({"found": linkedin_import(body.get("name", ""), body.get("data", ""))}))
            except Exception as e:
                return self.send(json.dumps({"error": str(e)[:160]}), code=400)
        if self.path == "/api/cv/parse":
            f = cv_file()
            if not f:
                return self.send('{"error":"Upload your CV first"}', code=400)
            try:
                return self.send(json.dumps({"found": parse_cv(f)}))
            except Exception as e:
                return self.send(json.dumps({"error": "Couldn't read that CV: " + str(e)[:100]}), code=400)
        if self.path == "/api/apply":
            jb = body.get("job", {})
            if not str(jb.get("url", "")).startswith(("http://", "https://")):
                return self.send('{"error":"no link"}', code=400)
            with lock:
                items = load_saved()
                found = next((i for i in items if i.get("url") == jb["url"]), None)
                if found:
                    if found.get("status") in (None, "", "Saved"):
                        set_status(found, "Applying")
                else:
                    jb.update(notes="", saved_on=today())
                    set_status(jb, "Applying")
                    items.insert(0, jb)
                write_saved(items)
            state["active"] = {"job": jb, "t": time.time()}
            chrome = open_in_chrome(jb["url"])
            return self.send(json.dumps({"saved": items, "chrome": chrome}))
        if self.path == "/api/openfolder":
            open_path(install_extension())
            return self.send("{}")
        if self.path == "/api/ext/setup":
            # as close to "auto install" as Chrome allows: open the extensions page and the folder,
            # with the folder path ready on the clipboard (Chrome doesn't allow silent installs)
            folder = install_extension()
            try:
                copy_to_clipboard(folder)
            except Exception:
                pass
            open_in_chrome("chrome://extensions/")
            open_path(folder)
            return self.send(json.dumps({"folder": folder}))
        if self.path == "/api/phone":
            # turn phone access on/off, make a new PIN, or sign every phone out
            if body.get("new_pin") or (body.get("enabled") and not phone_settings().get("pin")):
                new_pin()
            if body.get("signout"):
                update_settings(lambda s: s.setdefault("phone", {}).update(sessions=[]))
            if "enabled" in body:
                on = bool(body["enabled"])
                update_settings(lambda s: s.setdefault("phone", {}).update(enabled=on))
                ok = start_phone_server() if on else (stop_phone_server() or True)
                if on and not ok:
                    update_settings(lambda s: s.setdefault("phone", {}).update(enabled=False))
                    return self.send(json.dumps({**phone_status(), "error": f"Port {PHONE_PORT} is busy - close other apps using it"}))
            return self.send(json.dumps(phone_status()))
        if self.path == "/api/copy":
            # clipboard fallback for the app window
            text = str(body.get("text", ""))[:4000]
            try:
                copy_to_clipboard(text)
                return self.send('{"ok":true}')
            except Exception:
                return self.send('{"ok":false}')
        if self.path == "/api/ext/status":
            return self.send(json.dumps({"connected": state["ext_seen"] > 0 and time.time() - state["ext_seen"] < 7 * 24 * 3600,
                                         "seconds_ago": int(time.time() - state["ext_seen"]) if state["ext_seen"] else None}))
        if self.path == "/api/match_terms":
            clean = []
            for g in body.get("terms", [])[:60]:
                name = str(g.get("name", "")).strip()[:60]
                aliases = g.get("aliases", [])
                if isinstance(aliases, str):
                    aliases = aliases.split(",")
                aliases = [str(a).strip()[:60] for a in aliases if str(a).strip()][:20]
                if name:
                    clean.append({"name": name, "aliases": aliases, "title_only": bool(g.get("title_only", True))})
            update_settings(lambda s: s.__setitem__("match_terms", clean))
            return self.send(json.dumps(clean))
        if self.path == "/api/saved":
            with lock:
                items = load_saved()
                jb = body.get("job", {})
                url = jb.get("url")
                act = body.get("action")
                if act == "remove":
                    items = [i for i in items if i.get("url") != url]
                if act == "restore" and url and not any(i.get("url") == url for i in items):
                    # undo a removal: put the card back exactly as it was
                    pos = max(0, min(int(body.get("index", 0) or 0), len(items)))
                    items.insert(pos, jb)
                if act in ("save", "applied", "add") and not any(i.get("url") == url and url for i in items):
                    # save = bookmark, applied = mark applied straight away, add = typed in by hand
                    if act == "add" and not url:
                        jb["url"] = url = "manual:" + secrets.token_hex(6)
                    jb.setdefault("notes", "")
                    jb["saved_on"] = today()
                    set_status(jb, jb.get("status") or ("Applied" if act in ("applied", "add") else "Saved"),
                               jb.get("applied_on"))
                    items.insert(0, jb)
                elif act == "applied":
                    for i in items:
                        if i.get("url") == url and i.get("status") in (None, "", "Saved", "Applying"):
                            set_status(i, "Applied")
                if act == "unapply":
                    # "✓ Applied" clicked again: back to Saved, forgetting the application dates
                    for i in items:
                        if i.get("url") == url and i.get("status") in APPLIED_STAGES + ("Applying",):
                            i["status"] = "Saved"
                            i.pop("applied_on", None)
                            dates = i.setdefault("dates", {})
                            for st in APPLIED_STAGES + ("Applying",):
                                dates.pop(st, None)
                            dates.setdefault("Saved", i.get("saved_on") or today())
                if act == "set_all" and isinstance(body.get("items"), list):
                    # undo: the whole tracker exactly as it was before your last change
                    items = [dict(i) for i in body["items"] if isinstance(i, dict) and i.get("url")][:5000]
                if act == "put" and url:
                    # undo: put a card back exactly as it was, in the same place
                    items = [dict(jb) if i.get("url") == url else i for i in items]
                if act == "update":
                    for i in items:
                        if i.get("url") == url:
                            if jb.get("status") and jb["status"] != i.get("status"):
                                set_status(i, jb["status"])
                            for f in ("notes", "follow_up", "title", "company", "location", "salary"):
                                if f in jb:
                                    i[f] = str(jb[f])[:4000]
                            if jb.get("applied_on"):
                                i["applied_on"] = str(jb["applied_on"])[:10]
                write_saved(items)
            self.send(json.dumps(items))
        elif self.path == "/api/settings":
            save_settings(body, setting_keys())
            self.send(json.dumps(public_settings(setting_keys())))
        elif self.path == "/api/export":
            path = export_csv(body.get("rows", []), body.get("cols", []), body.get("name", "jobs"))
            self.send(json.dumps({"path": path}))
        elif self.path == "/api/open":
            # open a job link or the downloads folder in the normal browser / Explorer
            target = body.get("url", "")
            if target.startswith(("http://", "https://")):
                webbrowser.open(target)
            elif target.startswith("mailto:" + FEEDBACK_EMAIL + "?") and len(target) < 8000:
                # the "tell us" email: opens in your own email app, ready for you to check and send
                if config.IS_WIN:
                    os.startfile(target)
                else:
                    webbrowser.open(target)
            elif target and Path(target).exists():
                open_path(Path(target).parent)
            self.send("{}")
        else:
            self.send('{"error":"not found"}', code=404)


def setting_keys():
    """Keys the Settings window may save: the app's own plus every enabled plugin's."""
    return tuple(dict.fromkeys(KEY_NAMES + tuple(POINTS.setting_keys())))


def load_page():
    """The app's screen lives in ui.html next to this file (bundled inside the .exe)."""
    return (RES_DIR / "ui.html").read_text(encoding="utf-8")
