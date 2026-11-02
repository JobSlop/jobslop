"""
jobslop (formerly Job Finder) - type the kind of job you want, get organized UK job listings with links.

Run as a script:  python jobfinder.py
Or build the standalone program:  build.bat  ->  dist\\jobslop.exe

Sources:
  UK boards (free API key, set in Settings): Reed, Adzuna  - includes in-person UK jobs
  Remote boards (no key): Himalayas, Jobicy, Remotive, RemoteOK, Arbeitnow - filtered to UK-friendly jobs

Saved jobs and settings live in %APPDATA%\\JobFinder (the folder keeps its old name, so nothing is lost).
"""

import base64
import csv
import hashlib
import html
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

IS_WIN, IS_MAC = sys.platform.startswith("win"), sys.platform == "darwin"


def _data_dir():
    if IS_WIN:
        return Path(os.environ.get("APPDATA") or Path.home()) / "JobFinder"
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / "JobFinder"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "JobFinder"


DATA_DIR = _data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)


def open_path(path):
    """Open a file or folder in Explorer / Finder."""
    if IS_WIN:
        os.startfile(str(path))
    elif IS_MAC:
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def copy_to_clipboard(text):
    if IS_WIN:
        subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    elif IS_MAC:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    else:
        subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True)


def _use_bundled_certificates():
    """Python on a Mac often has no certificate store, so every secure connection fails.
    Use certifi's certificates for all connections (harmless on Windows)."""
    try:
        import ssl
        import certifi
        if not IS_WIN:
            ssl._create_default_https_context = lambda *a, **k: ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass


_use_bundled_certificates()
SAVED_FILE = DATA_DIR / "saved_jobs.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
UA = {"User-Agent": "Mozilla/5.0 (personal JobFinder app)"}
STOPWORDS = {"a", "an", "the", "and", "or", "of", "for", "in", "to", "job", "jobs", "remote"}

# ---- countries: code -> (name, JobSpy name, Adzuna code, Jobicy geo, region, currency, extra place names)
COUNTRIES = {
    "GB": ("United Kingdom", "UK", "gb", "uk", "eu", "GBP", "uk|u\\.k\\.|great britain|britain|england|scotland|wales|northern ireland|london|manchester|birmingham|leeds|glasgow|edinburgh|bristol|gmt"),
    "US": ("United States", "USA", "us", "usa", "na", "USD", "usa|u\\.s\\.a?\\.?|united states|america"),
    "CA": ("Canada", "CANADA", "ca", "canada", "na", "CAD", "canada|toronto|vancouver|montreal"),
    "AU": ("Australia", "AUSTRALIA", "au", "australia", "apac", "AUD", "australia|sydney|melbourne"),
    "NZ": ("New Zealand", "NEWZEALAND", "nz", "", "apac", "NZD", "new zealand|auckland"),
    "IE": ("Ireland", "IRELAND", "", "ireland", "eu", "EUR", "ireland|dublin"),
    "DE": ("Germany", "GERMANY", "de", "germany", "eu", "EUR", "germany|deutschland|berlin|munich|hamburg"),
    "FR": ("France", "FRANCE", "fr", "france", "eu", "EUR", "france|paris"),
    "NL": ("Netherlands", "NETHERLANDS", "nl", "netherlands", "eu", "EUR", "netherlands|holland|amsterdam"),
    "BE": ("Belgium", "BELGIUM", "be", "belgium", "eu", "EUR", "belgium|brussels"),
    "ES": ("Spain", "SPAIN", "es", "spain", "eu", "EUR", "spain|madrid|barcelona"),
    "IT": ("Italy", "ITALY", "it", "italy", "eu", "EUR", "italy|milan|rome"),
    "PT": ("Portugal", "PORTUGAL", "", "portugal", "eu", "EUR", "portugal|lisbon|porto"),
    "AT": ("Austria", "AUSTRIA", "at", "austria", "eu", "EUR", "austria|vienna"),
    "CH": ("Switzerland", "SWITZERLAND", "ch", "switzerland", "eu", "CHF", "switzerland|zurich|geneva"),
    "SE": ("Sweden", "SWEDEN", "", "sweden", "eu", "SEK", "sweden|stockholm"),
    "DK": ("Denmark", "DENMARK", "", "denmark", "eu", "DKK", "denmark|copenhagen"),
    "NO": ("Norway", "NORWAY", "", "norway", "eu", "NOK", "norway|oslo"),
    "FI": ("Finland", "FINLAND", "", "finland", "eu", "EUR", "finland|helsinki"),
    "PL": ("Poland", "POLAND", "pl", "poland", "eu", "PLN", "poland|warsaw|krakow"),
    "CZ": ("Czech Republic", "CZECHREPUBLIC", "", "czechia", "eu", "CZK", "czech|czechia|prague"),
    "RO": ("Romania", "ROMANIA", "", "romania", "eu", "RON", "romania|bucharest"),
    "GR": ("Greece", "GREECE", "", "greece", "eu", "EUR", "greece|athens"),
    "HU": ("Hungary", "HUNGARY", "", "hungary", "eu", "HUF", "hungary|budapest"),
    "UA": ("Ukraine", "UKRAINE", "", "ukraine", "eu", "UAH", "ukraine|kyiv"),
    "TR": ("Turkey", "TURKEY", "", "turkiye", "emea", "TRY", "turkey|türkiye|turkiye|istanbul"),
    "IN": ("India", "INDIA", "in", "india", "apac", "INR", "india|bangalore|bengaluru|mumbai|delhi|hyderabad|pune"),
    "SG": ("Singapore", "SINGAPORE", "sg", "singapore", "apac", "SGD", "singapore"),
    "MY": ("Malaysia", "MALAYSIA", "", "malaysia", "apac", "MYR", "malaysia|kuala lumpur"),
    "PH": ("Philippines", "PHILIPPINES", "", "philippines", "apac", "PHP", "philippines|manila"),
    "JP": ("Japan", "JAPAN", "", "japan", "apac", "JPY", "japan|tokyo"),
    "KR": ("South Korea", "SOUTHKOREA", "", "south-korea", "apac", "KRW", "korea|seoul"),
    "HK": ("Hong Kong", "HONGKONG", "", "", "apac", "HKD", "hong kong"),
    "ID": ("Indonesia", "INDONESIA", "", "indonesia", "apac", "IDR", "indonesia|jakarta"),
    "TH": ("Thailand", "THAILAND", "", "thailand", "apac", "THB", "thailand|bangkok"),
    "VN": ("Vietnam", "VIETNAM", "", "vietnam", "apac", "VND", "vietnam|ho chi minh|hanoi"),
    "AE": ("United Arab Emirates", "UNITEDARABEMIRATES", "", "uae", "emea", "AED", "uae|united arab emirates|dubai|abu dhabi"),
    "SA": ("Saudi Arabia", "SAUDIARABIA", "", "", "emea", "SAR", "saudi|riyadh"),
    "QA": ("Qatar", "QATAR", "", "", "emea", "QAR", "qatar|doha"),
    "IL": ("Israel", "ISRAEL", "", "israel", "emea", "ILS", "israel|tel aviv"),
    "EG": ("Egypt", "EGYPT", "", "egypt", "emea", "EGP", "egypt|cairo"),
    "ZA": ("South Africa", "SOUTHAFRICA", "za", "south-africa", "emea", "ZAR", "south africa|johannesburg|cape town"),
    "NG": ("Nigeria", "NIGERIA", "", "nigeria", "emea", "NGN", "nigeria|lagos"),
    "BR": ("Brazil", "BRAZIL", "br", "brazil", "latam", "BRL", "brazil|brasil|são paulo|sao paulo"),
    "MX": ("Mexico", "MEXICO", "mx", "mexico", "latam", "MXN", "mexico|méxico"),
    "AR": ("Argentina", "ARGENTINA", "", "argentina", "latam", "ARS", "argentina|buenos aires"),
    "CL": ("Chile", "CHILE", "", "chile", "latam", "CLP", "chile|santiago"),
    "CO": ("Colombia", "COLOMBIA", "", "colombia", "latam", "COP", "colombia|bogota|bogotá"),
}
REGIONS = {"eu": "europe|emea|eu|european union|cet|gmt",
           "na": "north america|americas|us timezones|est|pst",
           "apac": "apac|asia|asia pacific|oceania",
           "emea": "emea|middle east|africa",
           "latam": "latam|latin america|south america|americas"}


def country_info(code):
    return COUNTRIES.get((code or "GB").upper(), COUNTRIES["GB"])


def local_ok_re(code):
    """Locations someone in this country can work from (filters the remote boards)."""
    name, _, _, _, region, _, extra = country_info(code)
    pat = "|".join([re.escape(name.lower()), extra, REGIONS.get(region, ""), "worldwide|anywhere|global"])
    return re.compile(r"(?<![a-z])(" + pat.strip("|") + r")(?![a-z])", re.I)


COUNTRY_ALIASES = {"uk": "GB", "u.k.": "GB", "britain": "GB", "great britain": "GB", "england": "GB", "gb": "GB",
                   "usa": "US", "us": "US", "u.s.": "US", "america": "US", "united states of america": "US",
                   "deutschland": "DE", "holland": "NL", "uae": "AE", "the netherlands": "NL",
                   # how countries are written in their own languages (job boards use these)
                   "nederland": "NL", "danmark": "DK", "españa": "ES", "espana": "ES", "italia": "IT", "sverige": "SE",
                   "norge": "NO", "suomi": "FI", "polska": "PL", "schweiz": "CH", "suisse": "CH", "österreich": "AT",
                   "belgië": "BE", "belgie": "BE", "belgique": "BE", "brasil": "BR", "méxico": "MX", "eire": "IE",
                   "éire": "IE", "verenigd koninkrijk": "GB", "storbritannien": "GB", "verenigde staten": "US",
                   "usa (remote)": "US", "england, uk": "GB", "eng": "GB", "sct": "GB", "wls": "GB"}


def is_country_name(text, code):
    """True when 'Where?' is empty or just names the whole country ("UK", "Germany")."""
    t = (text or "").strip().lower()
    if not t:
        return True
    code = (code or "GB").upper()
    return t in (country_info(code)[0].lower(), code.lower()) or COUNTRY_ALIASES.get(t) == code


# ---------------------------------------------------------------- offline towns (GeoNames, CC BY 4.0)
# ~70,000 towns with coordinates, bundled with the app: powers the map search and job distances
# without any online lookup service.
import gzip
import math

RES_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
_cities = {"by_name": None, "rows": None}
_cities_lock = threading.Lock()


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


def cities():
    with _cities_lock:
        if _cities["rows"] is None:
            rows, by_name = [], {}
            try:
                with gzip.open(RES_DIR / "cities.tsv.gz", "rt", encoding="utf-8") as f:
                    for line in f:
                        name, lat, lon, cc, admin1, pop, alts = line.rstrip("\n").split("\t")
                        row = (name, float(lat), float(lon), cc, admin1, int(pop or 0))
                        rows.append(row)
                        for n in [name] + (alts.split("|") if alts else []):
                            by_name.setdefault(_norm(n), []).append(row)
            except Exception:
                pass
            _cities["rows"], _cities["by_name"] = rows, by_name
    return _cities


def code_for_country_text(text):
    t = (text or "").strip().lower()
    if not t:
        return None
    if t.upper() in COUNTRIES:
        return t.upper()
    for code, v in COUNTRIES.items():
        if t == v[0].lower():
            return code
    return COUNTRY_ALIASES.get(t)


def find_city(name, cc=None):
    """Best town for a name (prefers the given country, then the biggest)."""
    hits = cities()["by_name"].get(_norm(name)) or []
    if not hits:
        return None
    if cc:
        hits = [h for h in hits if h[3] == cc]      # e.g. "Nederland" must not become Nederland, Colorado
        if not hits:
            return None
    return max(hits, key=lambda h: h[5])


def city_label(row):
    return f"{row[0]}, {country_info(row[3])[0] if row[3] in COUNTRIES else row[3]}"


def geocode_text(q, cc=None):
    """'Birmingham, United Kingdom' / 'Austin' -> town row, using the offline list."""
    parts = [p.strip() for p in re.split(r"[,·]", q or "") if p.strip()]
    if not parts:
        return None
    if len(parts) > 1 and code_for_country_text(parts[-1]):
        cc = code_for_country_text(parts[-1])
        parts = parts[:-1]
    for i in range(len(parts)):
        row = find_city(parts[i], cc)
        if row:
            return row
    return None


def nearest_city(lat, lon):
    """The biggest town within 8 km of a point (so central Amsterdam gives Amsterdam, not a
    neighbourhood), otherwise simply the nearest town."""
    best, bd, near = None, 1e9, []
    for row in cities()["rows"]:
        if abs(row[1] - lat) > 1 or abs(row[2] - lon) > 2:
            continue
        d = km_between(lat, lon, row[1], row[2])
        if d < bd:
            best, bd = row, d
        if d <= 8:
            near.append(row)
    return max(near, key=lambda r: r[5]) if near else best


def km_between(a_lat, a_lon, b_lat, b_lon):
    p = math.pi / 180
    h = 0.5 - math.cos((b_lat - a_lat) * p) / 2 + math.cos(a_lat * p) * math.cos(b_lat * p) * (1 - math.cos((b_lon - a_lon) * p)) / 2
    return 12742 * math.asin(math.sqrt(h))


REMOTE_RE = re.compile(r"remote|anywhere|worldwide|thuiswerk|hjemmearbejde|home ?office", re.I)


def job_point(j, cc):
    """Where a job is: exact coordinates if the board gave them, else its town looked up offline."""
    if j.get("lat") is not None and j.get("lon") is not None:
        return j["lat"], j["lon"]
    loc = j.get("location") or ""
    if not loc or REMOTE_RE.search(loc) and not re.search(r"hybrid", loc, re.I):
        return None
    parts = [p.strip() for p in re.split(r"[,·/|()]| - ", loc) if p.strip()]
    hint = next((code_for_country_text(p) for p in reversed(parts) if code_for_country_text(p)), None) or cc
    for p in parts[:3]:
        if code_for_country_text(p):
            continue                                  # "Nederland", "UK" etc. name a country, not a town
        p2 = re.sub(r"\s+(n|s|v|c|ø|k|area|metropolitan area|greater)$", "", p, flags=re.I)   # "Aarhus N", "London Area"
        row = find_city(p2, hint)
        if row:
            return row[1], row[2]
    return None


def towns_in_box(s, w, n, e, limit=60):
    """Biggest towns inside a map view (labels for the offline map)."""
    rows = [r for r in cities()["rows"] if s <= r[1] <= n and w <= r[2] <= e]
    rows.sort(key=lambda r: -r[5])
    return [{"n": r[0], "lat": r[1], "lon": r[2], "p": r[5]} for r in rows[:limit]]


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


# ---- "Where?" understands more than a town: "B3 2BJ", "12 Colmore Row, Birmingham B3 2BJ",
# "Coventry, West Midlands", "Daytona Beach, FL 32114", "1012 AB Amsterdam", "8000 Aarhus C", "Austin TX".
# Job boards only understand a town, so everything is boiled down to: town (+ state), postcode, country, point.

