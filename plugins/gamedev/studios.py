"""Game studios for the map: Game Dev Map's public list plus Wikipedia's indie developers (CC BY-SA).

Both are downloaded at most once a week into the plugin's data folder and placed with jobslop's offline towns.
"""

import csv
import json
import re
import threading
import time
import urllib.request

WEEK = 7 * 24 * 3600
GAMEDEVMAP_URL = "https://www.gamedevmap.com/cmsdata/gamedevmapdata.csv"
WIKIPEDIA_URL = ("https://en.wikipedia.org/w/api.php?action=parse&page=List_of_indie_game_developers&prop=text"
                 "&format=json&formatversion=2")


class Studios:
    def __init__(self, api):
        self.api = api
        self.studios_file = api.data_dir / "gamedevmap.csv"
        self.indie_file = api.data_dir / "indiestudios.json"
        self._cache = {"t": 0, "rows": []}
        self._lock = threading.Lock()

    def _fresh(self, path):
        return path.exists() and time.time() - path.stat().st_mtime < WEEK

    def all(self):
        with self._lock:
            if self._cache["rows"] and time.time() - self._cache["t"] < 24 * 3600:
                return self._cache["rows"]
            if not self._fresh(self.studios_file):
                try:
                    req = urllib.request.Request(GAMEDEVMAP_URL, headers=self.api.http.BROWSER_HEADERS)
                    self.studios_file.write_bytes(urllib.request.urlopen(req, timeout=30).read())
                except Exception:
                    pass                                  # keep the old copy (or none) when offline
            geo, rows = self.api.geo, []
            try:
                for r in csv.DictReader(self.studios_file.read_text(encoding="utf-8", errors="replace").splitlines()):
                    cc = geo.country_code(r.get("Country/Region", ""))
                    town = geo.find_town(r.get("City", ""), cc) if cc else None
                    if not town:
                        continue
                    cat = r.get("Category", "")
                    rows.append({"name": r.get("Organization", ""), "url": r.get("URL", ""), "city": r.get("City", ""),
                                 "country": r.get("Country/Region", ""), "type": cat, "lat": town["lat"],
                                 "lon": town["lon"], "indie": cat == "Microstudio", "source": "Game Dev Map"})
            except Exception:
                pass
            # Wikipedia's indie developers, added when not listed already (and marking listed ones as indie)
            have = {geo.normalise(r["name"]): r for r in rows}
            for s in self.indie():
                known = have.get(geo.normalise(s["name"]))
                if known:
                    known["indie"] = True
                else:
                    rows.append(s)
            self._cache.update(t=time.time(), rows=rows)
            return rows

    def indie(self):
        """Active indie developers with their city, from Wikipedia."""
        if not self._fresh(self.indie_file):
            try:
                req = urllib.request.Request(WIKIPEDIA_URL, headers={"User-Agent": "jobslop/1.0 (personal job search app)"})
                found = parse_wikipedia(json.loads(urllib.request.urlopen(req, timeout=30).read())["parse"]["text"],
                                        self.api.text.strip_html)
                if found:
                    self.indie_file.write_text(json.dumps(found, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        try:
            listed = json.loads(self.indie_file.read_text(encoding="utf-8"))
        except Exception:
            return []
        out = []
        for s in listed:
            cc = self.api.geo.country_code(s.get("country", ""))
            town = self.api.geo.find_town(s.get("city", ""), cc) if s.get("city") else None
            if town:
                out.append({"name": s["name"], "url": s.get("url", ""), "city": s["city"], "country": s.get("country", ""),
                            "type": "Indie" + (f" · {s['games']}" if s.get("games") else ""), "lat": town["lat"],
                            "lon": town["lon"], "indie": True, "source": "Wikipedia"})
        return out

    def near(self, lat, lon, km, limit=400, indie_only=False):
        out = []
        for s in self.all():
            if indie_only and not s.get("indie"):
                continue
            d = self.api.geo.km_between(lat, lon, s["lat"], s["lon"])
            if d <= km:
                out.append({**s, "dist_km": round(d, 1)})
        out.sort(key=lambda s: s["dist_km"])
        return out[:limit]


def parse_wikipedia(page, strip_html):
    found = []
    for table in re.findall(r'<table class="wikitable[^>]*>(.*?)</table>', page, re.S):
        rows = re.findall(r"<tr([^>]*)>(.*?)</tr>", table, re.S)
        head = [strip_html(c, 40).lower() for c in re.findall(r"<th[^>]*>(.*?)</th>", rows[0][1], re.S)] if rows else []
        if "developer" not in head or "city" not in head:
            continue
        for attrs, row in rows[1:]:
            if "#ffe8a9" in attrs.lower():
                continue                                  # shaded yellow = closed / no longer active
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)
            if len(cells) < len(head):
                continue
            cell = dict(zip(head, cells))
            link = re.search(r'href="(/wiki/[^"#]+)"', cell["developer"])
            games = [strip_html(g, 60) for g in re.findall(r"<li[^>]*>(.*?)</li>", cell.get("notable games", ""), re.S)]
            found.append({"name": strip_html(cell["developer"], 80), "city": strip_html(cell["city"], 60),
                          "region": strip_html(cell.get("autonomous area", ""), 60),
                          "country": strip_html(cell.get("country", ""), 60),
                          "url": "https://en.wikipedia.org" + link[1] if link else "",
                          "games": ", ".join(g for g in games if g)[:120]})
    return found
