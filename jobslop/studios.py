"""Game studios (Game Dev Map's public list + Wikipedia's indie developers) for the map."""

import csv
import json
import re
import threading
import time
import urllib.request

from jobslop.config import DATA_DIR
from jobslop.geo.cities import _norm, code_for_country_text, find_city, km_between
from jobslop.geo.countries import COUNTRY_ALIASES
from jobslop.net import BROWSER_UA
from jobslop.text import strip_html

# ---- game studios (Game Dev Map's public studio list, refreshed weekly, placed with the offline towns)
STUDIOS_FILE = DATA_DIR / "gamedevmap.csv"
_studios = {"t": 0, "rows": []}
_studios_lock = threading.Lock()


def studios():
    with _studios_lock:
        if _studios["rows"] and time.time() - _studios["t"] < 24 * 3600:
            return _studios["rows"]
        fresh = STUDIOS_FILE.exists() and time.time() - STUDIOS_FILE.stat().st_mtime < 7 * 24 * 3600
        if not fresh:
            try:
                data = urllib.request.urlopen(urllib.request.Request(
                    "https://www.gamedevmap.com/cmsdata/gamedevmapdata.csv", headers=BROWSER_UA), timeout=30).read()
                STUDIOS_FILE.write_bytes(data)
            except Exception:
                pass
        rows = []
        try:
            for r in csv.DictReader(STUDIOS_FILE.read_text(encoding="utf-8", errors="replace").splitlines()):
                cc = code_for_country_text(r.get("Country/Region", ""))
                town = find_city(r.get("City", ""), cc) if cc else None
                if not town:
                    continue
                cat = r.get("Category", "")
                rows.append({"name": r.get("Organization", ""), "url": r.get("URL", ""), "city": r.get("City", ""),
                             "country": r.get("Country/Region", ""), "type": cat, "lat": town[1], "lon": town[2],
                             "indie": cat == "Microstudio", "source": "Game Dev Map"})
        except Exception:
            pass
        # indie studios from Wikipedia's "List of indie game developers" (CC BY-SA), added when not already listed
        have = {_norm(r["name"]) for r in rows}
        for s in indie_studios():
            if _norm(s["name"]) in have:
                for r in rows:
                    if _norm(r["name"]) == _norm(s["name"]):
                        r["indie"] = True
                continue
            rows.append(s)
        _studios.update(t=time.time(), rows=rows)
        return rows


INDIE_FILE = DATA_DIR / "indiestudios.json"


def indie_studios():
    """Active indie developers with their city, from Wikipedia (refreshed weekly, works offline after that)."""
    fresh = INDIE_FILE.exists() and time.time() - INDIE_FILE.stat().st_mtime < 7 * 24 * 3600
    if not fresh:
        try:
            url = ("https://en.wikipedia.org/w/api.php?action=parse&page=List_of_indie_game_developers&prop=text"
                   "&format=json&formatversion=2")
            page = json.loads(urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "JobFinder/1.0 (personal job search app)"}), timeout=30).read())["parse"]["text"]
            found = []
            for table in re.findall(r'<table class="wikitable[^>]*>(.*?)</table>', page, re.S):
                rows = re.findall(r"<tr([^>]*)>(.*?)</tr>", table, re.S)
                head = [strip_html(c, 40).lower() for c in re.findall(r"<th[^>]*>(.*?)</th>", rows[0][1], re.S)] if rows else []
                if "developer" not in head or "city" not in head:
                    continue
                for attrs, row in rows[1:]:
                    if "#ffe8a9" in attrs.lower():
                        continue                         # shaded yellow = closed / no longer active
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
            if found:
                INDIE_FILE.write_text(json.dumps(found, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    try:
        listed = json.loads(INDIE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for s in listed:
        cc = code_for_country_text(s.get("country", "")) or COUNTRY_ALIASES.get(s.get("country", "").lower())
        town = find_city(s.get("city", ""), cc) if s.get("city") else None
        if town:
            out.append({"name": s["name"], "url": s.get("url", ""), "city": s["city"], "country": s.get("country", ""),
                        "type": "Indie" + (f" · {s['games']}" if s.get("games") else ""), "lat": town[1], "lon": town[2],
                        "indie": True, "source": "Wikipedia"})
    return out


def studios_near(lat, lon, km, limit=400, indie_only=False):
    out = []
    for s in studios():
        if indie_only and not s.get("indie"):
            continue
        d = km_between(lat, lon, s["lat"], s["lon"])
        if d <= km:
            out.append({**s, "dist_km": round(d, 1)})
    out.sort(key=lambda s: s["dist_km"])
    return out[:limit]
