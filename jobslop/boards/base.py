"""What every job board shares: the job record, the board description and the errors a board can raise.

A board is a `Board`: a name, a `search(query, options)` function and a few facts the search and the
screen need (which countries it covers, which keys it needs, how long its results can be reused).

`options` given to `search`:
    where (town or ""), miles, country (ISO code), local (only jobs workable from that country),
    strict, posted (max days old, 0 = any), jtype ("", fulltime, parttime, contract, internship),
    remote ("", remote, hybrid, onsite), salary_min (yearly, local currency, 0 = any), intern
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from jobslop.text import strip_html

Job = dict            # one job: see job() for its fields
SearchFn = Callable[[str, dict], list[Job]]

# how the boards are grouped on the search screen, in this order
GROUPS = ("main", "country", "specialist", "remote")
DEFAULT_CACHE_SECONDS = 15 * 60


class NotHere(Exception):
    """This board doesn't cover the chosen country."""


class NeedsKey(Exception):
    """This board needs a key (set in Settings) that hasn't been given."""


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
        "desc": strip_html(desc),
        "remote": remote,
    }


def km_radius(o):
    return max(5, round(o["miles"] * 1.609))