PLACES_FILE = DATA_DIR / "places.json"
_places = {"mem": {}, "disk": None}
_places_lock = threading.Lock()
WHERE_POSTCODES = [                                   # (country, pattern) — tried in this order
    ("GB", r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b"),        # B3 2BJ, SW1A 1AA
    ("NL", r"\b(\d{4}\s?[A-Z]{2})\b"),                           # 1012 AB
    ("US", r"\b(\d{5})(?:-\d{4})?\b"),                           # 32114, 32114-1234
    ("*", r"\b(?:[A-Z]{1,2}-)?(\d{4,5})\b"),                     # 8000 (DK), 10115 (DE), D-10115
]
UK_OUTCODE = r"[A-Z]{1,2}\d[A-Z\d]?"                             # "B3", "CV1", "SW1A" on their own
WHERE_SKIP = re.compile(r"^(?:flat|apt|apartment|unit|suite|ste|room|floor|fl|po box|c/o|the)\b|^\d", re.I)
WHERE_NOT_TOWN = re.compile(r"^(?:" + r"street|st|road|rd|avenue|ave|lane|ln|drive|dr|close|way|court|ct|place|pl|"
                            r"crescent|grove|terrace|gardens|row|walk|hill|park|view|rise|green|house|flat|unit|"
                            r"north|south|east|west|upper|lower|new|old|great|little|centre|center|city|town" + r")$", re.I)


def _place_disk():
    if _places["disk"] is None:
        try:
            _places["disk"] = json.loads(PLACES_FILE.read_text(encoding="utf-8"))
        except Exception:
            _places["disk"] = {}
    return _places["disk"]


def lookup_postcode(pc, cc):
    """A postcode -> (lat, lon) online (postcodes.io for the UK, OpenStreetMap elsewhere). Cached on disk for good."""
    key = cc + "|" + re.sub(r"\s+", "", pc.upper())
    with _places_lock:
        hit = _place_disk().get(key)
    if hit is not None:
        return tuple(hit) if hit else None
    point = None
    try:
        if cc == "GB":
            compact = re.sub(r"\s+", "", pc)
            full = re.fullmatch(r"[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}", compact.upper())
            d = get_json(("https://api.postcodes.io/postcodes/" if full else "https://api.postcodes.io/outcodes/")
                         + urllib.parse.quote(compact), timeout=8)
            r = d.get("result") or {}
            if r.get("latitude") is not None:
                point = (r["latitude"], r["longitude"])
        else:
            found = nominatim("search", {"postalcode": pc, "countrycodes": cc.lower(), "limit": 1})
            if found:
                point = (float(found[0]["lat"]), float(found[0]["lon"]))
    except Exception:
        return None                                   # offline / not found: try again next time
    with _places_lock:
        _place_disk()[key] = list(point) if point else []
        try:
            PLACES_FILE.write_text(json.dumps(_place_disk()), encoding="utf-8")
        except Exception:
            pass
    return point


def _town_in(parts, cc):
    """The first town named in the address parts (whole parts first, then words inside a part)."""
    order = [p for p in parts if not WHERE_SKIP.search(p)] + [p for p in parts if WHERE_SKIP.search(p)]
    for p in order:                                   # "Birmingham", "Daytona Beach", "Aarhus C"
        p2 = re.sub(r"\s+(n|s|v|c|ø|k|sv|nv|centre|center|city|area)$", "", p, flags=re.I)
        for cand in (p, p2):
            row = find_city(cand, cc)
            if row and not WHERE_NOT_TOWN.match(cand):
                return row, p, cand
    for p in order:                                   # "12 Colmore Row Birmingham", "Main St Austin"
        words = [w for w in re.split(r"\s+", p) if w]
        for n in range(min(len(words), 4), 0, -1):
            for start in [len(words) - n] + list(range(0, len(words) - n)):
                cand = " ".join(words[start:start + n])
                if len(cand) < 3 or WHERE_NOT_TOWN.match(cand) or re.search(r"\d", cand):
                    continue
                row = find_city(cand, cc)
                if row:
                    return row, p, cand
    return None, None, None


def resolve_where(text, cc="GB", online=True):
    """Anything typed in "Where?" -> {town, region, postcode, country_code, lat, lon, label, explicit_country,
    board_where}. None means "anywhere in the country" (empty, or just the country's name)."""
    t = re.sub(r"\s+", " ", (text or "").replace("\n", ", ")).strip(" ,.")
    cc = (cc or "GB").upper()
    if is_country_name(t, cc):
        return None
    mkey = (t.lower(), cc, online)
    with _places_lock:
        if mkey in _places["mem"]:
            return dict(_places["mem"][mkey])
    out = {"input": t, "town": "", "region": "", "postcode": "", "country_code": cc, "lat": None, "lon": None,
           "explicit_country": False, "found": False}
    parts = [p.strip(" .") for p in re.split(r"[,·;|]", t) if p.strip(" .")]
    # a country at the end: "..., United Kingdom", "Birmingham UK"
    if parts and code_for_country_text(parts[-1]):
        out.update(country_code=code_for_country_text(parts[-1]), explicit_country=True)
        parts = parts[:-1]
    elif parts and len(parts[-1].split()) > 1 and code_for_country_text(parts[-1].split()[-1]) \
            and parts[-1].split()[-1].lower() not in ("in", "de", "me", "ca", "co", "la", "pa"):
        out.update(country_code=code_for_country_text(parts[-1].split()[-1]), explicit_country=True)
        parts[-1] = " ".join(parts[-1].split()[:-1])
    # US "City, ST 12345" / "City ST" / "City, Texas"
    if len(parts) >= 1:
        last = parts[-1]
        m = re.fullmatch(r"(?:(.*?)\s+)?([A-Z]{2})\.?(?:\s+(\d{5})(?:-\d{4})?)?", last)
        if m and m.group(2) in US_STATES and (m.group(3) or len(parts) > 1 or m.group(1)) and cc not in ("CA",) \
                and not (cc == "GB" and re.fullmatch(UK_OUTCODE, last)):
            out.update(country_code="US", explicit_country=True, region=m.group(2), postcode=m.group(3) or "")
            parts = parts[:-1] + ([m.group(1)] if m.group(1) else [])
        elif last.lower() in US_STATE_NAMES and len(parts) > 1:
            out.update(country_code="US", explicit_country=True, region=US_STATE_NAMES[last.lower()])
            parts = parts[:-1]
    cc = out["country_code"]
    # postcodes (taken out of the text so they aren't mistaken for towns)
    if not out["postcode"]:
        for pcc, pat in WHERE_POSTCODES:
            if pcc not in ("*", cc) and not (pcc == "GB" and cc in ("GB", "IE")):
                continue
            hit = None
            for i, p in enumerate(parts):
                m = re.search(pat, p.upper() if pcc in ("GB", "NL") else p)
                if m:
                    hit = (i, m)
                    break
            if hit:
                i, m = hit
                out["postcode"] = re.sub(r"\s+", " ", m.group(1).upper())
                if pcc == "GB" and " " not in out["postcode"]:
                    out["postcode"] = out["postcode"][:-3] + " " + out["postcode"][-3:]
                parts[i] = (parts[i][:m.start()] + " " + parts[i][m.end():]).strip(" -")
                break
        if not out["postcode"] and cc == "GB":            # an outward code on its own: "B3", "CV1"
            for i, p in enumerate(parts):
                if re.fullmatch(UK_OUTCODE, p.upper().strip()) and not find_city(p, cc):
                    out["postcode"] = p.upper().strip()
                    parts[i] = ""
                    break
    parts = [p for p in parts if p]
    # the town
    row, part, typed = _town_in(parts, cc) if parts else (None, None, None)
    if row:
        # keep the user's spelling ("Aarhus", "Leamington Spa") — boards know those better than "Århus"
        name = row[0] if typed.islower() or _norm(typed) == _norm(row[0]) else typed.strip()
        out.update(town=name, lat=row[1], lon=row[2], found=True)
        if cc == "US" and not out["region"]:
            out["region"] = row[4]
        rest = parts[parts.index(part) + 1:] if part in parts else []
        if rest and not out["region"] and not WHERE_SKIP.search(rest[0]):
            out["region"] = rest[0]                       # "Coventry, West Midlands"
    # a postcode pins the exact spot (and the town, when only the postcode was given)
    if out["postcode"] and online:
        pt = lookup_postcode(out["postcode"], cc)
        if pt and (not row or km_between(pt[0], pt[1], row[1], row[2]) < 60):
            out.update(lat=pt[0], lon=pt[1])
            if not row:
                near = nearest_city(pt[0], pt[1])
                if near:
                    out.update(town=near[0], found=True)
                    if cc == "US":
                        out["region"] = out["region"] or near[4]
    # last resort: OpenStreetMap search for small places that aren't in the offline list
    if not out["found"] and online and parts:
        try:
            hits = nominatim("search", {"q": ", ".join(parts), "countrycodes": cc.lower(), "limit": 1})
            if hits:
                s = place_summary(hits[0])
                if s["town"]:
                    out.update(town=s["town"], lat=s["lat"], lon=s["lon"], found=True)
        except Exception:
            pass
    if not out["town"] and parts:                         # unknown place: pass the cleanest part on as typed
        cand = next((p for p in parts if not WHERE_SKIP.search(p)), parts[0])
        out["town"] = re.sub(r"^\d+[A-Za-z]?\s+", "", cand).strip()
    out["board_where"] = (f"{out['town']}, {out['region']}" if cc == "US" and out["region"] and out["town"]
                          else out["town"])
    local = f"{out['region']} {out['postcode']}".strip() if cc == "US" else out["postcode"]   # "FL 32114"
    out["label"] = ", ".join(x for x in (out["town"], local, country_info(cc)[0] if cc in COUNTRIES else cc) if x)
    with _places_lock:
        _places["mem"][mkey] = dict(out)
    return out


def place(o):
    """Location text to send to job boards: the town if given, else the country."""
    name = country_info(o["country"])[0]
    if is_country_name(o["where"], o["country"]):
        return name
    return o["where"] if "," in o["where"] else f"{o['where']}, {name}"   # "Austin" -> "Austin, United States"


# ---------------------------------------------------------------- helpers

def get_json(url, timeout=20, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def strip_html(text, limit=600):
    if not text:
        return ""
    text = html.unescape(html.unescape(str(text)))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def to_date(value):
    """Turn epoch numbers, ISO strings or dd/mm/yyyy into 'YYYY-MM-DD'."""
    if value in (None, "", 0):
        return ""
    try:
        s = str(value)
        if isinstance(value, (int, float)) or s.isdigit():
            return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%d")
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
        if m:
            return f"{m[3]}-{m[2]}-{m[1]}"
        return s[:10]
    except Exception:
        return ""


def money(lo, hi, cur="USD"):
    sym = {"GBP": "£", "USD": "$", "EUR": "€", "INR": "₹", "JPY": "¥", "AUD": "A$", "CAD": "C$",
           "NZD": "NZ$", "SGD": "S$", "HKD": "HK$", "BRL": "R$", "ZAR": "R", "CHF": "CHF ",
           "PLN": "zł ", "SEK": "kr ", "NOK": "kr ", "DKK": "kr ", "MXN": "MX$"}.get((cur or "").upper())

    def fmt(n):
        try:
            n = float(n)
        except (TypeError, ValueError):
            return None
        if n <= 0:
            return None
        return f"{n/1000:.0f}k" if n >= 1000 else f"{n:.0f}"
    lo, hi = fmt(lo), fmt(hi)
    pre = sym or (cur + " ")
    if lo and hi and lo != hi:
        return f"{pre}{lo}–{pre}{hi}"
    if lo or hi:
        return f"{pre}{lo or hi}"
    return ""


def as_list(v):
    if isinstance(v, list):
        return [str(x.get("name", x)) if isinstance(x, dict) else str(x) for x in v]
    return [str(v)] if v else []


def job(source, title, company, url, location="", date="", salary="", jtype="", tags=None, desc="", remote=True):
    return {
        "source": source,
        "title": strip_html(title, 200),
        "company": strip_html(company, 120),
        "url": url or "",
        "location": strip_html(location, 160) or "Not listed",
        "date": date,
        "salary": salary or "",
        "type": jtype or "",
        "tags": [t for t in (tags or []) if t][:8],
        "desc": strip_html(desc),
        "remote": remote,
    }


class NeedsKey(Exception):
    pass


# ---------------------------------------------------------------- settings

KEY_NAMES = ("reed_key", "adzuna_id", "adzuna_key", "apify_token", "usajobs_key", "usajobs_email")

def load_settings():
    if not SETTINGS_FILE.exists():
        return {}
    for attempt in range(5):                 # retry briefly if the file is being swapped in
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
        except Exception:
            time.sleep(0.05)
    return {}


settings_lock = threading.RLock()


def update_settings(change):
    """Change settings.json safely: one change at a time, and written to a temporary file first,
    so two quick saves can't overwrite each other and a half-written file is never read."""
    with settings_lock:
        s = load_settings()
        change(s)
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
        os.replace(tmp, SETTINGS_FILE)
        return s


def save_settings(data):
    def change(s):
        for k in KEY_NAMES:
            if k in data:
                s[k] = (data[k] or "").strip()
    return update_settings(change)


def public_settings():
    s = load_settings()
    mask = lambda v: (v[:3] + "•" * 6 + v[-2:]) if v and len(v) > 6 else ("set" if v else "")
    return {k: mask(s.get(k, "")) for k in KEY_NAMES}


# ---------------------------------------------------------------- sources
# Each source takes (query, opts). opts keys:
#   where (town or ""), miles, country (ISO code), local (only jobs workable from that country),
#   strict, posted (max days old, 0 = any), jtype ("", fulltime, parttime, contract, internship),
#   remote ("", remote, hybrid, onsite), salary_min (yearly, local currency, 0 = any)

class NotHere(Exception):
    """This board doesn't cover the chosen country."""


def src_reed(q, o):
    if o["country"] != "GB":
        raise NotHere("UK only")
    key = load_settings().get("reed_key")
    if not key:
        raise NeedsKey("add a free key in Settings")
    auth = {"Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()}
    out = []
    for skip in (0, 100):
        params = {"keywords": q, "resultsToTake": 100, "resultsToSkip": skip}
        if not is_country_name(o["where"], "GB"):
            params.update(locationName=o["where"], distanceFromLocation=o["miles"])
        if o["salary_min"]:
            params["minimumSalary"] = o["salary_min"]
        jt = {"fulltime": "fullTime", "parttime": "partTime", "contract": "contract", "internship": "temp"}.get(o["jtype"])
        if jt:
            params[jt] = "true"
        d = get_json("https://www.reed.co.uk/api/1.0/search?" + urllib.parse.urlencode(params), headers=auth)
        res = d.get("results", [])
        for j in res:
            out.append(job("Reed", j.get("jobTitle"), j.get("employerName"), j.get("jobUrl"),
                           j.get("locationName"), to_date(j.get("date")),
                           money(j.get("minimumSalary"), j.get("maximumSalary"), j.get("currency") or "GBP"),
                           "", [], j.get("jobDescription"), remote=False))
        if len(res) < 100:
            break
    return out


def src_adzuna(q, o):
    code = country_info(o["country"])[2]
    if not code:
        raise NotHere("not available in " + country_info(o["country"])[0])
    s = load_settings()
    if not (s.get("adzuna_id") and s.get("adzuna_key")):
        raise NeedsKey("add a free key in Settings")
    cur = country_info(o["country"])[5]
    out = []
    for page in (1, 2):
        params = {"app_id": s["adzuna_id"], "app_key": s["adzuna_key"], "what": q,
                  "results_per_page": 50, "content-type": "application/json"}
        if not is_country_name(o["where"], o["country"]):
            params.update(where=o["where"], distance=round(o["miles"] * 1.609))
        if o["posted"]:
            params["max_days_old"] = o["posted"]
        if o["salary_min"]:
            params["salary_min"] = o["salary_min"]
        jt = {"fulltime": "full_time", "parttime": "part_time", "contract": "contract"}.get(o["jtype"])
        if jt:
            params[jt] = 1
        d = get_json(f"https://api.adzuna.com/v1/api/jobs/{code}/search/{page}?" + urllib.parse.urlencode(params))
        res = d.get("results", [])
        for j in res:
            jt = " ".join(x for x in (j.get("contract_time"), j.get("contract_type")) if x).replace("_", " ")
            out.append(job("Adzuna", j.get("title"), (j.get("company") or {}).get("display_name"),
                           j.get("redirect_url"), (j.get("location") or {}).get("display_name"),
                           to_date(j.get("created")), money(j.get("salary_min"), j.get("salary_max"), cur),
                           jt, [(j.get("category") or {}).get("label", "")], j.get("description"), remote=False))
        if len(res) < 50:
            break
    return out


def src_himalayas(q, o):
    out = []
    country = f"&country={o['country']}" if o["local"] else ""
    name = country_info(o["country"])[0]
    for page in (1, 2, 3):
        d = get_json(f"https://himalayas.app/jobs/api/search?q={urllib.parse.quote(q)}&page={page}{country}")
        jobs = d.get("jobs", [])
        for j in jobs:
            locs = as_list(j.get("locationRestrictions"))
            if name in locs and len(locs) > 4:
                loc = f"{name} + {len(locs) - 1} more countries"
            else:
                loc = ", ".join(locs[:4]) + (" +more" if len(locs) > 4 else "") if locs else "Worldwide"
            out.append(job("Himalayas", j.get("title"), j.get("companyName"),
                           j.get("applicationLink") or j.get("guid"), "Remote · " + loc, to_date(j.get("pubDate")),
                           money(j.get("minSalary"), j.get("maxSalary"), j.get("currency") or "USD"),
                           j.get("employmentType"), as_list(j.get("categories")),
                           j.get("description") or j.get("excerpt")))
        if len(jobs) < 20:
            break
    return out


def src_jobicy(q, o):
    geo = country_info(o["country"])[3] if o["local"] else ""
    base = "https://jobicy.com/api/v2/remote-jobs?count=50" + (f"&tag={urllib.parse.quote(q)}" if q else "")
    try:
        d = get_json(base + (f"&geo={geo}" if geo else ""))
    except Exception:
        d = {}
    if geo and not d.get("jobs"):
        d = get_json(base)            # unknown region name: fetch all and filter afterwards
    return [job("Jobicy", j.get("jobTitle"), j.get("companyName"), j.get("url"), "Remote · " + (j.get("jobGeo") or ""),
                to_date(j.get("pubDate")),
                money(j.get("annualSalaryMin") or j.get("salaryMin"),
                      j.get("annualSalaryMax") or j.get("salaryMax"),
                      j.get("salaryCurrency") or "USD"),
                ", ".join(as_list(j.get("jobType"))), as_list(j.get("jobIndustry")),
                j.get("jobDescription") or j.get("jobExcerpt"))
            for j in d.get("jobs", []) or []]


def src_remotive(q, o):
    d = get_json("https://remotive.com/api/remote-jobs?limit=150" + (f"&search={urllib.parse.quote(q)}" if q else ""))
    return [job("Remotive", j.get("title"), j.get("company_name"), j.get("url"),
                "Remote · " + (j.get("candidate_required_location") or ""), to_date(j.get("publication_date")),
                j.get("salary"), (j.get("job_type") or "").replace("_", " "),
                as_list(j.get("tags")), j.get("description"))
            for j in d.get("jobs", [])]


def src_remoteok(q, o):
    words = [w for w in re.findall(r"[a-z0-9+#]+", q.lower()) if w not in STOPWORDS][:2]
    urls = ["https://remoteok.com/api"] + [f"https://remoteok.com/api?tag={urllib.parse.quote(w)}" for w in words]
    out = []
    for u in urls:
        try:
            for j in get_json(u):
                if not isinstance(j, dict) or "position" not in j:
                    continue  # first item is a legal notice
                out.append(job("RemoteOK", j.get("position"), j.get("company"), j.get("url"),
                               "Remote · " + (j.get("location") or ""), to_date(j.get("epoch") or j.get("date")),
                               money(j.get("salary_min"), j.get("salary_max")), "",
                               as_list(j.get("tags")), j.get("description")))
        except Exception:
            pass
    return out


def src_arbeitnow(q, o):
    out = []
    for page in (1, 2, 3):
        d = get_json(f"https://www.arbeitnow.com/api/job-board-api?page={page}")
        for j in d.get("data", []):
            out.append(job("Arbeitnow", j.get("title"), j.get("company_name"), j.get("url"),
                           (j.get("location") or "") + (" (remote)" if j.get("remote") else ""),
                           to_date(j.get("created_at")), "", ", ".join(as_list(j.get("job_types"))),
                           as_list(j.get("tags")), j.get("description"), remote=bool(j.get("remote"))))
    return out


# ---- LinkedIn, Indeed, Glassdoor
# Indeed and Glassdoor are searched for free with JobSpy from this computer; Apify is the backup.
# LinkedIn reads the public (no-login) listings slowly, or uses Apify when a token is set.

APIFY_MAX_USD = 0.25          # spending cap per Apify search
LI_GAP = 6                    # seconds between direct LinkedIn requests
LI_COOLDOWN = 15 * 60         # pause after LinkedIn rate-limits us
li_lock = threading.Lock()
li_state = {"last": 0.0, "blocked_until": 0.0}


def rel_date(text):
    """'3 days ago', 'Just posted', '30+ days ago', '2d', '24h' -> YYYY-MM-DD."""
    if not text:
        return ""
    s = str(text).lower()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    if any(w in s for w in ("just", "today", "hour", "minute")) or re.fullmatch(r"\d+\s*h", s.strip()):
        days = 0
    else:
        m = re.search(r"(\d+)\s*\+?\s*(d|day|w|week|mo|month)", s)
        if not m:
            return to_date(text)
        n, unit = int(m[1]), m[2]
        days = n * (30 if unit.startswith("mo") else 7 if unit.startswith("w") else 1)
    return datetime.fromtimestamp(time.time() - days * 86400).strftime("%Y-%m-%d")


def apify_run(actor, run_input, timeout=280):
    token = load_settings().get("apify_token")
    if not token:
        raise NeedsKey("add a free Apify token in Settings")
    url = (f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
           f"?timeout={timeout - 20}&maxTotalChargeUsd={APIFY_MAX_USD}")
    req = urllib.request.Request(url, data=json.dumps(run_input).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        items = json.loads(r.read().decode("utf-8", "replace"))
    return [i for i in items if isinstance(i, dict) and not i.get("error")]


def build_ca_bundle():
    """Python's certificates + the ones Windows trusts. Fixes 'certificate verify failed' when
    antivirus or a company network inspects secure connections."""
    path = DATA_DIR / "ca-bundle.pem"
    try:
        import ssl
        import certifi
        pems = [Path(certifi.where()).read_text(encoding="utf-8")]
        if hasattr(ssl, "enum_certificates"):
            for store in ("ROOT", "CA"):
                pems += [ssl.DER_cert_to_PEM_cert(c) for c, enc, _ in ssl.enum_certificates(store) if enc == "x509_asn"]
        path.write_text("\n".join(pems), encoding="utf-8")
        return str(path)
    except Exception:
        return None


CA_BUNDLE = build_ca_bundle()
JS_GAP = 4                    # seconds between JobSpy searches on the same site
JS_COOLDOWN = 15 * 60         # pause a site after it refuses us
js_locks = {"indeed": threading.Lock(), "glassdoor": threading.Lock(), "zip_recruiter": threading.Lock()}
js_state = {}                 # site -> {"last": t, "blocked_until": t}


class _Grab(__import__("logging").Handler):
    def __init__(self):
        super().__init__()
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


def jobspy_run(site, q, o):
    """Search one site with JobSpy. Raises RuntimeError if the site refuses or JobSpy isn't available."""
    import logging
    try:
        from jobspy import scrape_jobs
        from jobspy.model import Country
    except Exception:
        raise RuntimeError("JobSpy not installed")
    country = Country[country_info(o["country"])[1]]
    st = js_state.setdefault(site, {"last": 0.0, "blocked_until": 0.0})
    with js_locks[site]:
        left = st["blocked_until"] - time.time()
        if left > 0:
            raise RuntimeError(f"{site.capitalize()} paused for {int(left // 60) + 1} more min after refusing")
        gap = JS_GAP - (time.time() - st["last"])
        if gap > 0:
            time.sleep(gap)
        st["last"] = time.time()
        specific = not is_country_name(o["where"], o["country"])
        kw = dict(site_name=[site], search_term=q or None,
                  location=(o["where"] + ", " + country_info(o["country"])[0]) if specific else country_info(o["country"])[0],
                  distance=o["miles"] if specific else 50, results_wanted=30,
                  country_indeed=country, ca_cert=CA_BUNDLE, verbose=0)
        # Indeed allows only one of: date filter, or job type + remote
        if o["posted"]:
            kw["hours_old"] = o["posted"] * 24
        else:
            if o["jtype"]:
                kw["job_type"] = o["jtype"]
            if o["remote"] == "remote":
                kw["is_remote"] = True
        log = logging.getLogger(f"jobspy.{site}")
        grab = _Grab()
        log.addHandler(grab)
        try:
            df = scrape_jobs(**kw)
        except ValueError as e:
            raise NotHere(str(e)[:80])
        finally:
            log.removeHandler(grab)
        errors = " ".join(grab.msgs)
        if len(df) == 0 and errors:
            if any(c in errors for c in ("403", "429", "blocked")):
                st["blocked_until"] = time.time() + JS_COOLDOWN
                raise RuntimeError(f"{site.capitalize()} refused the search (paused 15 min)")
            raise RuntimeError(errors[:140])

    def val(row, k):
        v = row.get(k)
        try:
            import pandas as pd
            return None if v is None or pd.isna(v) else v
        except (TypeError, ValueError):
            return v

    out = []
    for row in df.to_dict("records"):
        sal = money(val(row, "min_amount"), val(row, "max_amount"), val(row, "currency") or country_info(o["country"])[5])
        if sal and val(row, "interval") and val(row, "interval") != "yearly":
            sal += " / " + str(val(row, "interval")).replace("ly", "").replace("dai", "day")
        out.append(job(site.capitalize(), val(row, "title"), val(row, "company"),
                       val(row, "job_url") or val(row, "job_url_direct"), val(row, "location"),
                       to_date(val(row, "date_posted")), sal,
                       str(val(row, "job_type") or "").replace("fulltime", "Full time").replace("parttime", "Part time"),
                       [], str(val(row, "description") or "")[:2000], remote=bool(val(row, "is_remote"))))
    return out


def with_backup(site, q, o, apify_fn):
    """Try JobSpy first; if the site refuses, fall back to Apify when a token is set."""
    try:
        return jobspy_run(site, q, o)
    except RuntimeError as e:
        if load_settings().get("apify_token"):
            return apify_fn(q, o)
        raise RuntimeError(f"{e} - add an Apify token in Settings as backup")


def src_indeed(q, o):
    return with_backup("indeed", q, o, apify_indeed)


def src_glassdoor(q, o):
    return with_backup("glassdoor", q, o, apify_glassdoor)


def apify_indeed(q, o):
    items = apify_run("misceres~indeed-scraper", {
        "position": q, "country": o["country"], "location": place(o),
        "maxItemsPerSearch": 30, "saveOnlyUniqueItems": True, "parseCompanyDetails": False,
    })
    return [job("Indeed", i.get("positionName"), i.get("company"), i.get("url") or i.get("externalApplyLink"),
                i.get("location"), rel_date(i.get("postedAt")), i.get("salary"),
                ", ".join(as_list(i.get("jobType"))), [], i.get("description"), remote=False)
            for i in items]


def apify_glassdoor(q, o):
    name = country_info(o["country"])[3] or country_info(o["country"])[0].lower()
    items = apify_run("orgupdate~glassdoor-jobs-scraper", {
        "includeKeyword": q, "locationName": place(o), "countryName": name,
        "pagesToFetch": 1, "datePosted": "month",
    })
    return [job("Glassdoor", i.get("job_title"), i.get("company_name"), i.get("URL") or i.get("url"),
                i.get("location"), rel_date(i.get("date")), i.get("salary"), i.get("job_type") or "",
                [], "", remote=False)
            for i in items]


def linkedin_search_url(q, o, guest=False):
    params = {"keywords": q, "location": place(o) if o["local"] or o["where"] else "Worldwide"}
    if not is_country_name(o["where"], o["country"]):
        params["distance"] = o["miles"]
    if o["posted"]:
        params["f_TPR"] = f"r{o['posted'] * 86400}"
    jt = {"fulltime": "F", "parttime": "P", "contract": "C", "internship": "I"}.get(o["jtype"])
    if jt:
        params["f_JT"] = jt
    wt = {"onsite": "1", "remote": "2", "hybrid": "3"}.get(o["remote"])
    if wt:
        params["f_WT"] = wt
    base = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?" if guest
            else "https://www.linkedin.com/jobs/search/?")
    return base + urllib.parse.urlencode(params)


def src_linkedin(q, o):
    if load_settings().get("apify_token"):
        items = apify_run("curious_coder~linkedin-jobs-scraper",
                          {"urls": [linkedin_search_url(q, o)], "limitPerSource": 30, "scrapeCompany": False})
        return [job("LinkedIn", i.get("title"), i.get("companyName"), (i.get("link") or "").split("?")[0],
                    i.get("location"), to_date(i.get("postedAt")), i.get("salaryInfo") and " – ".join(as_list(i.get("salaryInfo"))),
                    i.get("employmentType"), as_list(i.get("industries")), i.get("descriptionText"), remote=False)
                for i in items]

    # Direct, no login: at most 2 pages (about 20 jobs), spaced out, with back-off.
    out = []
    for start in (0, 10):
        with li_lock:
            wait_left = li_state["blocked_until"] - time.time()
            if wait_left > 0:
                if out:
                    break
                raise RuntimeError(f"LinkedIn asked us to slow down - try again in {int(wait_left // 60) + 1} min "
                                   "(or add an Apify token)")
            gap = LI_GAP - (time.time() - li_state["last"])
            if gap > 0:
                time.sleep(gap)
            li_state["last"] = time.time()
            try:
                req = urllib.request.Request(
                    linkedin_search_url(q, o, guest=True) + f"&start={start}",
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                           "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
                             "Accept-Language": "en-GB,en;q=0.9"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    page = r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                if e.code in (429, 999):
                    li_state["blocked_until"] = time.time() + LI_COOLDOWN
                    if out:
                        break
                    raise RuntimeError("LinkedIn asked us to slow down - paused for 15 min (or add an Apify token)")
                raise
        cards = page.split("<li>")[1:]
        for c in cards:
            def grab(pattern):
                m = re.search(pattern, c, re.S)
                return strip_html(m[1]) if m else ""
            link = re.search(r'class="base-card__full-link[^"]*"\s+href="([^"]+)"', c) or \
                re.search(r'href="(https://[a-z.]*linkedin\.com/jobs/view/[^"]+)"', c)
            out.append(job("LinkedIn",
                           grab(r'base-search-card__title[^>]*>(.*?)</h3>'),
                           grab(r'base-search-card__subtitle[^>]*>(.*?)</h4>'),
                           html.unescape(link[1]).split("?")[0] if link else "",
                           grab(r'job-search-card__location[^>]*>(.*?)</span>'),
                           (re.search(r'datetime="([\d-]+)"', c) or [None, ""])[1],
                           grab(r'job-search-card__salary-info[^>]*>(.*?)</span>'),
                           remote=False))
        if len(cards) < 10:
            break
    return out


# ---- country boards: Denmark, Netherlands, US; and ArtStation (art / games, worldwide)

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


def km_radius(o):
    return max(5, round(o["miles"] * 1.609))


def src_jobindex(q, o):
    """Jobindex.dk - Denmark's biggest job board (open JSON search, includes exact coordinates)."""
    if o["country"] != "DK":
        raise NotHere("Denmark only")
    out = []
    for page in (1, 2):
        params = {"q": q, "page": page}
        if not is_country_name(o["where"], "DK"):
            params.update(address=o["where"], radius=km_radius(o))
        d = get_json("https://www.jobindex.dk/api/jobsearch/v3/?" + urllib.parse.urlencode(params), headers=BROWSER_UA)
        for r in d.get("results", []):
            addr = (r.get("addresses") or [{}])[0]
            coords = addr.get("coordinates") or {}
            sal = r.get("salary")
            j = job("Jobindex", r.get("headline"), r.get("companytext") or (r.get("company") or {}).get("name"),
                    r.get("share_url") or r.get("url"), r.get("area") or addr.get("city"), to_date(r.get("firstdate")),
                    sal if isinstance(sal, str) else "", "", [], "", remote=bool(r.get("home_workplace")))
            if coords.get("latitude"):
                j["lat"], j["lon"] = coords["latitude"], coords["longitude"]
            out.append(j)
        if page >= (d.get("total_pages") or 1):
            break
    return out


def dutch_date(text):
    s = (text or "").lower()
    if any(w in s for w in ("nieuw", "vandaag", "uur", "minu")):
        return rel_date("today")
    if "gisteren" in s:
        return rel_date("1 day ago")
    m = re.search(r"(\d+)\s*(dag|week|weken|maand)", s)
    if m:
        unit = {"dag": "day", "week": "week", "weken": "week", "maand": "month"}[m[2]]
        return rel_date(f"{m[1]} {unit} ago")
    return ""


def src_jobbird(q, o):
    """Jobbird.com - Dutch job board (reads the public search page)."""
    if o["country"] != "NL":
        raise NotHere("Netherlands only")
    out = []
    for page in (1, 2):
        params = {"s": q, "rad": km_radius(o), "ot": "date", "p": page}
        if not is_country_name(o["where"], "NL"):
            params["l"] = o["where"]
        req = urllib.request.Request("https://www.jobbird.com/nl/vacature?" + urllib.parse.urlencode(params), headers=BROWSER_UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            h = r.read().decode("utf-8", "replace")
        links = list(re.finditer(r'<a href="(https://www\.jobbird\.com/nl/vacature/[^"]+)"[^>]*class="job-search__result-list__result__title">(.*?)</a>', h, re.S))
        for i, m in enumerate(links):
            card = h[m.end(): links[i + 1].start() if i + 1 < len(links) else m.end() + 4000]
            grab = lambda cls: strip_html((re.search(cls + r'[^>]*>(.*?)</span>\s*</span>', card, re.S) or [None, ""])[1])
            out.append(job("Jobbird", m[2], grab("cro-recruiter-name"), m[1], grab("cro-job-location"),
                           dutch_date(grab("cro-time-posted")), grab("cro-salary"), grab("cro-employment-type"),
                           [], "", remote=False))
        if len(links) < 10:
            break
    return out


def src_jobs2careers(q, o):
    """Jobs2Careers - large US job search (reads the data embedded in its results page)."""
    if o["country"] != "US":
        raise NotHere("US only")
    loc = ""
    if not is_country_name(o["where"], "US"):
        row = geocode_text(o["where"], "US")
        loc = f"{row[0]}, {row[4]}" if row else o["where"]          # "Austin, TX"
    out = []
    for page in (1, 2, 3):
        params = {"q": q, "l": loc}
        if page > 1:
            params["p"] = page
        req = urllib.request.Request("https://www.jobs2careers.com/search/results?" + urllib.parse.urlencode(params), headers=BROWSER_UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            h = r.read().decode("utf-8", "replace")
        i = h.find('"jobAds":{"byId":')
        if i < 0:
            break
        ads = json.JSONDecoder().raw_decode(h, i + len('"jobAds":'))[0].get("byId", {})
        before = len(out)
        items = lambda x: list(x.values()) if isinstance(x, dict) else (x or [])   # lists arrive as {"0": .., "1": ..}
        for a in ads.values():
            if a.get("adType") not in (None, "job"):
                continue
            sd = items(a.get("salaryDetails"))
            sal = (sd[0].get("label") if sd and isinstance(sd[0], dict) else "") or a.get("compensation") or ""
            types = ", ".join(w.get("label", "") for w in items(a.get("workTypeDetails")) if isinstance(w, dict))
            remote = (a.get("workLocation") or "") == "remote"
            j = job("Jobs2Careers", a.get("title"), a.get("companyName"), a.get("link"),
                    ("Remote · " if remote else "") + (a.get("cityState") or ""), to_date(a.get("datePosted")),
                    sal, types, [a.get("primaryMajorCategory") or ""], a.get("description"), remote=remote)
            c = (items(a.get("coordinates")) or [None])[0]
            if c and "," in str(c):
                j["lat"], j["lon"] = (float(x) for x in str(c).split(",")[:2])
            if not any(x["url"] == j["url"] for x in out):
                out.append(j)
        if len(out) == before:
            break
    return out


def src_usajobs(q, o):
    """USAJOBS - official US government jobs (free key from developer.usajobs.gov)."""
    if o["country"] != "US":
        raise NotHere("US only")
    s = load_settings()
    if not (s.get("usajobs_key") and s.get("usajobs_email")):
        raise NeedsKey("add a free key in Settings")
    params = {"Keyword": q, "ResultsPerPage": 100}
    if not is_country_name(o["where"], "US"):
        params.update(LocationName=o["where"], Radius=o["miles"])
    if o["posted"]:
        params["DatePosted"] = o["posted"]
    d = get_json("https://data.usajobs.gov/api/search?" + urllib.parse.urlencode(params),
                 headers={"Host": "data.usajobs.gov", "User-Agent": s["usajobs_email"], "Authorization-Key": s["usajobs_key"]})
    out = []
    for item in (d.get("SearchResult") or {}).get("SearchResultItems", []):
        m = item.get("MatchedObjectDescriptor", {})
        pay = (m.get("PositionRemuneration") or [{}])[0]
        per = {"PA": "", "PH": " / hour", "PD": " / day", "PW": " / week", "PM": " / month"}.get(pay.get("RateIntervalCode"), "")
        sal = money(pay.get("MinimumRange"), pay.get("MaximumRange"), "USD") + (per if pay.get("MinimumRange") else "")
        locs = m.get("PositionLocation") or [{}]
        j = job("USAJOBS", m.get("PositionTitle"), m.get("OrganizationName"), m.get("PositionURI"),
                m.get("PositionLocationDisplay"), to_date(m.get("PublicationStartDate")), sal,
                ", ".join(t.get("Name", "") for t in m.get("PositionSchedule") or []), [],
                ((m.get("UserArea") or {}).get("Details") or {}).get("JobSummary", ""), remote=False)
        if locs[0].get("Latitude"):
            j["lat"], j["lon"] = locs[0]["Latitude"], locs[0]["Longitude"]
        out.append(j)
    return out


def src_ziprecruiter(q, o):
    """ZipRecruiter - big US/Canada board, searched with JobSpy."""
    if o["country"] not in ("US", "CA"):
        raise NotHere("US & Canada only")
    return jobspy_run("zip_recruiter", q, o)


def src_artstation(q, o):
    """ArtStation Jobs - art, animation and games jobs worldwide (open JSON feed)."""
    out = []
    for page in (1, 2, 3):
        d = get_json(f"https://www.artstation.com/api/v2/jobs/public/jobs.json?page={page}&per_page=50", headers=BROWSER_UA)
        for a in d.get("data", []):
            places = []
            for loc in a.get("recruitment_localities") or []:
                l = loc.get("locality") or {}
                places.append(l.get("formatted_name") or ", ".join(x for x in (l.get("city_name"), l.get("country_name")) if x))
            sr = a.get("salary_range") or {}
            sal = money(sr.get("min_salary"), sr.get("max_salary"), sr.get("currency") or "USD")
            if sal and sr.get("period") and sr["period"] != "year":
                sal += " / " + sr["period"]
            remote = bool(a.get("work_remotely"))
            location = ("Remote · " if remote else "") + "; ".join(p for p in places if p)
            out.append(job("ArtStation", a.get("title"), a.get("company_name"),
                           f"https://www.artstation.com/jobs/{a.get('hash_id')}" if a.get("hash_id") else a.get("apply_link"),
                           location or ("Remote" if remote else ""),
                           to_date((a.get("listing_placement") or {}).get("posted_at") or a.get("created_at")), sal,
                           " · ".join(x for x in (a.get("job_type"), a.get("level")) if x), [a.get("skills") or ""],
                           a.get("about") or a.get("description"), remote=remote))
        if len(d.get("data", [])) < 50:
            break
    return out


# ---- ZipRecruiter UK, games (Work With Indies) and accounting (ICAEW, ACCA) boards

def fetch_html(url, timeout=25):
    with urllib.request.urlopen(urllib.request.Request(url, headers={**BROWSER_UA, "Accept-Language": "en-GB,en;q=0.9"}),
                                timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def short_date(text):
    """'24 Oct' / '3 days ago' -> YYYY-MM-DD (ZipRecruiter UK)."""
    s = (text or "").strip()
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3})", s)
    if m:
        try:
            d = datetime.strptime(f"{m[1]} {m[2]} {datetime.now().year}", "%d %b %Y")
            if d > datetime.now():
                d = d.replace(year=d.year - 1)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return rel_date(s)


def src_ziprecruiter_uk(q, o):
    """ZipRecruiter UK (ziprecruiter.co.uk) - reads the public search page."""
    if o["country"] != "GB":
        raise NotHere("UK only")
    out = []
    for page in (1, 2, 3):
        params = {"q": q, "page": page}
        if not is_country_name(o["where"], "GB"):
            params.update(l=o["where"], d=o["miles"])
        h = fetch_html("https://www.ziprecruiter.co.uk/jobs/search?" + urllib.parse.urlencode(params))
        cards = re.split(r'<li class="job-listing', h)[1:]
        for c in cards:
            link = re.search(r'class="jobList-title[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', c, re.S)
            if not link:
                continue
            company = re.search(r'fa-building"></i>(.*?)</li>', c, re.S)
            loc = re.search(r'fa-map-marker-alt"></i>(.*?)</li>', c, re.S)
            desc = re.search(r'jobList-description">(.*?)</div>', c, re.S)
            date = re.search(r'jobList-date[^>]*>(.*?)</div>', c, re.S)
            sal = re.search(r'fa-(?:pound-sign|money[^"]*)"></i>(.*?)</li>', c, re.S)
            out.append(job("ZipRecruiter", link[2], company[1] if company else "", html.unescape(link[1]),
                           loc[1] if loc else "", short_date(strip_html(date[1])) if date else "",
                           strip_html(sal[1]) if sal else "", "", [], desc[1] if desc else "", remote=False))
        if len(cards) < 20:
            break
    return out


def src_workwithindies(q, o):
    """Work With Indies - indie games studio jobs worldwide (reads the public job list)."""
    h = fetch_html("https://www.workwithindies.com/")
    out = []
    for m in re.finditer(r'<a[^>]*href="(/careers/[^"]+)"[^>]*class="job-card[^"]*"[^>]*>(.*?)</a>', h, re.S):
        card = m[2]
        company = re.search(r'job-card-text bold">(.*?)</div>', card, re.S)
        title = re.search(r'text-block-28">(.*?)</div>', card, re.S)
        mobile = re.findall(r'job-card-text-smol">(.*?)</div>', card, re.S)
        location = strip_html(mobile[-1]) if mobile else ""
        if not location or location == "|":
            bolds = re.findall(r'job-card-text bold">(.*?)</div>', card, re.S)
            location = strip_html(bolds[-1]) if len(bolds) > 1 else ""
        remote = bool(re.search(r"remote|anywhere", location, re.I))
        out.append(job("WorkWithIndies", title[1] if title else "", company[1] if company else "",
                       "https://www.workwithindies.com" + m[1], ("Remote · " if remote and "remote" not in location.lower() else "") + location,
                       "", "", "", ["games"], "", remote=remote))
    return out


def tail_place(text, cc):
    """Find a town at the end of a text, e.g. '...to d West Sussex, Horsham' -> 'Horsham' (offline towns)."""
    parts = [p.strip() for p in text[-90:].split(",") if p.strip()]
    for p in reversed(parts[-3:]):
        words = p.split()
        for k in (3, 2, 1):
            if len(words) >= k and find_city(" ".join(words[-k:]), cc):
                return " ".join(words[-k:])
    return ""


def madgex_feed(source, base, q, o, pages=4, keep_unknown=False):
    """ICAEW / ACCA job boards share the same RSS format: 'Company: Title' + 'salary: company: text. Place (CC)'."""
    cc = o["country"]
    out = []
    for page in range(1, pages + 1):
        x = fetch_html(f"{base}/jobsrss/?" + urllib.parse.urlencode({"keywords": q, "page": page}))
        items = re.findall(r"<item>(.*?)</item>", x, re.S)
        for it in items:
            title = html.unescape(strip_html((re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1]))
            desc = html.unescape(strip_html((re.search(r"<description>(.*?)</description>", it, re.S) or [None, ""])[1], 1500))
            link = html.unescape((re.search(r"<link>(.*?)</link>", it, re.S) or [None, ""])[1]).split("?")[0]
            pub = (re.search(r"<pubDate>(.*?)</pubDate>", it, re.S) or [None, ""])[1]
            company, _, role = title.partition(": ")
            if not role:
                company, role = "", title
            m = re.search(r"([^.:]{2,80})\s\(([A-Z]{2})\)\s*$", desc)
            if m:
                where, pcc = m[1].strip(), m[2]
            else:
                where = tail_place(desc, cc)
                pcc = cc if where else None
            if o["local"] and (pcc != cc if pcc else not keep_unknown):
                continue                          # these boards are worldwide; keep your country
            salary = desc.split(":")[0] if desc.count(":") >= 2 and len(desc.split(":")[0]) < 80 else ""
            try:
                date = datetime.strptime(pub[:16], "%a, %d %b %Y").strftime("%Y-%m-%d")
            except ValueError:
                date = ""
            out.append(job(source, role, company, link, where, date,
                           salary if re.search(r"\d", salary) else "", "", ["accounting"], desc, remote=False))
        if len(items) < 20:
            break
    return out


def src_icaew(q, o):
    """ICAEW Jobs - chartered accountancy jobs (mostly UK)."""
    return madgex_feed("ICAEW", "https://www.icaewjobs.com", q, o, keep_unknown=(o["country"] == "GB"))


def src_acca(q, o):
    """ACCA Careers - accounting & finance jobs worldwide."""
    return madgex_feed("ACCA", "https://jobs.accaglobal.com", q, o)


SOURCES = {
    "Reed": src_reed,
    "Adzuna": src_adzuna,
    "LinkedIn": src_linkedin,
    "Indeed": src_indeed,
    "Glassdoor": src_glassdoor,
    # US ZipRecruiter via JobSpy refuses UK connections; the UK site works, so that's used for the UK
    "ZipRecruiter": src_ziprecruiter_uk,
    "Jobs2Careers": src_jobs2careers,
    "USAJOBS": src_usajobs,
    "Jobindex": src_jobindex,
    "Jobbird": src_jobbird,
    "ArtStation": src_artstation,
    "WorkWithIndies": src_workwithindies,
    "ICAEW": src_icaew,
    "ACCA": src_acca,
    "Himalayas": src_himalayas,
    "Jobicy": src_jobicy,
    "Remotive": src_remotive,
    "RemoteOK": src_remoteok,
    "Arbeitnow": src_arbeitnow,
}
# How long to reuse results before asking a site again (seconds)
CACHE_TTL = {"LinkedIn": 3600, "Indeed": 3 * 3600, "Glassdoor": 3 * 3600}
DEFAULT_TTL = 15 * 60
CACHE_FILE = DATA_DIR / "cache.json"
cache_lock = threading.Lock()
COUNTRY_NATIVE = {"Reed", "Adzuna", "LinkedIn", "Indeed", "Glassdoor", "ZipRecruiter", "Jobs2Careers",
                  "USAJOBS", "Jobindex", "Jobbird", "ICAEW", "ACCA"}       # already limited to the chosen country
LOCATION_AWARE = COUNTRY_NATIVE - {"ICAEW", "ACCA"}                      # these also search around a town themselves
KEYED_SOURCES = {"Reed", "Adzuna", "USAJOBS"}                             # a 401/403 from these means a bad key
COUNTRY_PARAM = {"Himalayas", "Jobicy"}                                  # filtered by the board itself (mostly)


# ---------------------------------------------------------------- matching

# ---- how long the job lasts: "6-month contract", "12-month fixed term", "Maternity cover", "Permanent"
_UNIT = r"(months?|mths?|mos?|weeks?|wks?|years?|yrs?|maanden|maand|måneder|måned|monate?n?|mois|meses)"
_KIND = (r"(fixed[\s-]?term|ftc|contract|contractor|temp|temporary|placement|internship|secondment|role|position|"
         r"assignment|project|engagement|maternity|cover|opdracht|tijdelijk|kontrakt|vikariat|befristet|stage|praktik)")
INTERN_RE = re.compile(r"\bintern\b|internship|placement year|industrial placement|year in industry|work placement|"
                       r"graduate (scheme|programme|program)|\btrainee|\bstage\b|stagiair|stagiaire|\bpraktik|"
                       r"werkstudent|summer analyst|\bco-?op\b|apprentice", re.I)


def contract_length(j):
    """(label, months) — months is 1000 for permanent, 500 for a contract of unknown length, None if not stated."""
    t = " ".join([j.get("title", ""), j.get("type", ""), j.get("desc", "")])[:4000].lower()
    m = re.search(r"(\d{1,2})(?:\s*(?:-|–|to)\s*(\d{1,2}))?[\s-]*" + _UNIT + r"\b[\s-]*(?:\w+[\s-]+)?" + _KIND, t) or \
        re.search(_KIND + r"\D{0,30}?\b(?:of|for|length|duration|period|lasting|van|på)?\W{0,3}(\d{1,2})(?:\s*(?:-|–|to)\s*"
                  r"(\d{1,2}))?\s*" + _UNIT + r"\b", t)
    if m:
        g = m.groups()
        if g[0] and g[0][0].isdigit():
            lo, hi, unit, kind = g[0], g[1], g[2], g[3]
        else:
            kind, lo, hi, unit = g[0], g[1], g[2], g[3]
        n = int(hi or lo)
        months = n * 12 if unit.startswith(("y", "å")) and not unit.startswith("må") else \
            max(1, round(n / 4.345)) if unit.startswith("w") else n
        if 0 < months <= 60:
            what = "maternity cover" if re.match(r"maternity|cover|vikariat", kind) else \
                "internship" if re.match(r"intern|placement|stage|praktik", kind) else \
                "fixed term" if re.match(r"fixed|ftc|befristet|tijdelijk", kind) else "contract"
            span = f"{lo}–{hi}" if hi else lo
            unit_word = "year" if unit.startswith(("y", "å")) and not unit.startswith("må") else \
                "week" if unit.startswith("w") else "month"
            return f"{span}-{unit_word} {what}", months
    if re.search(r"maternity (leave )?cover|mat cover|parental leave cover|barselsvikariat|zwangerschapsvervanging", t):
        return "Maternity cover", 12
    if re.search(r"summer internship|summer placement|zomerstage|sommerpraktik", t):
        return "Summer internship", 3
    if re.search(r"\bpermanent\b|vast contract|vaste baan|fast stilling|fastansættelse|unbefristet|\bcdi\b", t):
        return "Permanent", 1000
    if re.search(r"fixed[\s-]?term|\btemporary\b|\btemp\b|\bcontract\b(?! manager| management| law)|freelance|interim|"
                 r"tijdelijk|vikariat|befristet", t):
        return "Contract", 500
    return "", None


def score(j, words, phrase, strict):
    if not words:                       # "Any job" mode: everything matches, newest first
        return 1
    title = j["title"].lower()
    tags = " ".join(j["tags"]).lower()
    desc = j["desc"].lower()

    def has(text, w):
        return re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text) is not None

    t = sum(has(title, w) for w in words)
    g = sum(has(tags, w) for w in words)
    d = sum(has(desc, w) for w in words)
    if strict and t < len(words):
        return 0
    if t == 0 and g < len(words) and d < len(words):
        return 0
    # Rank on the title so sites without descriptions (LinkedIn, Glassdoor) aren't pushed down
    if t:
        return 10 * t + (15 if phrase in title else 0)
    return 3 * g + d


def load_cache():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fetch_cached(name, q, opts, fresh):
    """Run one source for one query, reusing recent results. Returns (jobs, from_cache)."""
    key = json.dumps([name, q.lower(), opts["where"].lower(), opts["miles"], opts["country"], opts["local"],
                      opts["posted"], opts["jtype"], opts["remote"], opts["salary_min"]])
    ttl = CACHE_TTL.get(name, DEFAULT_TTL)
    with cache_lock:
        hit = load_cache().get(key)
    if hit and not fresh and time.time() - hit["t"] < ttl:
        return hit["jobs"], True
    jobs = SOURCES[name](q, opts)
    with cache_lock:
        c = {k: v for k, v in load_cache().items() if time.time() - v["t"] < 24 * 3600}
        c[key] = {"t": time.time(), "jobs": jobs}
        CACHE_FILE.write_text(json.dumps(c), encoding="utf-8")
    return jobs, False


# ---- job match terms: user-defined job names with aliases, optionally matched in the job TITLE only
# e.g. {"name": "Communications", "aliases": ["comms", "PR", "public relations"], "title_only": True}
# so "communication" listed as a skill in a description doesn't count as a communications job.

def match_groups():
    out = []
    for g in load_settings().get("match_terms", []):
        name = str(g.get("name", "")).strip()
        aliases = [a.strip() for a in (g.get("aliases") or []) if str(a).strip()]
        if name:
            out.append({"name": name, "aliases": aliases, "title_only": bool(g.get("title_only", True))})
    return out


def find_group(q, groups):
    ql = q.strip().lower()
    return next((g for g in groups if ql == g["name"].lower() or ql in (a.lower() for a in g["aliases"])), None)


def phrase_in(text, phrase):
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])", text) is not None


def group_score(j, g):
    title = j["title"].lower()
    terms = [g["name"]] + g["aliases"]
    hits = [t for t in terms if phrase_in(title, t)]
    if hits:
        return 40 + (5 if phrase_in(title, g["name"]) else 0)
    if not g["title_only"]:
        rest = (" ".join(j["tags"]) + " " + j["desc"]).lower()
        if any(phrase_in(rest, t) for t in terms):
            return 4
    return 0


def search(query, sources, opts, fresh=False):
    # The filters on the results screen (date, job type, remote, salary, "workable from my country",
    # "title must match") never narrow what is fetched: boards are always asked for everything, and
    # each job is marked (local_ok, title_match) so the screen can hide what you are not interested in.
    opts = {**opts, "posted": 0, "jtype": "", "remote": "", "salary_min": 0, "local": True, "strict": False}
    # "Where?" may be a postcode or a full address: boards get a clean town, distances use the exact point
    loc = resolve_where(opts.get("where", ""), opts["country"])
    if loc and loc["explicit_country"] and loc["country_code"] in COUNTRIES:
        opts["country"] = loc["country_code"]          # "Austin, TX" means the US whatever the drop-down says
    opts["where"] = loc["board_where"] if loc else ""
    queries = [q.strip() for q in query.split(",") if q.strip()] or [""]     # "" = any job
    # expand any job-match term into its aliases (a few, to keep the number of requests reasonable)
    groups, expanded, qgroup = match_groups(), [], {}
    for q in queries:
        g = find_group(q, groups) if q else None
        for t in ([g["name"]] + g["aliases"])[:4] if g else [q]:
            if t.lower() not in (e.lower() for e in expanded):
                expanded.append(t)
                qgroup[t] = g
    queries = expanded
    # internships: boards without an "internship" filter get the word added to the search itself
    sent_as = {}
    TYPE_NATIVE = {"LinkedIn", "Indeed", "Glassdoor"}
    tasks = []
    for q in queries:
        for name in sources:
            if name not in SOURCES:
                continue
            sq = q
            if opts.get("intern") and name not in TYPE_NATIVE and not INTERN_RE.search(q):
                sq = (q + " internship").strip()
            sent_as[(name, sq)] = q
            tasks.append((name, sq))
    status = {}
    raw = []

    def run(name, q):
        try:
            jobs, cached = fetch_cached(name, q, opts, fresh)
            return name, q, [dict(j) for j in jobs], None, cached
        except NeedsKey:
            return name, q, [], "needs key", False
        except NotHere as e:
            return name, q, [], str(e) or "not available here", False
        except Exception as e:
            msg = str(e)[:140]
            if ("401" in msg or "403" in msg) and name in KEYED_SOURCES:
                msg = "key rejected - check Settings"
            elif "401" in msg or "403" in msg or "429" in msg:
                msg = "the site turned the search away - try again later"
            elif "402" in msg:
                msg = "Apify credit used up for this month"
            elif "408" in msg or "timed out" in msg.lower():
                msg = "took too long - try again"
            return name, q, [], msg, False

    with ThreadPoolExecutor(max_workers=12) as ex:
        for name, q, res, err, cached in ex.map(lambda t: run(*t), tasks):
            s = status.setdefault(name, {"found": 0, "error": None, "cached": False})
            if err:
                s["error"] = err
            s["cached"] = s["cached"] or cached
            for j in res:
                j["_q"] = sent_as.get((name, q), q)
            raw.extend(res)

    local_re = local_ok_re(opts["country"])
    town = (loc["town"] if loc else "").lower()
    center = (None, loc["lat"], loc["lon"]) if loc and loc["lat"] is not None else None
    radius_km = opts["miles"] * 1.609
    seen = {}
    for j in raw:
        q = j.pop("_q")
        j["local_ok"] = j["source"] in COUNTRY_NATIVE or bool(local_re.search(j["location"]))
        # how far away is it? (offline town list; exact coordinates when the board gives them)
        pt = job_point(j, opts["country"]) if center else None
        j["dist_km"] = round(km_between(center[1], center[2], pt[0], pt[1]), 1) if pt else None
        # a town was given: on-site jobs from the worldwide boards must be within the radius
        if town and j["source"] not in LOCATION_AWARE and not REMOTE_RE.search(j["location"]):
            if j["dist_km"] is not None:
                if j["dist_km"] > radius_km * 1.25:
                    continue
            elif town not in j["location"].lower():
                continue
        g = qgroup.get(q)
        if g:
            sc = group_score(j, g)
            j["title_match"] = sc >= 40
        else:
            words = [w for w in re.findall(r"[a-z0-9+#.]+", q.lower()) if w not in STOPWORDS] if q else []
            sc = score(j, words, q.lower(), False)
            j["title_match"] = score(j, words, q.lower(), True) > 0
        if sc <= 0 or not j["url"]:
            continue
        j["duration"], j["duration_m"] = contract_length(j)
        if opts.get("intern") and INTERN_RE.search(j["title"]):
            sc += 5                                      # internship search: real internships rank first
        key = (re.sub(r"\W+", "", j["title"].lower()), re.sub(r"\W+", "", j["company"].lower()))
        j["score"] = sc
        j["matched"] = q
        j["cur_hint"] = country_info(opts["country"])[5] if j["source"] in COUNTRY_NATIVE else "USD"
        if key not in seen or (seen[key]["score"], seen[key]["title_match"]) < (sc, j["title_match"]):
            seen[key] = j

    results = sorted(seen.values(), key=lambda j: j["date"] or "", reverse=True)
    results.sort(key=lambda j: j["score"], reverse=True)
    for j in results:
        status[j["source"]]["found"] += 1
    return {"results": results, "status": status, "place": loc}


# ---------------------------------------------------------------- saved jobs

lock = threading.Lock()


def load_saved():
    try:
        return json.loads(SAVED_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        return []


def write_saved(items):
    SAVED_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def today():
    return datetime.now().strftime("%Y-%m-%d")


APPLIED_STAGES = ("Applied", "Interview", "Offer", "Rejected")


def set_status(item, status, applied_on=None):
    """Change a tracked job's status and remember when each step happened (for the stats)."""
    item["status"] = status
    item.setdefault("dates", {})[status] = today()
    if status in APPLIED_STAGES and not item.get("applied_on"):
        item["applied_on"] = (applied_on or today())[:10]


# ---------------------------------------------------------------- profile, CV, Chrome extension

APP_PORT = 47321                       # fixed so the Chrome extension can find the app
APP_VERSION = "2.3.1"                  # raise this for every release (release.py publishes it on GitHub)
# The GitHub repository jobslop's releases are published in ("owner/name"). Empty = update checks are off.
UPDATE_REPO = os.environ.get("JOBSLOP_UPDATE_REPO", "JobSlop/jobslop")
PROFILE_FILE = DATA_DIR / "profile.json"
CV_DIR = DATA_DIR / "cv"
EXT_DIR = DATA_DIR / "chrome-extension"
ACTIVE_MINUTES = 60                    # how long an Easy apply stays "current" for the extension
state = {"port": APP_PORT, "active": None, "ext_seen": 0.0}


JOB_FIELDS = ("title", "company", "location", "start", "end", "description")


def load_profile():
    try:
        return json.loads(PROFILE_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def save_profile(data):
    clean = {str(k)[:40]: str(v)[:8000] for k, v in data.items() if isinstance(v, (str, int, float))}
    if isinstance(data.get("jobs"), list):
        clean["jobs"] = [{f: str(j.get(f) or "")[:3000] for f in JOB_FIELDS}
                         for j in data["jobs"] if isinstance(j, dict)][:20]
    PROFILE_FILE.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    return clean


def cv_file():
    files = [f for f in CV_DIR.glob("*") if f.is_file()] if CV_DIR.exists() else []
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


def save_cv(name, b64):
    data = base64.b64decode(b64)
    if len(data) > 10 * 1024 * 1024:
        raise ValueError("CV must be under 10 MB")
    safe = re.sub(r"[^\w.\- ()]+", "_", Path(name).name)[:120] or "cv.pdf"
    if CV_DIR.exists():
        shutil.rmtree(CV_DIR)
    CV_DIR.mkdir(parents=True)
    (CV_DIR / safe).write_bytes(data)
    return safe


# ---- read details out of a CV (PDF or Word) to pre-fill the profile

LIG_CANDIDATES = ("ti", "tt", "ft", "tti", "fti")   # joined letters that have no text code of their own
LIG_DEFAULT_W = {"t": 335, "i": 229, "f": 305}      # Calibri, used when the CV gives no widths to compare with
_lig_words = None


def lig_words():
    global _lig_words
    if _lig_words is None:
        try:
            with gzip.open(RES_DIR / "static" / "ligwords.txt.gz", "rt", encoding="utf-8") as f:
                _lig_words = set(f.read().split())
        except Exception:
            _lig_words = set()
    return _lig_words


def resolve_ligatures(text, marks):
    """marks: {placeholder char: candidate strings, best width match first}. Pick the one that makes real words."""
    words = lig_words()
    for p in marks:
        text = re.sub(r"(?<![^\W\d_])" + p + r"(?![^\W\d_])", "•", text)
    best = {p: c[0] for p, c in marks.items()}
    for p, cands in marks.items():
        found = re.findall(r"[\w" + "".join(marks) + r"]*" + p + r"[\w" + "".join(marks) + r"]*", text)

        def hits(c):
            n = 0
            for w in found:
                w2 = w.replace(p, c)
                for q, b in best.items():
                    w2 = w2.replace(q, b)
                w2 = w2.lower()
                if w2 in words or re.sub(r"(s|es|ed|ing|ly|er)$", "", w2) in words:
                    n += 1
            return n
        scores = [(hits(c), -i) for i, c in enumerate(cands)]
        best[p] = cands[-max(scores)[1]]

    def apply(t):
        for p in marks:
            t = re.sub(r"(?<![^\W\d_])" + p + r"(?![^\W\d_])", "•", t)   # a lone unknown glyph is a bullet/icon
        for p, c in best.items():
            t = t.replace(p, c)
        return t
    return apply


def line_key(s):
    """Loose key for matching a line of CV text back to its font info."""
    import unicodedata
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", s)).lower()[:80]


BOLD_RE = re.compile(r"bold|black|heavy|semibold|demi|-b\b|,b\b|extrab", re.I)


def pdf_text(path, meta=None):
    """Read a PDF the way it looks: columns kept together, spaces from letter gaps, joined letters repaired.
    meta (optional dict) gets each line's font size and boldness, keyed by line_key()."""
    from pdfminer.converter import PDFPageAggregator
    from pdfminer.layout import LAParams, LTChar, LTTextBox, LTTextLine, LTFigure
    from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
    from pdfminer.pdfpage import PDFPage

    class Collector(PDFPageAggregator):
        def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):
            adv = super().render_char(matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate)
            item = self.cur_item._objs[-1]
            item.jf_cid = cid
            try:
                item.jf_w = font.char_width(cid) * 1000
            except Exception:
                item.jf_w = 0
            return adv

    rm = PDFResourceManager()
    dev = Collector(rm, laparams=LAParams(line_margin=0.4, all_texts=True))
    interp = PDFPageInterpreter(rm, dev)
    lines, widths, unknown, infos = [], {}, [], []
    with open(path, "rb") as fh:
        for n, page in enumerate(PDFPage.get_pages(fh)):
            if n >= 6:
                break
            interp.process_page(page)

            def walk(obj):
                if isinstance(obj, LTTextLine):
                    chars, sizes, bolds = [], [], 0
                    for ch in obj:
                        t = ch.get_text()
                        if isinstance(ch, LTChar):
                            if t.strip():
                                sizes.append(round(ch.size, 1))
                                bolds += bool(BOLD_RE.search(ch.fontname))
                            fam = ch.fontname.split("+")[-1].lower()
                            if t in ("�", "") or t.startswith("(cid:"):
                                unknown.append((fam, ch.jf_cid, ch.jf_w))
                                t = ("\x00", len(unknown) - 1)
                            elif t in "tif" and ch.jf_w:
                                widths.setdefault((fam, t), ch.jf_w)
                        chars.append(t)
                    lines.append(chars)
                    infos.append((max(set(sizes), key=sizes.count) if sizes else 0,
                                  bool(sizes) and bolds > len(sizes) * .6))
                elif isinstance(obj, (LTTextBox, LTFigure)) or hasattr(obj, "_objs"):
                    for o in obj:
                        walk(o)
                    if isinstance(obj, LTTextBox):
                        lines.append(["\n"])
                        infos.append(None)
            walk(dev.get_result())
    # one placeholder per distinct unknown glyph; the glyph's width says how many letters it holds
    marks, slot = {}, {}
    for fam, cid, w in unknown:
        if (fam, cid) in slot:
            continue
        p = chr(0xE000 + len(slot))
        slot[(fam, cid)] = p

        def guess(c):
            exp = sum(widths.get((fam, ch)) or LIG_DEFAULT_W[ch] for ch in c)
            return abs(1 - w / exp * 1.03) if w else 0      # joined glyphs are a little narrower
        cands = sorted(LIG_CANDIDATES, key=guess)
        marks[p] = [c for c in cands if not w or guess(c) < 0.12] or cands[:1]
    out = []
    for chars in lines:
        out.append("".join(slot[unknown[c[1]][:2]] if isinstance(c, tuple) else c for c in chars))
    fix = resolve_ligatures("".join(out), marks) if marks else (lambda t: t)
    out = [fix(o) for o in out]
    if meta is not None:
        for o, info in zip(out, infos):
            if info and o.strip():
                meta.setdefault(line_key(clean_text(o)), {"size": info[0], "bold": info[1]})
    return "".join(out)


def docx_text(path, meta=None):
    """Word text in reading order: headers first, then the body (tables cell by cell, text boxes once)."""
    import zipfile
    from xml.etree import ElementTree as ET
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    mc = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(r"word/header\d*\.xml", n)) + ["word/document.xml"]
        parts = [ET.fromstring(z.read(n)) for n in names if n in z.namelist()]
    lines = []

    def para_text(p):
        out = []

        def walk(e):
            if e.tag == mc + "Fallback":          # old-style copy of a text box we already read
                return
            if e.tag == w + "t":
                out.append(e.text or "")
            elif e.tag == w + "tab":
                out.append("  |  ")
            elif e.tag in (w + "br", w + "cr"):
                out.append("\n")
            elif e.tag == w + "p" and e is not p:
                return                            # paragraphs inside a text box are read on their own
            for c in e:
                walk(c)
        walk(p)
        return "".join(out)

    def walk(e):
        if e.tag == mc + "Fallback":
            return
        if e.tag == w + "p":
            listed = e.find(w + "pPr/" + w + "numPr") is not None    # Word list item = bullet point
            t = para_text(e)
            lines.append(("• " if listed else "") + t)
            if meta is not None and t.strip():
                st = e.find(w + "pPr/" + w + "pStyle")
                style = (st.get(w + "val", "") if st is not None else "").lower()
                szs = [int(x.get(w + "val")) / 2 for x in e.iter(w + "sz") if (x.get(w + "val") or "").isdigit()]
                runs = [r for r in e.iter(w + "r") if "".join(x.text or "" for x in r.iter(w + "t")).strip()]

                def is_bold(r):
                    b = r.find(w + "rPr/" + w + "b")
                    return b is not None and b.get(w + "val", "1") not in ("0", "false")
                size = max(szs) if szs else 26 if style.startswith("title") else 16 if style.startswith("heading") else 11
                meta.setdefault(line_key(clean_text(t)), {"size": size,
                                                          "bold": (bool(runs) and all(map(is_bold, runs)))
                                                          or style.startswith("heading"),
                                                          "heading": style.startswith("heading")})
        if e.tag == w + "tc":
            lines.append("")
        for c in e:
            walk(c)
    for root in parts:
        walk(root)
    return "\n".join(lines)


def cv_text(path, meta=None):
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            text = pdf_text(path, meta)
            if len(text.strip()) > 40:
                return text
        except Exception:
            pass
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:6])
    if ext == ".docx":
        return docx_text(path, meta)
    if ext in (".txt", ".rtf"):
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError("Can only read PDF, Word (.docx) or text CVs")


