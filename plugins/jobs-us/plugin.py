"""United States: Job boards for the US: Jobs2Careers (a large job search) and USAJOBS (government jobs, needs a free key)."""

import json
import urllib.parse
import urllib.request

api = None                                     # set by register()
COMMON = {"group": "country", "country_native": True, "location_aware": True}


def register(_api):
    global api
    api = _api
    api.add_board("ZipRecruiter", src_ziprecruiter, "ZipRecruiter, searched free with JobSpy", countries={"US", "CA"},
                  native_types=True, cache_seconds=3 * 3600, **COMMON)
    api.add_board("Jobs2Careers", src_jobs2careers, "Large US job search", countries={"US"}, **COMMON)
    api.add_board("USAJOBS", src_usajobs, "US government jobs", countries={"US"}, needs=("usajobs_key", "usajobs_email"), **COMMON)


def _page(url, timeout=25):
    req = urllib.request.Request(url, headers=api.http.BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def src_jobs2careers(q, o):
    """Jobs2Careers - large US job search (reads the data embedded in its results page)."""
    if o["country"] != "US":
        raise api.jobs.NotHere("US only")
    loc = ""
    if not api.geo.is_country_name(o["where"], "US"):
        town = api.geo.place_town(o["where"], "US")
        loc = f"{town['name']}, {town['region']}" if town else o["where"]          # "Austin, TX"
    out = []
    for page in (1, 2, 3):
        params = {"q": q, "l": loc}
        if page > 1:
            params["p"] = page
        h = _page("https://www.jobs2careers.com/search/results?" + urllib.parse.urlencode(params))
        i = h.find('"jobAds":{"byId":')
        if i < 0:
            break
        ads = json.JSONDecoder().raw_decode(h, i + len('"jobAds":'))[0].get("byId", {})
        before = len(out)

        def items(x):
            return list(x.values()) if isinstance(x, dict) else (x or [])          # lists arrive as {"0": .., "1": ..}
        for a in ads.values():
            if a.get("adType") not in (None, "job"):
                continue
            sd = items(a.get("salaryDetails"))
            sal = (sd[0].get("label") if sd and isinstance(sd[0], dict) else "") or a.get("compensation") or ""
            types = ", ".join(w.get("label", "") for w in items(a.get("workTypeDetails")) if isinstance(w, dict))
            remote = (a.get("workLocation") or "") == "remote"
            j = api.jobs.make("Jobs2Careers", a.get("title"), a.get("companyName"), a.get("link"),
                              ("Remote · " if remote else "") + (a.get("cityState") or ""),
                              api.text.to_date(a.get("datePosted")), sal, types, [a.get("primaryMajorCategory") or ""],
                              a.get("description"), remote=remote)
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
        raise api.jobs.NotHere("US only")
    key, email = api.setting("usajobs_key"), api.setting("usajobs_email")
    if not (key and email):
        raise api.jobs.NeedsKey("add a free key in Settings")
    params = {"Keyword": q, "ResultsPerPage": 100}
    if not api.geo.is_country_name(o["where"], "US"):
        params.update(LocationName=o["where"], Radius=o["miles"])
    if o["posted"]:
        params["DatePosted"] = o["posted"]
    d = api.http.get_json("https://data.usajobs.gov/api/search?" + urllib.parse.urlencode(params),
                          headers={"Host": "data.usajobs.gov", "User-Agent": email, "Authorization-Key": key})
    out = []
    for item in (d.get("SearchResult") or {}).get("SearchResultItems", []):
        m = item.get("MatchedObjectDescriptor", {})
        pay = (m.get("PositionRemuneration") or [{}])[0]
        per = {"PA": "", "PH": " / hour", "PD": " / day", "PW": " / week", "PM": " / month"}.get(pay.get("RateIntervalCode"), "")
        sal = api.text.money(pay.get("MinimumRange"), pay.get("MaximumRange"), "USD") + (per if pay.get("MinimumRange") else "")
        locs = m.get("PositionLocation") or [{}]
        j = api.jobs.make("USAJOBS", m.get("PositionTitle"), m.get("OrganizationName"), m.get("PositionURI"),
                          m.get("PositionLocationDisplay"), api.text.to_date(m.get("PublicationStartDate")), sal,
                          ", ".join(t.get("Name", "") for t in m.get("PositionSchedule") or []), [],
                          ((m.get("UserArea") or {}).get("Details") or {}).get("JobSummary", ""), remote=False)
        if locs[0].get("Latitude"):
            j["lat"], j["lon"] = locs[0]["Latitude"], locs[0]["Longitude"]
        out.append(j)
    return out


def src_ziprecruiter(q, o):
    """ZipRecruiter - big US/Canada board, searched with JobSpy (it turns away connections from outside)."""
    if o["country"] not in ("US", "CA"):
        raise api.jobs.NotHere("US & Canada only")
    return api.jobs.jobspy("zip_recruiter", q, o, source="ZipRecruiter")
