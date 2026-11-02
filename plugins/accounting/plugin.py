"""Accounting: ICAEW and ACCA job boards, accounting profile fields and accounting job titles in other languages."""

import html
import re
import urllib.parse
from datetime import datetime

api = None                                     # set by register()

# job titles, so a search for "accountant" in the Netherlands also finds "boekhouder"
TERMS = {
    "nl": {"accountant": ["boekhouder", "financieel administrateur"], "bookkeeper": ["boekhouder"],
           "auditor": ["controller", "auditor"], "financial controller": ["controller"],
           "accounts payable": ["crediteurenadministrateur"], "accounts receivable": ["debiteurenadministrateur"],
           "tax advisor": ["belastingadviseur", "fiscalist"], "payroll": ["salarisadministrateur"]},
    "es": {"accountant": ["contable", "contador"], "bookkeeper": ["auxiliar contable"], "auditor": ["auditor"],
           "financial controller": ["controller financiero"], "accounts payable": ["cuentas a pagar"],
           "accounts receivable": ["cuentas a cobrar"], "tax advisor": ["asesor fiscal"], "payroll": ["técnico de nóminas"]},
    "da": {"accountant": ["revisor", "bogholder", "regnskabsmedarbejder"], "bookkeeper": ["bogholder"],
           "auditor": ["revisor"], "financial controller": ["controller"], "accounts payable": ["kreditorbogholder"],
           "accounts receivable": ["debitorbogholder"], "tax advisor": ["skatterådgiver"], "payroll": ["lønbogholder"]},
}


def register(_api):
    global api
    api = _api
    api.add_board("ICAEW", src_icaew, "Chartered accountancy jobs (ICAEW)", country_native=True)
    api.add_board("ACCA", src_acca, "Accounting & finance jobs (ACCA Careers)", country_native=True)
    for lang, terms in TERMS.items():
        api.add_search_terms(lang, terms)


def madgex_feed(source, base, q, o, pages=4, keep_unknown=False):
    """ICAEW / ACCA job boards share the same RSS format: 'Company: Title' + 'salary: company: text. Place (CC)'."""
    cc = o["country"]
    strip = api.text.strip_html
    out = []
    for page in range(1, pages + 1):
        x = api.http.get_text(f"{base}/jobsrss/?" + urllib.parse.urlencode({"keywords": q, "page": page}))
        items = re.findall(r"<item>(.*?)</item>", x, re.S)
        for it in items:
            title = html.unescape(strip((re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1]))
            desc = html.unescape(strip((re.search(r"<description>(.*?)</description>", it, re.S) or [None, ""])[1], 1500))
            link = html.unescape((re.search(r"<link>(.*?)</link>", it, re.S) or [None, ""])[1]).split("?")[0]
            pub = (re.search(r"<pubDate>(.*?)</pubDate>", it, re.S) or [None, ""])[1]
            company, _, role = title.partition(": ")
            if not role:
                company, role = "", title
            m = re.search(r"([^.:]{2,80})\s\(([A-Z]{2})\)\s*$", desc)
            if m:
                where, pcc = m[1].strip(), m[2]
            else:
                where = api.geo.town_at_end(desc, cc)
                pcc = cc if where else None
            if o["local"] and (pcc != cc if pcc else not keep_unknown):
                continue                          # these boards are worldwide; keep your country
            salary = desc.split(":")[0] if desc.count(":") >= 2 and len(desc.split(":")[0]) < 80 else ""
            try:
                date = datetime.strptime(pub[:16], "%a, %d %b %Y").strftime("%Y-%m-%d")
            except ValueError:
                date = ""
            out.append(api.jobs.make(source, role, company, link, where, date,
                                     salary if re.search(r"\d", salary) else "", "", ["accounting"], desc, remote=False))
        if len(items) < 20:
            break
    return out


def src_icaew(q, o):
    """ICAEW Jobs - chartered accountancy jobs (mostly UK)."""
    return madgex_feed("ICAEW", "https://www.icaewjobs.com", q, o, keep_unknown=(o["country"] == "GB"))


def src_acca(q, o):
    """ACCA Careers - accounting & finance jobs worldwide."""
    return madgex_feed("ACCA", "https://jobs.accaglobal.com", q, o)
