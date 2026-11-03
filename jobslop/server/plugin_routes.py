"""The server's plugin endpoints.

GET  /api/plugins                    every plugin, plus the profile fields and settings enabled plugins add
POST /api/plugins                    {"id", "enabled"}: switch one on or off
POST /api/plugins/install            {"link"}: download and check a plugin -> {"preview"}; then {"token"}: install it
POST /api/plugins/remove             {"id"}: remove a plugin installed from a link
POST /api/plugins/check              newer releases of plugins -> {"updates"}
GET  /api/plugin/<id>/<name>         a plugin's own endpoint (api.add_endpoint); POST sends JSON to it
GET  /plugins/<id>/<file>            a file of an enabled plugin (its screen code, styles, data)
"""

import json
import re
from dataclasses import asdict

from jobslop.plugins.installer import INSTALLER, Installer, InstallError
from jobslop.plugins.manager import PLUGINS, PluginManager
from jobslop.plugins.points import POINTS, ExtensionPoints

STATIC_TYPES = {"js": "text/javascript", "css": "text/css", "json": "application/json", "png": "image/png",
                "svg": "image/svg+xml"}
ENDPOINT_RE = re.compile(r"/api/plugin/([a-z0-9-]{2,40})/([a-z][a-z0-9_]{1,39})")
FILE_RE = re.compile(r"/plugins/([a-z0-9-]{2,40})/((?:[\w-]+/)*[\w.-]+\.(\w+))")


class PluginRoutes:
    def __init__(self, plugins: PluginManager = PLUGINS, points: ExtensionPoints = POINTS,
                 installer: Installer = INSTALLER) -> None:
        self.plugins, self.points, self.installer = plugins, points, installer

    def overview(self) -> dict:
        return {"plugins": [self.plugins.describe(p) for p in self.plugins.all()],
                "profile_fields": [{**asdict(f), "autofill": list(f.autofill), "plugin": pid}
                                   for pid, f in self.points.profile_fields.items()],
                "settings": [{**asdict(s), "plugin": pid} for pid, s in self.points.settings.items()]}

    def get(self, req, path: str, params: dict) -> bool:
        """Answer a GET if it is a plugin path. Returns False when it isn't one."""
        if path == "/api/plugins":
            req.send(json.dumps(self.overview()))
            return True
        m = ENDPOINT_RE.fullmatch(path)
        if m:
            self._call(req, m[1], m[2], params, None)
            return True
        m = FILE_RE.fullmatch(path)
        if m:
            self._file(req, m[1], m[2], m[3].lower())
            return True
        return False

    def post(self, req, path: str, body: dict) -> bool:
        if path in ("/api/plugins/install", "/api/plugins/remove", "/api/plugins/check"):
            try:
                req.send(json.dumps(self._manage(path, body)))
            except InstallError as e:
                req.send(json.dumps({"error": str(e)}), code=400)
            return True
        if path == "/api/plugins":
            try:
                self.plugins.set_enabled(str(body.get("id", "")), bool(body.get("enabled")))
            except ValueError as e:
                req.send(json.dumps({"error": str(e)}), code=404)
                return True
            req.send(json.dumps(self.overview()))
            return True
        m = ENDPOINT_RE.fullmatch(path)
        if m:
            self._call(req, m[1], m[2], {}, body)
            return True
        return False

    def _manage(self, path: str, body: dict) -> dict:
        if path == "/api/plugins/check":
            return {"updates": self.installer.check_updates()}
        if path == "/api/plugins/remove":
            self.installer.remove(str(body.get("id", "")))
            return self.overview()
        if body.get("token"):                                   # step 2: the user said yes
            pid = self.installer.confirm(str(body["token"]))
            return {**self.overview(), "installed": pid}
        return {"preview": self.installer.prepare(str(body.get("link", ""))[:300])}   # step 1: what is it?

    def _call(self, req, pid, name, params, body):
        fn = self.points.endpoint(pid, name)
        if not fn:
            return req.send('{"error":"no such plugin endpoint"}', code=404)
        try:
            req.send(json.dumps(fn(params, body)))
        except Exception as e:                         # a plugin's mistake must not take the server down
            req.send(json.dumps({"error": f"{pid}: {type(e).__name__}: {str(e)[:200]}"}), code=500)

    def _file(self, req, pid, rel, ext):
        p = self.plugins.get(pid)
        if not p or not p.loaded or ext not in STATIC_TYPES or ".." in rel:
            return req.send('{"error":"not found"}', code=404)
        f = (p.folder / rel).resolve()
        if not f.is_file() or p.folder.resolve() not in f.parents:
            return req.send('{"error":"not found"}', code=404)
        data = f.read_bytes()
        req.send_response(200)
        req.send_header("Content-Type", STATIC_TYPES[ext] + "; charset=utf-8")
        req.send_header("Content-Length", str(len(data)))
        req.send_header("Cache-Control", "no-cache")
        req.end_headers()
        req.wfile.write(data)


ROUTES = PluginRoutes()
