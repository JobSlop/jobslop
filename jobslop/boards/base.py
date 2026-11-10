"""What every job board shares: the job record, the board description and the errors a board can raise.

A board is a `Board`: a name, a `search(query, options)` function and a few facts the search and the
screen need (which countries it covers, which keys it needs, how long its results can be reused).

`options` given to `search`:
    where (town or ""), miles, country (ISO code), local (only jobs workable from that country),
    strict, posted (max days old, 0 = any), jtype ("", fulltime, parttime, contract, internship),
    remote ("", remote, hybrid, onsite), salary_min (yearly, local currency, 0 = any), intern
"""

import re
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

from jobslop.text import strip_html, to_date

Job = dict            # one job: see job() for its fields
SearchFn = Callable[[str, dict], list[Job]]

# how the boards are grouped on the search screen, in this order
GROUPS = ("main", "country", "specialist", "remote")
DEFAULT_CACHE_SECONDS = 15 * 60


class NotHere(Exception):
    """This board doesn't cover the chosen country."""


class NeedsKey(Exception):
    """This board needs a key (set in Settings) that hasn't been given."""


class Cancelled(Exception):
    """The search this request belongs to was stopped or replaced by a newer one."""


@contextmanager
def take_turn(lock, o):
    """Wait for a board's turn (boards that must be asked one at a time), unless the search is stopped."""
    cancel = o.get("cancel")
    while not lock.acquire(timeout=0.25):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
    try:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        yield
    finally:
        lock.release()


def pause(seconds, o):
    """Sleep between requests to a site, waking straight away when the search is stopped."""
    cancel = o.get("cancel")
    if cancel is None:
        time.sleep(max(0, seconds))
    elif cancel.wait(max(0, seconds)):
        raise Cancelled()


@dataclass(frozen=True)
class Board:
    """A job board the app can search."""

    name: str
    search: SearchFn
    description: str = ""
    group: str = "main"
    countries: frozenset[str] | None = None   # None = every country
    country_native: bool = False              # its results are already limited to the chosen country
    location_aware: bool = False              # it searches around the chosen town itself
    native_types: bool = False                # it filters job types (internships) itself
    needs: tuple[str, ...] = ()               # settings that must all be filled in (API keys)
    slow_without: str = ""                    # a setting that makes it faster (shown as "slow" when missing)
    cache_seconds: int = DEFAULT_CACHE_SECONDS
    plugin: str = "core"                      # who added it

    def __post_init__(self):
        if self.group not in GROUPS:
            raise ValueError(f"{self.name}: group must be one of {', '.join(GROUPS)}")
        if self.countries is not None:
            object.__setattr__(self, "countries", frozenset(c.upper() for c in self.countries))

    def covers(self, country: str) -> bool:
        return self.countries is None or country.upper() in self.countries

    def missing_keys(self, settings: Mapping) -> bool:
        return any(not settings.get(k) for k in self.needs)

    def describe(self, settings: Mapping) -> dict:
        """What the screen needs to show this board."""
        return {"name": self.name, "description": self.description, "group": self.group,
                "countries": sorted(self.countries) if self.countries is not None else None,
                "needs_key": self.missing_keys(settings),
                "slow": bool(self.slow_without) and not settings.get(self.slow_without),
                "plugin": self.plugin}


def as_list(v):
    if isinstance(v, list):
        return [str(x.get("name", x)) if isinstance(x, dict) else str(x) for x in v]
    return [str(v)] if v else []


def job(source, title, company, url, location="", date="", salary="", jtype="", tags=None, desc="", remote=True) -> Job:
    return {
        "source": source,
        "title": strip_html(title, 200),
        "company": strip_html(company, 120),
        "url": url or "",
        "location": strip_html(location, 160) or "Not listed",
        "date": date,
        "salary": salary or "",
        "type": jtype or "",
        "tags": [t for t in (tags or []) if t][:8],
        "desc": strip_html(desc, DESC_LIMIT),
        "remote": remote,
    }


DESC_LIMIT = 4000          # enough of the advert to search in (and to preview)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def clean_job(j, board_name):
    """A job as a board (or a plugin, or an old cache) gave it, made safe for the search: every field
    there and of the right kind. Returns None for something that isn't a job at all."""
    if not isinstance(j, Mapping):
        return None
    out = dict(j)

    def text(k, limit):
        v = out.get(k)
        return strip_html(v, limit) if v not in (None, False) and not isinstance(v, (dict, list, tuple, set)) else ""
    out["title"] = text("title", 200)
    out["company"] = text("company", 120)
    out["location"] = text("location", 160) or "Not listed"
    out["salary"] = text("salary", 120)
    out["type"] = text("type", 80)
    out["desc"] = text("desc", DESC_LIMIT)
    url = out.get("url")
    out["url"] = url.strip() if isinstance(url, str) else ""
    date = to_date(out.get("date")) if out.get("date") not in (None, "") else ""
    out["date"] = date if _DATE_RE.fullmatch(date or "") else ""
    tags = out.get("tags")
    out["tags"] = [strip_html(t, 60) for t in tags if t not in (None, "")][:8] if isinstance(tags, (list, tuple)) else []
    out["remote"] = bool(out.get("remote"))
    out["source"] = text("source", 60) or board_name
    out["board"] = board_name
    return out if out["title"] else None


def km_radius(o):
    return max(5, round(o["miles"] * 1.609))
