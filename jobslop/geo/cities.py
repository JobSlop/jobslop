"""Offline towns (GeoNames, CC BY 4.0): ~70,000 towns with coordinates for the map and job distances."""

import gzip
import math
import re
import threading

from jobslop.config import RES_DIR
from jobslop.geo.countries import COUNTRIES, COUNTRY_ALIASES, country_info

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


def tail_place(text, cc):
    """Find a town at the end of a text, e.g. '...to d West Sussex, Horsham' -> 'Horsham' (offline towns)."""
    parts = [p.strip() for p in text[-90:].split(",") if p.strip()]
    for p in reversed(parts[-3:]):
        words = p.split()
        for k in (3, 2, 1):
            if len(words) >= k and find_city(" ".join(words[-k:]), cc):
                return " ".join(words[-k:])
    return ""
