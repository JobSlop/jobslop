"""Boards that need a free API key: Reed and Adzuna."""

import base64
import urllib.parse

from jobslop import net
from jobslop.boards.base import Board, NeedsKey, NotHere, job
from jobslop.geo.countries import COUNTRIES, country_info, is_country_name
from jobslop.settings import load_settings
from jobslop.text import money, to_date


def src_reed(q, o):
    if o["country"] != "GB":
        raise NotHere("UK only")
    key = load_settings().get("reed_key")
    if not key:
        raise NeedsKey("add a free key in Settings")
    auth = {"Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()}
    out = []
    for skip in (0, 100):
        params = {"keywords": q, "resultsToTake": 100, "resultsToSkip": skip}
        if not is_country_name(o["where"], "GB"):
            params.update(locationName=o["where"], distanceFromLocation=o["miles"])
        if o["salary_min"]:
            params["minimumSalary"] = o["salary_min"]
        jt = {"fulltime": "fullTime", "parttime": "partTime", "contract": "contract", "internship": "temp"}.get(o["jtype"])
        if jt:
            params[jt] = "true"
        d = net.get_json("https://www.reed.co.uk/api/1.0/search?" + urllib.parse.urlencode(params), headers=auth)
        res = d.get("results", [])
        for j in res:
            out.append(job("Reed", j.get("jobTitle"), j.get("employerName"), j.get("jobUrl"),
                           j.get("locationName"), to_date(j.get("date")),
                           money(j.get("minimumSalary"), j.get("maximumSalary"), j.get("currency") or "GBP"),
                           "", [], j.get("jobDescription"), remote=False))
        if len(res) < 100:
            break
    return out


def src_adzuna(q, o):
    code = country_info(o["country"])[2]
    if not code:
        raise NotHere("not available in " + country_info(o["country"])[0])
    s = load_settings()
    if not (s.get("adzuna_id") and s.get("adzuna_key")):
        raise NeedsKey("add a free key in Settings")
    cur = country_info(o["country"])[5]
    out = []
    for page in (1, 2):
        params = {"app_id": s["adzuna_id"], "app_key": s["adzuna_key"], "what": q,
                  "results_per_page": 50, "content-type": "application/json"}
        if not is_country_name(o["where"], o["country"]):
            params.update(where=o["where"], distance=round(o["miles"] * 1.609))
        if o["posted"]:
            params["max_days_old"] = o["posted"]
        if o["salary_min"]:
            params["salary_min"] = o["salary_min"]
        jt = {"fulltime": "full_time", "parttime": "part_time", "contract": "contract"}.get(o["jtype"])
        if jt:
            params[jt] = 1
        d = net.get_json(f"https://api.adzuna.com/v1/api/jobs/{code}/search/{page}?" + urllib.parse.urlencode(params))
        res = d.get("results", [])
        for j in res:
            jt = " ".join(x for x in (j.get("contract_time"), j.get("contract_type")) if x).replace("_", " ")
            out.append(job("Adzuna", j.get("title"), (j.get("company") or {}).get("display_name"),
                           j.get("redirect_url"), (j.get("location") or {}).get("display_name"),
                           to_date(j.get("created")), money(j.get("salary_min"), j.get("salary_max"), cur),
                           jt, [(j.get("category") or {}).get("label", "")], j.get("description"), remote=False))
        if len(res) < 50:
            break
    return out


BOARDS = [
    Board("Reed", src_reed, "Big UK job board (needs a free key)", group="country", countries={"GB"},
          country_native=True, location_aware=True, needs=("reed_key",)),
    Board("Adzuna", src_adzuna, "Job search in many countries (needs a free key)", group="country",
          countries={c for c, v in COUNTRIES.items() if v[2]}, country_native=True, location_aware=True,
          needs=("adzuna_id", "adzuna_key")),
]
