"""What every job board shares: the job record and the errors a board can raise."""

from jobslop.text import strip_html


def as_list(v):
    if isinstance(v, list):
        return [str(x.get("name", x)) if isinstance(x, dict) else str(x) for x in v]
    return [str(v)] if v else []


def job(source, title, company, url, location="", date="", salary="", jtype="", tags=None, desc="", remote=True):
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


class NeedsKey(Exception):
    pass


# ---------------------------------------------------------------- sources
# Each source takes (query, opts). opts keys:
#   where (town or ""), miles, country (ISO code), local (only jobs workable from that country),
#   strict, posted (max days old, 0 = any), jtype ("", fulltime, parttime, contract, internship),
#   remote ("", remote, hybrid, onsite), salary_min (yearly, local currency, 0 = any)

class NotHere(Exception):
    """This board doesn't cover the chosen country."""


def km_radius(o):
    return max(5, round(o["miles"] * 1.609))
