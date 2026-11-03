"""Languages: the screen's words and job titles in other languages, both supplied by plugins.

English is built in. A language pack is a plugin with a "language" in its plugin.json and two word lists:
  translations   English screen text -> translation        ({"Search jobs": "Vacatures zoeken"})
  search_terms   English job title  -> local job titles    ({"accountant": ["boekhouder"]})
Any plugin can add words for its own screen text, and job titles for its field, in any language.
"""

import json
import re

from jobslop.plugins.manager import PLUGINS, PluginManager
from jobslop.plugins.points import POINTS, ExtensionPoints

ENGLISH = {"code": "en", "name": "English"}

# the languages job adverts in a country are written in (language packs can add countries)
COUNTRY_LANGS = {
    "NL": ("nl",), "BE": ("nl", "fr"), "DK": ("da",), "ES": ("es",), "MX": ("es",), "AR": ("es",), "CL": ("es",),
    "CO": ("es",), "DE": ("de",), "AT": ("de",), "CH": ("de", "fr", "it"), "FR": ("fr",), "IT": ("it",), "PT": ("pt",),
    "BR": ("pt",), "SE": ("sv",), "NO": ("no",), "FI": ("fi",), "PL": ("pl",), "CZ": ("cs",), "RO": ("ro",),
    "GR": ("el",), "HU": ("hu",), "UA": ("uk",), "TR": ("tr",), "JP": ("ja",), "KR": ("ko",), "ID": ("id",),
    "TH": ("th",), "VN": ("vi",),
}


class Languages:
    def __init__(self, points: ExtensionPoints = POINTS, plugins: PluginManager = PLUGINS) -> None:
        self.points, self.plugins = points, plugins

    def available(self) -> list[dict]:
        """English plus every language pack (switched on or not), for the language picker."""
        out = [dict(ENGLISH, plugin="", enabled=True)]
        for p in self.plugins.all():
            lang = p.manifest.language if p.manifest else None
            if lang:
                out.append({"code": lang.code, "name": lang.name, "plugin": p.id, "enabled": p.loaded})
        return out

    def pack_for(self, code: str) -> str:
        """The plugin that provides a language ("" for English or unknown)."""
        return next((x["plugin"] for x in self.available() if x["code"] == code), "")

    def words(self, code: str) -> dict[str, str]:
        """Every translation of the screen's text into a language, from all switched-on plugins
        (and, from switched-off ones, just their own name and description for the Plugins list)."""
        out: dict[str, str] = {}
        for p in self.plugins.all():
            m = p.manifest
            if m and not p.loaded and code in m.translations:
                try:
                    own = json.loads((p.folder / m.translations[code]).read_text(encoding="utf-8-sig"))
                    out.update({k: own[k] for k in (m.name, m.description) if isinstance(own.get(k), str)})
                except (OSError, ValueError):
                    pass
        for t in self.points.translations:
            if t.lang == code:
                out.update({k: v for k, v in t.words.items() if isinstance(v, str) and v.strip()})
        return out

    def country_languages(self, country: str) -> tuple[str, ...]:
        langs = list(COUNTRY_LANGS.get((country or "").upper(), ()))
        for p in self.plugins.all():
            lang = p.manifest.language if p.manifest and p.loaded else None
            if lang and country.upper() in lang.countries and lang.code not in langs:
                langs.append(lang.code)
        return tuple(langs)

    def job_titles(self, langs) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for t in self.points.search_terms:
            if t.lang in langs:
                for k, v in t.words.items():
                    words = [v] if isinstance(v, str) else list(v or [])
                    have = out.setdefault(str(k).lower(), [])
                    have += [w for w in words if isinstance(w, str) and w.strip() and w not in have]
        return out

    def local_terms(self, query: str, country: str, limit: int = 3) -> list[str]:
        """'accountant' searched in the Netherlands -> ['boekhouder', 'financieel administrateur'].

        A whole-query match first; otherwise a known title inside the query is swapped
        ('senior accountant' -> 'senior boekhouder')."""
        q = " ".join((query or "").lower().split())
        if not q:
            return []
        titles = self.job_titles(self.country_languages(country))
        if not titles:
            return []
        found = list(titles.get(q, []))
        if not found:
            for key in sorted(titles, key=len, reverse=True):
                if re.search(r"\b" + re.escape(key) + r"\b", q):
                    found = [re.sub(r"\b" + re.escape(key) + r"\b", w, q) for w in titles[key]]
                    break
        out = []
        for w in found:
            w = " ".join(w.split())
            if w and w.lower() != q and w.lower() not in (x.lower() for x in out):
                out.append(w)
        return out[:limit]


LANGUAGES = Languages()
