"""Game development: Work With Indies job board and game studios on the map."""

import re

from .studios import Studios

api = None                                     # set by register()
studios = None


def register(_api):
    global api, studios
    api = _api
    studios = Studios(api)
    api.add_board("WorkWithIndies", src_workwithindies, "Indie games studio jobs worldwide")
    api.add_endpoint("studios", studios_endpoint)


def studios_endpoint(params, body):
    """Studios around a point (?lat=&lon=) or a town (?town=&country=), within ?km=, ?kind=all|indie"""
    place = None
    try:
        km = max(1.0, min(500.0, float(params.get("km", 40))))
        if params.get("lat") is not None or not params.get("town"):
            lat, lon = float(params["lat"]), float(params["lon"])
        else:
            place = api.geo.place_town(params["town"], api.geo.country_code(params.get("country", "")))
            if not place:
                return {"studios": [], "total": 0, "error": f"Couldn't find {params['town'][:60]}"}
            lat, lon = place["lat"], place["lon"]
    except (KeyError, ValueError):
        return {"studios": [], "total": 0}
    return {"studios": studios.near(lat, lon, km, indie_only=params.get("kind") == "indie"),
            "total": len(studios.all()), "source": "Game Dev Map + Wikipedia",
            "place": place["name"] if place else ""}


def src_workwithindies(q, o):
    """Work With Indies - indie games studio jobs worldwide (reads the public job list)."""
    h = api.http.get_text("https://www.workwithindies.com/")
    strip = api.text.strip_html
    out = []
    for m in re.finditer(r'<a[^>]*href="(/careers/[^"]+)"[^>]*class="job-card[^"]*"[^>]*>(.*?)</a>', h, re.S):
        card = m[2]
        company = re.search(r'job-card-text bold">(.*?)</div>', card, re.S)
        title = re.search(r'text-block-28">(.*?)</div>', card, re.S)
        mobile = re.findall(r'job-card-text-smol">(.*?)</div>', card, re.S)
        location = strip(mobile[-1]) if mobile else ""
        if not location or location == "|":
            bolds = re.findall(r'job-card-text bold">(.*?)</div>', card, re.S)
            location = strip(bolds[-1]) if len(bolds) > 1 else ""
        remote = bool(re.search(r"remote|anywhere", location, re.I))
        out.append(api.jobs.make("WorkWithIndies", title[1] if title else "", company[1] if company else "",
                                 "https://www.workwithindies.com" + m[1],
                                 ("Remote · " if remote and "remote" not in location.lower() else "") + location,
                                 "", "", "", ["games"], "", remote=remote))
    return out
