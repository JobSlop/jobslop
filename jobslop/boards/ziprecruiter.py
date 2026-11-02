"""ZipRecruiter UK (ziprecruiter.co.uk), read from its public search page.

The US site (through JobSpy) turns away connections from the UK, so the UK site is used."""

import html
import re
import urllib.parse

from jobslop import net
from jobslop.boards.base import Board, NotHere, job
from jobslop.geo.countries import is_country_name
from jobslop.text import short_date, strip_html


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


BOARDS = [
    Board("ZipRecruiter", src_ziprecruiter_uk, "ZipRecruiter UK", countries={"GB"}, country_native=True, location_aware=True),
]