def clean_text(t):
    """Remove icon glyphs, emoji, rating dots and PDF spacing glitches from CV text."""
    import unicodedata
    t = unicodedata.normalize("NFKC", t)                       # "ﬁ" -> "fi", odd widths -> normal
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"(https?:)/\s+/", r"\1//", t)                  # "https:/ /" -> "https://"
    t = t.replace("\xad", "-")                                 # soft hyphens are drawn as hyphens in many PDFs
    t = "".join(" " if unicodedata.category(c) in ("So", "Co", "Cn", "Cs", "Sk", "Cf") or c in "○●◯◉★☆✓✔" else c
                for c in t)
    t = t.replace("\xad", "-")                                 # soft hyphens are drawn as hyphens in many PDFs
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", t)                     # words split across lines
    t = re.sub(r"\b(?![AI]\b)([A-Z]) ([a-z]{2,})", r"\1\2", t)  # "T eamCity" -> "TeamCity"
    t = re.sub(r"\)([A-Za-z])", r") \1", t)                    # "(Project)content" -> "(Project) content"
    t = re.sub(r"(\d{3,})(?=[A-Z][a-z]{2,})", r"\1 ", t)       # "+44 754 9768198Coventry" -> "... 9768198 Coventry"
    t = re.sub(r"[ \t]+", " ", t)
    return t


