"""Reading details (name, contact, jobs, education) out of CV text to pre-fill the profile."""

import re
from datetime import datetime
from pathlib import Path

from jobslop.geo.cities import _norm, code_for_country_text, find_city
from jobslop.geo.countries import COUNTRIES, US_STATE_NAMES, US_STATES
from jobslop.profile.cvtext import clean_text, cv_text, line_key
from jobslop.profile.ocr import ocr_pdf

JOB_WORDS = (r"engineer|developer|programmer|manager|analyst|designer|nurse|assistant|assistent|officer|consultant|"
             r"konsulent|\blead\b|director|directeur|technician|specialist|co-?ordinator|coördinator|koordinator|"
             r"executive|administrator|\bintern\b|internship|teacher|lecturer|tutor|architect|arkitekt|scientist|"
             r"researcher|advisor|adviser|adviseur|rådgiver|associate|representative|supervisor|accountant|"
             r"bookkeeper|boekhouder|bogholder|clerk|operative|operator|worker|\bcook\b|\bkok\b|driver|chauffeur|"
             r"artist|writer|editor|producer|tester|\bqa\b|head of|owner|founder|apprentice|trainee|volunteer|"
             r"vrijwilliger|frivillig|carer|caregiver|care giver|bartender|barista|cashier|waiter|waitress|"
             r"receptionist|secretary|secretaresse|sekretær|merchandiser|\bstaff\b|team member|crew|cleaner|porter|"
             r"housekeeper|nanny|freelance|self-employed|zelfstandig|medewerker|medewerkster|verkoper|beheerder|"
             r"docent|leraar|verpleegkundige|monteur|stagiair|medarbejder|medhjælper|ingeniør|ingenieur|"
             r"sygeplejerske|pædagog|\bleder\b|sælger|praktikant|værnepligtig|chef\b|president|\bvp\b|\bcto\b|"
             r"\bceo\b|\bcfo\b|\bpartner\b|\bagent\b|planner|buyer|inspector|electrician|plumber|mechanic|"
             r"labourer|laborer|warehouse|picker|packer|attendant|steward|hostess|instructor|\bcoach\b|therapist|"
             r"pharmacist|doctor|physician|surgeon|dentist|paramedic|midwife|support worker|fellow\b|postdoc|"
             r"ambassador|promoter|sales\b|salesperson|server\b")
MONTHS = r"(?:jan|feb|maart|mar|mrt|apr|may|mei|maj|jun|jul|aug|sep|oct|okt|nov|dec|spring|summer|fall|autumn|" \
         r"winter|zomer|sommer|forår|efterår)[a-zæøåé]*\.?"
DAY = r"(?:\d{1,2}(?:st|nd|rd|th|\.)?\s+)"
DAY_AFTER = r"(?:\s+\d{1,2}(?:st|nd|rd|th)?\b,?)"            # US style: "January 18th", "Jan 18, 2023"
ONE_DATE = (r"(?:" + DAY + r"?" + MONTHS + DAY_AFTER + r"?\s*,?\s*(?:19|20)\d{2}|\d{1,2}\s*[/.\-]\s*(?:19|20)\d{2}"
            r"|(?:19|20)\d{2})")
PRESENT = r"present|pres\.?|current(?:ly)?|now|date|today|ongoing|tot heden|heden|nu|huidig|d\.d\.|dags dato|i dag|aktuell|heute"
DATE_RANGE = (r"(?<![\w/])(" + ONE_DATE + r"|" + DAY + r"?" + MONTHS + DAY_AFTER + r"?)\s*(?:-|–|—|−|to|until|till|tot|til|bis)\s*("
              + ONE_DATE + r"|" + PRESENT + r")(?!\w)")
DURATION = r"\(?\s*(?:approx\.?|approximately|ca\.?|about|around|circa|over|ruim|omkring|cirka)?\s*(\d{1,2})\+?\s*" \
           r"(?:years?|yrs?|jaar|år)\s*\)?"


STREET_WORDS = (r"street|st|road|rd|avenue|ave|lane|ln|drive|dr|close|way|court|ct|place|pl|crescent|cres|grove|"
                r"terrace|gardens|gdns|boulevard|blvd|parkway|pkwy|highway|hwy|circle|cir|square|sq|mews|row|walk|"
                r"hill|park|view|rise|green")
STREET = (r"(?:\b\d{1,5}[A-Za-z]?\s+(?:[A-Z][\w'\-]*\s+){0,4}(?:" + STREET_WORDS + r")\b\.?"
          r"|\b[A-ZÆØÅÄÖÜ][\wæøåäöüß\-]*(?:straat|weg|laan|plein|gracht|kade|singel|dijk|gade|vej|allé|alle|stræde|"
          r"strasse|straße|gasse|platz)\s+\d{1,4}[a-zA-Z]?\b)")
UNIT_RE = r"^(apt|apartment|unit|suite|ste|flat|room|#|floor|fl)\b\.?"
UK_POSTCODE = r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b"
NL_POSTCODE = r"\b(\d{4}\s?[A-Z]{2})\s+([A-Z][\w'\-]+(?:[ \-][A-Z][\w'\-]+)?)"
EU_POSTCODE = r"\b(?:[A-Z]{1,2}-)?(\d{4,5})\s+([A-ZÆØÅÄÖÜ][\wæøåäöüß\-]+(?: [A-ZÆØÅÄÖÜ][\wæøåäöüß\-]+)?)"
US_PLACE = r"([A-Z][A-Za-z.'\-]+(?: [A-Z][A-Za-z.'\-]+){0,3}),\s*([A-Z]{2})\b\.?(?:\s+(\d{5})(?:-\d{4})?)?"
EXTRA_COUNTRIES = {"korea": "KR", "south korea": "KR", "republic of korea": "KR", "s.korea": "KR", "s. korea": "KR",
                   "nl": "NL", "dk": "DK", "the uk": "GB", "united states": "US", "u.s.a.": "US", "deutschland": "DE"}
PARTICLES = {"van", "de", "der", "den", "von", "la", "le", "da", "di", "du", "del", "della", "ten", "ter", "te",
             "bin", "al", "el", "dos", "das", "do", "'t", "op", "het"}
NAME_SKIP = (r"curriculum|vitae|\bcv\b|r[eé]sum[eé]|eksempel|voorbeeld|sample|example|template|your name|name here|"
             r"lebenslauf|personal|personlige|persoonlijke|contact|profile|profil|address|adres|page \d|references|"
             r"available|request|dear |sincerely|regards|kind |hiring|hello|united kingdom|universit|college|school|"
             r"institut|academy|hogeschool|gymnasium|\binc\b|\bltd\b|limited|\bgroup\b|\bin\b|\bof\b|\band\b|&")
