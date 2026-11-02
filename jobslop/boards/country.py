"""Country boards: Jobindex (DK), Jobbird (NL), Jobs2Careers & USAJOBS (US), ZipRecruiter UK."""

import html
import json
import re
import urllib.parse
import urllib.request

from jobslop import net
from jobslop.boards.base import NeedsKey, NotHere, job, km_radius
from jobslop.geo.cities import geocode_text
from jobslop.geo.countries import is_country_name
from jobslop.net import BROWSER_UA
from jobslop.settings import load_settings
from jobslop.text import money, rel_date, short_date, strip_html, to_date


def src_jobindex(q, o):
    """Jobindex.dk - Denmark's biggest job board (open JSON search, includes exact coordinates)."""
    if o["country"] != "DK":
        raise NotHere("Denmark only")
    out = []
    for page in (1, 2):
        params = {"q": q, "page": page}
        if not is_country_name(o["where"], "DK"):
            params.update(address=o["where"], radius=km_radius(o))
        d = net.get_json("https://www.jobindex.dk/api/jobsearch/v3/?" + urllib.parse.urlencode(params), headers=BROWSER_UA)
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
    d = net.get_json("https://data.usajobs.gov/api/search?" + urllib.parse.urlencode(params),
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


def src_ziprecruiter_uk(q, o):
    """ZipRecruiter UK (ziprecruiter.co.uk) - reads the public search page."""
    if o["country"] != "GB":
        raise NotHere("UK only")
    out = []
    for page in (1, 2, 3):
        params = {"q": q, "page": page}
        if not is_country_name(o["where"], "GB"):
            params.update(l=o["where"], d=o["miles"])
        h = net.fetch_html("https://www.ziprecruiter.co.uk/jobs/search?" + urllib.parse.urlencode(params))
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
