"""plugin.json: what a plugin is and what it adds. Read and checked before any of its code runs."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

API_VERSION = 1                      # raise when the plugin API changes in a way old plugins can't handle
MANIFEST = "plugin.json"

ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,39}")
VERSION_RE = re.compile(r"\d+(\.\d+){0,3}")
KEY_RE = re.compile(r"[a-z][a-z0-9_]{1,39}")
FILE_RE = re.compile(r"[\w-]+(/[\w-]+)*\.(py|js|css|json)")
FIELD_TYPES = ("text", "area", "yn", "email", "tel", "url")
SETTING_TYPES = ("secret", "text", "number", "toggle", "choice")   # toggle values are "1" or ""


class ManifestError(ValueError):
    """plugin.json is missing, unreadable or describes something the app can't accept."""


@dataclass(frozen=True)
class ProfileField:
    key: str
    label: str
    section: str
    type: str = "text"
    autofill: tuple[str, ...] = ()        # regular expressions for form labels the Chrome extension fills


@dataclass(frozen=True)
class SettingField:
    key: str
    label: str
    type: str = "secret"
    help: str = ""
    link: str = ""
    options: tuple[tuple[str, str], ...] = ()   # for "choice": (value, label) pairs
    default: str = ""


def setting_field(key, label, type="secret", help="", link="", options=(), default="") -> SettingField:
    """A checked SettingField (used for plugin.json and api.add_setting alike)."""
    if not KEY_RE.fullmatch(str(key)):
        raise ManifestError(f'setting "{key}": use a-z, 0-9 and _')
    if type not in SETTING_TYPES:
        raise ManifestError(f'setting "{key}": type must be one of {", ".join(SETTING_TYPES)}')
    if link and not str(link).startswith("https://"):
        raise ManifestError(f'setting "{key}": "link" must start with https://')
    pairs = []
    for o in options or ():
        value, text = (o, o) if isinstance(o, str) else (list(o) + [""])[:2]
        pairs.append((str(value)[:60], str(text or value)[:80]))
    if type == "choice" and not pairs:
        raise ManifestError(f'setting "{key}": a choice needs "options"')
    if isinstance(default, bool):
        default = "1" if default else ""
    default = "" if default is None else str(default)[:200]
    if type == "choice" and default and default not in [v for v, _ in pairs]:
        raise ManifestError(f'setting "{key}": "default" must be one of its options')
    if type == "number" and default:
        try:
            float(default)
        except ValueError:
            raise ManifestError(f'setting "{key}": "default" must be a number') from None
    return SettingField(str(key), str(label)[:80], type, str(help)[:200], str(link)[:200], tuple(pairs), default)


@dataclass(frozen=True)
class Language:
    code: str                             # "nl"
    name: str                             # "Nederlands"
    countries: tuple[str, ...] = ()       # where its search terms are used, e.g. ("NL", "BE")


@dataclass(frozen=True)
class Manifest:
    id: str
    name: str
    version: str
    api: int
    description: str = ""
    author: str = ""
    homepage: str = ""
    python: str = ""                       # file with register(api)
    ui: str = ""                           # screen code
    enabled_by_default: bool = False
    countries: tuple[str, ...] = ()        # where it's most useful (suggested for people there); () = anywhere
    profile_fields: tuple[ProfileField, ...] = ()
    settings: tuple[SettingField, ...] = ()
    language: Language | None = None
    translations: dict[str, str] = field(default_factory=dict)   # language code -> json file
    search_terms: dict[str, str] = field(default_factory=dict)   # language code -> json file

    def adds(self) -> list[str]:
        """Plain words for what it adds (shown before installing)."""
        out = []
        if self.python:
            out.append("runs Python code")
        if self.ui:
            out.append("adds to the screen")
        if self.profile_fields:
            out.append(f"{len(self.profile_fields)} profile field{'s' if len(self.profile_fields) != 1 else ''}")
        if self.settings:
            out.append("settings")
        if self.language:
            out.append(f"the {self.language.name} language")
        elif self.translations:
            out.append("translations")
        return out


def _text(d, key, limit, required=False):
    v = d.get(key, "")
    if not isinstance(v, str):
        raise ManifestError(f'"{key}" must be text')
    v = v.strip()
    if required and not v:
        raise ManifestError(f'"{key}" is missing')
    if len(v) > limit:
        raise ManifestError(f'"{key}" is too long (max {limit})')
    return v


def _file(d, key, folder):
    v = _text(d, key, 120)
    if not v:
        return ""
    if not FILE_RE.fullmatch(v) or ".." in v:
        raise ManifestError(f'"{key}" must be a file inside the plugin, like "plugin.py"')
    if not (folder / v).is_file():
        raise ManifestError(f'"{key}": {v} is not in the plugin')
    return v