HEADINGS = [
    ("experience", r"((relevant|work|professional|employment|career|industry|volunteer(ing)?|other|previous|additional|"
                   r"recent|selected|teaching|research|work and volunteer) )*(experience|history|employment)|"
                   r"employment( history)?|career( history| summary)?|work history|(werk|praktijk|relevante )?ervaring|"
                   r"werkervaring|arbeidsverleden|loopbaan|werkgeschiedenis|(erhvervs|arbejds|relevant )?erfaring|"
                   r"beskæftigelse|(berufs|praktische |berufliche )?erfahrung|beruflicher werdegang|research|"
                   r"internships?|placements?|volunteer work|work placements?"),
    ("education", r"education|qualifications|academic( background| history| qualifications)?|educational background|"
                  r"opleiding(en)?|educatie|onderwijs|scholing|uddannelse(r)?|(schul)?ausbildung|bildung|studies|"
                  r"studie|training and education|education, training"),
    ("skills", r"((key|technical|core|relevant|professional|personal|transferable|it|computer|soft|hard|other|"
               r"additional|digital) )*(skills|competencies|competences|abilities|expertise|strengths|proficiencies)|"
               r"skills summary|vaardigheden|competenties|kwaliteiten|kennis|kompetencer|færdigheder|kvalifikationer|"
               r"it-?(kompetencer|kennis|vaardigheden)|kenntnisse|fähigkeiten|it"),
    ("summary", r"((personal|professional|career) )?(profile|summary|statement|objective)|about( me)?|"
                r"(persoonlijk )?profiel|over mij|profil|om mig|resumé|sammenfatning|kurzprofil"),
    ("personal", r"personal (details|information|data|info)|contact( details| information| info| me)?|details|"
                 r"persoonlijke gegevens|personalia|contactgegevens|personlige (oplysninger|data)|kontakt(oplysninger)?|"
                 r"persönliche (daten|angaben)|location|address|adres|adresse|woonplaats"),
    ("languages", r"languages?( skills)?|talen|taalvaardigheid|sprog(kundskaber)?|sprachen(kenntnisse)?"),
    ("other", r"interests|hobbies|hobby'?s|references|referees|certifications?|certificates|courses|training|"
              r"achievements|awards|hono(u)?rs|volunteering|projects|publications|availability|interesses|referenties|"
              r"cursussen|certificaten|nevenactiviteiten|fritidsinteresser|interesser|referencer|kurser|"
              r"frivilligt arbejde|hobbys|interessen|referenzen|weiterbildung|cover letter|declaration|"
              r"additional information|activities|extra[- ]?curricular( activities)?|leadership|memberships|"
              r"nevenfuncties|bestuursfuncties|tillidshverv"),
]


def collapse_spaced(s):
    """'P R O F I L E' -> 'PROFILE', 'N a a m' -> 'Naam' (letter-spaced headings)."""
    groups = re.split(r"\s{2,}", s)
    out = []
    for g in groups:
        toks = g.split(" ")
        if len(toks) >= 4 and all(len(t) <= 2 for t in toks) and sum(len(t) == 1 for t in toks) >= len(toks) * 0.6:
            g = "".join(toks)
        out.append(g)
    return " ".join(out)


def heading_key(line):
    s = collapse_spaced(line).strip(" :-–—_•|*#").lower()
    s = re.sub(r"\s+", " ", s)
    if not s or len(s) > 50:
        return None
    for key, pat in HEADINGS:
        if re.fullmatch(r"(" + pat + r")((,| and| &| og| en| und) [\w' ]{2,25})?", s):
            return key
    return None


def country_code(text):
    t = (text or "").strip(" .").lower()
    return code_for_country_text(t) or EXTRA_COUNTRIES.get(t)


def country_label(cc):
    return COUNTRIES[cc][0] if cc in COUNTRIES else cc


def is_place(s, strict=True):
    """A town, 'Town, Country', 'Town, ST', a country, or a line with a postcode."""
    s = s.strip(" ,.;()")
    if not s or len(s.split()) > 8 or re.search(r"@|https?:|www\.", s):
        return False
    if re.search(UK_POSTCODE, s) or re.search(NL_POSTCODE, s) or re.fullmatch(US_PLACE, s):
        return True
    if country_code(s):
        return True
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) >= 2:
        last = parts[-1]
        us = last in US_STATES or last.lower() in US_STATE_NAMES
        if not (country_code(last) or us or find_city(last) or last.lower() in ("england", "scotland", "wales")):
            return False
        cc = country_code(last) or ("US" if us else None) or \
            ("GB" if last.lower() in ("england", "scotland", "wales") else None) or (find_city(last) or [None] * 4)[3]
        return bool(find_city(parts[0], cc) or (cc and not strict and len(parts) == 2 and not is_title(parts[0])))
    row = find_city(s)
    return bool(row and (not strict or row[5] >= 15000))


def is_title(s):
    return bool(re.search(JOB_WORDS, s, re.I))


def tidy_caps(s):
    """'SUE RYDER' -> 'Sue Ryder', keeps short acronyms ('BRAVISSIMO HQ' -> 'Bravissimo HQ')."""
    if s.isupper() and len(re.sub(r"\W", "", s)) > 4 and not re.fullmatch(r"[A-Z&]{2,6}", s.strip()):
        small = {"of", "and", "the", "in", "for", "at", "on", "de", "van"}         # one short word = brand/acronym (NASCAR)
        words = s.split()
        return " ".join(w.lower() if w.lower() in small and i else w.capitalize() if len(w) > 3 or not w.isalpha() else w
                        for i, w in enumerate(words))
    return s


def tidy_description(lines):
    """Re-join wrapped lines, keep bullets, and turn 'ProjectC++•UE4•Git' into 'Project — C++, UE4, Git'."""
    out = []
    for ln in lines:
        ln = re.sub(r"\b(the|a|an|of|on|in|for|to|and|with)([A-Z])", r"\1 \2", ln)   # "theSea" -> "the Sea"
        if ln.count("•") >= 2 and not ln.startswith("• "):
            segs = [s.strip() for s in ln.split("•") if s.strip()]
            m = re.match(r"(.*[a-z)\]])([A-Z][\w#+.]*)$", segs[0])
            name = ""
            if m:
                name, segs[0] = m[1].strip(), m[2]
            out.append((name + " — " if name else "") + ", ".join(segs))
            continue
        if out and not ln.startswith("• ") and not re.search(r"[.!?:]$", out[-1]) and " — " not in out[-1] \
                and ln[:1].islower():
            out[-1] += " " + ln                      # continuation of a wrapped line
        else:
            out.append(ln)
    return "\n".join(out).strip()


