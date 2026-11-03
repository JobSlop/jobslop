"""The `api` object a plugin's register(api) is given: the only way a plugin changes the app.

    def register(api):
        api.add_board("ICAEW", search_icaew, "Chartered accountancy jobs", country_native=True)
        api.add_search_terms("nl", {"accountant": ["boekhouder"]})
"""

from collections.abc import Callable
from pathlib import Path

from jobslop.boards.base import Board, SearchFn
from jobslop.boards.registry import BoardRegistry
from jobslop.config import DATA_DIR
from jobslop.plugins import tools
from jobslop.plugins.manifest import API_VERSION, KEY_RE, Manifest, setting_field
from jobslop.plugins.points import Endpoint, ExtensionPoints, NamedEndpoint, Terms
from jobslop.settings import load_settings


class PluginAPI:
    api_version = API_VERSION
    http, jobs, text, geo = tools.http, tools.jobs, tools.text, tools.geo

    def __init__(self, manifest: Manifest, folder: Path, boards: BoardRegistry, points: ExtensionPoints,
                 log: Callable[[str, str], None] = lambda plugin, msg: None) -> None:
        self._m, self._boards, self._points, self._log = manifest, boards, points, log
        self.id, self.name, self.version, self.folder = manifest.id, manifest.name, manifest.version, Path(folder)

    # ---- what a plugin can add
    def add_board(self, name: str, search: SearchFn, description: str = "", *, group: str = "specialist",
                  countries=None, country_native: bool = False, location_aware: bool = False,
                  native_types: bool = False, needs=(), slow_without: str = "", cache_seconds: int = 15 * 60) -> None:
        """A job board. search(query, options) returns a list of api.jobs.make(...) jobs."""
        if not callable(search):
            raise TypeError("search must be a function")
        self._boards.add(Board(str(name)[:40], search, str(description)[:120], group=group, countries=countries,
                               country_native=country_native, location_aware=location_aware,
                               native_types=native_types, needs=tuple(needs), slow_without=slow_without,
                               cache_seconds=max(60, int(cache_seconds)), plugin=self.id))

    def add_setting(self, key: str, label: str, *, type: str = "secret", help: str = "", link: str = "",
                    options=(), default="", secret: bool | None = None) -> None:
        """A setting shown in the plugin's fold in Settings → Plugins. type: secret (an API key, hidden),
        text, number, toggle (on/off, read as "1" or "") or choice (options: [(value, label), ...]).
        Read it with api.setting(key)."""
        if secret is not None:                       # older form: secret=True/False
            type = "secret" if secret else "text"
        self._points.settings.add(self.id, setting_field(key, label, type, help, link, options, default))

    def setting(self, key: str) -> str:
        """The setting's value, or its default when it has never been set (a toggle reads "1" or "")."""
        value = load_settings().get(key)
        if value is None:
            f = next((f for f in self._points.settings if f.key == key), None)
            return f.default if f else ""
        return str(value)

    def add_endpoint(self, name: str, fn: Endpoint) -> None:
        """Data for the plugin's own screen code, at /api/plugin/<id>/<name>. fn(params, body) -> JSON-able."""
        if not KEY_RE.fullmatch(name):
            raise ValueError(f'endpoint "{name}": use a-z, 0-9 and _')
        self._points.endpoints.add(self.id, NamedEndpoint(name, fn))

    def add_search_terms(self, lang: str, terms: dict[str, list[str]]) -> None:
        """Job titles in a language: {"accountant": ["boekhouder", "financieel administrateur"]}."""
        self._points.search_terms.add(self.id, Terms(lang, _clean_terms(terms)))

    def add_translations(self, lang: str, words: dict[str, str]) -> None:
        """Screen text: {"Search": "Zoeken"}."""
        self._points.translations.add(self.id, Terms(lang, {str(k)[:300]: str(v)[:300] for k, v in words.items()}))

    # ---- what a plugin can use
    @property
    def data_dir(self) -> Path:
        """A folder of its own for files it wants to keep (made when first asked for)."""
        d = DATA_DIR / "plugin-data" / self.id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def log(self, message: str) -> None:
        self._log(self.id, str(message)[:500])


def _clean_terms(terms: dict) -> dict[str, list[str]]:
    out = {}
    for k, v in terms.items():
        words = [v] if isinstance(v, str) else list(v)
        out[str(k).lower()[:80]] = [str(w)[:80] for w in words if str(w).strip()][:8]
    return out