JOB_WORDS = (r"engineer|developer|programmer|manager|analyst|designer|nurse|assistant|assistent|officer|consultant|"
             r"konsulent|\blead\b|director|directeur|technician|specialist|co-?ordinator|coördinator|koordinator|"
             r"executive|administrator|\bintern\b|internship|teacher|lecturer|tutor|architect|arkitekt|scientist|"
             r"researcher|advisor|adviser|adviseur|rådgiver|associate|representative|supervisor|accountant|"
             r"bookkeeper|boekhouder|bogholder|clerk|operative|operator|worker|\bcook\b|\bkok\b|driver|chauffeur|"
             r"artist|writer|editor|producer|tester|\bqa\b|head of|owner|founder|apprentice|trainee|volunteer|"
             r"vrijwilliger|frivillig|carer|caregiver|care giver|bartender|barista|cashier|waiter|waitress|"
             r"receptionist|secretary|secretaresse|sekretær|merchandiser|\bstaff\b|team member|crew|cleaner|porter|"
             r"housekeeper|nanny|freelance|self-employed|zelfstandig|medewerker|medewerkster|verkoper|beheerder|"
             r"docent|leraar|verpleegkundige|monteur|stagiair|medarbejder|medhjælper|ingeniør|ingenieur|"
             r"sygeplejerske|pædagog|\bleder\b|sælger|praktikant|værnepligtig|chef\b|president|\bvp\b|\bcto\b|"
             r"\bceo\b|\bcfo\b|\bpartner\b|\bagent\b|planner|buyer|inspector|electrician|plumber|mechanic|"
             r"labourer|laborer|warehouse|picker|packer|attendant|steward|hostess|instructor|\bcoach\b|therapist|"
             r"pharmacist|doctor|physician|surgeon|dentist|paramedic|midwife|support worker|fellow\b|postdoc|"
             r"ambassador|promoter|sales\b|salesperson|server\b")
