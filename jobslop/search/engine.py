"""Running a search across the boards and putting the results in order."""

import re
from concurrent.futures import ThreadPoolExecutor

from jobslop.boards.base import NeedsKey, NotHere
from jobslop.boards.registry import COUNTRY_NATIVE, KEYED_SOURCES, LOCATION_AWARE, SOURCES
from jobslop.geo.cities import REMOTE_RE, job_point, km_between
from jobslop.geo.countries import COUNTRIES, country_info, local_ok_re
from jobslop.geo.places import resolve_where
from jobslop.search.cache import fetch_cached
from jobslop.search.contract import INTERN_RE, contract_length
from jobslop.search.matching import STOPWORDS, find_group, group_score, match_groups, score


def search(query, sources, opts, fresh=False):
    # The filters on the results screen (date, job type, remote, salary, "workable from my country",
    # "title must match") never narrow what is fetched: boards are always asked for everything, and
    # each job is marked (local_ok, title_match) so the screen can hide what you are not interested in.
    opts = {**opts, "posted": 0, "jtype": "", "remote": "", "salary_min": 0, "local": True, "strict": False}
    # "Where?" may be a postcode or a full address: boards get a clean town, distances use the exact point
    loc = resolve_where(opts.get("where", ""), opts["country"])
    if loc and loc["explicit_country"] and loc["country_code"] in COUNTRIES:
        opts["country"] = loc["country_code"]          # "Austin, TX" means the US whatever the drop-down says
    opts["where"] = loc["board_where"] if loc else ""
    queries = [q.strip() for q in query.split(",") if q.strip()] or [""]     # "" = any job
    # expand any job-match term into its aliases (a few, to keep the number of requests reasonable)
    groups, expanded, qgroup = match_groups(), [], {}
    for q in queries:
        g = find_group(q, groups) if q else None
        for t in ([g["name"]] + g["aliases"])[:4] if g else [q]:
            if t.lower() not in (e.lower() for e in expanded):
                expanded.append(t)
                qgroup[t] = g
    queries = expanded
    # internships: boards without an "internship" filter get the word added to the search itself
    sent_as = {}
    TYPE_NATIVE = {"LinkedIn", "Indeed", "Glassdoor"}
    tasks = []
    for q in queries:
        for name in sources:
            if name not in SOURCES:
                continue
            sq = q
            if opts.get("intern") and name not in TYPE_NATIVE and not INTERN_RE.search(q):
                sq = (q + " internship").strip()
            sent_as[(name, sq)] = q
            tasks.append((name, sq))
    status = {}
    raw = []

    def run(name, q):
        try:
            jobs, cached = fetch_cached(name, q, opts, fresh)
            return name, q, [dict(j) for j in jobs], None, cached
        except NeedsKey:
            return name, q, [], "needs key", False
        except NotHere as e:
            return name, q, [], str(e) or "not available here", False
        except Exception as e:
            msg = str(e)[:140]
            if ("401" in msg or "403" in msg) and name in KEYED_SOURCES:
                msg = "key rejected - check Settings"
            elif "401" in msg or "403" in msg or "429" in msg:
                msg = "the site turned the search away - try again later"
            elif "402" in msg:
                msg = "Apify credit used up for this month"
            elif "408" in msg or "timed out" in msg.lower():
                msg = "took too long - try again"
            return name, q, [], msg, False

    with ThreadPoolExecutor(max_workers=12) as ex:
        for name, q, res, err, cached in ex.map(lambda t: run(*t), tasks):
            s = status.setdefault(name, {"found": 0, "error": None, "cached": False})
            if err:
                s["error"] = err
            s["cached"] = s["cached"] or cached
            for j in res:
                j["_q"] = sent_as.get((name, q), q)
            raw.extend(res)

    local_re = local_ok_re(opts["country"])
    town = (loc["town"] if loc else "").lower()
    center = (None, loc["lat"], loc["lon"]) if loc and loc["lat"] is not None else None
    radius_km = opts["miles"] * 1.609
    seen = {}
    for j in raw:
        q = j.pop("_q")
        j["local_ok"] = j["source"] in COUNTRY_NATIVE or bool(local_re.search(j["location"]))
        # how far away is it? (offline town list; exact coordinates when the board gives them)
        pt = job_point(j, opts["country"]) if center else None
        j["dist_km"] = round(km_between(center[1], center[2], pt[0], pt[1]), 1) if pt else None
        # a town was given: on-site jobs from the worldwide boards must be within the radius
        if town and j["source"] not in LOCATION_AWARE and not REMOTE_RE.search(j["location"]):
            if j["dist_km"] is not None:
                if j["dist_km"] > radius_km * 1.25:
                    continue
            elif town not in j["location"].lower():
                continue
        g = qgroup.get(q)
        if g:
            sc = group_score(j, g)
            j["title_match"] = sc >= 40
        else:
            words = [w for w in re.findall(r"[a-z0-9+#.]+", q.lower()) if w not in STOPWORDS] if q else []
            sc = score(j, words, q.lower(), False)
            j["title_match"] = score(j, words, q.lower(), True) > 0
        if sc <= 0 or not j["url"]:
            continue
        j["duration"], j["duration_m"] = contract_length(j)
        if opts.get("intern") and INTERN_RE.search(j["title"]):
            sc += 5                                      # internship search: real internships rank first
        key = (re.sub(r"\W+", "", j["title"].lower()), re.sub(r"\W+", "", j["company"].lower()))
        j["score"] = sc
        j["matched"] = q
        j["cur_hint"] = country_info(opts["country"])[5] if j["source"] in COUNTRY_NATIVE else "USD"
        if key not in seen or (seen[key]["score"], seen[key]["title_match"]) < (sc, j["title_match"]):
            seen[key] = j

    results = sorted(seen.values(), key=lambda j: j["date"] or "", reverse=True)
    results.sort(key=lambda j: j["score"], reverse=True)
    for j in results:
        status[j["source"]]["found"] += 1
    return {"results": results, "status": status, "place": loc}
