"""Adzuna: Adzuna job search in 19 countries: the UK, US, Canada, Australia, much of Europe and more. Needs a free key."""

import urllib.parse

api = None                                     # set by register()
COMMON = {"group": "country", "country_native": True, "location_aware": True}

# Adzuna's own code for each country it covers
ADZUNA = {"GB": "gb", "US": "us", "CA": "ca", "AU": "au", "NZ": "nz", "DE": "de", "FR": "fr", "NL": "nl", "BE": "be",
          "ES": "es", "IT": "it", "AT": "at", "CH": "ch", "PL": "pl", "IN": "in", "SG": "sg", "ZA": "za", "BR": "br",
          "MX": "mx"}


def register(_api):
    global api
    api = _api
    api.add_board("Adzuna", src_adzuna, "Job search in many countries (needs a free key)", countries=set(ADZUNA), needs=("adzuna_id", "adzuna_key"), **COMMON)


def src_adzuna(q, o):
    code = ADZUNA.get(o["country"])
    country = api.geo.country(o["country"])
    if not code:
        raise api.jobs.NotHere("not available in " + country["name"])
    app_id, app_key = api.setting("adzuna_id"), api.setting("adzuna_key")
    if not (app_id and app_key):
        raise api.jobs.NeedsKey("add a free key in Settings")
    out = []
    for page in (1, 2):
        params = {"app_id": app_id, "app_key": app_key, "what": q, "results_per_page": 50, "content-type": "application/json"}
        if not api.geo.is_country_name(o["where"], o["country"]):
            params.update(where=o["where"], distance=round(o["miles"] * 1.609))
        if o["posted"]:
            params["max_days_old"] = o["posted"]
        if o["salary_min"]:
            params["salary_min"] = o["salary_min"]
        jt = {"fulltime": "full_time", "parttime": "part_time", "contract": "contract"}.get(o["jtype"])
        if jt:
            params[jt] = 1
        d = api.http.get_json(f"https://api.adzuna.com/v1/api/jobs/{code}/search/{page}?" + urllib.parse.urlencode(params))
        res = d.get("results", [])
        for j in res:
            jt = " ".join(x for x in (j.get("contract_time"), j.get("contract_type")) if x).replace("_", " ")
            out.append(api.jobs.make("Adzuna", j.get("title"), (j.get("company") or {}).get("display_name"),
                                     j.get("redirect_url"), (j.get("location") or {}).get("display_name"),
                                     api.text.to_date(j.get("created")),
                                     api.text.money(j.get("salary_min"), j.get("salary_max"), country["currency"]),
                                     jt, [(j.get("category") or {}).get("label", "")], j.get("description"), remote=False))
        if len(res) < 50:
            break
    return out