MONTHS = r"(?:jan|feb|maart|mar|mrt|apr|may|mei|maj|jun|jul|aug|sep|oct|okt|nov|dec|spring|summer|fall|autumn|" \
         r"winter|zomer|sommer|forår|efterår)[a-zæøåé]*\.?"
DAY = r"(?:\d{1,2}(?:st|nd|rd|th|\.)?\s+)"
DAY_AFTER = r"(?:\s+\d{1,2}(?:st|nd|rd|th)?\b,?)"            # US style: "January 18th", "Jan 18, 2023"
ONE_DATE = (r"(?:" + DAY + r"?" + MONTHS + DAY_AFTER + r"?\s*,?\s*(?:19|20)\d{2}|\d{1,2}\s*[/.\-]\s*(?:19|20)\d{2}"
            r"|(?:19|20)\d{2})")
PRESENT = r"present|pres\.?|current(?:ly)?|now|date|today|ongoing|tot heden|heden|nu|huidig|d\.d\.|dags dato|i dag|aktuell|heute"
DATE_RANGE = (r"(?<![\w/])(" + ONE_DATE + r"|" + DAY + r"?" + MONTHS + DAY_AFTER + r"?)\s*(?:-|–|—|−|to|until|till|tot|til|bis)\s*("
              + ONE_DATE + r"|" + PRESENT + r")(?!\w)")
DURATION = r"\(?\s*(?:approx\.?|approximately|ca\.?|about|around|circa|over|ruim|omkring|cirka)?\s*(\d{1,2})\+?\s*" \
           r"(?:years?|yrs?|jaar|år)\s*\)?"
US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC "
                "ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
US_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC"}
STREET_WORDS = (r"street|st|road|rd|avenue|ave|lane|ln|drive|dr|close|way|court|ct|place|pl|crescent|cres|grove|"
                r"terrace|gardens|gdns|boulevard|blvd|parkway|pkwy|highway|hwy|circle|cir|square|sq|mews|row|walk|"
                r"hill|park|view|rise|green")
STREET = (r"(?:\b\d{1,5}[A-Za-z]?\s+(?:[A-Z][\w'\-]*\s+){0,4}(?:" + STREET_WORDS + r")\b\.?"
          r"|\b[A-ZÆØÅÄÖÜ][\wæøåäöüß\-]*(?:straat|weg|laan|plein|gracht|kade|singel|dijk|gade|vej|allé|alle|stræde|"
          r"strasse|straße|gasse|platz)\s+\d{1,4}[a-zA-Z]?\b)")
UNIT_RE = r"^(apt|apartment|unit|suite|ste|flat|room|#|floor|fl)\b\.?"
UK_POSTCODE = r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b"
NL_POSTCODE = r"\b(\d{4}\s?[A-Z]{2})\s+([A-Z][\w'\-]+(?:[ \-][A-Z][\w'\-]+)?)"
EU_POSTCODE = r"\b(?:[A-Z]{1,2}-)?(\d{4,5})\s+([A-ZÆØÅÄÖÜ][\wæøåäöüß\-]+(?: [A-ZÆØÅÄÖÜ][\wæøåäöüß\-]+)?)"
US_PLACE = r"([A-Z][A-Za-z.'\-]+(?: [A-Z][A-Za-z.'\-]+){0,3}),\s*([A-Z]{2})\b\.?(?:\s+(\d{5})(?:-\d{4})?)?"
EXTRA_COUNTRIES = {"korea": "KR", "south korea": "KR", "republic of korea": "KR", "s.korea": "KR", "s. korea": "KR",
                   "nl": "NL", "dk": "DK", "the uk": "GB", "united states": "US", "u.s.a.": "US", "deutschland": "DE"}
PARTICLES = {"van", "de", "der", "den", "von", "la", "le", "da", "di", "du", "del", "della", "ten", "ter", "te",
             "bin", "al", "el", "dos", "das", "do", "'t", "op", "het"}
NAME_SKIP = (r"curriculum|vitae|\bcv\b|r[eé]sum[eé]|eksempel|voorbeeld|sample|example|template|your name|name here|"
             r"lebenslauf|personal|personlige|persoonlijke|contact|profile|profil|address|adres|page \d|references|"
             r"available|request|dear |sincerely|regards|kind |hiring|hello|united kingdom|universit|college|school|"
             r"institut|academy|hogeschool|gymnasium|\binc\b|\bltd\b|limited|\bgroup\b|\bin\b|\bof\b|\band\b|&")
HEADINGS = [
    ("experience", r"((relevant|work|professional|employment|career|industry|volunteer(ing)?|other|previous|additional|"
                   r"recent|selected|teaching|research|work and volunteer) )*(experience|history|employment)|"
                   r"employment( history)?|career( history| summary)?|work history|(werk|praktijk|relevante )?ervaring|"
                   r"werkervaring|arbeidsverleden|loopbaan|werkgeschiedenis|(erhvervs|arbejds|relevant )?erfaring|"
                   r"beskæftigelse|(berufs|praktische |berufliche )?erfahrung|beruflicher werdegang|research|"
                   r"internships?|placements?|volunteer work|work placements?"),
    ("education", r"education|qualifications|academic( background| history| qualifications)?|educational background|"
                  r"opleiding(en)?|educatie|onderwijs|scholing|uddannelse(r)?|(schul)?ausbildung|bildung|studies|"
                  r"studie|training and education|education, training"),
    ("skills", r"((key|technical|core|relevant|professional|personal|transferable|it|computer|soft|hard|other|"
               r"additional|digital) )*(skills|competencies|competences|abilities|expertise|strengths|proficiencies)|"
               r"skills summary|vaardigheden|competenties|kwaliteiten|kennis|kompetencer|færdigheder|kvalifikationer|"
               r"it-?(kompetencer|kennis|vaardigheden)|kenntnisse|fähigkeiten|it"),
    ("summary", r"((personal|professional|career) )?(profile|summary|statement|objective)|about( me)?|"
                r"(persoonlijk )?profiel|over mij|profil|om mig|resumé|sammenfatning|kurzprofil"),
    ("personal", r"personal (details|information|data|info)|contact( details| information| info| me)?|details|"
                 r"persoonlijke gegevens|personalia|contactgegevens|personlige (oplysninger|data)|kontakt(oplysninger)?|"
                 r"persönliche (daten|angaben)|location|address|adres|adresse|woonplaats"),
    ("languages", r"languages?( skills)?|talen|taalvaardigheid|sprog(kundskaber)?|sprachen(kenntnisse)?"),
    ("other", r"interests|hobbies|hobby'?s|references|referees|certifications?|certificates|courses|training|"
              r"achievements|awards|hono(u)?rs|volunteering|projects|publications|availability|interesses|referenties|"
              r"cursussen|certificaten|nevenactiviteiten|fritidsinteresser|interesser|referencer|kurser|"
              r"frivilligt arbejde|hobbys|interessen|referenzen|weiterbildung|cover letter|declaration|"
              r"additional information|activities|extra[- ]?curricular( activities)?|leadership|memberships|"
              r"nevenfuncties|bestuursfuncties|tillidshverv"),
]


def collapse_spaced(s):
    """'P R O F I L E' -> 'PROFILE', 'N a a m' -> 'Naam' (letter-spaced headings)."""
    groups = re.split(r"\s{2,}", s)
    out = []
    for g in groups:
        toks = g.split(" ")
        if len(toks) >= 4 and all(len(t) <= 2 for t in toks) and sum(len(t) == 1 for t in toks) >= len(toks) * 0.6:
            g = "".join(toks)
        out.append(g)
    return " ".join(out)


def heading_key(line):
    s = collapse_spaced(line).strip(" :-–—_•|*#").lower()
    s = re.sub(r"\s+", " ", s)
    if not s or len(s) > 50:
        return None
    for key, pat in HEADINGS:
        if re.fullmatch(r"(" + pat + r")((,| and| &| og| en| und) [\w' ]{2,25})?", s):
            return key
    return None


def country_code(text):
    t = (text or "").strip(" .").lower()
    return code_for_country_text(t) or EXTRA_COUNTRIES.get(t)


def country_label(cc):
    return COUNTRIES[cc][0] if cc in COUNTRIES else cc


def is_place(s, strict=True):
    """A town, 'Town, Country', 'Town, ST', a country, or a line with a postcode."""
    s = s.strip(" ,.;()")
    if not s or len(s.split()) > 8 or re.search(r"@|https?:|www\.", s):
        return False
    if re.search(UK_POSTCODE, s) or re.search(NL_POSTCODE, s) or re.fullmatch(US_PLACE, s):
        return True
    if country_code(s):
        return True
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) >= 2:
        last = parts[-1]
        us = last in US_STATES or last.lower() in US_STATE_NAMES
        if not (country_code(last) or us or find_city(last) or last.lower() in ("england", "scotland", "wales")):
            return False
        cc = country_code(last) or ("US" if us else None) or \
            ("GB" if last.lower() in ("england", "scotland", "wales") else None) or (find_city(last) or [None] * 4)[3]
        return bool(find_city(parts[0], cc) or (cc and not strict and len(parts) == 2 and not is_title(parts[0])))
    row = find_city(s)
    return bool(row and (not strict or row[5] >= 15000))


def is_title(s):
    return bool(re.search(JOB_WORDS, s, re.I))


def tidy_caps(s):
    """'SUE RYDER' -> 'Sue Ryder', keeps short acronyms ('BRAVISSIMO HQ' -> 'Bravissimo HQ')."""
    if s.isupper() and len(re.sub(r"\W", "", s)) > 4 and not re.fullmatch(r"[A-Z&]{2,6}", s.strip()):
        small = {"of", "and", "the", "in", "for", "at", "on", "de", "van"}         # one short word = brand/acronym (NASCAR)
        words = s.split()
        return " ".join(w.lower() if w.lower() in small and i else w.capitalize() if len(w) > 3 or not w.isalpha() else w
                        for i, w in enumerate(words))
    return s


def tidy_description(lines):
    """Re-join wrapped lines, keep bullets, and turn 'ProjectC++•UE4•Git' into 'Project — C++, UE4, Git'."""
    out = []
    for ln in lines:
        ln = re.sub(r"\b(the|a|an|of|on|in|for|to|and|with)([A-Z])", r"\1 \2", ln)   # "theSea" -> "the Sea"
        if ln.count("•") >= 2 and not ln.startswith("• "):
            segs = [s.strip() for s in ln.split("•") if s.strip()]
            m = re.match(r"(.*[a-z)\]])([A-Z][\w#+.]*)$", segs[0])
            name = ""
            if m:
                name, segs[0] = m[1].strip(), m[2]
            out.append((name + " — " if name else "") + ", ".join(segs))
            continue
        if out and not ln.startswith("• ") and not re.search(r"[.!?:]$", out[-1]) and " — " not in out[-1] \
                and ln[:1].islower():
            out[-1] += " " + ln                      # continuation of a wrapped line
        else:
            out.append(ln)
    return "\n".join(out).strip()


def norm_dates(text):
    """'May '20' -> 'May 2020'; drop LinkedIn's '(2 yrs 3 mos)' / '(1 year 2 months)' after a date range."""
    yy = datetime.now().year % 100
    text = re.sub(r"(?<=[a-z.]\s)'(\d{2})\b", lambda m: ("20" if int(m[1]) <= yy + 1 else "19") + m[1], text,
                  flags=re.I)
    text = re.sub(r"\s*·?\s*\((?:\s*\d+\+?\s*(?:yrs?|years?|mos?|months?|jaar|maanden|år|måneder))+\s*\)", "", text,
                  flags=re.I)
    return re.sub(r"\s*·\s*(?:\d+\+?\s*(?:yrs?|mos?)\s*)+$", "", text, flags=re.I)


def find_dates(text):
    """(start, end, matched span) for a date range, a single date, or a duration like '5 years'."""
    m = re.search(DATE_RANGE, text, re.I)
    if m:
        start, end = m[1], m[2]
        before = re.search(r"(" + ONE_DATE + r")\s*$", text[:m.start()], re.I)
        if before and not re.search(r"(19|20)\d{2}", start):
            start = before[1]                                   # "10th Feb 2025 Apr- June 2026"
            span = (before.start(), m.end())
        else:
            span = (m.start(), m.end())
        if not re.search(r"(19|20)\d{2}", start):
            y = re.search(r"(19|20)\d{2}", end)
            if y:
                start = re.sub(r"(\d)(st|nd|rd|th)?\s*,?$", r"\1\2", start.strip())
                start += " " + y[0]                             # "June - Sept 2024"
        start = re.sub(r"^\d{1,2}(st|nd|rd|th|\.)?\s+(?=[a-z])", "", start.strip(), flags=re.I)
        end = re.sub(r"^\d{1,2}(st|nd|rd|th|\.)?\s+(?=[a-z])", "", end.strip(), flags=re.I)
        # "January 18th 2023" -> "January 2023" (the day isn't needed)
        start, end = (re.sub(r"\b(" + MONTHS + r")\s+\d{1,2}(?:st|nd|rd|th)?\b,?", r"\1", x, flags=re.I) for x in (start, end))
        end = "Present" if re.fullmatch(PRESENT, end, re.I) else end
        return start.title() if not start[:1].isdigit() else start, end.title() if end[:1].isalpha() else end, span, None
    stripped = text.strip(" ,|–-()")
    if re.fullmatch(DURATION, stripped, re.I):
        return "", "", (0, len(text)), int(re.fullmatch(DURATION, stripped, re.I)[1])
    if re.fullmatch(r"\(?(" + ONE_DATE + r")\)?", stripped, re.I):
        return stripped.strip("()").title(), "", (0, len(text)), None
    # a month/season + year at the end of a heading line: "Marketing Intern, Kraft Heinz — Chicago, IL  Summer 2018"
    m = re.search(r"(?:\s|\|)\(?(" + DAY + r"?" + MONTHS + r"\s*,?\s*(?:19|20)\d{2})\)?\s*$", text, re.I)
    if m and len(text[:m.start()].split()) <= 12:
        return re.sub(r"^\d{1,2}(st|nd|rd|th|\.)?\s+", "", m[1]).title(), "", (m.start(), len(text)), None
    return None


def small_town(s):
    """A smaller town (5,000+ people) named after a comma in a job heading: "Codemasters, Southam"."""
    s = s.strip(" ,.;()")
    row = find_city(s) if 0 < len(s.split()) <= 3 else None
    return bool(row and not is_title(s) and _norm(row[0]) == _norm(s))


def split_header(lines):
    """Turn a job's heading lines into (title, company, location)."""
    segs, loc = [], ""
    for ln in lines:
        if re.search(UK_POSTCODE, ln) or re.search(NL_POSTCODE, ln) or (re.search(r"\d", ln) and ln.count(",") >= 2):
            if not loc:
                m = re.search(r"([A-Za-z][\w' \-]+?)\s*,?\s*" + UK_POSTCODE, ln) or re.search(NL_POSTCODE, ln)
                if m and re.search(UK_POSTCODE, m[0]):
                    loc = tidy_caps(m[1].split(",")[-1].strip())
                elif m:
                    loc = tidy_caps(m[2])
                else:
                    loc = tidy_caps(ln.split(",")[-1].strip(" ."))
            continue
        for major in re.split(r"\s+[–—|•·@]\s+|\s+-\s+|\s*\|\s*|\s+at\s+|\t", ln):
            cp = [p.strip(" .;:()") for p in major.split(",") if p.strip(" .;:()")]
            cut = len(cp)
            for k in range(min(3, len(cp)), 0, -1):
                if (len(cp) > k or segs) and (is_place(", ".join(cp[-k:])) or
                                             k == 1 and len(segs) + len(cp) > 2 and small_town(cp[-1])):
                    if not loc:
                        loc = ", ".join(cp[-k:])
                    cut = len(cp) - k
                    break
            segs += cp[:cut]
    segs = [tidy_caps(s) for s in segs if s]
    title = next((s for s in segs if is_title(s)), "")
    rest = [s for s in segs if s != title]
    if not title and rest:
        title = rest.pop(0)
    company = rest[0] if rest else ""
    if not loc and len(rest) > 1 and (is_place(rest[1]) or small_town(rest[1])):
        loc = rest[1]
    return title, company, loc


