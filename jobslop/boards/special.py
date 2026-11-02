"""Specialist boards: ArtStation, Work With Indies, ICAEW, ACCA."""

import html
import re
import urllib.parse
from datetime import datetime

from jobslop import net
from jobslop.boards.base import Board, job
from jobslop.geo.cities import tail_place
from jobslop.net import BROWSER_UA
from jobslop.text import money, strip_html, to_date


def src_artstation(q, o):
    """ArtStation Jobs - art, animation and games jobs worldwide (open JSON feed)."""
    out = []
    for page in (1, 2, 3):
        d = net.get_json(f"https://www.artstation.com/api/v2/jobs/public/jobs.json?page={page}&per_page=50", headers=BROWSER_UA)
        for a in d.get("data", []):
            places = []
            for loc in a.get("recruitment_localities") or []:
                l = loc.get("locality") or {}
                places.append(l.get("formatted_name") or ", ".join(x for x in (l.get("city_name"), l.get("country_name")) if x))
            sr = a.get("salary_range") or {}
            sal = money(sr.get("min_salary"), sr.get("max_salary"), sr.get("currency") or "USD")
            if sal and sr.get("period") and sr["period"] != "year":
                sal += " / " + sr["period"]
            remote = bool(a.get("work_remotely"))
            location = ("Remote · " if remote else "") + "; ".join(p for p in places if p)
            out.append(job("ArtStation", a.get("title"), a.get("company_name"),
                           f"https://www.artstation.com/jobs/{a.get('hash_id')}" if a.get("hash_id") else a.get("apply_link"),
                           location or ("Remote" if remote else ""),
                           to_date((a.get("listing_placement") or {}).get("posted_at") or a.get("created_at")), sal,
                           " · ".join(x for x in (a.get("job_type"), a.get("level")) if x), [a.get("skills") or ""],
                           a.get("about") or a.get("description"), remote=remote))
        if len(d.get("data", [])) < 50:
            break
    return out


def src_workwithindies(q, o):
    """Work With Indies - indie games studio jobs worldwide (reads the public job list)."""
    h = net.fetch_html("https://www.workwithindies.com/")
    out = []
    for m in re.finditer(r'<a[^>]*href="(/careers/[^"]+)"[^>]*class="job-card[^"]*"[^>]*>(.*?)</a>', h, re.S):
        card = m[2]
        company = re.search(r'job-card-text bold">(.*?)</div>', card, re.S)
        title = re.search(r'text-block-28">(.*?)</div>', card, re.S)
        mobile = re.findall(r'job-card-text-smol">(.*?)</div>', card, re.S)
        location = strip_html(mobile[-1]) if mobile else ""
        if not location or location == "|":
            bolds = re.findall(r'job-card-text bold">(.*?)</div>', card, re.S)
            location = strip_html(bolds[-1]) if len(bolds) > 1 else ""
        remote = bool(re.search(r"remote|anywhere", location, re.I))
        out.append(job("WorkWithIndies", title[1] if title else "", company[1] if company else "",
                       "https://www.workwithindies.com" + m[1], ("Remote · " if remote and "remote" not in location.lower() else "") + location,
                       "", "", "", ["games"], "", remote=remote))
    return out


def madgex_feed(source, base, q, o, pages=4, keep_unknown=False):
    """ICAEW / ACCA job boards share the same RSS format: 'Company: Title' + 'salary: company: text. Place (CC)'."""
    cc = o["country"]
    out = []
    for page in range(1, pages + 1):
        x = net.fetch_html(f"{base}/jobsrss/?" + urllib.parse.urlencode({"keywords": q, "page": page}))
        items = re.findall(r"<item>(.*?)</item>", x, re.S)
        for it in items:
            title = html.unescape(strip_html((re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1]))
            desc = html.unescape(strip_html((re.search(r"<description>(.*?)</description>", it, re.S) or [None, ""])[1], 1500))
            link = html.unescape((re.search(r"<link>(.*?)</link>", it, re.S) or [None, ""])[1]).split("?")[0]
            pub = (re.search(r"<pubDate>(.*?)</pubDate>", it, re.S) or [None, ""])[1]
            company, _, role = title.partition(": ")
            if not role:
                company, role = "", title
            m = re.search(r"([^.:]{2,80})\s\(([A-Z]{2})\)\s*$", desc)
            if m:
                where, pcc = m[1].strip(), m[2]
            else:
                where = tail_place(desc, cc)
                pcc = cc if where else None
            if o["local"] and (pcc != cc if pcc else not keep_unknown):
                continue                          # these boards are worldwide; keep your country
            salary = desc.split(":")[0] if desc.count(":") >= 2 and len(desc.split(":")[0]) < 80 else ""
            try:
                date = datetime.strptime(pub[:16], "%a, %d %b %Y").strftime("%Y-%m-%d")
            except ValueError:
                date = ""
            out.append(job(source, role, company, link, where, date,
                           salary if re.search(r"\d", salary) else "", "", ["accounting"], desc, remote=False))
        if len(items) < 20:
            break
    return out


def src_icaew(q, o):
    """ICAEW Jobs - chartered accountancy jobs (mostly UK)."""
    return madgex_feed("ICAEW", "https://www.icaewjobs.com", q, o, keep_unknown=(o["country"] == "GB"))


def src_acca(q, o):
    """ACCA Careers - accounting & finance jobs worldwide."""
    return madgex_feed("ACCA", "https://jobs.accaglobal.com", q, o)


BOARDS = [
    Board("WorkWithIndies", src_workwithindies, "Indie games studio jobs worldwide", group="specialist"),
    Board("ArtStation", src_artstation, "Art, animation & games jobs worldwide", group="specialist"),
    Board("ICAEW", src_icaew, "Chartered accountancy jobs (ICAEW)", group="specialist", country_native=True),
    Board("ACCA", src_acca, "Accounting & finance jobs (ACCA Careers)", group="specialist", country_native=True),
]
