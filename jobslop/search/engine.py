"""Running a search across the boards and putting the results in order."""

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from jobslop.boards.base import Cancelled, NeedsKey, NotHere, clean_job
from jobslop.boards.registry import BOARDS
from jobslop.geo.cities import REMOTE_RE, job_point, km_between
from jobslop.geo.countries import COUNTRIES, country_info, local_ok_re
from jobslop.geo.places import resolve_where
from jobslop.i18n import LANGUAGES
from jobslop.search.cache import fetch_cached
from jobslop.search.contract import INTERN_RE, contract_length
from jobslop.search.matching import find_group, group_score, match, match_groups, query_words


# ---- stopping a search: the screen gives each search an id; stopping it (or starting a newer one) wakes
# up its requests that are still waiting for a board's turn, so they don't hold up the next search
_runs: dict[str, tuple[threading.Event, float]] = {}
_runs_lock = threading.Lock()


def run_event(run_id):
    """The stop signal for one search (shared by its requests, one per board)."""
    if not run_id:
        return None
    with _runs_lock:
        now = time.time()
        for k in [k for k, (_, t) in _runs.items() if now - t > 1800]:
            del _runs[k]
        ev, _ = _runs.get(run_id) or (threading.Event(), now)
        _runs[run_id] = (ev, now)
        return ev


def cancel_run(run_id):
    ev = run_event(str(run_id)[:64])
    if ev is not None:
        ev.set()


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
    # searching in another language's country: its job titles are searched too, on that country's own boards
    local_for = {}
    for q in list(queries):
        for lt in LANGUAGES.local_terms(q, opts["country"]):
            if lt.lower() not in (x.lower() for x in queries):
                queries.append(lt)
                local_for[lt] = q
    # internships: boards without an "internship" filter get the word added to the search itself
    sent_as = {}
    tasks = []
    status = {}
    for q in queries:
        for name in sources:
            board = BOARDS.get(name)
            if board is None:
                status[name] = {"found": 0, "error": "switched off - turn it on in Settings → Plugins", "cached": False}
                continue
            if q in local_for and not board.country_native:
                continue
            sq = q
            if opts.get("intern") and not board.native_types and not INTERN_RE.search(q):
                sq = (q + " internship").strip()
            sent_as[(name, sq)] = q
            tasks.append((name, sq))
    raw = []

    def run(name, q):
        try:
            jobs, cached = fetch_cached(name, q, opts, fresh)
            if not isinstance(jobs, (list, tuple)):
                return name, q, [], "the site's answer couldn't be read", cached
            # every job made safe first: one odd job from a board or plugin must not sink the whole search
            return name, q, [c for c in (clean_job(j, name) for j in jobs) if c], None, cached
        except Cancelled:
            return name, q, [], "stopped", False
        except NeedsKey:
            return name, q, [], "needs key", False
        except NotHere as e:
            return name, q, [], str(e) or "not available here", False
        except Exception as e:
            msg = str(e)[:140].strip() or f"stopped unexpectedly ({type(e).__name__})"
            board = BOARDS.get(name)
            if ("401" in msg or "403" in msg) and board and board.needs:
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
        board = BOARDS.get(j["board"])
        native = bool(board and board.country_native)
        j["local_ok"] = native or bool(local_re.search(j["location"]))
        # how far away is it? (offline town list; exact coordinates when the board gives them)
        pt = job_point(j, opts["country"])
        if pt:                                             # where it is, for the jobs map (and distances)
            j["lat"], j["lon"] = round(pt[0], 5), round(pt[1], 5)
        j["dist_km"] = round(km_between(center[1], center[2], pt[0], pt[1]), 1) if pt and center else None
        # a town was given: on-site jobs from the worldwide boards must be within the radius
        if town and not (board and board.location_aware) and not REMOTE_RE.search(j["location"]):
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
            m = match(j, query_words(q), (q or "").lower().strip())
            sc, j["title_match"] = m["score"], m["title_match"]
            if m["snippet"]:
                j["found_in"] = m["snippet"]          # the bit of the advert that mentions the search
        if sc <= 0 or not j["url"]:
            continue
        j["duration"], j["duration_m"] = contract_length(j)
        if opts.get("intern") and INTERN_RE.search(j["title"]):
            sc += 5                                      # internship search: real internships rank first
        key = (re.sub(r"\W+", "", j["title"].lower()), re.sub(r"\W+", "", j["company"].lower()))
        j["score"] = sc
        j["matched"] = q
        j["cur_hint"] = country_info(opts["country"])[5] if native else "USD"
        if key not in seen or (seen[key]["score"], seen[key]["title_match"]) < (sc, j["title_match"]):
            seen[key] = j

    results = sorted(seen.values(), key=lambda j: j["date"] or "", reverse=True)
    results.sort(key=lambda j: j["score"], reverse=True)
    for j in results:
        status[j.pop("board")]["found"] += 1
    return {"results": results, "status": status, "place": loc, "also_searched": list(local_for)}