def parse_jobs(items, allowed):
    """items: [{'t': text, 'b': bullet?, 'sec': section}] — find each job by its dates, then its heading lines."""
    def headerish(it):
        t = it["t"]
        w = len(t.split())
        address = bool(re.search(UK_POSTCODE, t) or re.search(NL_POSTCODE, t))
        return (not it["b"] and not it.get("head") and len(t) <= 95 and w <= 12 and not t.endswith(":")
                and not (t.endswith(".") and w > 6 and not address) and not it.get("date") and not t[:1].islower())

    anchors = []
    for i, it in enumerate(items):
        if it["sec"] not in allowed or it.get("head") or (it["b"] and len(it["t"]) > 70):
            continue
        d = find_dates(it["t"])
        if d:
            rest = re.sub(r"\(\s*\)|\[\s*\]", " ", it["t"][:d[2][0]] + " " + it["t"][d[2][1]:])   # "Intern (dates), NASCAR"
            rest = re.sub(r"\s+,", ",", rest).strip(" ,|–-()\t")
            if rest and not is_title(rest) and is_place(rest, strict=False):
                it["loc"], rest = rest, ""                    # "June 2014 – Sep 2014 | Mountain View, CA"
            if len(rest.split()) <= 14:
                it["date"] = True
                anchors.append((i, d, rest))
    if not anchors:
        return [], 0

    def take(i, step, limit, stop):
        got, j = [], i + step
        while 0 <= j < len(items) and len(got) < limit and j != stop and headerish(items[j]) \
                and items[j]["sec"] == items[i]["sec"]:
            got.append(j)
            j += step
        return got if step > 0 else got[::-1]

    def plan(layout):
        out, prev_end = [], -1
        for n, (i, d, rest) in enumerate(anchors):
            nxt = anchors[n + 1][0] if n + 1 < len(anchors) else len(items)
            rest_parts = len([p for p in re.split(r"\s+[–—|•·@-]\s+|,\s+|\s*\|\s*|\s+at\s+", rest) if p.strip()])
            if rest_parts >= 2:
                hdr = []
            elif layout == "before":
                hdr = [j for j in take(i, -1, 3 - bool(rest), prev_end) if j > prev_end] or take(i, 1, 3, nxt)
            else:
                hdr = take(i, 1, 3, nxt) or [j for j in take(i, -1, 2, prev_end) if j > prev_end]
            out.append(hdr)
            prev_end = max([i] + hdr)
        return out

    def quality(p):
        return sum(any(is_title(items[j]["t"]) for j in hdr) for hdr in p)
    before, after = plan("before"), plan("after")
    chosen = after if quality(after) > quality(before) else before

    jobs, total_dur = [], 0
    starts = [min([a[0]] + h) for a, h in zip(anchors, chosen)]
    for n, ((i, d, rest), hdr) in enumerate(zip(anchors, chosen)):
        lines = ([rest] if rest else []) + [items[j]["t"] for j in hdr]
        title, company, loc = split_header(lines)
        loc = loc or items[i].get("loc", "")
        end_at = starts[n + 1] if n + 1 < len(anchors) else len(items)
        desc = []
        if d[3]:
            desc.append(f"{d[3]} years")
            total_dur += d[3]
        for k, it in enumerate(items[max([i] + hdr) + 1:end_at]):
            if it.get("head") or it["sec"] not in allowed:
                break
            if k == 0 and not loc and not it["b"] and len(it["t"].split()) <= 7 and is_place(it["t"], strict=False):
                loc = it["t"]                                   # LinkedIn puts the place on the line under the dates
                continue
            desc.append(("• " if it["b"] else "") + it["t"])
        if title or company:
            jobs.append({"title": title, "company": company, "location": loc, "start": d[0], "end": d[1],
                         "description": tidy_description(desc)[:2000]})
    return jobs[:15], total_dur


def find_phone(text, regions, with_region=False):
    """Phone number via Google's libphonenumber (the 'phonenumbers' library), trying likely countries in turn."""
    try:
        import phonenumbers as pn
    except Exception:
        return None
    year_range = r"\(?(19|20)\d\d\s*[-–/]\s*((19|20)\d\d|\d\d)\)?"
    for region in regions:
        for m in pn.PhoneNumberMatcher(text, region, leniency=pn.Leniency.VALID):
            raw = m.raw_string.strip(" .-")
            if re.fullmatch(year_range, raw) or re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-](19|20)\d\d", raw):
                continue
            region_of = pn.region_code_for_number(m.number)
            region_of = "GB" if region_of in ("GG", "JE", "IM") else region_of   # UK mobiles shared with the islands
            return (raw, region_of) if with_region else raw
    return None


def split_street(street, out):
    """'1234 Elm St, Apt 5B' -> address1 '1234 Elm St', address2 'Apt 5B' ('Flat 2, 8 Queen St' the other way)."""
    parts = [p.strip() for p in re.split(r",\s*|\s+(?=(?:apt|apartment|unit|suite|ste|#)\b\.?\s*\w)", street,
                                         flags=re.I) if p and p.strip(" ,")]
    if not parts:
        return
    if len(parts) > 1 and re.match(UNIT_RE, parts[0], re.I):
        parts = parts[1:2] + parts[:1] + parts[2:]
    out["address1"] = parts[0]
    if len(parts) > 1:
        out["address2"] = ", ".join(parts[1:])


# ---- OCR for CVs whose text is drawn as shapes or scanned (Windows' own offline OCR engine)

OCR_PS1 = r'''param([string]$path)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(); $t.Result }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new("en-US")) }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) {
    $words = @($line.Words)
    $r = $words[0].BoundingRect
    $h = 0; foreach ($w in $words) { if ($w.BoundingRect.Height -gt $h) { $h = $w.BoundingRect.Height } }
    [Console]::Out.WriteLine(([pscustomobject]@{ t = $line.Text; x = [int]$r.X; y = [int]$r.Y; h = [int]$h } | ConvertTo-Json -Compress))
}
$stream.Dispose()
'''


def _write_bmp(bitmap, out):
    """pypdfium2 bitmap -> 24-bit BMP file (no imaging library needed)."""
    import struct
    w, h, stride = bitmap.width, bitmap.height, bitmap.stride
    data = bytes(bitmap.buffer)
    bpp = 3 if stride // max(w, 1) == 3 else 4
    row = (w * 3 + 3) & ~3
    pad = b"\0" * (row - w * 3)
    with open(out, "wb") as f:
        f.write(b"BM" + struct.pack("<IHHI", 54 + row * h, 0, 0, 54))
        f.write(struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 24, 0, row * h, 2835, 2835, 0, 0))
        for y in range(h):
            line = data[y * stride: y * stride + w * bpp]
            if bpp == 4:
                line = b"".join(line[i:i + 3] for i in range(0, len(line), 4))
            f.write(line + pad)


def ocr_pdf(path, pages=2):
    """Read the first pages of a PDF as images with Windows OCR. [] when not on Windows or anything fails."""
    if sys.platform != "win32":
        return []
    try:
        import pypdfium2 as pdfium
    except Exception:
        return []
    work = DATA_DIR / "ocr"
    work.mkdir(exist_ok=True)
    script = work / "ocr.ps1"
    if not script.exists() or script.read_text(encoding="utf-8") != OCR_PS1:
        script.write_text(OCR_PS1, encoding="utf-8")
    lines = []
    try:
        pdf = pdfium.PdfDocument(str(path))
        for n in range(min(pages, len(pdf))):
            img = work / f"page{n}.bmp"
            bitmap = pdf[n].render(scale=3)
            _write_bmp(bitmap, img)
            width = bitmap.width
            run = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                  "-File", str(script), str(img)], capture_output=True, timeout=60,
                                 creationflags=0x08000000)               # no console window
            for raw in run.stdout.decode("utf-8", "replace").splitlines():
                try:
                    d = json.loads(raw)
                    d.update(page=n, w=width)
                    lines.append(d)
                except ValueError:
                    pass
            img.unlink(missing_ok=True)
        pdf.close()
    except Exception:
        return lines
    return lines


FIELD_LABELS = [
    ("Email", r"e-?mail( address)?|mail|correo|e-?post"),
    ("Phone", r"phone( number)?|mobile( number)?|mob|tel(ephone)?|cell( phone)?|telefoon|mobiel|telefon|mobil|tlf\.?|gsm|contact number"),
    ("Address", r"location|address|home address|city|town|based in|lives in|residence|woonplaats|adres|adresse|bop[æa]l|wohnort|by"),
    ("Website", r"website|web|portfolio|homepage|site"),
    ("LinkedIn", r"linked\s?in"),
    ("Name", r"(full )?name|naam|navn"),
]


