"""Place lookups for the map (OpenStreetMap Nominatim: max 1 request a second, cached)."""

import json
import threading
import time
import urllib.parse

from jobslop import net

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
        data = net.get_json(url, timeout=15, headers={"User-Agent": "JobFinder personal desktop app", "Accept-Language": "en"})
    geo_state["cache"][key] = data
    return data


def place_summary(item):
    a = item.get("address", {}) if item else {}
    town = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("county") or a.get("state") or ""
    return {"lat": float(item["lat"]), "lon": float(item["lon"]), "town": town,
            "country_code": (a.get("country_code") or "").upper(), "country": a.get("country", ""),
            "label": ", ".join(x for x in (town, a.get("country")) if x)}
