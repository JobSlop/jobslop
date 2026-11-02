"""LinkedIn: the profile PDF ("Save to PDF") or the data export .zip."""

import base64
import csv
import re
from datetime import datetime
from pathlib import Path

from jobslop.config import DATA_DIR
from jobslop.geo.cities import _norm, find_city
from jobslop.profile.cvparse import country_code, country_label, education_details, parse_cv

# ---- LinkedIn: the profile PDF ("Save to PDF") or the data export .zip ("Get a copy of your data")

def _csv_rows(text):
    text = text.lstrip("﻿")
    # some LinkedIn CSVs start with a "Notes:" paragraph before the real header
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines[:8]) if "," in ln and not ln.lower().startswith("notes")), 0)
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(lines[start:])]


def linkedin_place(text, out):
    """'Birmingham, England, United Kingdom' -> city / country."""
    parts = [p.strip() for p in (text or "").split(",") if p.strip()]
    if not parts:
        return
    cc = country_code(parts[-1]) or ("GB" if parts[-1].lower() in ("england", "scotland", "wales") else None)
    row = find_city(parts[0], cc) or find_city(parts[0])
    if row:
        out["city"] = row[0] if _norm(row[0]) == _norm(parts[0]) else parts[0]
        cc = cc or row[3]
    elif len(parts) > 1:
        out["city"] = parts[0]
    if cc:
        out["country"] = country_label(cc)


def linkedin_export(path):
    """Read LinkedIn's data export: Profile.csv, Positions.csv, Education.csv, Skills.csv, Email/Phone files."""
    import zipfile
    files = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.lower().endswith(".csv") and z.getinfo(n).file_size < 5_000_000:
                files[Path(n).name.lower()] = z.read(n).decode("utf-8", "replace")
    if not any(k in files for k in ("profile.csv", "positions.csv")):
        raise ValueError("This zip doesn't look like a LinkedIn data export (no Profile.csv or Positions.csv)")
    out = {}
    prof = (_csv_rows(files["profile.csv"]) or [{}])[0] if "profile.csv" in files else {}
    first = prof.get("first name", "").split()
    if first:
        out["first_name"] = first[0]
        if len(first) > 1:
            out["middle_name"] = " ".join(first[1:])
    if prof.get("last name"):
        out["last_name"] = prof["last name"]
    if prof.get("address"):
        out["address1"] = prof["address"]
    if prof.get("zip code"):
        out["postcode"] = prof["zip code"]
    linkedin_place(prof.get("geo location", ""), out)
    m = re.search(r"https?://[^\]\s,]+", prof.get("websites", ""))
    if m:
        out["website"] = m[0]
    for name in ("email addresses.csv", "email address.csv"):
        rows = _csv_rows(files.get(name, ""))
        if rows:
            best = next((r for r in rows if r.get("primary", "").lower() == "yes"), rows[0])
            out["email"] = best.get("email address", "")
    for name in ("phonenumbers.csv", "phone numbers.csv"):
        rows = _csv_rows(files.get(name, ""))
        if rows and rows[0].get("number"):
            out["phone"] = rows[0]["number"]
    jobs = []
    for r in _csv_rows(files.get("positions.csv", "")):
        if not (r.get("title") or r.get("company name")):
            continue
        jobs.append({"title": r.get("title", ""), "company": r.get("company name", ""), "location": r.get("location", ""),
                     "start": r.get("started on", ""), "end": r.get("finished on", "") or "Present",
                     "description": (r.get("description", "") or "")[:2000]})
    if jobs:
        out["jobs"] = jobs[:20]
        cur = next((j for j in jobs if j["end"] == "Present"), jobs[0])
        out["current_title"], out["current_company"] = cur["title"], cur["company"]
        years = [int(y) for j in jobs for y in re.findall(r"(?:19|20)\d{2}", j["start"])]
        if years and 0 < datetime.now().year - min(years) < 50:
            out["years_experience"] = str(datetime.now().year - min(years))
    edu_lines = []
    for r in _csv_rows(files.get("education.csv", "")):
        edu_lines.append(", ".join(x for x in (r.get("degree name"), r.get("notes"), r.get("school name")) if x))
    if edu_lines:
        education_details(edu_lines, out)
        school = next((r.get("school name") for r in _csv_rows(files.get("education.csv", "")) if r.get("school name")), "")
        if school and not out.get("university"):
            out["university"] = school
    skills = [r.get("name", "") for r in _csv_rows(files.get("skills.csv", "")) if r.get("name")]
    if skills:
        out["skills"] = ", ".join(skills)[:400]
    return {k: v for k, v in out.items() if v}


def linkedin_import(name, b64):
    """A LinkedIn PDF or export .zip -> profile details (nothing is saved here; the app asks add/replace first)."""
    data = base64.b64decode(b64 or "")
    if not data:
        raise ValueError("The file was empty")
    if len(data) > 30 * 1024 * 1024:
        raise ValueError("That file is too big (30 MB max)")
    ext = Path(name or "").suffix.lower()
    if data[:4] == b"%PDF":
        ext = ".pdf"
    elif data[:2] == b"PK":
        ext = ".zip"
    if ext not in (".pdf", ".zip", ".csv"):
        raise ValueError("Use your LinkedIn profile PDF or the data export .zip")
    tmp = DATA_DIR / ("linkedin-import" + ext)
    tmp.write_bytes(data)
    try:
        if ext == ".pdf":
            found = parse_cv(tmp)
            # the PDF's own links: "www.linkedin.com/in/name (LinkedIn)"
            found.pop("website", None) if "linkedin.com" in found.get("website", "") else None
            return found
        if ext == ".csv":                       # just Positions.csv on its own
            import zipfile
            z = DATA_DIR / "linkedin-import.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("Positions.csv", data.decode("utf-8", "replace"))
            try:
                return linkedin_export(z)
            finally:
                z.unlink(missing_ok=True)
        return linkedin_export(tmp)
    finally:
        tmp.unlink(missing_ok=True)
