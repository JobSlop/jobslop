"""Netherlands: Job boards for the Netherlands: Jobbird.com. No key needed."""

import re
import urllib.parse
import urllib.request

api = None                                     # set by register()
COMMON = {"group": "country", "country_native": True, "location_aware": True}


def register(_api):
    global api
    api = _api
    api.add_board("Jobbird", src_jobbird, "Dutch job board", countries={"NL"}, **COMMON)


def _page(url, timeout=25):
    req = urllib.request.Request(url, headers=api.http.BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def dutch_date(text):
    """'Nieuw' / 'gisteren' / '3 dagen geleden' -> YYYY-MM-DD."""
    s = (text or "").lower()
    if any(w in s for w in ("nieuw", "vandaag", "uur", "minu")):
        return api.text.rel_date("today")
    if "gisteren" in s:
        return api.text.rel_date("1 day ago")
    m = re.search(r"(\d+)\s*(dag|week|weken|maand)", s)
    if m:
        unit = {"dag": "day", "week": "week", "weken": "week", "maand": "month"}[m[2]]
        return api.text.rel_date(f"{m[1]} {unit} ago")
    return ""


def src_jobbird(q, o):
    """Jobbird.com - Dutch job board (reads the public search page)."""
    if o["country"] != "NL":
        raise api.jobs.NotHere("Netherlands only")
    out = []
    for page in (1, 2):
        params = {"s": q, "rad": api.jobs.km_radius(o), "ot": "date", "p": page}
        if not api.geo.is_country_name(o["where"], "NL"):
            params["l"] = o["where"]
        h = _page("https://www.jobbird.com/nl/vacature?" + urllib.parse.urlencode(params), timeout=20)
        links = list(re.finditer(r'<a href="(https://www\.jobbird\.com/nl/vacature/[^"]+)"[^>]*'
                                 r'class="job-search__result-list__result__title">(.*?)</a>', h, re.S))
        for i, m in enumerate(links):
            card = h[m.end(): links[i + 1].start() if i + 1 < len(links) else m.end() + 4000]

            def grab(cls, card=card):
                found = re.search(cls + r'[^>]*>(.*?)</span>\s*</span>', card, re.S)
                return api.text.strip_html(found[1] if found else "")
            out.append(api.jobs.make("Jobbird", m[2], grab("cro-recruiter-name"), m[1], grab("cro-job-location"),
                                     dutch_date(grab("cro-time-posted")), grab("cro-salary"), grab("cro-employment-type"),
                                     [], "", remote=False))
        if len(links) < 10:
            break
    return out
