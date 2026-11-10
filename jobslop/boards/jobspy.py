"""Indeed and Glassdoor through JobSpy, with Apify as a backup (plugins use JobSpy through api.jobs.jobspy)."""

import json
import threading
import time
import urllib.request
from pathlib import Path

from jobslop.boards.base import Board, Cancelled, NeedsKey, NotHere, as_list, job, pause, take_turn
from jobslop.config import DATA_DIR
from jobslop.geo.countries import country_info, is_country_name
from jobslop.geo.places import place
from jobslop.settings import load_settings
from jobslop.text import money, rel_date, to_date

# ---- LinkedIn, Indeed, Glassdoor
# Indeed and Glassdoor are searched for free with JobSpy from this computer; Apify is the backup.
# LinkedIn reads the public (no-login) listings slowly, or uses Apify when a token is set.

APIFY_MAX_USD = 0.25          # spending cap per Apify search
LI_GAP = 6                    # seconds between direct LinkedIn requests
LI_COOLDOWN = 15 * 60         # pause after LinkedIn rate-limits us
li_lock = threading.Lock()
li_state = {"last": 0.0, "blocked_until": 0.0}


def apify_run(actor, run_input, timeout=280):
    token = load_settings().get("apify_token")
    if not token:
        raise NeedsKey("add a free Apify token in Settings")
    url = (f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
           f"?timeout={timeout - 20}&maxTotalChargeUsd={APIFY_MAX_USD}")
    req = urllib.request.Request(url, data=json.dumps(run_input).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        items = json.loads(r.read().decode("utf-8", "replace"))
    return [i for i in items if isinstance(i, dict) and not i.get("error")]


def build_ca_bundle():
    """Python's certificates + the ones Windows trusts. Fixes 'certificate verify failed' when
    antivirus or a company network inspects secure connections."""
    path = DATA_DIR / "ca-bundle.pem"
    try:
        import ssl

        import certifi
        pems = [Path(certifi.where()).read_text(encoding="utf-8")]
        if hasattr(ssl, "enum_certificates"):
            for store in ("ROOT", "CA"):
                pems += [ssl.DER_cert_to_PEM_cert(c) for c, enc, _ in ssl.enum_certificates(store) if enc == "x509_asn"]
        path.write_text("\n".join(pems), encoding="utf-8")
        return str(path)
    except Exception:
        return None


CA_BUNDLE = build_ca_bundle()
JS_GAP = 4                    # seconds between JobSpy searches on the same site
JS_COOLDOWN = 15 * 60         # pause a site after it refuses us
js_locks = {"indeed": threading.Lock(), "glassdoor": threading.Lock(), "zip_recruiter": threading.Lock()}
js_state = {}                 # site -> {"last": t, "blocked_until": t}


class _Grab(__import__("logging").Handler):
    def __init__(self):
        super().__init__()
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


def jobspy_run(site, q, o, source=None):
    """Search one site with JobSpy. Raises RuntimeError if the site refuses or JobSpy isn't available."""
    import logging
    try:
        from jobspy import scrape_jobs
        from jobspy.model import Country
    except Exception:
        raise RuntimeError("JobSpy not installed")
    country = Country[country_info(o["country"])[1]]
    st = js_state.setdefault(site, {"last": 0.0, "blocked_until": 0.0})
    with take_turn(js_locks[site], o):
        left = st["blocked_until"] - time.time()
        if left > 0:
            raise RuntimeError(f"{site.capitalize()} paused for {int(left // 60) + 1} more min after refusing")
        pause(JS_GAP - (time.time() - st["last"]), o)
        st["last"] = time.time()
        specific = not is_country_name(o["where"], o["country"])
        kw = dict(site_name=[site], search_term=q or None,
                  location=(o["where"] + ", " + country_info(o["country"])[0]) if specific else country_info(o["country"])[0],
                  distance=o["miles"] if specific else 50, results_wanted=30,
                  country_indeed=country, ca_cert=CA_BUNDLE, verbose=0)
        # Indeed allows only one of: date filter, or job type + remote
        if o["posted"]:
            kw["hours_old"] = o["posted"] * 24
        else:
            if o["jtype"]:
                kw["job_type"] = o["jtype"]
            if o["remote"] == "remote":
                kw["is_remote"] = True
        log = logging.getLogger(f"jobspy.{site}")
        grab = _Grab()
        log.addHandler(grab)
        try:
            df = scrape_jobs(**kw)
        except ValueError as e:
            raise NotHere(str(e)[:80])
        finally:
            log.removeHandler(grab)
        errors = " ".join(grab.msgs)
        if len(df) == 0 and errors:
            if any(c in errors for c in ("403", "429", "blocked")):
                st["blocked_until"] = time.time() + JS_COOLDOWN
                raise RuntimeError(f"{site.capitalize()} refused the search (paused 15 min)")
            raise RuntimeError(errors[:140])

    def val(row, k):
        v = row.get(k)
        try:
            import pandas as pd
            return None if v is None or pd.isna(v) else v
        except (TypeError, ValueError):
            return v

    out = []
    for row in df.to_dict("records"):
        sal = money(val(row, "min_amount"), val(row, "max_amount"), val(row, "currency") or country_info(o["country"])[5])
        if sal and val(row, "interval") and val(row, "interval") != "yearly":
            sal += " / " + str(val(row, "interval")).replace("ly", "").replace("dai", "day")
        out.append(job(source or site.capitalize(), val(row, "title"), val(row, "company"),
                       val(row, "job_url") or val(row, "job_url_direct"), val(row, "location"),
                       to_date(val(row, "date_posted")), sal,
                       str(val(row, "job_type") or "").replace("fulltime", "Full time").replace("parttime", "Part time"),
                       [], str(val(row, "description") or "")[:6000], remote=bool(val(row, "is_remote"))))
    return out


def with_backup(site, q, o, apify_fn):
    """Try JobSpy first; if the site refuses, fall back to Apify when a token is set."""
    try:
        return jobspy_run(site, q, o)
    except Cancelled:
        raise
    except RuntimeError as e:
        if load_settings().get("apify_token"):
            return apify_fn(q, o)
        raise RuntimeError(f"{e} - add an Apify token in Settings as backup")


def src_indeed(q, o):
    return with_backup("indeed", q, o, apify_indeed)


def src_glassdoor(q, o):
    return with_backup("glassdoor", q, o, apify_glassdoor)


def apify_indeed(q, o):
    items = apify_run("misceres~indeed-scraper", {
        "position": q, "country": o["country"], "location": place(o),
        "maxItemsPerSearch": 30, "saveOnlyUniqueItems": True, "parseCompanyDetails": False,
    })
    return [job("Indeed", i.get("positionName"), i.get("company"), i.get("url") or i.get("externalApplyLink"),
                i.get("location"), rel_date(i.get("postedAt")), i.get("salary"),
                ", ".join(as_list(i.get("jobType"))), [], i.get("description"), remote=False)
            for i in items]


def apify_glassdoor(q, o):
    name = country_info(o["country"])[3] or country_info(o["country"])[0].lower()
    items = apify_run("orgupdate~glassdoor-jobs-scraper", {
        "includeKeyword": q, "locationName": place(o), "countryName": name,
        "pagesToFetch": 1, "datePosted": "month",
    })
    return [job("Glassdoor", i.get("job_title"), i.get("company_name"), i.get("URL") or i.get("url"),
                i.get("location"), rel_date(i.get("date")), i.get("salary"), i.get("job_type") or "",
                [], "", remote=False)
            for i in items]


BOARDS = [
    Board("Indeed", src_indeed, "Indeed, searched free with JobSpy", country_native=True, location_aware=True,
          native_types=True, cache_seconds=3 * 3600),
    Board("Glassdoor", src_glassdoor, "Glassdoor, searched free with JobSpy", country_native=True, location_aware=True,
          native_types=True, cache_seconds=3 * 3600),
]