def norm_dates(text):
    """'May '20' -> 'May 2020'; drop LinkedIn's '(2 yrs 3 mos)' / '(1 year 2 months)' after a date range."""
    yy = datetime.now().year % 100
    text = re.sub(r"(?<=[a-z.]\s)'(\d{2})\b", lambda m: ("20" if int(m[1]) <= yy + 1 else "19") + m[1], text,
                  flags=re.I)
    text = re.sub(r"\s*·?\s*\((?:\s*\d+\+?\s*(?:yrs?|years?|mos?|months?|jaar|maanden|år|måneder))+\s*\)", "", text,
                  flags=re.I)
    return re.sub(r"\s*·\s*(?:\d+\+?\s*(?:yrs?|mos?)\s*)+$", "", text, flags=re.I)


def find_dates(text):
    """(start, end, matched span) for a date range, a single date, or a duration like '5 years'."""
    m = re.search(DATE_RANGE, text, re.I)
    if m:
        start, end = m[1], m[2]
        before = re.search(r"(" + ONE_DATE + r")\s*$", text[:m.start()], re.I)
        if before and not re.search(r"(19|20)\d{2}", start):
            start = before[1]                                   # "10th Feb 2025 Apr- June 2026"
            span = (before.start(), m.end())
        else:
            span = (m.start(), m.end())
        if not re.search(r"(19|20)\d{2}", start):
            y = re.search(r"(19|20)\d{2}", end)
            if y:
                start = re.sub(r"(\d)(st|nd|rd|th)?\s*,?$", r"\1\2", start.strip())
                start += " " + y[0]                             # "June - Sept 2024"
        start = re.sub(r"^\d{1,2}(st|nd|rd|th|\.)?\s+(?=[a-z])", "", start.strip(), flags=re.I)
        end = re.sub(r"^\d{1,2}(st|nd|rd|th|\.)?\s+(?=[a-z])", "", end.strip(), flags=re.I)
        # "January 18th 2023" -> "January 2023" (the day isn't needed)
        start, end = (re.sub(r"\b(" + MONTHS + r")\s+\d{1,2}(?:st|nd|rd|th)?\b,?", r"\1", x, flags=re.I) for x in (start, end))
        end = "Present" if re.fullmatch(PRESENT, end, re.I) else end
        return start.title() if not start[:1].isdigit() else start, end.title() if end[:1].isalpha() else end, span, None
    stripped = text.strip(" ,|–-()")
    if re.fullmatch(DURATION, stripped, re.I):
        return "", "", (0, len(text)), int(re.fullmatch(DURATION, stripped, re.I)[1])
    if re.fullmatch(r"\(?(" + ONE_DATE + r")\)?", stripped, re.I):
        return stripped.strip("()").title(), "", (0, len(text)), None
    # a month/season + year at the end of a heading line: "Marketing Intern, Kraft Heinz — Chicago, IL  Summer 2018"
    m = re.search(r"(?:\s|\|)\(?(" + DAY + r"?" + MONTHS + r"\s*,?\s*(?:19|20)\d{2})\)?\s*$", text, re.I)
    if m and len(text[:m.start()].split()) <= 12:
        return re.sub(r"^\d{1,2}(st|nd|rd|th|\.)?\s+", "", m[1]).title(), "", (m.start(), len(text)), None
    return None


def small_town(s):
    """A smaller town (5,000+ people) named after a comma in a job heading: "Codemasters, Southam"."""
    s = s.strip(" ,.;()")
    row = find_city(s) if 0 < len(s.split()) <= 3 else None
    return bool(row and not is_title(s) and _norm(row[0]) == _norm(s))


def split_header(lines):
    """Turn a job's heading lines into (title, company, location)."""
    segs, loc = [], ""
    for ln in lines:
        if re.search(UK_POSTCODE, ln) or re.search(NL_POSTCODE, ln) or (re.search(r"\d", ln) and ln.count(",") >= 2):
            if not loc:
                m = re.search(r"([A-Za-z][\w' \-]+?)\s*,?\s*" + UK_POSTCODE, ln) or re.search(NL_POSTCODE, ln)
                if m and re.search(UK_POSTCODE, m[0]):
                    loc = tidy_caps(m[1].split(",")[-1].strip())
                elif m:
                    loc = tidy_caps(m[2])
                else:
                    loc = tidy_caps(ln.split(",")[-1].strip(" ."))
            continue
        for major in re.split(r"\s+[–—|•·@]\s+|\s+-\s+|\s*\|\s*|\s+at\s+|\t", ln):
            cp = [p.strip(" .;:()") for p in major.split(",") if p.strip(" .;:()")]
            cut = len(cp)
            for k in range(min(3, len(cp)), 0, -1):
                if (len(cp) > k or segs) and (is_place(", ".join(cp[-k:])) or
                                             k == 1 and len(segs) + len(cp) > 2 and small_town(cp[-1])):
                    if not loc:
                        loc = ", ".join(cp[-k:])
                    cut = len(cp) - k
                    break
            segs += cp[:cut]
    segs = [tidy_caps(s) for s in segs if s]
    title = next((s for s in segs if is_title(s)), "")
    rest = [s for s in segs if s != title]
    if not title and rest:
        title = rest.pop(0)
    company = rest[0] if rest else ""
    if not loc and len(rest) > 1 and (is_place(rest[1]) or small_town(rest[1])):
        loc = rest[1]
    return title, company, loc