def _files(d, key, folder):
    v = d.get(key) or {}
    if not isinstance(v, dict):
        raise ManifestError(f'"{key}" must map language codes to files')
    out = {}
    for code, path in v.items():
        if not re.fullmatch(r"[a-z]{2}", str(code)):
            raise ManifestError(f'"{key}": "{code}" is not a two-letter language code')
        out[code] = _file({"f": path}, "f", folder)
    return out


def parse(data: dict, folder: Path) -> Manifest:
    if not isinstance(data, dict):
        raise ManifestError("plugin.json must be an object")
    pid = _text(data, "id", 40, required=True)
    if not ID_RE.fullmatch(pid):
        raise ManifestError('"id" may only use a-z, 0-9 and "-", e.g. "accounting"')
    name = _text(data, "name", 60, required=True)
    version = _text(data, "version", 20, required=True)
    if not VERSION_RE.fullmatch(version):
        raise ManifestError('"version" must look like 1.0.0')
    api = data.get("api")
    if not isinstance(api, int) or api < 1:
        raise ManifestError('"api" must be the plugin API version it was made for, e.g. 1')
    if api > API_VERSION:
        raise ManifestError(f"made for a newer jobslop (plugin API {api}) - update jobslop first")
    fields = []
    for f in data.get("profile_fields") or []:
        if not isinstance(f, dict):
            raise ManifestError('"profile_fields" must be a list of fields')
        key = _text(f, "key", 40, required=True)
        if not KEY_RE.fullmatch(key):
            raise ManifestError(f'profile field "{key}": use a-z, 0-9 and _')
        ftype = _text(f, "type", 10) or "text"
        if ftype not in FIELD_TYPES:
            raise ManifestError(f'profile field "{key}": type must be one of {", ".join(FIELD_TYPES)}')
        autofill = f.get("autofill") or []
        if not isinstance(autofill, list) or not all(isinstance(a, str) and len(a) < 200 for a in autofill):
            raise ManifestError(f'profile field "{key}": "autofill" must be a list of patterns')
        for a in autofill:
            try:
                re.compile(a)
            except re.error:
                raise ManifestError(f'profile field "{key}": "{a}" is not a valid pattern') from None
        fields.append(ProfileField(key, _text(f, "label", 80, required=True), _text(f, "section", 40) or name,
                                   ftype, tuple(autofill)))
    settings = []
    for s in data.get("settings") or []:
        if not isinstance(s, dict):
            raise ManifestError('"settings" must be a list of settings')
        key = _text(s, "key", 40, required=True)
        if not KEY_RE.fullmatch(key):
            raise ManifestError(f'setting "{key}": use a-z, 0-9 and _')
        options = s.get("options") or []
        if not isinstance(options, list):
            raise ManifestError(f'setting "{key}": "options" must be a list')
        settings.append(setting_field(key, _text(s, "label", 80, required=True), _text(s, "type", 10) or "secret",
                                      _text(s, "help", 200), _text(s, "link", 200), options, s.get("default", "")))
    lang = None
    if data.get("language"):
        lg = data["language"]
        if not isinstance(lg, dict):
            raise ManifestError('"language" must be an object')
        code = _text(lg, "code", 10, required=True)
        if not re.fullmatch(r"[a-z]{2}", code):
            raise ManifestError('"language" code must be two letters, e.g. "nl"')
        countries = lg.get("countries") or []
        if not isinstance(countries, list) or not all(isinstance(c, str) and re.fullmatch(r"[A-Z]{2}", c) for c in countries):
            raise ManifestError('"language" countries must be codes like "NL"')
        lang = Language(code, _text(lg, "name", 40, required=True), tuple(countries))
    homepage = _text(data, "homepage", 200)
    if homepage and not homepage.startswith("https://"):
        raise ManifestError('"homepage" must start with https://')
    return Manifest(
        id=pid, name=name, version=version, api=api,
        description=_text(data, "description", 300), author=_text(data, "author", 60), homepage=homepage,
        python=_file(data, "python", folder), ui=_file(data, "ui", folder),
        enabled_by_default=bool(data.get("enabled_by_default")), countries=_countries(data),
        profile_fields=tuple(fields), settings=tuple(settings), language=lang,
        translations=_files(data, "translations", folder), search_terms=_files(data, "search_terms", folder))


def _countries(data: dict) -> tuple[str, ...]:
    c = data.get("countries") or []
    if not isinstance(c, list) or not all(isinstance(x, str) and re.fullmatch(r"[A-Z]{2}", x) for x in c):
        raise ManifestError('"countries" must be a list of codes like "GB"')
    return tuple(c)


def read(folder: Path) -> Manifest:
    path = Path(folder) / MANIFEST
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ManifestError("no plugin.json") from None
    except (OSError, ValueError) as e:
        raise ManifestError(f"plugin.json can't be read ({str(e)[:80]})") from None
    return parse(data, Path(folder))


def version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4])
