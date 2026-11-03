"""Helpers plugins get through `api` (api.http, api.jobs, api.text, api.geo), so they never need jobslop's internals.

These stay the same between jobslop versions with the same plugin API version.
"""

import threading
from types import SimpleNamespace

from jobslop import net
from jobslop.boards.base import NeedsKey, NotHere, as_list, job, km_radius
from jobslop.geo import cities, countries
from jobslop.text import money, rel_date, short_date, strip_html, to_date


def _town(row) -> dict | None:
    if not row:
        return None
    name, lat, lon, cc, region, population = row[:6]
    return {"name": name, "lat": lat, "lon": lon, "country": cc, "region": region, "population": population}


def find_town(name: str, country: str | None = None) -> dict | None:
    """A town from the offline list: {"name", "lat", "lon", "country", "region", "population"} or None."""
    return _town(cities.find_city(name, country.upper() if country else None))


def place_town(text: str, country: str | None = None) -> dict | None:
    """'Birmingham, United Kingdom' / 'Austin' -> town, or None."""
    return _town(cities.geocode_text(text, country))


def nearest_town(lat: float, lon: float) -> dict | None:
    return _town(cities.nearest_city(lat, lon))


def country(code: str) -> dict:
    """{"code", "name", "currency", "region"} for a country the app knows (unknown codes give the UK)."""
    info = countries.country_info(code)
    return {"code": (code or "GB").upper() if (code or "GB").upper() in countries.COUNTRIES else "GB",
            "name": info[0], "currency": info[5], "region": info[4]}


def country_code(text: str) -> str | None:
    """'United Kingdom' / 'uk' / 'GB' -> 'GB'."""
    return cities.code_for_country_text(text)


def get_json(url: str, timeout: int = 20, headers: dict | None = None):
    """Fetch and parse JSON."""
    return net.get_json(url, timeout=timeout, headers=headers)


def get_text(url: str, timeout: int = 25) -> str:
    """Fetch a page as text, sent with a normal browser's User-Agent."""
    return net.fetch_html(url, timeout=timeout)


http = SimpleNamespace(get_json=get_json, get_text=get_text, BROWSER_HEADERS=dict(net.BROWSER_UA))
JOBSPY_SITES = ("zip_recruiter", "indeed", "glassdoor", "google")


def jobspy(site: str, query: str, options: dict, source: str) -> list:
    """Search a site with JobSpy (bundled with jobslop): site is one of JOBSPY_SITES, source the board name
    the jobs are shown under. Raises RuntimeError when the site refuses (it's then paused for 15 minutes)."""
    from jobslop.boards import jobspy as js
    if site not in JOBSPY_SITES:
        raise ValueError(f"JobSpy site must be one of {', '.join(JOBSPY_SITES)}")
    js.js_locks.setdefault(site, threading.Lock())
    return js.jobspy_run(site, query, options, source=source)


jobs = SimpleNamespace(
    make=job,                       # make(source, title, company, url, location, date, salary, jtype, tags, desc, remote)
    as_list=as_list,
    km_radius=km_radius,            # search radius in km from the search options
    jobspy=jobspy,                  # jobspy(site, query, options, source): Indeed/ZipRecruiter/... via JobSpy
    NotHere=NotHere,                # raise when the board doesn't cover the chosen country
    NeedsKey=NeedsKey,              # raise when a setting (API key) is missing
)
text = SimpleNamespace(
    strip_html=strip_html, to_date=to_date, rel_date=rel_date, short_date=short_date, money=money,
)
geo = SimpleNamespace(
    find_town=find_town, place_town=place_town, nearest_town=nearest_town, km_between=cities.km_between,
    town_at_end=cities.tail_place, normalise=cities._norm, country=country, country_code=country_code,
    is_country_name=countries.is_country_name,
)
