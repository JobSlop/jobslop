"""LinkedIn's public job listings."""

import html
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from jobslop.boards.base import Board, as_list, job
from jobslop.boards.jobspy import LI_COOLDOWN, LI_GAP, apify_run, li_lock, li_state
from jobslop.geo.countries import is_country_name
from jobslop.geo.places import place
from jobslop.settings import load_settings
from jobslop.text import strip_html, to_date


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


BOARDS = [
    Board("LinkedIn", src_linkedin, "Public LinkedIn listings (no login)", country_native=True, location_aware=True,
          native_types=True, slow_without="apify_token", cache_seconds=3600),
]