def ocr_to_text(lines):
    """OCR lines -> CV text in reading order, with each field label joined to its value ("Email: me@x.com").
    Values are matched by position: right under the label (stacked fields) or beside it on the same row."""
    if not lines:
        return "", {}
    out_text, meta = [], {}
    for page in sorted({l["page"] for l in lines}):
        ls = sorted([dict(l) for l in lines if l["page"] == page], key=lambda l: (l["y"], l["x"]))
        W = ls[0]["w"]
        hs = sorted(l["h"] for l in ls if l["h"])
        med = hs[len(hs) // 2] if hs else 20
        # 1. labels -> values
        pairs = []
        for lab in ls:
            name = next((n for n, pat in FIELD_LABELS if re.fullmatch(r"\W*(" + pat + r")\W*", lab["t"].strip(), re.I)), None)
            if not name or lab.get("used"):
                continue
            below = [c for c in ls if c is not lab and not c.get("used") and abs(c["x"] - lab["x"]) < max(3 * lab["h"], 40)
                     and 0 < c["y"] - lab["y"] < 5 * max(lab["h"], med)]
            beside = [c for c in ls if c is not lab and not c.get("used") and abs(c["y"] - lab["y"]) < 0.7 * max(lab["h"], med)
                      and 0 < c["x"] - lab["x"] < W * 0.45]
            pick = min(below, key=lambda c: c["y"]) if below else min(beside, key=lambda c: c["x"]) if beside else None
            if pick and not any(re.fullmatch(r"\W*(" + pat + r")\W*", pick["t"].strip(), re.I) for _, pat in FIELD_LABELS):
                lab["used"] = pick["used"] = True
                pairs.append(f"{name}: {pick['t'].strip()}")
        # 2. big lines near the top that belong together (a name split over two lines)
        rest = [l for l in ls if not l.get("used")]
        top = [l for l in rest if l["y"] < ls[-1]["y"] * 0.3 and l["h"] >= 1.8 * med]
        if len(top) > 1:
            joined = " ".join(l["t"].strip() for l in top)
            if len(joined.split()) <= 5:
                for l in top[1:]:
                    l["used"] = True
                top[0]["t"] = joined
        rest = [l for l in rest if not l.get("used")]
        # 3. reading order: columns when the page clearly has a right-hand column
        right = [l for l in rest if l["x"] >= W * 0.45]
        left = [l for l in rest if l["x"] < W * 0.3]
        two_col = len(right) >= 6 and len(left) >= 6
        rest.sort(key=lambda l: ((l["x"] >= W * 0.45) if two_col else 0, l["y"], l["x"]))
        for l in rest:
            meta.setdefault(line_key(l["t"]), {"size": l["h"], "bold": False})
        out_text += pairs + [l["t"] for l in rest]
    return "\n".join(out_text), meta


def education_details(edu_lines, out):
    """Highest qualification, subject and school from education lines (CV or LinkedIn)."""
    levels = [("PhD", r"\bph\.?\s?d\b|doctorate|\bdphil\b|doctor of philosophy|promotieonderzoek"),
              ("Master's degree", r"\bmaster'?s?\b|\bkandidat\b|\bcand\.\s?\w+"),
              ("MSc", r"\bm\.?sc\b|\bm\.s\.(?!\w)"), ("MBA", r"\bmba\b"), ("MEng", r"\bmeng\b"), ("MA", r"\bm\.a\.(?!\w)|\bma\b(?= \(|\s+in\b)"),
              ("MRes", r"\bmres\b"), ("BSc", r"\bb\.?sc\b|\bb\.s\.(?!\w)"), ("BA", r"\bb\.?a\.?(?!\w)(?! level)"),
              ("BEng", r"\bbeng\b"), ("LLB", r"\bllb\b"), ("Bachelor's degree", r"bachelor|\bhbo\b|professionsbachelor"),
              ("Associate degree", r"\bassociate'?s?\b(?= (?:of|in|degree)\b)|\bassociate degree|\ba\.?a\.?s\.?\b|\ba\.s\.(?!\w)"),
              ("HND", r"\bhnd\b"), ("HNC", r"\bhnc\b"), ("Foundation degree", r"foundation degree"),
              ("Diploma", r"\bdiploma\b|erhvervsuddannelse|\bmbo\b"), ("A-Levels", r"\ba[- ]levels?\b"),
              ("BTEC", r"\bbtec\b"), ("GCSEs", r"\bgcses?\b"), ("Certificate", r"certificate|certificaat|certifikat")]
    order = [n for n, _ in levels]
    found = None
    for name, pat in levels:
        line = next((ln for ln in edu_lines if re.search(pat, ln, re.I)), None)
        if line is not None:
            found = (name, pat, line)
            break
    if found:
        name, pat, line = found
        if name == "Master's degree" and re.search(r"\b(m\.?sc|m\.s\.)\b", line, re.I):
            name = "MSc"
        out["highest_qualification"] = name
        if name not in ("A-Levels", "GCSEs", "BTEC", "Certificate"):
            ln = re.sub(r"\(?\bhons\.?\b\)?|\((kandidat|bachelor|master)\)", " ", line, flags=re.I)
            sm = re.search(r"(?:" + pat + r")\.?\s*(?:degree\s*)?(?:\s*of\s+(?:arts|science|engineering|laws|fine arts|"
                           r"business administration|education|music|technology|applied science)\b)?\s*"
                           r"(?:[–—\-:,]\s*)?(?:\b(?:in|of|i|en|im)\b\s+)?"
                           r"([A-ZÀ-Þa-zæøå][\w&'’ ]{2,60})", ln, re.I)
            # LinkedIn style: "Bachelor of Arts - BA, English · (2015 - 2018)" -> the subject comes after the comma
            lk = re.search(r"(?:" + pat + r")((?:\s+of\s+(?:arts|science|engineering|laws|business administration|"
                           r"fine arts|education|music|technology))?(?:\s*[-–]\s*[\w.]+)?)\s*,\s*([^,·(\d]+)", ln, re.I)
            if lk and not re.search(r"universit|college|school|institut|gpa|grade", lk[2], re.I) \
                    and not re.fullmatch(MONTHS + r"\s*", lk[2].strip(), re.I) and len(lk[2].split()) <= 7:
                sm = None
                out["degree_subject"] = lk[2].strip(" .")
            if sm:
                subj = re.split(r",|\s{2}| - | – | — |\(|\d|\|", sm[1])[0].strip()
                subj = re.sub(r"^(som|as|als|als een)\s+", "", subj, flags=re.I)
                if subj and not re.search(r"universit|college|hogeschool|school|institut|akademi", subj, re.I) \
                        and len(subj.split()) <= 7:
                    out["degree_subject"] = subj
        if re.fullmatch(r"(science|arts?|bs|ba|bsc|msc|ma|ms|engineering|laws|beng|meng|degree|hons)",
                        out.get("degree_subject", "").strip(" .").lower()):
            out.pop("degree_subject")                  # "Bachelor of Science - BS" names the degree, not the subject
    inst_re = r"universit\w*|college|hogeschool|højskole|akademi\w*|academy|institut\w*|polytechnic|school of|" \
              r"\bschool\b|gymnasium|lyceum|\bsdu\b|\bdtu\b|\bku\b|\bcbs\b|\bmit\b|\bucl\b|\blse\b"
    best_inst, best_rank = "", 99
    for ln in edu_lines:
        for seg in re.split(r"\s*[,|–—(\)]\s*|\s+-\s+|\s{2,}", ln):
            seg = re.sub(r"\b(19|20)\d{2}\b.*", "", seg).strip(" .")
            m = re.search(inst_re, seg, re.I)
            if m and re.search(r"diploma|degree|bachelor|master|ged\b|certificate|a-?levels?|gcse", seg, re.I) \
                    and not re.match(r"univ|hogeschool|college", m[0], re.I):
                continue                                         # "High School Diploma" is the level, not the school
            if not m or len(seg.split()) > 9 or not m[0][0].isupper():
                continue
            rank = 0 if re.match(r"univ|hogeschool|højskole|akademi|polytech|instit|sdu|dtu|ku\b|cbs|mit|ucl|lse",
                                 m[0], re.I) else 1 if re.match(r"college|academy", m[0], re.I) else 2
            if rank < best_rank:
                best_inst, best_rank = seg, rank
    if best_inst:
        out["university"] = tidy_caps(re.sub(r"^the\s+", "", best_inst, flags=re.I))
    if out.get("degree_subject", "").isupper() and len(out["degree_subject"]) > 4:
        out["degree_subject"] = tidy_caps(out["degree_subject"] + " ") .strip() if " " in out["degree_subject"] \
            else out["degree_subject"].capitalize()


def parse_text(raw, meta=None):
    """Profile details from CV text (meta: optional font size/bold per line, from the PDF/Word reader)."""
    meta = meta or {}
    text = clean_text(raw)
    items, pending_bullet, sec = [], False, "top"
    for raw in text.splitlines():
        s = re.sub(r"\s+", " ", raw).strip()
        if not s or re.fullmatch(r"[\W_]+", s) and not re.fullmatch(r"[•·▪●◦‣∙*o]", s):
            continue
        if re.fullmatch(r"page \d+( of \d+)?|\d+\s*/\s*\d+|-\s*\d+\s*-", s, re.I):
            continue                               # page numbers
        if re.fullmatch(r"[•·▪●◦‣∙*o\-–]", s):
            pending_bullet = True                  # a bullet on its own line belongs to the next line
            continue
        info = meta.get(line_key(s), {})
        bullet = pending_bullet or s[:1] in "•·▪●◦‣∙-–*" or bool(re.match(r"o\s", s))
        pending_bullet = False
        s = norm_dates(re.sub(r"^(o\s+|[•·▪●◦‣∙\-–*|/\s]+)", "", s).strip())
        if not s:
            continue
        key = heading_key(s)
        if key:
            sec = key
            items.append({"t": collapse_spaced(s), "b": False, "sec": sec, "head": True,
                          "size": info.get("size", 0), "bold": info.get("bold", False)})
            continue
        prev = items[-1] if items else None
        if not bullet and prev and prev["b"] and len(prev["t"]) >= 65 and not re.search(r"[.!?]$", prev["t"]) \
                and not is_title(s) and not find_dates(s) and not info.get("bold"):
            prev["t"] += " " + s                       # the wrapped end of a long bullet point
            continue
        items.append({"t": s, "b": bullet, "sec": sec, "size": info.get("size", 0), "bold": info.get("bold", False),
                      "wordhead": info.get("heading", False)})

    # font cues (the idea behind OpenResume's parser): body text size, and big/bold short lines that are
    # section titles even when we don't know the word ("RESEARCH", "Volunteering & Community")
    sizes = sorted(it["size"] for it in items if it.get("size") and not it.get("head"))
    body = sizes[len(sizes) // 2] if sizes else 0
    first_head = next((n for n, it in enumerate(items) if it.get("head")), len(items))
    head_looks = {(round(it["size"]), it["bold"]) for it in items if it.get("head") and it.get("size")}
    if body and head_looks:
        sec = None
        for n, it in enumerate(items):
            if it.get("head"):
                sec = it["sec"]
                continue
            if n > first_head and not it["b"] and (round(it.get("size", 0)), it.get("bold")) in head_looks \
                    and it.get("size", 0) >= body * 1.08 and len(it["t"].split()) <= 4 \
                    and not re.search(r"[\d@|,]", it["t"]) and not is_title(it["t"]) and not find_dates(it["t"]):
                it["head"], sec = True, "other"
                it["sec"] = "other"
            elif sec and it["sec"] != sec:
                it["sec"] = sec
    lines = [it["t"] for it in items if not it.get("head")]
    flat = " ".join(lines)
    out = {}

    # where the personal details are: before the first main section, plus any contact/location section
    first_main = next((n for n, it in enumerate(items) if it.get("head") and it["sec"] in
                       ("experience", "education", "skills")), len(items))
    first_date = next((n for n, it in enumerate(items) if re.search(DATE_RANGE, it["t"], re.I)), len(items))
    top = [it for n, it in enumerate(items) if (n < min(first_main, first_date, 30) or it["sec"] == "personal")
           and not it.get("head")][:40]
    top_text = " | ".join(it["t"] for it in top)
    email_re = r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z]{2,10})+"
    phone_re = r"(?<![\w/.])(\(?\+?\(?\d[\d ()\-./]{6,18}\d)(?!\d)"

    m = re.search(email_re, top_text) or re.search(email_re, flat)
    if m:
        local_part, _, domain = m[0].partition("@")
        out["email"] = local_part + "@" + domain.lower()          # "Me@Gmail.com" -> "Me@gmail.com"
    m = re.search(r"(https?://)?(www\.)?linkedin\.com/in/\s?[\w%-]+/?", flat, re.I)
    if m:
        out["linkedin"] = ("https://" + re.sub(r"^https?://", "", m[0])).rstrip("/").replace(" ", "")
    m = re.search(r"(https?://)?(www\.)?github\.com/[\w-]+", flat, re.I)
    if m:
        out["github"] = "https://" + re.sub(r"^https?://", "", m[0])
    no_mail = re.sub(email_re, " ", re.sub(phone_re, " ", flat))
    for m in re.finditer(r"(https?://|www\.)[\w.-]+\.[a-z]{2,}(?:/[\w.-]+)*/?", no_mail, re.I):
        if not re.search(r"linkedin|github", m[0], re.I):
            url = re.sub(r"/[a-z]{1,3}$", "", m[0].rstrip("/"))    # drop icon junk like "/ne" stuck on the end
            out["website"] = url if url.startswith("http") else "https://" + url
            break

    # Phone: libphonenumber, trying the CV's own country first
    tld = re.search(r"\.([a-z]{2})$", out.get("email", "").lower())
    guess = None
    regions = [r for r in dict.fromkeys([guess, (tld[1].upper().replace("UK", "GB") if tld else None),
                                         "GB", "US", "NL", "DK", "DE", "IE", "AU", "CA", "IN"]) if r]
    label = re.search(r"(?:phone|tel(?:ephone)?|mobile|mob|cell|tlf|telefoon|mobiel|telefon|mobil|gsm)\.?\s*"
                      r"(?:nr\.?|no\.?)?\s*[:.]?\s*(\+?\(?\d[\d ()\-./]{6,18}\d)", flat, re.I)
    phone = (find_phone(label[1], regions, True) if label else None) or find_phone(top_text, regions, True) \
        or find_phone(flat[:3000], regions, True)
    phone, phone_cc = phone if phone else (None, None)
    if not phone:                                       # library missing or nothing valid: simple pattern
        for c in ([label[1]] if label else []) + re.findall(phone_re, top_text):
            digits = re.sub(r"\D", "", c)
            if 8 <= len(digits) <= 15 and not re.fullmatch(r"\(?(19|20)\d\d\s*[-–/]\s*((19|20)\d\d|\d\d)\)?", c.strip()):
                phone = c.strip(" .-")
                break
    if phone:
        out["phone"] = phone


    # Name: a labelled name, else the best capitalised 2-5 word line near the top (bigger text scores higher)
    def clean_line(t):
        t = re.sub(email_re, " | ", t)
        t = re.sub(r"(https?://|www\.)\S+|linkedin\.com\S*|github\.com\S*", " | ", t, flags=re.I)
        # take out just the phone number we found (a looser pattern would also eat ZIP codes next to it)
        return t.replace(out["phone"], " | ") if out.get("phone") else re.sub(phone_re, " | ", t)

    def name_words(seg):
        seg = collapse_spaced(seg).strip(" ,|•·-–:")
        if not seg or re.search(r"[@\d/\\:;(),]|https?|www\.", seg) or re.search(NAME_SKIP, seg, re.I) \
                or is_title(seg) or heading_key(seg):
            return None
        words = seg.split()
        if not 2 <= len(words) <= 5 or words[0] in PARTICLES or words[-1] in PARTICLES:
            return None
        for w in words:
            if w not in PARTICLES and not re.fullmatch(r"[A-ZÀ-ÞĀ-Ž][A-Za-zÀ-ÿĀ-ž'’.\-]*", w):
                return None
        if is_place(seg) or country_code(seg) or seg.lower() in US_STATE_NAMES or re.fullmatch(r"[Xx\s.]+", seg):
            return None                                   # "Xxxxx Xxxxxx" is a template placeholder
        return words
    local = re.sub(r"[^a-z]", " ", out.get("email", "").split("@")[0].lower())
    best, best_score = None, -99
    lm = re.search(r"(?:^|\|)\s*(?:full name|name|naam|navn|voornaam en achternaam)\s*[:\-–]\s*([^|]+)", top_text, re.I)
    if lm and name_words(lm[1].strip()):
        best = name_words(lm[1].strip())
    else:
        for n, it in enumerate([it for it in items[:22] if not it.get("head")][:18]):
            if it["b"]:
                continue
            big = min(8, max(0, (it.get("size", 0) / body - 1) * 10)) if body and it.get("size") else 0
            for k, seg in enumerate(re.split(r"\s*[|•·]\s*", clean_line(it["t"]))):
                words = name_words(seg)
                if not words:
                    continue
                score = 10 - n * 0.6 - k + big + (6 if any(len(w) > 2 and w.lower().strip(".") in local for w in words)
                                                  else 0)
                if score > best_score:
                    best, best_score = words, score
    if best:
        def name_case(w):
            if not (w.isupper() and len(w) > 2):
                return w
            w = "-".join(p.capitalize() for p in w.split("-"))
            w = re.sub(r"^([OD]['’])([a-z])", lambda m: m[1] + m[2].upper(), w)     # O'Connor, D'Souza
            return re.sub(r"^(Ma?c)([a-z]{3,})", lambda m: m[1] + m[2].capitalize(), w)  # McDonald, MacLeod
        words = [name_case(w) for w in best]
        cut = next((i for i in range(1, len(words)) if words[i] in PARTICLES), len(words) - 1)
        if len(words) >= 4 and cut == len(words) - 1 and not re.search(r"\.$", words[-2]):
            cut = len(words) - 2      # 4 names: Spanish/Latin American double surname ("Irene Elizabeth Valle Urriola")
        out["first_name"] = words[0]
        if cut > 1:
            out["middle_name"] = " ".join(words[1:cut])        # "Mads Kristian Jørgensen", "Michael J. Rodriguez"
        out["last_name"] = " ".join(words[cut:])
    name_line = " ".join(best or [])

    # Address
    def set_city(row_or_name, cc=None):
        if isinstance(row_or_name, tuple):
            out["city"], cc = row_or_name[0], cc or row_or_name[3]
        else:
            out["city"] = row_or_name
        if cc:
            out["country"] = country_label(cc)

    addr_lines = []
    for it in top:
        t = clean_line(it["t"])
        lab = re.match(r"\s*(?:home address|address|location|adres|woonplaats|adresse|bopæl|city|town|residence|"
                       r"based in|lives in)\s*[:\-–]\s*(.+)", t, re.I)
        t = lab[1] if lab else t
        t = re.sub(r"^(e-?mail|phone|tel|tlf|mobile|mobil|cell)\s*[:.]?", "", t, flags=re.I)
        for seg in re.split(r"\s*[|•·]\s*|\s{3,}", t):
            seg = seg.strip(" ,.;")
            if seg and collapse_spaced(seg).strip() != name_line and not heading_key(seg):
                addr_lines.append(seg)

    def street_before(n, seg, start):
        """Street part: text before the town on the same line, else the line above if it looks like a street."""
        same = seg[:start].strip(" ,")
        if same:
            return same
        if n and (re.search(STREET, addr_lines[n - 1]) or re.match(r"\d", addr_lines[n - 1])):
            return addr_lines[n - 1]
        return ""

    for n, seg in enumerate(addr_lines):
        up = seg.upper()
        pm = re.search(UK_POSTCODE, up)
        if pm and not re.search(r"\d{5}", seg):
            pc = pm[1]
            out["postcode"] = pc if " " in pc else pc[:-3] + " " + pc[-3:]
            parts = [p.strip() for p in seg[:pm.start()].split(",") if p.strip()]
            prev = [p for p in addr_lines[max(0, n - 3):n] if not re.search(r"@", p) and len(p) < 60]
            if not parts:
                parts = prev                                    # address written over several lines
            elif len(parts) == 1 and prev and re.match(r"\d", prev[-1]):
                parts = prev[-1:] + parts                       # "27 Crookes Park Road" / "Sheffield S10 2QQ"
            if parts:
                out["city"] = parts[-1]
                if len(parts) >= 2:
                    out["address1"] = parts[0]
                if len(parts) >= 3:
                    out["address2"] = ", ".join(parts[1:-1])
                if len(parts) >= 4:
                    out["address2"], out["county"], out["city"] = ", ".join(parts[1:-2]), parts[-1], parts[-2]
            if re.match(UNIT_RE, out.get("address1", ""), re.I) and out.get("address2"):
                out["address1"], out["address2"] = out["address2"], out["address1"]
            out["country"] = "United Kingdom"
            break
        m = re.search(NL_POSTCODE, seg)
        if m and find_city(m[2], "NL"):
            out["postcode"] = m[1][:4] + " " + m[1][-2:].strip()
            set_city(m[2], "NL")
            street = street_before(n, seg, m.start())
            if street:
                split_street(street, out)
            break
        m = re.search(EU_POSTCODE, seg)
        if m:
            town = re.sub(r"\s+[A-ZØ]$", "", m[2])               # "København N" -> "København"
            row = find_city(town)
            if row and row[3] in ("DK", "DE", "NO", "BE", "AT", "CH", "SE", "FI", "FR", "ES", "IT", "PT", "PL"):
                out["postcode"] = m[1]
                set_city(m[2] if row[0] != town else row[0], row[3])
                street = street_before(n, seg, m.start())
                if street:
                    split_street(street, out)
                break
        # US: "Springfield, IL 62704" / "Austin, Texas 78701" / "Brooklyn, NY"
        m = st = None
        for m in re.finditer(r"([A-Z][A-Za-z.'\-]+(?: [A-Z][A-Za-z.'\-]+){0,3}),\s*([A-Z]{2}|[A-Z][a-z]+(?: [A-Z][a-z]+)?)"
                             r"\b\.?(?:\s+(\d{5})(?:-\d{4})?)?", seg):
            st = m[2] if m[2] in US_STATES else US_STATE_NAMES.get(m[2].lower())
            if st and (m[3] or find_city(m[1], "US")):
                break
            st = None
        if m and st:
            out["city"], out["county"], out["country"] = m[1], st, "United States"
            if m[3]:
                out["postcode"] = m[3]
            street = street_before(n, seg, m.start())
            if street:
                split_street(street, out)
            break
    if "city" not in out:
        # no postcode: "12 High Street, Leamington Spa" / "Town, Country" / a lone big town
        for n, seg in enumerate(addr_lines[:25]):
            sm = re.search(STREET, seg)
            if sm:
                rest = [p.strip() for p in seg[sm.end():].split(",") if p.strip()]
                nxt = addr_lines[n + 1] if n + 1 < len(addr_lines) else ""
                cand = rest or [p.strip() for p in nxt.split(",") if p.strip()]
                rows = [(p, find_city(p)) for p in cand]
                rows = [(p, r) for p, r in rows if r]
                if rows:
                    split_street(seg[:sm.end()] if rest else seg, out)
                    set_city(rows[0][1])
                    cc = next((country_code(p) for p in cand if country_code(p)), None)
                    if cc:
                        out["country"] = country_label(cc)
                    break
            if re.search(r"\d", seg) or len(seg.split()) > 7:
                continue
            parts = [p.strip() for p in seg.split(",") if p.strip()]
            cc = country_code(parts[-1]) if parts else None
            if cc and len(parts) >= 2:
                rows = [find_city(p, cc) for p in parts[:-1]]
                rows = [r for r in rows if r]
                if rows:
                    set_city(max(rows, key=lambda r: r[5]), cc)
                else:
                    out["county"], out["country"] = parts[-2], country_label(cc)
                break
            if len(parts) == 1:
                row = find_city(parts[0])
                if row and (row[5] >= 50000 or any(it["sec"] == "personal" for it in top)):
                    set_city(row)
                    break

    # no address country? the phone's country code says where they are (+44 -> UK, +1 -> US/Canada)
    if out.get("phone") and not out.get("country") and phone_cc:
        out["country"] = country_label(phone_cc)

    # Sections
    def sec_lines(*keys):
        return [it for it in items if it["sec"] in keys and not it.get("head")]

    skills = []
    for it in sec_lines("skills"):
        t = re.sub(r"^[\w &/]{2,25}:\s*", "", it["t"])            # "Languages: Python, Go" -> "Python, Go"
        for s in re.split(r"[,;•·|]|\s{2,}", t):
            s = s.strip(" .-–")
            if s and not s.endswith(":") and len(s.split()) <= 8                     and not re.search(r"citizen|licen[cs]e|rijbewijs|kørekort|references|available|sponsorship", s, re.I) and s.lower() not in [x.lower() for x in skills]:
                skills.append(s)
    if skills:
        out["skills"] = ", ".join(skills)[:400].rsplit(",", 1)[0] if len(", ".join(skills)) > 400 else ", ".join(skills)

    has_exp = any(it.get("head") and it["sec"] == "experience" for it in items)
    allowed = {"experience"} if has_exp else {"top", "summary", "personal", "other", "experience"}
    jobs, total_dur = parse_jobs(items, allowed)
    if jobs:
        out["jobs"] = jobs
        cur = next((j for j in jobs if j["end"] == "Present"), jobs[0])
        out["current_title"], out["current_company"] = cur["title"], cur["company"]
        years = [int(y) for j in jobs for y in re.findall(r"(?:19|20)\d{2}", j["start"])]
        if years:
            span = datetime.now().year - min(years)
            if 0 < span < 50:
                out["years_experience"] = str(span)
        elif total_dur:
            out["years_experience"] = str(min(total_dur, 50))

    edu_items = sec_lines("education")
    edu_lines = [it["t"] for it in edu_items] or [ln for ln in lines if len(ln.split()) <= 14]
    education_details(edu_lines, out)

    if re.search(r"full (uk |clean )*driving licen[cs]e|driving licen[cs]e|driver'?s licen[cs]e|clean licen[cs]e|"
                 r"rijbewijs|kørekort|führerschein", flat, re.I):
        out["driving_licence"] = "Yes"
    if re.search(r"right to work in the uk|british (citizen|national)|uk citizen|settled status|u\.?s\.? citizen|"
                 r"eu citizen|permanent resident|green card holder|eligible to work|right to work", flat, re.I):
        out["right_to_work"] = "Yes"
        if not re.search(r"require[sd]? (visa )?sponsorship", flat, re.I):
            out["needs_sponsorship"] = "No"
    m = re.search(r"notice period\W+(\d+\s*(weeks?|months?|days?))", flat, re.I)
    if m:
        out["notice_period"] = m[1]

    return {k: v for k, v in out.items() if v and (k == "jobs" or len(str(v)) < 500)}


def parse_cv(path):
    """Read a CV file. PDFs whose name/email are drawn as shapes (or scanned) are also read with OCR,
    which fills in whatever the text layer was missing."""
    meta = {}
    raw = cv_text(path, meta)
    out = parse_text(raw, meta)
    if Path(path).suffix.lower() == ".pdf" and (len(raw.strip()) < 300 or not out.get("first_name") or not out.get("email")):
        lines = ocr_pdf(path)
        if lines:
            text, ometa = ocr_to_text(lines)
            seen = parse_text(text, ometa)
            if len(raw.strip()) < 300:
                out = seen                                    # scanned CV: OCR is all there is
            else:
                for k, v in seen.items():
                    if k == "jobs":
                        if not out.get("jobs"):
                            out["jobs"] = v
                    elif not out.get(k):
                        out[k] = v
            out["read_with_ocr"] = "yes"
    return out


# ---- LinkedIn: the profile PDF ("Save to PDF") or the data export .zip ("Get a copy of your data")

def _csv_rows(text):
    text = text.lstrip("﻿")
    # some LinkedIn CSVs start with a "Notes:" paragraph before the real header
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines[:8]) if "," in ln and not ln.lower().startswith("notes")), 0)
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(lines[start:])]


def linkedin_place(text, out):
    """'Birmingham, England, United Kingdom' -> city / country."""
    parts = [p.strip() for p in (text or "").split(",") if p.strip()]
    if not parts:
        return
    cc = country_code(parts[-1]) or ("GB" if parts[-1].lower() in ("england", "scotland", "wales") else None)
    row = find_city(parts[0], cc) or find_city(parts[0])
    if row:
        out["city"] = row[0] if _norm(row[0]) == _norm(parts[0]) else parts[0]
        cc = cc or row[3]
    elif len(parts) > 1:
        out["city"] = parts[0]
    if cc:
        out["country"] = country_label(cc)


def linkedin_export(path):
    """Read LinkedIn's data export: Profile.csv, Positions.csv, Education.csv, Skills.csv, Email/Phone files."""
    import zipfile
    files = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.lower().endswith(".csv") and z.getinfo(n).file_size < 5_000_000:
                files[Path(n).name.lower()] = z.read(n).decode("utf-8", "replace")
    if not any(k in files for k in ("profile.csv", "positions.csv")):
        raise ValueError("This zip doesn't look like a LinkedIn data export (no Profile.csv or Positions.csv)")
    out = {}
    prof = (_csv_rows(files["profile.csv"]) or [{}])[0] if "profile.csv" in files else {}
    first = prof.get("first name", "").split()
    if first:
        out["first_name"] = first[0]
        if len(first) > 1:
            out["middle_name"] = " ".join(first[1:])
    if prof.get("last name"):
        out["last_name"] = prof["last name"]
    if prof.get("address"):
        out["address1"] = prof["address"]
    if prof.get("zip code"):
        out["postcode"] = prof["zip code"]
    linkedin_place(prof.get("geo location", ""), out)
    m = re.search(r"https?://[^\]\s,]+", prof.get("websites", ""))
    if m:
        out["website"] = m[0]
    for name in ("email addresses.csv", "email address.csv"):
        rows = _csv_rows(files.get(name, ""))
        if rows:
            best = next((r for r in rows if r.get("primary", "").lower() == "yes"), rows[0])
            out["email"] = best.get("email address", "")
    for name in ("phonenumbers.csv", "phone numbers.csv"):
        rows = _csv_rows(files.get(name, ""))
        if rows and rows[0].get("number"):
            out["phone"] = rows[0]["number"]
    jobs = []
    for r in _csv_rows(files.get("positions.csv", "")):
        if not (r.get("title") or r.get("company name")):
            continue
        jobs.append({"title": r.get("title", ""), "company": r.get("company name", ""), "location": r.get("location", ""),
                     "start": r.get("started on", ""), "end": r.get("finished on", "") or "Present",
                     "description": (r.get("description", "") or "")[:2000]})
    if jobs:
        out["jobs"] = jobs[:20]
        cur = next((j for j in jobs if j["end"] == "Present"), jobs[0])
        out["current_title"], out["current_company"] = cur["title"], cur["company"]
        years = [int(y) for j in jobs for y in re.findall(r"(?:19|20)\d{2}", j["start"])]
        if years and 0 < datetime.now().year - min(years) < 50:
            out["years_experience"] = str(datetime.now().year - min(years))
    edu_lines = []
    for r in _csv_rows(files.get("education.csv", "")):
        edu_lines.append(", ".join(x for x in (r.get("degree name"), r.get("notes"), r.get("school name")) if x))
    if edu_lines:
        education_details(edu_lines, out)
        school = next((r.get("school name") for r in _csv_rows(files.get("education.csv", "")) if r.get("school name")), "")
        if school and not out.get("university"):
            out["university"] = school
    skills = [r.get("name", "") for r in _csv_rows(files.get("skills.csv", "")) if r.get("name")]
    if skills:
        out["skills"] = ", ".join(skills)[:400]
    return {k: v for k, v in out.items() if v}


def linkedin_import(name, b64):
    """A LinkedIn PDF or export .zip -> profile details (nothing is saved here; the app asks add/replace first)."""
    data = base64.b64decode(b64 or "")
    if not data:
        raise ValueError("The file was empty")
    if len(data) > 30 * 1024 * 1024:
        raise ValueError("That file is too big (30 MB max)")
    ext = Path(name or "").suffix.lower()
    if data[:4] == b"%PDF":
        ext = ".pdf"
    elif data[:2] == b"PK":
        ext = ".zip"
    if ext not in (".pdf", ".zip", ".csv"):
        raise ValueError("Use your LinkedIn profile PDF or the data export .zip")
    tmp = DATA_DIR / ("linkedin-import" + ext)
    tmp.write_bytes(data)
    try:
        if ext == ".pdf":
            found = parse_cv(tmp)
            # the PDF's own links: "www.linkedin.com/in/name (LinkedIn)"
            found.pop("website", None) if "linkedin.com" in found.get("website", "") else None
            return found
        if ext == ".csv":                       # just Positions.csv on its own
            import zipfile
            z = DATA_DIR / "linkedin-import.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("Positions.csv", data.decode("utf-8", "replace"))
            try:
                return linkedin_export(z)
            finally:
                z.unlink(missing_ok=True)
        return linkedin_export(tmp)
    finally:
        tmp.unlink(missing_ok=True)


# ---- import from a LinkedIn profile link: LinkedIn only shows profiles to signed-in people, so the app
# opens the link in your own Chrome and the extension reads the page you're looking at and sends it here.
FEEDBACK_EMAIL = "jobslop@proton.me"
li_link = {"url": "", "at": 0.0, "found": None, "error": ""}
LI_LINK_WAIT = 600                      # seconds the app waits for the extension to read the page


def linkedin_profile_url(text):
    """'linkedin.com/in/jane-doe-123?x=1' (with or without https/www) -> 'https://www.linkedin.com/in/jane-doe-123/'."""
    m = re.search(r"(?:https?://)?(?:[\w-]+\.)?linkedin\.com/in/([^/?#\s]+)", text or "", re.I)
    if not m:
        return None
    slug = urllib.parse.unquote(m[1]).strip()
    if not slug or len(slug) > 100 or not re.fullmatch(r"[^\s<>\"'\\]+", slug):
        return None
    return "https://www.linkedin.com/in/" + urllib.parse.quote(slug, safe="-_.~") + "/"


