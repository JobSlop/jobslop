"""What "Where?" means: a town, postcode or full address."""

import json
import re
import threading
import urllib.parse

from jobslop import net
from jobslop.config import DATA_DIR
from jobslop.geo import osm
from jobslop.geo.cities import _norm, code_for_country_text, find_city, km_between, nearest_city
from jobslop.geo.countries import COUNTRIES, US_STATE_NAMES, US_STATES, country_info, is_country_name
from jobslop.geo.osm import place_summary

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
            d = net.get_json(("https://api.postcodes.io/postcodes/" if full else "https://api.postcodes.io/outcodes/")
                         + urllib.parse.quote(compact), timeout=8)
            r = d.get("result") or {}
            if r.get("latitude") is not None:
                point = (r["latitude"], r["longitude"])
        else:
            found = osm.nominatim("search", {"postalcode": pc, "countrycodes": cc.lower(), "limit": 1})
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
            hits = osm.nominatim("search", {"q": ", ".join(parts), "countrycodes": cc.lower(), "limit": 1})
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
