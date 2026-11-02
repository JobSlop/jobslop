"""How long a job lasts ("6-month contract", "Permanent") and spotting internships."""

import re

# ---------------------------------------------------------------- matching

# ---- how long the job lasts: "6-month contract", "12-month fixed term", "Maternity cover", "Permanent"
_UNIT = r"(months?|mths?|mos?|weeks?|wks?|years?|yrs?|maanden|maand|måneder|måned|monate?n?|mois|meses)"
_KIND = (r"(fixed[\s-]?term|ftc|contract|contractor|temp|temporary|placement|internship|secondment|role|position|"
         r"assignment|project|engagement|maternity|cover|opdracht|tijdelijk|kontrakt|vikariat|befristet|stage|praktik)")
INTERN_RE = re.compile(r"\bintern\b|internship|placement year|industrial placement|year in industry|work placement|"
                       r"graduate (scheme|programme|program)|\btrainee|\bstage\b|stagiair|stagiaire|\bpraktik|"
                       r"werkstudent|summer analyst|\bco-?op\b|apprentice", re.I)


def contract_length(j):
    """(label, months) — months is 1000 for permanent, 500 for a contract of unknown length, None if not stated."""
    t = " ".join([j.get("title", ""), j.get("type", ""), j.get("desc", "")])[:4000].lower()
    m = re.search(r"(\d{1,2})(?:\s*(?:-|–|to)\s*(\d{1,2}))?[\s-]*" + _UNIT + r"\b[\s-]*(?:\w+[\s-]+)?" + _KIND, t) or \
        re.search(_KIND + r"\D{0,30}?\b(?:of|for|length|duration|period|lasting|van|på)?\W{0,3}(\d{1,2})(?:\s*(?:-|–|to)\s*"
                  r"(\d{1,2}))?\s*" + _UNIT + r"\b", t)
    if m:
        g = m.groups()
        if g[0] and g[0][0].isdigit():
            lo, hi, unit, kind = g[0], g[1], g[2], g[3]
        else:
            kind, lo, hi, unit = g[0], g[1], g[2], g[3]
        n = int(hi or lo)
        months = n * 12 if unit.startswith(("y", "å")) and not unit.startswith("må") else \
            max(1, round(n / 4.345)) if unit.startswith("w") else n
        if 0 < months <= 60:
            what = "maternity cover" if re.match(r"maternity|cover|vikariat", kind) else \
                "internship" if re.match(r"intern|placement|stage|praktik", kind) else \
                "fixed term" if re.match(r"fixed|ftc|befristet|tijdelijk", kind) else "contract"
            span = f"{lo}–{hi}" if hi else lo
            unit_word = "year" if unit.startswith(("y", "å")) and not unit.startswith("må") else \
                "week" if unit.startswith("w") else "month"
            return f"{span}-{unit_word} {what}", months
    if re.search(r"maternity (leave )?cover|mat cover|parental leave cover|barselsvikariat|zwangerschapsvervanging", t):
        return "Maternity cover", 12
    if re.search(r"summer internship|summer placement|zomerstage|sommerpraktik", t):
        return "Summer internship", 3
    if re.search(r"\bpermanent\b|vast contract|vaste baan|fast stilling|fastansættelse|unbefristet|\bcdi\b", t):
        return "Permanent", 1000
    if re.search(r"fixed[\s-]?term|\btemporary\b|\btemp\b|\bcontract\b(?! manager| management| law)|freelance|interim|"
                 r"tijdelijk|vikariat|befristet", t):
        return "Contract", 500
    return "", None
