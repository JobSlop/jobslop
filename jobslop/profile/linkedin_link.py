"""Import from a LinkedIn profile link, read by the Chrome extension."""

import re
import time
import urllib.parse
from datetime import datetime

from jobslop.geo.cities import find_city
from jobslop.profile.cvparse import country_code, education_details, find_dates, norm_dates
from jobslop.profile.linkedin_import import linkedin_place

li_link = {"url": "", "at": 0.0, "found": None, "error": ""}
LI_LINK_WAIT = 600                      # seconds the app waits for the extension to read the page


def linkedin_profile_url(text):
    """'linkedin.com/in/jane-doe-123?x=1' (with or without https/www) -> 'https://www.linkedin.com/in/jane-doe-123/'."""
    m = re.search(r"(?:https?://)?(?:[\w-]+\.)?linkedin\.com/in/([^/?#\s]+)", text or "", re.I)
    if not m:
        return None
    slug = urllib.parse.unquote(m[1]).strip()
    if not slug or len(slug) > 100 or not re.fullmatch(r"[^\s<>\"'\\]+", slug):
        return None
    return "https://www.linkedin.com/in/" + urllib.parse.quote(slug, safe="-_.~") + "/"


def linkedin_link_status():
    waiting = bool(li_link["url"]) and li_link["found"] is None and not li_link["error"] \
        and time.time() - li_link["at"] < LI_LINK_WAIT
    return {"url": li_link["url"], "waiting": waiting, "found": li_link["found"], "error": li_link["error"]}


def _li_lines(lines):
    out = []
    for ln in lines or []:
        ln = re.sub(r"\s+", " ", str(ln)).strip()
        if ln and not re.fullmatch(r"(?:…|\.\.\.)?\s*(?:see more|show more|see less)", ln, re.I) and (not out or out[-1] != ln):
            out.append(ln[:2000])
    return out[:60]


def _li_is_place(s):
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts or len(s) > 80 or s.endswith("."):
        return False
    if re.fullmatch(r"remote|hybrid|on-site", s, re.I):
        return True
    cc = country_code(parts[-1]) or ("GB" if parts[-1].lower() in ("england", "scotland", "wales", "northern ireland") else None)
    return bool(cc or find_city(parts[0]))


JOB_KIND = re.compile(r"(?:full|part)[- ]time|self-employed|freelance|contract|internship|apprenticeship|seasonal|"
                      r"temporary|permanent|on-site|hybrid|remote", re.I)


def _li_job(lines, company=""):
    """One experience entry from a LinkedIn profile page (its lines of text) -> a work history job."""
    lines = _li_lines(lines)
    if not lines:
        return None
    job = {"title": lines[0], "company": company, "location": "", "start": "", "end": "", "description": ""}
    desc = []
    for ln in lines[1:]:
        d = find_dates(norm_dates(ln))
        if d and d[0] and not job["start"]:
            job["start"], job["end"] = d[0], d[1] or ""
            continue
        head = ln.split(" · ")[0].strip()
        if JOB_KIND.fullmatch(head) or ln.lower().startswith("skills:"):
            continue
        if not job["start"] and not job["company"]:
            job["company"] = head                 # "Rare · Full-time" comes before the dates
            continue
        if job["start"] and not job["location"] and not desc and _li_is_place(head):
            job["location"] = head
            continue
        desc.append(ln)
    job["description"] = "\n".join(desc)[:2000]
    return job


def linkedin_from_page(page):
    """What the extension read on a LinkedIn profile page -> profile details (the app asks add/replace first)."""
    out = {}
    name = re.split(r",|\(|\|", str(page.get("name") or ""))[0].strip()
    parts = name.split()
    if parts:
        out["first_name"] = parts[0]
        if len(parts) > 1:
            out["last_name"] = " ".join(parts[1:])
    for ln in _li_lines(page.get("top")):
        if ln != name and _li_is_place(ln) and not JOB_KIND.fullmatch(ln):
            linkedin_place(ln, out)
            break
    jobs = []
    for e in page.get("experience") or []:
        if not isinstance(e, dict):
            continue
        roles = [r for r in e.get("roles") or [] if any(find_dates(norm_dates(x)) for x in _li_lines(r))]
        if roles:                                  # several roles at one company
            head = _li_lines(e.get("lines"))
            place = next((x.split(" · ")[0] for x in head[1:] if _li_is_place(x.split(" · ")[0])), "")
            for r in roles:
                j = _li_job(r, head[0] if head else "")
                if j:
                    j["location"] = j["location"] or place
                    jobs.append(j)
        else:                                      # one role; its description and skills sit in parts inside it
            extra = [x for r in e.get("roles") or [] for x in _li_lines(r)]
            j = _li_job(list(e.get("lines") or []) + extra)
            if j:
                jobs.append(j)
    if jobs:
        out["jobs"] = jobs[:20]
        cur = next((j for j in jobs if j["end"] == "Present"), jobs[0])
        out["current_title"], out["current_company"] = cur["title"], cur["company"]
        years = [int(y) for j in jobs for y in re.findall(r"(?:19|20)\d{2}", j["start"])]
        if years and 0 < datetime.now().year - min(years) < 50:
            out["years_experience"] = str(datetime.now().year - min(years))
    edu = [_li_lines(e) for e in page.get("education") or [] if isinstance(e, list)]
    edu = [e for e in edu if e]
    if edu:
        first = edu[0]
        degree = first[1] if len(first) > 1 and not find_dates(norm_dates(first[1])) else ""
        education_details([", ".join(x for x in (degree, first[0]) if x)], out)
        out.setdefault("university", first[0])
    skills = []
    for s in page.get("skills") or []:
        s = re.sub(r"\s+", " ", str(s)).strip()
        if s and len(s) < 60 and s.lower() not in (x.lower() for x in skills):
            skills.append(s)
    if skills:
        out["skills"] = ", ".join(skills)[:400]
    url = linkedin_profile_url(page.get("url") or "")
    if url:
        out["linkedin"] = url
    return {k: v for k, v in out.items() if v}
