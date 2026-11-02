"""Remote-job boards: Himalayas, Jobicy, Remotive, RemoteOK, Arbeitnow."""

import re
import urllib.parse

from jobslop import net
from jobslop.boards.base import as_list, job
from jobslop.geo.countries import country_info
from jobslop.search.matching import STOPWORDS
from jobslop.text import money, to_date


def src_himalayas(q, o):
    out = []
    country = f"&country={o['country']}" if o["local"] else ""
    name = country_info(o["country"])[0]
    for page in (1, 2, 3):
        d = net.get_json(f"https://himalayas.app/jobs/api/search?q={urllib.parse.quote(q)}&page={page}{country}")
        jobs = d.get("jobs", [])
        for j in jobs:
            locs = as_list(j.get("locationRestrictions"))
            if name in locs and len(locs) > 4:
                loc = f"{name} + {len(locs) - 1} more countries"
            else:
                loc = ", ".join(locs[:4]) + (" +more" if len(locs) > 4 else "") if locs else "Worldwide"
            out.append(job("Himalayas", j.get("title"), j.get("companyName"),
                           j.get("applicationLink") or j.get("guid"), "Remote · " + loc, to_date(j.get("pubDate")),
                           money(j.get("minSalary"), j.get("maxSalary"), j.get("currency") or "USD"),
                           j.get("employmentType"), as_list(j.get("categories")),
                           j.get("description") or j.get("excerpt")))
        if len(jobs) < 20:
            break
    return out


def src_jobicy(q, o):
    geo = country_info(o["country"])[3] if o["local"] else ""
    base = "https://jobicy.com/api/v2/remote-jobs?count=50" + (f"&tag={urllib.parse.quote(q)}" if q else "")
    try:
        d = net.get_json(base + (f"&geo={geo}" if geo else ""))
    except Exception:
        d = {}
    if geo and not d.get("jobs"):
        d = net.get_json(base)            # unknown region name: fetch all and filter afterwards
    return [job("Jobicy", j.get("jobTitle"), j.get("companyName"), j.get("url"), "Remote · " + (j.get("jobGeo") or ""),
                to_date(j.get("pubDate")),
                money(j.get("annualSalaryMin") or j.get("salaryMin"),
                      j.get("annualSalaryMax") or j.get("salaryMax"),
                      j.get("salaryCurrency") or "USD"),
                ", ".join(as_list(j.get("jobType"))), as_list(j.get("jobIndustry")),
                j.get("jobDescription") or j.get("jobExcerpt"))
            for j in d.get("jobs", []) or []]


def src_remotive(q, o):
    d = net.get_json("https://remotive.com/api/remote-jobs?limit=150" + (f"&search={urllib.parse.quote(q)}" if q else ""))
    return [job("Remotive", j.get("title"), j.get("company_name"), j.get("url"),
                "Remote · " + (j.get("candidate_required_location") or ""), to_date(j.get("publication_date")),
                j.get("salary"), (j.get("job_type") or "").replace("_", " "),
                as_list(j.get("tags")), j.get("description"))
            for j in d.get("jobs", [])]


def src_remoteok(q, o):
    words = [w for w in re.findall(r"[a-z0-9+#]+", q.lower()) if w not in STOPWORDS][:2]
    urls = ["https://remoteok.com/api"] + [f"https://remoteok.com/api?tag={urllib.parse.quote(w)}" for w in words]
    out = []
    for u in urls:
        try:
            for j in net.get_json(u):
                if not isinstance(j, dict) or "position" not in j:
                    continue  # first item is a legal notice
                out.append(job("RemoteOK", j.get("position"), j.get("company"), j.get("url"),
                               "Remote · " + (j.get("location") or ""), to_date(j.get("epoch") or j.get("date")),
                               money(j.get("salary_min"), j.get("salary_max")), "",
                               as_list(j.get("tags")), j.get("description")))
        except Exception:
            pass
    return out


def src_arbeitnow(q, o):
    out = []
    for page in (1, 2, 3):
        d = net.get_json(f"https://www.arbeitnow.com/api/job-board-api?page={page}")
        for j in d.get("data", []):
            out.append(job("Arbeitnow", j.get("title"), j.get("company_name"), j.get("url"),
                           (j.get("location") or "") + (" (remote)" if j.get("remote") else ""),
                           to_date(j.get("created_at")), "", ", ".join(as_list(j.get("job_types"))),
                           as_list(j.get("tags")), j.get("description"), remote=bool(j.get("remote"))))
    return out
