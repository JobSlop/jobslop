"""Remote-job boards: Himalayas, Jobicy, Remotive, RemoteOK, Arbeitnow (no keys needed)."""

import re
import urllib.parse

api = None                                     # set by register()

# Jobicy's region name for each country
JOBICY_GEO = {"GB": "uk", "US": "usa", "CA": "canada", "AU": "australia", "IE": "ireland", "DE": "germany", "FR": "france",
              "NL": "netherlands", "BE": "belgium", "ES": "spain", "IT": "italy", "PT": "portugal", "AT": "austria",
              "CH": "switzerland", "SE": "sweden", "DK": "denmark", "NO": "norway", "FI": "finland", "PL": "poland",
              "CZ": "czechia", "RO": "romania", "GR": "greece", "HU": "hungary", "UA": "ukraine", "TR": "turkiye",
              "IN": "india", "SG": "singapore", "MY": "malaysia", "PH": "philippines", "JP": "japan", "KR": "south-korea",
              "ID": "indonesia", "TH": "thailand", "VN": "vietnam", "AE": "uae", "IL": "israel", "EG": "egypt",
              "ZA": "south-africa", "NG": "nigeria", "BR": "brazil", "MX": "mexico", "AR": "argentina", "CL": "chile",
              "CO": "colombia"}
STOPWORDS = {"a", "an", "the", "and", "or", "of", "for", "in", "to", "job", "jobs", "remote"}


def register(_api):
    global api
    api = _api
    api.add_board("Himalayas", src_himalayas, "Remote jobs board", group="remote")
    api.add_board("Jobicy", src_jobicy, "Remote jobs board", group="remote")
    api.add_board("Remotive", src_remotive, "Remote jobs board", group="remote")
    api.add_board("RemoteOK", src_remoteok, "Remote jobs board", group="remote")
    api.add_board("Arbeitnow", src_arbeitnow, "Remote & European jobs board", group="remote")


def src_himalayas(q, o):
    out = []
    country = f"&country={o['country']}" if o["local"] else ""
    name = api.geo.country(o["country"])["name"]
    for page in (1, 2, 3):
        d = api.http.get_json(f"https://himalayas.app/jobs/api/search?q={urllib.parse.quote(q)}&page={page}{country}")
        jobs = d.get("jobs", [])
        for j in jobs:
            locs = api.jobs.as_list(j.get("locationRestrictions"))
            if name in locs and len(locs) > 4:
                loc = f"{name} + {len(locs) - 1} more countries"
            else:
                loc = ", ".join(locs[:4]) + (" +more" if len(locs) > 4 else "") if locs else "Worldwide"
            out.append(api.jobs.make("Himalayas", j.get("title"), j.get("companyName"),
                                     j.get("applicationLink") or j.get("guid"), "Remote · " + loc,
                                     api.text.to_date(j.get("pubDate")),
                                     api.text.money(j.get("minSalary"), j.get("maxSalary"), j.get("currency") or "USD"),
                                     j.get("employmentType"), api.jobs.as_list(j.get("categories")),
                                     j.get("description") or j.get("excerpt")))
        if len(jobs) < 20:
            break
    return out


def src_jobicy(q, o):
    geo = JOBICY_GEO.get(o["country"], "") if o["local"] else ""
    base = "https://jobicy.com/api/v2/remote-jobs?count=50" + (f"&tag={urllib.parse.quote(q)}" if q else "")
    try:
        d = api.http.get_json(base + (f"&geo={geo}" if geo else ""))
    except Exception:
        d = {}
    if geo and not d.get("jobs"):
        d = api.http.get_json(base)            # unknown region name: fetch all and filter afterwards
    return [api.jobs.make("Jobicy", j.get("jobTitle"), j.get("companyName"), j.get("url"),
                          "Remote · " + (j.get("jobGeo") or ""), api.text.to_date(j.get("pubDate")),
                          api.text.money(j.get("annualSalaryMin") or j.get("salaryMin"),
                                         j.get("annualSalaryMax") or j.get("salaryMax"), j.get("salaryCurrency") or "USD"),
                          ", ".join(api.jobs.as_list(j.get("jobType"))), api.jobs.as_list(j.get("jobIndustry")),
                          j.get("jobDescription") or j.get("jobExcerpt"))
            for j in d.get("jobs", []) or []]


def src_remotive(q, o):
    d = api.http.get_json("https://remotive.com/api/remote-jobs?limit=150" + (f"&search={urllib.parse.quote(q)}" if q else ""))
    return [api.jobs.make("Remotive", j.get("title"), j.get("company_name"), j.get("url"),
                          "Remote · " + (j.get("candidate_required_location") or ""),
                          api.text.to_date(j.get("publication_date")), j.get("salary"),
                          (j.get("job_type") or "").replace("_", " "), api.jobs.as_list(j.get("tags")), j.get("description"))
            for j in d.get("jobs", [])]


def src_remoteok(q, o):
    words = [w for w in re.findall(r"[a-z0-9+#]+", q.lower()) if w not in STOPWORDS][:2]
    urls = ["https://remoteok.com/api"] + [f"https://remoteok.com/api?tag={urllib.parse.quote(w)}" for w in words]
    out = []
    for u in urls:
        try:
            for j in api.http.get_json(u):
                if not isinstance(j, dict) or "position" not in j:
                    continue                   # the first item is a legal notice
                out.append(api.jobs.make("RemoteOK", j.get("position"), j.get("company"), j.get("url"),
                                         "Remote · " + (j.get("location") or ""),
                                         api.text.to_date(j.get("epoch") or j.get("date")),
                                         api.text.money(j.get("salary_min"), j.get("salary_max")), "",
                                         api.jobs.as_list(j.get("tags")), j.get("description")))
        except Exception:
            pass
    return out


def src_arbeitnow(q, o):
    out = []
    for page in (1, 2, 3):
        d = api.http.get_json(f"https://www.arbeitnow.com/api/job-board-api?page={page}")
        for j in d.get("data", []):
            out.append(api.jobs.make("Arbeitnow", j.get("title"), j.get("company_name"), j.get("url"),
                                     (j.get("location") or "") + (" (remote)" if j.get("remote") else ""),
                                     api.text.to_date(j.get("created_at")), "", ", ".join(api.jobs.as_list(j.get("job_types"))),
                                     api.jobs.as_list(j.get("tags")), j.get("description"), remote=bool(j.get("remote"))))
    return out