def parse_jobs(items, allowed):
    """items: [{'t': text, 'b': bullet?, 'sec': section}] — find each job by its dates, then its heading lines."""
    def headerish(it):
        t = it["t"]
        w = len(t.split())
        address = bool(re.search(UK_POSTCODE, t) or re.search(NL_POSTCODE, t))
        return (not it["b"] and not it.get("head") and len(t) <= 95 and w <= 12 and not t.endswith(":")
                and not (t.endswith(".") and w > 6 and not address) and not it.get("date") and not t[:1].islower())

    anchors = []
    for i, it in enumerate(items):
        if it["sec"] not in allowed or it.get("head") or (it["b"] and len(it["t"]) > 70):
            continue
        d = find_dates(it["t"])
        if d:
            rest = re.sub(r"\(\s*\)|\[\s*\]", " ", it["t"][:d[2][0]] + " " + it["t"][d[2][1]:])   # "Intern (dates), NASCAR"
            rest = re.sub(r"\s+,", ",", rest).strip(" ,|–-()\t")
            if rest and not is_title(rest) and is_place(rest, strict=False):
                it["loc"], rest = rest, ""                    # "June 2014 – Sep 2014 | Mountain View, CA"
            if len(rest.split()) <= 14:
                it["date"] = True
                anchors.append((i, d, rest))
    if not anchors:
        return [], 0

    def take(i, step, limit, stop):
        got, j = [], i + step
        while 0 <= j < len(items) and len(got) < limit and j != stop and headerish(items[j]) \
                and items[j]["sec"] == items[i]["sec"]:
            got.append(j)
            j += step
        return got if step > 0 else got[::-1]

    def plan(layout):
        out, prev_end = [], -1
        for n, (i, d, rest) in enumerate(anchors):
            nxt = anchors[n + 1][0] if n + 1 < len(anchors) else len(items)
            rest_parts = len([p for p in re.split(r"\s+[–—|•·@-]\s+|,\s+|\s*\|\s*|\s+at\s+", rest) if p.strip()])
            if rest_parts >= 2:
                hdr = []
            elif layout == "before":
                hdr = [j for j in take(i, -1, 3 - bool(rest), prev_end) if j > prev_end] or take(i, 1, 3, nxt)
            else:
                hdr = take(i, 1, 3, nxt) or [j for j in take(i, -1, 2, prev_end) if j > prev_end]
            out.append(hdr)
            prev_end = max([i] + hdr)
        return out

    def quality(p):
        return sum(any(is_title(items[j]["t"]) for j in hdr) for hdr in p)
    before, after = plan("before"), plan("after")
    chosen = after if quality(after) > quality(before) else before

    jobs, total_dur = [], 0
    starts = [min([a[0]] + h) for a, h in zip(anchors, chosen)]
    for n, ((i, d, rest), hdr) in enumerate(zip(anchors, chosen)):
        lines = ([rest] if rest else []) + [items[j]["t"] for j in hdr]
        title, company, loc = split_header(lines)
        loc = loc or items[i].get("loc", "")
        end_at = starts[n + 1] if n + 1 < len(anchors) else len(items)
        desc = []
        if d[3]:
            desc.append(f"{d[3]} years")
            total_dur += d[3]
        for k, it in enumerate(items[max([i] + hdr) + 1:end_at]):
            if it.get("head") or it["sec"] not in allowed:
                break
            if k == 0 and not loc and not it["b"] and len(it["t"].split()) <= 7 and is_place(it["t"], strict=False):
                loc = it["t"]                                   # LinkedIn puts the place on the line under the dates
                continue
            desc.append(("• " if it["b"] else "") + it["t"])
        if title or company:
            jobs.append({"title": title, "company": company, "location": loc, "start": d[0], "end": d[1],
                         "description": tidy_description(desc)[:2000]})
    return jobs[:15], total_dur


def find_phone(text, regions, with_region=False):
    """Phone number via Google's libphonenumber (the 'phonenumbers' library), trying likely countries in turn."""
    try:
        import phonenumbers as pn
    except Exception:
        return None
    year_range = r"\(?(19|20)\d\d\s*[-–/]\s*((19|20)\d\d|\d\d)\)?"
    for region in regions:
        for m in pn.PhoneNumberMatcher(text, region, leniency=pn.Leniency.VALID):
            raw = m.raw_string.strip(" .-")
            if re.fullmatch(year_range, raw) or re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-](19|20)\d\d", raw):
                continue
            region_of = pn.region_code_for_number(m.number)
            region_of = "GB" if region_of in ("GG", "JE", "IM") else region_of   # UK mobiles shared with the islands
            return (raw, region_of) if with_region else raw
    return None


def split_street(street, out):
    """'1234 Elm St, Apt 5B' -> address1 '1234 Elm St', address2 'Apt 5B' ('Flat 2, 8 Queen St' the other way)."""
    parts = [p.strip() for p in re.split(r",\s*|\s+(?=(?:apt|apartment|unit|suite|ste|#)\b\.?\s*\w)", street,
                                         flags=re.I) if p and p.strip(" ,")]
    if not parts:
        return
    if len(parts) > 1 and re.match(UNIT_RE, parts[0], re.I):
        parts = parts[1:2] + parts[:1] + parts[2:]
    out["address1"] = parts[0]
    if len(parts) > 1:
        out["address2"] = ", ".join(parts[1:])


FIELD_LABELS = [
    ("Email", r"e-?mail( address)?|mail|correo|e-?post"),
    ("Phone", r"phone( number)?|mobile( number)?|mob|tel(ephone)?|cell( phone)?|telefoon|mobiel|telefon|mobil|tlf\.?|gsm|contact number"),
    ("Address", r"location|address|home address|city|town|based in|lives in|residence|woonplaats|adres|adresse|bop[æa]l|wohnort|by"),
    ("Website", r"website|web|portfolio|homepage|site"),
    ("LinkedIn", r"linked\s?in"),
    ("Name", r"(full )?name|naam|navn"),
]