def linkedin_link_status():
    waiting = bool(li_link["url"]) and li_link["found"] is None and not li_link["error"] \
        and time.time() - li_link["at"] < LI_LINK_WAIT
    return {"url": li_link["url"], "waiting": waiting, "found": li_link["found"], "error": li_link["error"]}


def _li_lines(lines):
    out = []
    for ln in lines or []:
        ln = re.sub(r"\s+", " ", str(ln)).strip()
        if ln and not re.fullmatch(r"(?:…|\.\.\.)?\s*(?:see more|show more|see less)", ln, re.I) and (not out or out[-1] != ln):
            out.append(ln[:2000])
    return out[:60]


def _li_is_place(s):
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts or len(s) > 80 or s.endswith("."):
        return False
    if re.fullmatch(r"remote|hybrid|on-site", s, re.I):
        return True
    cc = country_code(parts[-1]) or ("GB" if parts[-1].lower() in ("england", "scotland", "wales", "northern ireland") else None)
    return bool(cc or find_city(parts[0]))


JOB_KIND = re.compile(r"(?:full|part)[- ]time|self-employed|freelance|contract|internship|apprenticeship|seasonal|"
                      r"temporary|permanent|on-site|hybrid|remote", re.I)


def _li_job(lines, company=""):
    """One experience entry from a LinkedIn profile page (its lines of text) -> a work history job."""
    lines = _li_lines(lines)
    if not lines:
        return None
    job = {"title": lines[0], "company": company, "location": "", "start": "", "end": "", "description": ""}
    desc = []
    for ln in lines[1:]:
        d = find_dates(norm_dates(ln))
        if d and d[0] and not job["start"]:
            job["start"], job["end"] = d[0], d[1] or ""
            continue
        head = ln.split(" · ")[0].strip()
        if JOB_KIND.fullmatch(head) or ln.lower().startswith("skills:"):
            continue
        if not job["start"] and not job["company"]:
            job["company"] = head                 # "Rare · Full-time" comes before the dates
            continue
        if job["start"] and not job["location"] and not desc and _li_is_place(head):
            job["location"] = head
            continue
        desc.append(ln)
    job["description"] = "\n".join(desc)[:2000]
    return job


def linkedin_from_page(page):
    """What the extension read on a LinkedIn profile page -> profile details (the app asks add/replace first)."""
    out = {}
    name = re.split(r",|\(|\|", str(page.get("name") or ""))[0].strip()
    parts = name.split()
    if parts:
        out["first_name"] = parts[0]
        if len(parts) > 1:
            out["last_name"] = " ".join(parts[1:])
    for ln in _li_lines(page.get("top")):
        if ln != name and _li_is_place(ln) and not JOB_KIND.fullmatch(ln):
            linkedin_place(ln, out)
            break
    jobs = []
    for e in page.get("experience") or []:
        if not isinstance(e, dict):
            continue
        roles = [r for r in e.get("roles") or [] if any(find_dates(norm_dates(x)) for x in _li_lines(r))]
        if roles:                                  # several roles at one company
            head = _li_lines(e.get("lines"))
            place = next((x.split(" · ")[0] for x in head[1:] if _li_is_place(x.split(" · ")[0])), "")
            for r in roles:
                j = _li_job(r, head[0] if head else "")
                if j:
                    j["location"] = j["location"] or place
                    jobs.append(j)
        else:                                      # one role; its description and skills sit in parts inside it
            extra = [x for r in e.get("roles") or [] for x in _li_lines(r)]
            j = _li_job(list(e.get("lines") or []) + extra)
            if j:
                jobs.append(j)
    if jobs:
        out["jobs"] = jobs[:20]
        cur = next((j for j in jobs if j["end"] == "Present"), jobs[0])
        out["current_title"], out["current_company"] = cur["title"], cur["company"]
        years = [int(y) for j in jobs for y in re.findall(r"(?:19|20)\d{2}", j["start"])]
        if years and 0 < datetime.now().year - min(years) < 50:
            out["years_experience"] = str(datetime.now().year - min(years))
    edu = [_li_lines(e) for e in page.get("education") or [] if isinstance(e, list)]
    edu = [e for e in edu if e]
    if edu:
        first = edu[0]
        degree = first[1] if len(first) > 1 and not find_dates(norm_dates(first[1])) else ""
        education_details([", ".join(x for x in (degree, first[0]) if x)], out)
        out.setdefault("university", first[0])
    skills = []
    for s in page.get("skills") or []:
        s = re.sub(r"\s+", " ", str(s)).strip()
        if s and len(s) < 60 and s.lower() not in (x.lower() for x in skills):
            skills.append(s)
    if skills:
        out["skills"] = ", ".join(skills)[:400]
    url = linkedin_profile_url(page.get("url") or "")
    if url:
        out["linkedin"] = url
    return {k: v for k, v in out.items() if v}


def pairing_code():
    s = load_settings()
    if s.get("ext_code"):
        return s["ext_code"]

    def change(s):
        if not s.get("ext_code"):
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            s["ext_code"] = code[:4] + "-" + code[4:]
    return update_settings(change)["ext_code"]


def active_job():
    a = state["active"]
    if a and time.time() - a["t"] < ACTIVE_MINUTES * 60:
        return a["job"]
    return None


def render_letter(template, profile, job):
    full = " ".join(x for x in (profile.get("first_name"), profile.get("last_name")) if x)
    repl = {"company": (job or {}).get("company") or "your company",
            "title": (job or {}).get("title") or "this role",
            "first_name": profile.get("first_name", ""), "last_name": profile.get("last_name", ""),
            "full_name": full}
    return re.sub(r"\{(\w+)\}", lambda m: repl.get(m[1], m[0]), template or "")


def extension_payload():
    p = load_profile()
    jobs = p.get("jobs") or []
    if jobs:   # most recent job doubles as "current job" for forms that ask once
        p["current_title"] = p.get("current_title") or jobs[0].get("title", "")
        p["current_company"] = p.get("current_company") or jobs[0].get("company", "")
    job = active_job()
    cv = cv_file()
    return {"profile": p,
            "full_name": " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x),
            "cover_letter": render_letter(p.get("cover_letter_template", ""), p, job),
            "active": {"title": job["title"], "company": job["company"], "url": job["url"]} if job else None,
            "cv_name": cv.name if cv else ""}


def install_extension():
    """Copy the bundled Chrome extension to a fixed folder the user can load in Chrome."""
    src = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "chrome-extension"
    try:
        if src.exists():
            shutil.copytree(src, EXT_DIR, dirs_exist_ok=True)
        # the extension reads this to connect by itself (this folder is only in your own user profile)
        (EXT_DIR / "pairing.json").write_text(json.dumps({"code": pairing_code(), "port": APP_PORT}), encoding="utf-8")
    except Exception:
        pass
    return str(EXT_DIR)


def open_in_chrome(url):
    if IS_WIN:
        candidates = [Path(os.environ.get(v, "")) / "Google" / "Chrome" / "Application" / "chrome.exe"
                      for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    elif IS_MAC:
        candidates = [Path(p) / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome"
                      for p in ("/Applications", str(Path.home() / "Applications"))]
    else:
        candidates = [Path(p) for p in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium")]
    for c in candidates:
        if c.is_file():
            subprocess.Popen([str(c), url])
            return True
    webbrowser.open(url)
    return False


# ---------------------------------------------------------------- updates (GitHub Releases)
# Each release on GitHub carries jobslop.exe plus jobslop.exe.sha256 (its checksum). The app checks the
# newest release now and then, and on Windows can download it, check it against the checksum, then close,
# swap the .exe and start again. Nothing is installed without the user pressing "Update".
FROZEN = bool(getattr(sys, "frozen", False))
UPDATE_DIR = DATA_DIR / "update"
UPDATE_ASSET = "jobslop.exe" if IS_WIN else "jobslop-Mac.zip" if IS_MAC else ""
UPDATE_CHECK_EVERY = 12 * 3600
update_state = {"done": 0, "total": 0, "busy": False, "ready": "", "error": "", "updated_from": ""}


def version_tuple(v):
    nums = [int(n) for n in re.findall(r"\d+", str(v or ""))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(a, b):
    return version_tuple(a) > version_tuple(b)


def release_info(rel):
    """GitHub's 'latest release' answer -> what the app needs (only github.com download links are kept)."""
    assets = {a.get("name"): a for a in rel.get("assets") or [] if isinstance(a, dict)}
    gh = lambda u: u if str(u or "").startswith("https://github.com/") else ""
    exe, sha = assets.get(UPDATE_ASSET) or {}, assets.get(UPDATE_ASSET + ".sha256") or {}
    return {"version": str(rel.get("tag_name") or "").strip().lstrip("vV")[:20], "notes": str(rel.get("body") or "")[:5000],
            "page": gh(rel.get("html_url")), "asset_url": gh(exe.get("browser_download_url")),
            "size": int(exe.get("size") or 0), "sha256_url": gh(sha.get("browser_download_url")),
            "published": str(rel.get("published_at") or "")[:10]}


def check_for_update(force=False):
    """Newest release vs this version. GitHub is asked at most every 12 hours unless you press Check."""
    s = load_settings()
    out = {"enabled": bool(UPDATE_REPO), "current": APP_VERSION, "off": bool(s.get("updates_off")),
           "updated_from": update_state["updated_from"]}
    if not UPDATE_REPO or out["off"]:          # "Don't receive any updates": GitHub is never asked
        return out
    cache = s.get("update_check") or {}
    if force or time.time() - cache.get("t", 0) > UPDATE_CHECK_EVERY or not cache.get("info"):
        rel = get_json(f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest", timeout=15,
                       headers={"Accept": "application/vnd.github+json", "User-Agent": f"jobslop/{APP_VERSION}"})
        cache = {"t": time.time(), "info": release_info(rel)}
        update_settings(lambda st: st.__setitem__("update_check", cache))
    info = cache["info"]
    out.update(info, available=bool(info["version"]) and is_newer(info["version"], APP_VERSION),
               can_install=FROZEN and IS_WIN and bool(info["asset_url"] and info["sha256_url"]),
               skipped=s.get("update_skip") == info["version"])
    return out


def _download(url, max_bytes, on_chunk=None):
    req = urllib.request.Request(url, headers={"User-Agent": f"jobslop/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                return
            max_bytes -= len(chunk)
            if max_bytes < 0:
                raise ValueError("The download is bigger than expected - stopped")
            if on_chunk:
                on_chunk(chunk)
            yield chunk


def download_update():
    """Fetch the new jobslop.exe into the data folder and check it against the release's checksum."""
    st = update_state
    st.update(busy=True, done=0, total=0, ready="", error="")
    try:
        (UPDATE_DIR / "jobslop-new.exe").unlink(missing_ok=True)   # never install an older download by mistake
        info = check_for_update()
        if not (info.get("available") and info.get("can_install")):
            raise ValueError("There's no update that can be installed automatically")
        st["total"] = info["size"]
        want = b"".join(_download(info["sha256_url"], 10_000)).decode("ascii", "replace").split()
        want = want[0].lower() if want else ""
        if not re.fullmatch(r"[0-9a-f]{64}", want):
            raise ValueError("The update's checksum file is broken - nothing was changed")
        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        part, h, final = UPDATE_DIR / "jobslop-new.exe.part", hashlib.sha256(), UPDATE_DIR / "jobslop-new.exe"
        with open(part, "wb") as f:
            for chunk in _download(info["asset_url"], max(info["size"], 1) + 1024,
                                   lambda c: st.__setitem__("done", st["done"] + len(c))):
                f.write(chunk)
                h.update(chunk)
        if h.hexdigest() != want:
            part.unlink(missing_ok=True)
            raise ValueError("The download didn't match its checksum - nothing was changed. Try again later.")
        os.replace(part, final)
        st["ready"] = str(final)
    except Exception as e:
        st["error"] = str(e)[:200] or "The download failed"
    finally:
        st["busy"] = False


def swap_in_update(new_exe, target):
    """Put the new .exe where the running one is. Windows won't let a running program be overwritten or
    deleted, but it can be renamed - so the running copy steps aside as '.old' (the new version deletes it
    once this one has closed). If anything fails, the original is put back and nothing changes."""
    target, new_exe = Path(target), Path(new_exe)
    old = Path(str(target) + ".old")
    try:
        old.unlink(missing_ok=True)                 # left over from an earlier update
    except OSError:
        raise ValueError("An older update is still being tidied up - restart jobslop and try again")
    try:
        os.replace(target, old)
    except OSError:
        raise ValueError("jobslop can't replace itself in this folder (no permission). "
                         "Download the new version from the release page instead.")
    try:
        shutil.move(str(new_exe), str(target))      # a move, or copy + delete when it's on another drive
    except Exception:
        os.replace(old, target)
        raise ValueError("Couldn't put the new version in place - nothing was changed")


def launch_fresh(exe):
    """Start a separate copy of jobslop. A self-unpacking app passes hidden settings to programs it starts;
    a new copy of itself must ignore them, or it can't find its own files and never opens."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI_", "_MEI"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen([str(exe)], env=env, cwd=str(Path(exe).parent), creationflags=flags, close_fds=True)


def install_update():
    """Swap in the downloaded version, start it, and close this one."""
    new = Path(update_state["ready"] or "")
    if not (FROZEN and IS_WIN and new.is_file()):
        raise ValueError("Download the update first")
    target = Path(sys.executable)
    swap_in_update(new, target)
    update_state["ready"] = ""
    launch_fresh(target)
    threading.Timer(0.8, lambda: os._exit(0)).start()    # time to answer the screen, then close


def after_update_cleanup():
    """On start: remember which version ran last (to say "Updated to ..."), tidy the update leftovers."""
    try:
        prev = load_settings().get("last_version", "")
        update_state["updated_from"] = prev if prev and prev != APP_VERSION else ""
        if prev != APP_VERSION:
            update_settings(lambda s: s.__setitem__("last_version", APP_VERSION))
    except Exception:
        pass
    old = Path(str(sys.executable) + ".old")
    if FROZEN and old.exists():
        # just updated: the old version may still be closing (Windows won't delete a program that's running)
        for _ in range(40):
            try:
                old.unlink()
                break
            except OSError:
                time.sleep(0.25)
    for f in ("jobslop-new.exe", "jobslop-new.exe.part"):
        try:
            (UPDATE_DIR / f).unlink(missing_ok=True)
        except OSError:
            pass                                    # tidying up must never stop jobslop from starting


# ---- exchange rates (per 1 US dollar), refreshed twice a day, with offline fallback
RATES_FILE = DATA_DIR / "rates.json"
FALLBACK_RATES = {"USD": 1, "GBP": 0.75, "EUR": 0.9, "CAD": 1.38, "AUD": 1.52, "NZD": 1.66, "INR": 95, "JPY": 157,
                  "CHF": 0.8, "SEK": 10.3, "NOK": 10.6, "DKK": 6.7, "PLN": 3.8, "CZK": 22.5, "HUF": 355, "RON": 4.5,
                  "ZAR": 17.5, "SGD": 1.3, "HKD": 7.8, "AED": 3.67, "SAR": 3.75, "QAR": 3.64, "BRL": 5.5, "MXN": 18.5,
                  "TRY": 41, "ILS": 3.6, "MYR": 4.3, "PHP": 57, "IDR": 16000, "THB": 33, "VND": 26000, "KRW": 1380,
                  "UAH": 41, "EGP": 49, "NGN": 1500, "ARS": 1300, "CLP": 940, "COP": 4000}
rates_lock = threading.Lock()


def get_rates():
    with rates_lock:
        try:
            cached = json.loads(RATES_FILE.read_text(encoding="utf-8"))
            if time.time() - cached["t"] < 12 * 3600:
                return cached
        except Exception:
            cached = None
        for url, key in (("https://open.er-api.com/v6/latest/USD", "rates"),
                         ("https://api.frankfurter.app/latest?from=USD", "rates")):
            try:
                rates = get_json(url, timeout=10)[key]
                rates["USD"] = 1
                data = {"t": time.time(), "rates": rates, "source": url.split("/")[2],
                        "updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
                RATES_FILE.write_text(json.dumps(data), encoding="utf-8")
                return data
            except Exception:
                continue
        return cached or {"t": 0, "rates": FALLBACK_RATES, "source": "built-in (offline)", "updated": "approximate"}


# ---- place lookups for the map (OpenStreetMap Nominatim: max 1 request a second, cached)
geo_lock = threading.Lock()
geo_state = {"last": 0.0, "cache": {}}


def nominatim(path, params):
    key = path + json.dumps(params, sort_keys=True)
    if key in geo_state["cache"]:
        return geo_state["cache"][key]
    with geo_lock:
        gap = 1.1 - (time.time() - geo_state["last"])
        if gap > 0:
            time.sleep(gap)
        geo_state["last"] = time.time()
        url = f"https://nominatim.openstreetmap.org/{path}?" + urllib.parse.urlencode({**params, "format": "jsonv2",
                                                                                         "addressdetails": 1})
        data = get_json(url, timeout=15, headers={"User-Agent": "JobFinder personal desktop app", "Accept-Language": "en"})
    geo_state["cache"][key] = data
    return data


def place_summary(item):
    a = item.get("address", {}) if item else {}
    town = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("county") or a.get("state") or ""
    return {"lat": float(item["lat"]), "lon": float(item["lon"]), "town": town,
            "country_code": (a.get("country_code") or "").upper(), "country": a.get("country", ""),
            "label": ", ".join(x for x in (town, a.get("country")) if x)}


def export_csv(rows, cols, name):
    folder = Path.home() / "Downloads"
    folder = folder if folder.exists() else Path.home()
    path = folder / f"{name}-{datetime.now().strftime('%Y-%m-%d_%H%M')}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])
    return str(path)


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
        if u.path == "/api/linkedin/link":
            return self.send(json.dumps(linkedin_link_status()))
        if u.path == "/api/update":
            try:
                return self.send(json.dumps(check_for_update()))
            except Exception as e:
                return self.send(json.dumps({"enabled": bool(UPDATE_REPO), "current": APP_VERSION,
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
                found = nominatim("search", {"q": q, "limit": 1})
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
        elif u.path == "/api/studios":
            try:
                lat, lon = float(p["lat"]), float(p["lon"])
                self.send(json.dumps({"studios": studios_near(lat, lon, float(p.get("km", 40)),
                                                              indie_only=p.get("kind") == "indie"),
                                      "total": len(studios()), "source": "Game Dev Map + Wikipedia"}))
            except (KeyError, ValueError):
                self.send('{"studios":[],"total":0}')
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
            srcs = p.get("sources", ",".join(SOURCES)).split(",")
            fresh = p.get("fresh", "0") == "1"
            any_job = p.get("any", "0") == "1"
            if not q.strip() and not any_job:
                return self.send(json.dumps({"results": [], "status": {}}))
            self.send(json.dumps(search("" if any_job else q, srcs, opts, fresh)))
        elif u.path == "/api/saved":
            self.send(json.dumps(load_saved()))
        elif u.path == "/api/settings":
            self.send(json.dumps(public_settings()))
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
            save_settings(body)
            self.send(json.dumps(public_settings()))
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
                if IS_WIN:
                    os.startfile(target)
                else:
                    webbrowser.open(target)
            elif target and Path(target).exists():
                open_path(Path(target).parent)
            self.send("{}")
        else:
            self.send('{"error":"not found"}', code=404)


def load_page():
    """The app's screen lives in ui.html next to this file (bundled inside the .exe)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return (base / "ui.html").read_text(encoding="utf-8")


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


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    after_update_cleanup()
    install_extension()
    pairing_code()
    arg_port = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--port=")), None)
    port = int(arg_port or os.environ.get("JOBFINDER_PORT") or APP_PORT)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        # Port taken: most likely jobslop is already open, so just show another window onto it
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
                page = r.read(3000)
                already = b"jobslop" in page or b"Job Finder" in page   # older versions were called Job Finder
        except Exception:
            already = False
        if not already:
            port = free_port()   # something else has the port; the extension won't connect this time
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        else:
            server = None
    state["port"] = port
    if server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        if phone_settings().get("enabled") and "--no-phone" not in sys.argv:
            start_phone_server()                       # phone access was left switched on
    url = f"http://127.0.0.1:{port}"

    if "--browser" not in sys.argv:
        try:
            import webview  # pywebview: gives the app its own window
            webview.create_window("jobslop", url, width=1200, height=850, min_size=(420, 500))
            icon = RES_DIR / "jf.ico"            # same jF icon as the .exe file
            webview.start(private_mode=False, storage_path=str(DATA_DIR / "window"),
                          icon=str(icon) if icon.exists() else None)
            return
        except Exception as e:
            print("Couldn't open app window, using browser instead:", e)

    print(f"jobslop is running at {url}\nKeep this window open. Press Ctrl+C to stop.")
    if "--no-open" not in sys.argv:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
