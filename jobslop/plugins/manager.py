"""Finding, loading and switching plugins on and off.

Plugins live in two places:
  built in   <app files>/plugins/<id>      come with jobslop (off unless "enabled_by_default")
  installed  <data folder>/plugins/<id>    installed from a GitHub link; a newer copy replaces a built-in one
Whether each is on is remembered in settings.json under "plugins".
"""

import importlib.machinery
import importlib.util
import json
import sys
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from jobslop.boards.registry import BOARDS, BoardRegistry
from jobslop.config import DATA_DIR, RES_DIR
from jobslop.plugins.api import PluginAPI
from jobslop.plugins.manifest import Manifest, ManifestError, read, version_tuple
from jobslop.plugins.points import POINTS, ExtensionPoints, Terms
from jobslop.settings import load_settings, update_settings

BUILTIN_DIR = RES_DIR / "plugins"
INSTALLED_DIR = DATA_DIR / "plugins"
SOURCE_FILE = ".jobslop-source.json"          # where an installed plugin came from (written by the installer)


@dataclass
class Plugin:
    folder: Path
    builtin: bool
    manifest: Manifest | None = None
    error: str = ""                           # why it couldn't be read or started
    loaded: bool = False
    source: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.manifest.id if self.manifest else self.folder.name


class PluginManager:
    def __init__(self, builtin_dir: Path, installed_dir: Path, boards: BoardRegistry, points: ExtensionPoints) -> None:
        self.builtin_dir, self.installed_dir = Path(builtin_dir), Path(installed_dir)
        self.boards, self.points = boards, points
        self._plugins: dict[str, Plugin] = {}
        self._lock = threading.RLock()
        self.messages: list[str] = []

    # ---- finding plugins
    def discover(self) -> None:
        """Read every plugin.json (no plugin code runs here)."""
        with self._lock:
            found: dict[str, Plugin] = {}
            for folder, builtin in self._folders():
                p = Plugin(folder, builtin)
                try:
                    p.manifest = read(folder)
                except ManifestError as e:
                    p.error = str(e)
                if not builtin:
                    try:
                        p.source = json.loads((folder / SOURCE_FILE).read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        p.source = {}
                old = found.get(p.id)
                if old and old.manifest and p.manifest and \
                        version_tuple(old.manifest.version) > version_tuple(p.manifest.version):
                    continue                     # the copy built into this jobslop is newer than the installed one
                found[p.id] = p
            for pid, p in self._plugins.items():         # keep what's running as it is
                if p.loaded and pid in found and found[pid].folder == p.folder:
                    found[pid] = p
            self._plugins = found

    def _folders(self):
        for base, builtin in ((self.builtin_dir, True), (self.installed_dir, False)):
            if base.is_dir():
                for d in sorted(base.iterdir()):
                    if d.is_dir() and not d.name.startswith((".", "_")):
                        yield d, builtin

    def get(self, pid: str) -> Plugin | None:
        return self._plugins.get(pid)

    def all(self) -> list[Plugin]:
        return sorted(self._plugins.values(), key=lambda p: (not p.builtin, (p.manifest.name if p.manifest else p.id).lower()))

    # ---- on and off
    def is_enabled(self, pid: str) -> bool:
        p = self._plugins.get(pid)
        if not p or not p.manifest:
            return False
        choice = (load_settings().get("plugins") or {}).get(pid, {})
        return bool(choice.get("enabled", p.manifest.enabled_by_default))

    def load_enabled(self) -> None:
        for p in self.all():
            if self.is_enabled(p.id) and not p.loaded:
                self._load(p)

    def set_enabled(self, pid: str, on: bool) -> Plugin:
        with self._lock:
            p = self._plugins.get(pid)
            if not p or not p.manifest:
                raise ValueError("No plugin called " + pid)
            update_settings(lambda s: s.setdefault("plugins", {}).setdefault(pid, {}).update(enabled=bool(on)))
            if on and not p.loaded:
                self._load(p)
            elif not on and p.loaded:
                self._unload(p)
            return p

    def unload(self, pid: str) -> None:
        with self._lock:
            p = self._plugins.get(pid)
            if p and p.loaded:
                self._unload(p)

    # ---- starting one
    def _load(self, p: Plugin) -> None:
        m = p.manifest
        p.error = ""
        try:
            for f in m.settings:
                self.points.settings.add(m.id, f)
            for f in m.profile_fields:
                self.points.profile_fields.add(m.id, f)
            for lang, file in m.translations.items():
                self.points.translations.add(m.id, Terms(lang, _json_words(p.folder / file)))
            for lang, file in m.search_terms.items():
                self.points.search_terms.add(m.id, Terms(lang, _json_words(p.folder / file)))
            if m.python:
                module = _import(m.id, p.folder, m.python)
                register = getattr(module, "register", None)
                if not callable(register):
                    raise ManifestError(f"{m.python} has no register(api) function")
                register(PluginAPI(m, p.folder, self.boards, self.points, self._log))
            p.loaded = True
        except Exception as e:
            self._unload(p)
            p.error = f"Couldn't start: {type(e).__name__}: {str(e)[:200]}"
            self._log(m.id, p.error + "\n" + traceback.format_exc(limit=4))

    def _unload(self, p: Plugin) -> None:
        self.boards.remove_plugin(p.id)
        self.points.remove_plugin(p.id)
        for name in [n for n in sys.modules if n == _package(p.id) or n.startswith(_package(p.id) + ".")]:
            del sys.modules[name]
        p.loaded = False

    def _log(self, pid: str, msg: str) -> None:
        self.messages = (self.messages + [f"[{pid}] {msg}"])[-50:]

    # ---- what the screen is told
    def describe(self, p: Plugin) -> dict:
        m = p.manifest
        return {"id": p.id, "name": m.name if m else p.folder.name, "version": m.version if m else "",
                "description": m.description if m else "", "author": m.author if m else "",
                "homepage": (m.homepage if m else "") or p.source.get("url", ""), "builtin": p.builtin,
                "enabled": self.is_enabled(p.id), "loaded": p.loaded, "error": p.error,
                "adds": m.adds() if m else [], "has_settings": bool(m and m.settings),
                "countries": list((m.language.countries if m.language else m.countries) if m else ()), "ui": f"/plugins/{p.id}/{m.ui}" if m and m.ui and p.loaded else "",
                "language": {"code": m.language.code, "name": m.language.name} if m and m.language else None}


def _package(pid: str) -> str:
    return "jobslop_plugins." + pid.replace("-", "_")


def _import(pid: str, folder: Path, file: str):
    """Load the plugin's Python file as part of its own package, so it can import its other files (from . import x)."""
    if "jobslop_plugins" not in sys.modules:
        root = importlib.util.module_from_spec(importlib.machinery.ModuleSpec("jobslop_plugins", None, is_package=True))
        root.__path__ = []
        sys.modules["jobslop_plugins"] = root
    pkg_name = _package(pid)
    pkg = importlib.util.module_from_spec(importlib.machinery.ModuleSpec(pkg_name, None, is_package=True))
    pkg.__path__ = [str(folder)]
    sys.modules[pkg_name] = pkg
    name = pkg_name + "." + Path(file).with_suffix("").as_posix().replace("/", ".")
    spec = importlib.util.spec_from_file_location(name, folder / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _json_words(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ManifestError(f"{path.name} must be an object")
    return data


PLUGINS = PluginManager(BUILTIN_DIR, INSTALLED_DIR, BOARDS, POINTS)