def ocr_to_text(lines):
    """OCR lines -> CV text in reading order, with each field label joined to its value ("Email: me@x.com").
    Values are matched by position: right under the label (stacked fields) or beside it on the same row."""
    if not lines:
        return "", {}
    out_text, meta = [], {}
    for page in sorted({l["page"] for l in lines}):
        ls = sorted([dict(l) for l in lines if l["page"] == page], key=lambda l: (l["y"], l["x"]))
        W = ls[0]["w"]
        hs = sorted(l["h"] for l in ls if l["h"])
        med = hs[len(hs) // 2] if hs else 20
        # 1. labels -> values
        pairs = []
        for lab in ls:
            name = next((n for n, pat in FIELD_LABELS if re.fullmatch(r"\W*(" + pat + r")\W*", lab["t"].strip(), re.I)), None)
            if not name or lab.get("used"):
                continue
            below = [c for c in ls if c is not lab and not c.get("used") and abs(c["x"] - lab["x"]) < max(3 * lab["h"], 40)
                     and 0 < c["y"] - lab["y"] < 5 * max(lab["h"], med)]
            beside = [c for c in ls if c is not lab and not c.get("used") and abs(c["y"] - lab["y"]) < 0.7 * max(lab["h"], med)
                      and 0 < c["x"] - lab["x"] < W * 0.45]
            pick = min(below, key=lambda c: c["y"]) if below else min(beside, key=lambda c: c["x"]) if beside else None
            if pick and not any(re.fullmatch(r"\W*(" + pat + r")\W*", pick["t"].strip(), re.I) for _, pat in FIELD_LABELS):
                lab["used"] = pick["used"] = True
                pairs.append(f"{name}: {pick['t'].strip()}")
        # 2. big lines near the top that belong together (a name split over two lines)
        rest = [l for l in ls if not l.get("used")]
        top = [l for l in rest if l["y"] < ls[-1]["y"] * 0.3 and l["h"] >= 1.8 * med]
        if len(top) > 1:
            joined = " ".join(l["t"].strip() for l in top)
            if len(joined.split()) <= 5:
                for l in top[1:]:
                    l["used"] = True
                top[0]["t"] = joined
        rest = [l for l in rest if not l.get("used")]
        # 3. reading order: columns when the page clearly has a right-hand column
        right = [l for l in rest if l["x"] >= W * 0.45]
        left = [l for l in rest if l["x"] < W * 0.3]
        two_col = len(right) >= 6 and len(left) >= 6
        rest.sort(key=lambda l: ((l["x"] >= W * 0.45) if two_col else 0, l["y"], l["x"]))
        for l in rest:
            meta.setdefault(line_key(l["t"]), {"size": l["h"], "bold": False})
        out_text += pairs + [l["t"] for l in rest]
    return "\n".join(out_text), meta


def education_details(edu_lines, out):
    """Highest qualification, subject and school from education lines (CV or LinkedIn)."""
    levels = [("PhD", r"\bph\.?\s?d\b|doctorate|\bdphil\b|doctor of philosophy|promotieonderzoek"),
              ("Master's degree", r"\bmaster'?s?\b|\bkandidat\b|\bcand\.\s?\w+"),
              ("MSc", r"\bm\.?sc\b|\bm\.s\.(?!\w)"), ("MBA", r"\bmba\b"), ("MEng", r"\bmeng\b"), ("MA", r"\bm\.a\.(?!\w)|\bma\b(?= \(|\s+in\b)"),
              ("MRes", r"\bmres\b"), ("BSc", r"\bb\.?sc\b|\bb\.s\.(?!\w)"), ("BA", r"\bb\.?a\.?(?!\w)(?! level)"),
              ("BEng", r"\bbeng\b"), ("LLB", r"\bllb\b"), ("Bachelor's degree", r"bachelor|\bhbo\b|professionsbachelor"),
              ("Associate degree", r"\bassociate'?s?\b(?= (?:of|in|degree)\b)|\bassociate degree|\ba\.?a\.?s\.?\b|\ba\.s\.(?!\w)"),
              ("HND", r"\bhnd\b"), ("HNC", r"\bhnc\b"), ("Foundation degree", r"foundation degree"),
              ("Diploma", r"\bdiploma\b|erhvervsuddannelse|\bmbo\b"), ("A-Levels", r"\ba[- ]levels?\b"),
              ("BTEC", r"\bbtec\b"), ("GCSEs", r"\bgcses?\b"), ("Certificate", r"certificate|certificaat|certifikat")]
    found = None
    for name, pat in levels:
        line = next((ln for ln in edu_lines if re.search(pat, ln, re.I)), None)
        if line is not None:
            found = (name, pat, line)
            break
    if found:
        name, pat, line = found
        if name == "Master's degree" and re.search(r"\b(m\.?sc|m\.s\.)\b", line, re.I):
            name = "MSc"
        out["highest_qualification"] = name
        if name not in ("A-Levels", "GCSEs", "BTEC", "Certificate"):
            ln = re.sub(r"\(?\bhons\.?\b\)?|\((kandidat|bachelor|master)\)", " ", line, flags=re.I)
            sm = re.search(r"(?:" + pat + r")\.?\s*(?:degree\s*)?(?:\s*of\s+(?:arts|science|engineering|laws|fine arts|"
                           r"business administration|education|music|technology|applied science)\b)?\s*"
                           r"(?:[–—\-:,]\s*)?(?:\b(?:in|of|i|en|im)\b\s+)?"
                           r"([A-ZÀ-Þa-zæøå][\w&'’ ]{2,60})", ln, re.I)
            # LinkedIn style: "Bachelor of Arts - BA, English · (2015 - 2018)" -> the subject comes after the comma
            lk = re.search(r"(?:" + pat + r")((?:\s+of\s+(?:arts|science|engineering|laws|business administration|"
                           r"fine arts|education|music|technology))?(?:\s*[-–]\s*[\w.]+)?)\s*,\s*([^,·(\d]+)", ln, re.I)
            if lk and not re.search(r"universit|college|school|institut|gpa|grade", lk[2], re.I) \
                    and not re.fullmatch(MONTHS + r"\s*", lk[2].strip(), re.I) and len(lk[2].split()) <= 7:
                sm = None
                out["degree_subject"] = lk[2].strip(" .")
            if sm:
                subj = re.split(r",|\s{2}| - | – | — |\(|\d|\|", sm[1])[0].strip()
                subj = re.sub(r"^(som|as|als|als een)\s+", "", subj, flags=re.I)
                if subj and not re.search(r"universit|college|hogeschool|school|institut|akademi", subj, re.I) \
                        and len(subj.split()) <= 7:
                    out["degree_subject"] = subj
        if re.fullmatch(r"(science|arts?|bs|ba|bsc|msc|ma|ms|engineering|laws|beng|meng|degree|hons)",
                        out.get("degree_subject", "").strip(" .").lower()):
            out.pop("degree_subject")                  # "Bachelor of Science - BS" names the degree, not the subject
    inst_re = r"universit\w*|college|hogeschool|højskole|akademi\w*|academy|institut\w*|polytechnic|school of|" \
              r"\bschool\b|gymnasium|lyceum|\bsdu\b|\bdtu\b|\bku\b|\bcbs\b|\bmit\b|\bucl\b|\blse\b"
    best_inst, best_rank = "", 99
    for ln in edu_lines:
        for seg in re.split(r"\s*[,|–—(\)]\s*|\s+-\s+|\s{2,}", ln):
            seg = re.sub(r"\b(19|20)\d{2}\b.*", "", seg).strip(" .")
            m = re.search(inst_re, seg, re.I)
            if m and re.search(r"diploma|degree|bachelor|master|ged\b|certificate|a-?levels?|gcse", seg, re.I) \
                    and not re.match(r"univ|hogeschool|college", m[0], re.I):
                continue                                         # "High School Diploma" is the level, not the school
            if not m or len(seg.split()) > 9 or not m[0][0].isupper():
                continue
            rank = 0 if re.match(r"univ|hogeschool|højskole|akademi|polytech|instit|sdu|dtu|ku\b|cbs|mit|ucl|lse",
                                 m[0], re.I) else 1 if re.match(r"college|academy", m[0], re.I) else 2
            if rank < best_rank:
                best_inst, best_rank = seg, rank
    if best_inst:
        out["university"] = tidy_caps(re.sub(r"^the\s+", "", best_inst, flags=re.I))
    if out.get("degree_subject", "").isupper() and len(out["degree_subject"]) > 4:
        out["degree_subject"] = tidy_caps(out["degree_subject"] + " ") .strip() if " " in out["degree_subject"] \
            else out["degree_subject"].capitalize()


def parse_text(raw, meta=None):
    """Profile details from CV text (meta: optional font size/bold per line, from the PDF/Word reader)."""
    meta = meta or {}
    text = clean_text(raw)
    items, pending_bullet, sec = [], False, "top"
    for raw in text.splitlines():
        s = re.sub(r"\s+", " ", raw).strip()
        if not s or re.fullmatch(r"[\W_]+", s) and not re.fullmatch(r"[•·▪●◦‣∙*o]", s):
            continue
        if re.fullmatch(r"page \d+( of \d+)?|\d+\s*/\s*\d+|-\s*\d+\s*-", s, re.I):
            continue                               # page numbers
        if re.fullmatch(r"[•·▪●◦‣∙*o\-–]", s):
            pending_bullet = True                  # a bullet on its own line belongs to the next line
            continue
        info = meta.get(line_key(s), {})
        bullet = pending_bullet or s[:1] in "•·▪●◦‣∙-–*" or bool(re.match(r"o\s", s))
        pending_bullet = False
        s = norm_dates(re.sub(r"^(o\s+|[•·▪●◦‣∙\-–*|/\s]+)", "", s).strip())
        if not s:
            continue
        key = heading_key(s)
        if key:
            sec = key
            items.append({"t": collapse_spaced(s), "b": False, "sec": sec, "head": True,
                          "size": info.get("size", 0), "bold": info.get("bold", False)})
            continue
        prev = items[-1] if items else None
        if not bullet and prev and prev["b"] and len(prev["t"]) >= 65 and not re.search(r"[.!?]$", prev["t"]) \
                and not is_title(s) and not find_dates(s) and not info.get("bold"):
            prev["t"] += " " + s                       # the wrapped end of a long bullet point
            continue
        items.append({"t": s, "b": bullet, "sec": sec, "size": info.get("size", 0), "bold": info.get("bold", False),
                      "wordhead": info.get("heading", False)})

    # font cues (the idea behind OpenResume's parser): body text size, and big/bold short lines that are
    # section titles even when we don't know the word ("RESEARCH", "Volunteering & Community")
    sizes = sorted(it["size"] for it in items if it.get("size") and not it.get("head"))
    body = sizes[len(sizes) // 2] if sizes else 0
    first_head = next((n for n, it in enumerate(items) if it.get("head")), len(items))
    head_looks = {(round(it["size"]), it["bold"]) for it in items if it.get("head") and it.get("size")}
    if body and head_looks:
        sec = None
        for n, it in enumerate(items):
            if it.get("head"):
                sec = it["sec"]
                continue
            if n > first_head and not it["b"] and (round(it.get("size", 0)), it.get("bold")) in head_looks \
                    and it.get("size", 0) >= body * 1.08 and len(it["t"].split()) <= 4 \
                    and not re.search(r"[\d@|,]", it["t"]) and not is_title(it["t"]) and not find_dates(it["t"]):
                it["head"], sec = True, "other"
                it["sec"] = "other"
            elif sec and it["sec"] != sec:
                it["sec"] = sec
    lines = [it["t"] for it in items if not it.get("head")]
    flat = " ".join(lines)
    out = {}

    # where the personal details are: before the first main section, plus any contact/location section
    first_main = next((n for n, it in enumerate(items) if it.get("head") and it["sec"] in
                       ("experience", "education", "skills")), len(items))
    first_date = next((n for n, it in enumerate(items) if re.search(DATE_RANGE, it["t"], re.I)), len(items))
    top = [it for n, it in enumerate(items) if (n < min(first_main, first_date, 30) or it["sec"] == "personal")
           and not it.get("head")][:40]
    top_text = " | ".join(it["t"] for it in top)
    email_re = r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z]{2,10})+"
    phone_re = r"(?<![\w/.])(\(?\+?\(?\d[\d ()\-./]{6,18}\d)(?!\d)"

    m = re.search(email_re, top_text) or re.search(email_re, flat)
    if m:
        local_part, _, domain = m[0].partition("@")
        out["email"] = local_part + "@" + domain.lower()          # "Me@Gmail.com" -> "Me@gmail.com"
    m = re.search(r"(https?://)?(www\.)?linkedin\.com/in/\s?[\w%-]+/?", flat, re.I)
    if m:
        out["linkedin"] = ("https://" + re.sub(r"^https?://", "", m[0])).rstrip("/").replace(" ", "")
    m = re.search(r"(https?://)?(www\.)?github\.com/[\w-]+", flat, re.I)
    if m:
        out["github"] = "https://" + re.sub(r"^https?://", "", m[0])
    no_mail = re.sub(email_re, " ", re.sub(phone_re, " ", flat))
    for m in re.finditer(r"(https?://|www\.)[\w.-]+\.[a-z]{2,}(?:/[\w.-]+)*/?", no_mail, re.I):
        if not re.search(r"linkedin|github", m[0], re.I):
            url = re.sub(r"/[a-z]{1,3}$", "", m[0].rstrip("/"))    # drop icon junk like "/ne" stuck on the end
            out["website"] = url if url.startswith("http") else "https://" + url
            break

    # Phone: libphonenumber, trying the CV's own country first
    tld = re.search(r"\.([a-z]{2})$", out.get("email", "").lower())
    guess = None
    regions = [r for r in dict.fromkeys([guess, (tld[1].upper().replace("UK", "GB") if tld else None),
                                         "GB", "US", "NL", "DK", "DE", "IE", "AU", "CA", "IN"]) if r]
    label = re.search(r"(?:phone|tel(?:ephone)?|mobile|mob|cell|tlf|telefoon|mobiel|telefon|mobil|gsm)\.?\s*"
                      r"(?:nr\.?|no\.?)?\s*[:.]?\s*(\+?\(?\d[\d ()\-./]{6,18}\d)", flat, re.I)
    phone = (find_phone(label[1], regions, True) if label else None) or find_phone(top_text, regions, True) \
        or find_phone(flat[:3000], regions, True)
    phone, phone_cc = phone if phone else (None, None)
    if not phone:                                       # library missing or nothing valid: simple pattern
        for c in ([label[1]] if label else []) + re.findall(phone_re, top_text):
            digits = re.sub(r"\D", "", c)
            if 8 <= len(digits) <= 15 and not re.fullmatch(r"\(?(19|20)\d\d\s*[-–/]\s*((19|20)\d\d|\d\d)\)?", c.strip()):
                phone = c.strip(" .-")
                break
    if phone:
        out["phone"] = phone


    # Name: a labelled name, else the best capitalised 2-5 word line near the top (bigger text scores higher)
    def clean_line(t):
        t = re.sub(email_re, " | ", t)
        t = re.sub(r"(https?://|www\.)\S+|linkedin\.com\S*|github\.com\S*", " | ", t, flags=re.I)
        # take out just the phone number we found (a looser pattern would also eat ZIP codes next to it)
        return t.replace(out["phone"], " | ") if out.get("phone") else re.sub(phone_re, " | ", t)

    def name_words(seg):
        seg = collapse_spaced(seg).strip(" ,|•·-–:")
        if not seg or re.search(r"[@\d/\\:;(),]|https?|www\.", seg) or re.search(NAME_SKIP, seg, re.I) \
                or is_title(seg) or heading_key(seg):
            return None
        words = seg.split()
        if not 2 <= len(words) <= 5 or words[0] in PARTICLES or words[-1] in PARTICLES:
            return None
        for w in words:
            if w not in PARTICLES and not re.fullmatch(r"[A-ZÀ-ÞĀ-Ž][A-Za-zÀ-ÿĀ-ž'’.\-]*", w):
                return None
        if is_place(seg) or country_code(seg) or seg.lower() in US_STATE_NAMES or re.fullmatch(r"[Xx\s.]+", seg):
            return None                                   # "Xxxxx Xxxxxx" is a template placeholder
        return words
    local = re.sub(r"[^a-z]", " ", out.get("email", "").split("@")[0].lower())
    best, best_score = None, -99
    lm = re.search(r"(?:^|\|)\s*(?:full name|name|naam|navn|voornaam en achternaam)\s*[:\-–]\s*([^|]+)", top_text, re.I)
    if lm and name_words(lm[1].strip()):
        best = name_words(lm[1].strip())
    else:
        for n, it in enumerate([it for it in items[:22] if not it.get("head")][:18]):
            if it["b"]:
                continue
            big = min(8, max(0, (it.get("size", 0) / body - 1) * 10)) if body and it.get("size") else 0
            for k, seg in enumerate(re.split(r"\s*[|•·]\s*", clean_line(it["t"]))):
                words = name_words(seg)
                if not words:
                    continue
                score = 10 - n * 0.6 - k + big + (6 if any(len(w) > 2 and w.lower().strip(".") in local for w in words)
                                                  else 0)
                if score > best_score:
                    best, best_score = words, score
    if best:
        def name_case(w):
            if not (w.isupper() and len(w) > 2):
                return w
            w = "-".join(p.capitalize() for p in w.split("-"))
            w = re.sub(r"^([OD]['’])([a-z])", lambda m: m[1] + m[2].upper(), w)     # O'Connor, D'Souza
            return re.sub(r"^(Ma?c)([a-z]{3,})", lambda m: m[1] + m[2].capitalize(), w)  # McDonald, MacLeod
        words = [name_case(w) for w in best]
        cut = next((i for i in range(1, len(words)) if words[i] in PARTICLES), len(words) - 1)
        if len(words) >= 4 and cut == len(words) - 1 and not re.search(r"\.$", words[-2]):
            cut = len(words) - 2      # 4 names: Spanish/Latin American double surname ("Irene Elizabeth Valle Urriola")
        out["first_name"] = words[0]
        if cut > 1:
            out["middle_name"] = " ".join(words[1:cut])        # "Mads Kristian Jørgensen", "Michael J. Rodriguez"
        out["last_name"] = " ".join(words[cut:])
    name_line = " ".join(best or [])

    # Address
    def set_city(row_or_name, cc=None):
        if isinstance(row_or_name, tuple):
            out["city"], cc = row_or_name[0], cc or row_or_name[3]
        else:
            out["city"] = row_or_name
        if cc:
            out["country"] = country_label(cc)

    addr_lines = []
    for it in top:
        t = clean_line(it["t"])
        lab = re.match(r"\s*(?:home address|address|location|adres|woonplaats|adresse|bopæl|city|town|residence|"
                       r"based in|lives in)\s*[:\-–]\s*(.+)", t, re.I)
        t = lab[1] if lab else t
        t = re.sub(r"^(e-?mail|phone|tel|tlf|mobile|mobil|cell)\s*[:.]?", "", t, flags=re.I)
        for seg in re.split(r"\s*[|•·]\s*|\s{3,}", t):
            seg = seg.strip(" ,.;")
            if seg and collapse_spaced(seg).strip() != name_line and not heading_key(seg):
                addr_lines.append(seg)

    def street_before(n, seg, start):
        """Street part: text before the town on the same line, else the line above if it looks like a street."""
        same = seg[:start].strip(" ,")
        if same:
            return same
        if n and (re.search(STREET, addr_lines[n - 1]) or re.match(r"\d", addr_lines[n - 1])):
            return addr_lines[n - 1]
        return ""

    for n, seg in enumerate(addr_lines):
        up = seg.upper()
        pm = re.search(UK_POSTCODE, up)
        if pm and not re.search(r"\d{5}", seg):
            pc = pm[1]
            out["postcode"] = pc if " " in pc else pc[:-3] + " " + pc[-3:]
            parts = [p.strip() for p in seg[:pm.start()].split(",") if p.strip()]
            prev = [p for p in addr_lines[max(0, n - 3):n] if not re.search(r"@", p) and len(p) < 60]
            if not parts:
                parts = prev                                    # address written over several lines
            elif len(parts) == 1 and prev and re.match(r"\d", prev[-1]):
                parts = prev[-1:] + parts                       # "27 Crookes Park Road" / "Sheffield S10 2QQ"
            if parts:
                out["city"] = parts[-1]
                if len(parts) >= 2:
                    out["address1"] = parts[0]
                if len(parts) >= 3:
                    out["address2"] = ", ".join(parts[1:-1])
                if len(parts) >= 4:
                    out["address2"], out["county"], out["city"] = ", ".join(parts[1:-2]), parts[-1], parts[-2]
            if re.match(UNIT_RE, out.get("address1", ""), re.I) and out.get("address2"):
                out["address1"], out["address2"] = out["address2"], out["address1"]
            out["country"] = "United Kingdom"
            break
        m = re.search(NL_POSTCODE, seg)
        if m and find_city(m[2], "NL"):
            out["postcode"] = m[1][:4] + " " + m[1][-2:].strip()
            set_city(m[2], "NL")
            street = street_before(n, seg, m.start())
            if street:
                split_street(street, out)
            break
        m = re.search(EU_POSTCODE, seg)
        if m:
            town = re.sub(r"\s+[A-ZØ]$", "", m[2])               # "København N" -> "København"
            row = find_city(town)
            if row and row[3] in ("DK", "DE", "NO", "BE", "AT", "CH", "SE", "FI", "FR", "ES", "IT", "PT", "PL"):
                out["postcode"] = m[1]
                set_city(m[2] if row[0] != town else row[0], row[3])
                street = street_before(n, seg, m.start())
                if street:
                    split_street(street, out)
                break
        # US: "Springfield, IL 62704" / "Austin, Texas 78701" / "Brooklyn, NY"
        m = st = None
        for m in re.finditer(r"([A-Z][A-Za-z.'\-]+(?: [A-Z][A-Za-z.'\-]+){0,3}),\s*([A-Z]{2}|[A-Z][a-z]+(?: [A-Z][a-z]+)?)"
                             r"\b\.?(?:\s+(\d{5})(?:-\d{4})?)?", seg):
            st = m[2] if m[2] in US_STATES else US_STATE_NAMES.get(m[2].lower())
            if st and (m[3] or find_city(m[1], "US")):
                break
            st = None
        if m and st:
            out["city"], out["county"], out["country"] = m[1], st, "United States"
            if m[3]:
                out["postcode"] = m[3]
            street = street_before(n, seg, m.start())
            if street:
                split_street(street, out)
            break
    if "city" not in out:
        # no postcode: "12 High Street, Leamington Spa" / "Town, Country" / a lone big town
        for n, seg in enumerate(addr_lines[:25]):
            sm = re.search(STREET, seg)
            if sm:
                rest = [p.strip() for p in seg[sm.end():].split(",") if p.strip()]
                nxt = addr_lines[n + 1] if n + 1 < len(addr_lines) else ""
                cand = rest or [p.strip() for p in nxt.split(",") if p.strip()]
                rows = [(p, find_city(p)) for p in cand]
                rows = [(p, r) for p, r in rows if r]
                if rows:
                    split_street(seg[:sm.end()] if rest else seg, out)
                    set_city(rows[0][1])
                    cc = next((country_code(p) for p in cand if country_code(p)), None)
                    if cc:
                        out["country"] = country_label(cc)
                    break
            if re.search(r"\d", seg) or len(seg.split()) > 7:
                continue
            parts = [p.strip() for p in seg.split(",") if p.strip()]
            cc = country_code(parts[-1]) if parts else None
            if cc and len(parts) >= 2:
                rows = [find_city(p, cc) for p in parts[:-1]]
                rows = [r for r in rows if r]
                if rows:
                    set_city(max(rows, key=lambda r: r[5]), cc)
                else:
                    out["county"], out["country"] = parts[-2], country_label(cc)
                break
            if len(parts) == 1:
                row = find_city(parts[0])
                if row and (row[5] >= 50000 or any(it["sec"] == "personal" for it in top)):
                    set_city(row)
                    break

    # no address country? the phone's country code says where they are (+44 -> UK, +1 -> US/Canada)
    if out.get("phone") and not out.get("country") and phone_cc:
        out["country"] = country_label(phone_cc)

    # Sections
    def sec_lines(*keys):
        return [it for it in items if it["sec"] in keys and not it.get("head")]

    skills = []
    for it in sec_lines("skills"):
        t = re.sub(r"^[\w &/]{2,25}:\s*", "", it["t"])            # "Languages: Python, Go" -> "Python, Go"
        for s in re.split(r"[,;•·|]|\s{2,}", t):
            s = s.strip(" .-–")
            if s and not s.endswith(":") and len(s.split()) <= 8                     and not re.search(r"citizen|licen[cs]e|rijbewijs|kørekort|references|available|sponsorship", s, re.I) and s.lower() not in [x.lower() for x in skills]:
                skills.append(s)
    if skills:
        out["skills"] = ", ".join(skills)[:400].rsplit(",", 1)[0] if len(", ".join(skills)) > 400 else ", ".join(skills)

    has_exp = any(it.get("head") and it["sec"] == "experience" for it in items)
    allowed = {"experience"} if has_exp else {"top", "summary", "personal", "other", "experience"}
    jobs, total_dur = parse_jobs(items, allowed)
    if jobs:
        out["jobs"] = jobs
        cur = next((j for j in jobs if j["end"] == "Present"), jobs[0])
        out["current_title"], out["current_company"] = cur["title"], cur["company"]
        years = [int(y) for j in jobs for y in re.findall(r"(?:19|20)\d{2}", j["start"])]
        if years:
            span = datetime.now().year - min(years)
            if 0 < span < 50:
                out["years_experience"] = str(span)
        elif total_dur:
            out["years_experience"] = str(min(total_dur, 50))

    edu_items = sec_lines("education")
    edu_lines = [it["t"] for it in edu_items] or [ln for ln in lines if len(ln.split()) <= 14]
    education_details(edu_lines, out)

    if re.search(r"full (uk |clean )*driving licen[cs]e|driving licen[cs]e|driver'?s licen[cs]e|clean licen[cs]e|"
                 r"rijbewijs|kørekort|führerschein", flat, re.I):
        out["driving_licence"] = "Yes"
    if re.search(r"right to work in the uk|british (citizen|national)|uk citizen|settled status|u\.?s\.? citizen|"
                 r"eu citizen|permanent resident|green card holder|eligible to work|right to work", flat, re.I):
        out["right_to_work"] = "Yes"
        if not re.search(r"require[sd]? (visa )?sponsorship", flat, re.I):
            out["needs_sponsorship"] = "No"
    m = re.search(r"notice period\W+(\d+\s*(weeks?|months?|days?))", flat, re.I)
    if m:
        out["notice_period"] = m[1]

    return {k: v for k, v in out.items() if v and (k == "jobs" or len(str(v)) < 500)}


def parse_cv(path):
    """Read a CV file. PDFs whose name/email are drawn as shapes (or scanned) are also read with OCR,
    which fills in whatever the text layer was missing."""
    meta = {}
    raw = cv_text(path, meta)
    out = parse_text(raw, meta)
    if Path(path).suffix.lower() == ".pdf" and (len(raw.strip()) < 300 or not out.get("first_name") or not out.get("email")):
        lines = ocr_pdf(path)
        if lines:
            text, ometa = ocr_to_text(lines)
            seen = parse_text(text, ometa)
            if len(raw.strip()) < 300:
                out = seen                                    # scanned CV: OCR is all there is
            else:
                for k, v in seen.items():
                    if k == "jobs":
                        if not out.get("jobs"):
                            out["jobs"] = v
                    elif not out.get(k):
                        out[k] = v
            out["read_with_ocr"] = "yes"
    return out
