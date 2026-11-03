"""United Kingdom: Job boards for the UK: Reed.co.uk, one of the biggest (needs a free API key)."""

import base64
import html
import re
import urllib.parse

api = None                                     # set by register()
COMMON = {"group": "country", "country_native": True, "location_aware": True}


def register(_api):
    global api
    api = _api
    api.add_board("Reed", src_reed, "Big UK job board (needs a free key)", countries={"GB"}, needs=("reed_key",), **COMMON)
    api.add_board("ZipRecruiter UK", src_ziprecruiter_uk, "ZipRecruiter's UK site", countries={"GB"}, **COMMON)


def src_reed(q, o):
    if o["country"] != "GB":
        raise api.jobs.NotHere("UK only")
    key = api.setting("reed_key")
    if not key:
        raise api.jobs.NeedsKey("add a free key in Settings")
    auth = {"Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()}
    out = []
    for skip in (0, 100):
        params = {"keywords": q, "resultsToTake": 100, "resultsToSkip": skip}
        if not api.geo.is_country_name(o["where"], "GB"):
            params.update(locationName=o["where"], distanceFromLocation=o["miles"])
        if o["salary_min"]:
            params["minimumSalary"] = o["salary_min"]
        jt = {"fulltime": "fullTime", "parttime": "partTime", "contract": "contract", "internship": "temp"}.get(o["jtype"])
        if jt:
            params[jt] = "true"
        d = api.http.get_json("https://www.reed.co.uk/api/1.0/search?" + urllib.parse.urlencode(params), headers=auth)
        res = d.get("results", [])
        for j in res:
            out.append(api.jobs.make("Reed", j.get("jobTitle"), j.get("employerName"), j.get("jobUrl"),
                                     j.get("locationName"), api.text.to_date(j.get("date")),
                                     api.text.money(j.get("minimumSalary"), j.get("maximumSalary"), j.get("currency") or "GBP"),
                                     "", [], j.get("jobDescription"), remote=False))
        if len(res) < 100:
            break
    return out


def src_ziprecruiter_uk(q, o):
    """ZipRecruiter UK (ziprecruiter.co.uk) - reads the public search page."""
    if o["country"] != "GB":
        raise api.jobs.NotHere("UK only")
    strip = api.text.strip_html
    out = []
    for page in (1, 2, 3):
        params = {"q": q, "page": page}
        if not api.geo.is_country_name(o["where"], "GB"):
            params.update(l=o["where"], d=o["miles"])
        h = api.http.get_text("https://www.ziprecruiter.co.uk/jobs/search?" + urllib.parse.urlencode(params))
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
            out.append(api.jobs.make("ZipRecruiter UK", link[2], company[1] if company else "", html.unescape(link[1]),
                                     loc[1] if loc else "", api.text.short_date(strip(date[1])) if date else "",
                                     strip(sal[1]) if sal else "", "", [], desc[1] if desc else "", remote=False))
        if len(cards) < 20:
            break
    return out
