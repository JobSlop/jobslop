"""Denmark: Job boards for Denmark: Jobindex.dk, the country's biggest. No key needed."""

import urllib.parse

api = None                                     # set by register()
COMMON = {"group": "country", "country_native": True, "location_aware": True}


def register(_api):
    global api
    api = _api
    api.add_board("Jobindex", src_jobindex, "Denmark's biggest job board", countries={"DK"}, **COMMON)


def src_jobindex(q, o):
    """Jobindex.dk - Denmark's biggest job board (open JSON search, includes exact coordinates)."""
    if o["country"] != "DK":
        raise api.jobs.NotHere("Denmark only")
    out = []
    for page in (1, 2):
        params = {"q": q, "page": page}
        if not api.geo.is_country_name(o["where"], "DK"):
            params.update(address=o["where"], radius=api.jobs.km_radius(o))
        d = api.http.get_json("https://www.jobindex.dk/api/jobsearch/v3/?" + urllib.parse.urlencode(params),
                              headers=api.http.BROWSER_HEADERS)
        for r in d.get("results", []):
            addr = (r.get("addresses") or [{}])[0]
            coords = addr.get("coordinates") or {}
            sal = r.get("salary")
            j = api.jobs.make("Jobindex", r.get("headline"), r.get("companytext") or (r.get("company") or {}).get("name"),
                              r.get("share_url") or r.get("url"), r.get("area") or addr.get("city"),
                              api.text.to_date(r.get("firstdate")), sal if isinstance(sal, str) else "", "", [], "",
                              remote=bool(r.get("home_workplace")))
            if coords.get("latitude"):
                j["lat"], j["lon"] = coords["latitude"], coords["longitude"]
            out.append(j)
        if page >= (d.get("total_pages") or 1):
            break
    return out
