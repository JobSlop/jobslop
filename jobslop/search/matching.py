"""Scoring how well a job matches a search, and the user's job match terms."""

import re

from jobslop.settings import load_settings

STOPWORDS = {"a", "an", "the", "and", "or", "of", "for", "in", "to", "job", "jobs", "remote"}


# Other ways adverts write the same thing, so ".net" also finds "ASP.NET" and "dotnet", and "dev"
# finds "developer". One way only: a search for "developer" shouldn't turn up every "engineer".
SYNONYMS = {
    ".net": ["dotnet", "asp.net", "net core"], "dotnet": [".net"], "c#": ["csharp", "c sharp"],
    "js": ["javascript"], "javascript": ["js"], "ts": ["typescript"], "typescript": ["ts"],
    "node": ["node.js", "nodejs"], "react": ["react.js", "reactjs"], "vue": ["vue.js", "vuejs"],
    "dev": ["developer", "development", "programmer", "engineer"], "developer": ["dev", "programmer"],
    "programmer": ["developer"], "sr": ["senior"], "senior": ["sr"], "jr": ["junior"], "junior": ["jr"],
    "qa": ["quality assurance", "tester"], "ux": ["user experience"], "ui": ["user interface"],
    "hr": ["human resources"], "pm": ["project manager", "product manager"], "ml": ["machine learning"],
    "ai": ["artificial intelligence", "machine learning"], "k8s": ["kubernetes"],
    "frontend": ["front-end", "front end"], "backend": ["back-end", "back end"],
    "fullstack": ["full-stack", "full stack"], "devops": ["dev ops", "site reliability"],
    "admin": ["administrator", "administration"], "mgr": ["manager"],
}
W_TITLE, W_TITLE_ALT, W_TAG, W_DESC = 10, 8, 5, 3


def query_words(q):
    """The words of a search, as the matcher uses them (".net" and "c#" stay whole)."""
    out = []
    for w in re.findall(r"[a-z0-9+#.]+", (q or "").lower()):
        w = w if w.startswith(".") else w.rstrip(".")
        if w and w.strip(".") and w not in STOPWORDS:
            out.append(w)
    return out


def _pattern(w):
    # ".net" may follow letters (ASP.NET, VB.NET); other words need a word edge. Plurals count.
    before = "" if w.startswith(".") else r"(?<![a-z0-9])"
    plural = "(?:s|es)?" if re.fullmatch(r"[a-z]{3,}", w) else ""
    return before + re.escape(w).replace(r"\ ", r"[\s-]") + plural + r"(?![a-z0-9#+])"


def _find(text, w, alts=True):
    """Where w (or another way of writing it) first shows up in text: (start, end, exact) or None."""
    for i, form in enumerate([w] + (SYNONYMS.get(w, []) if alts else [])):
        m = re.search(_pattern(form), text)
        if m:
            return m.start(), m.end(), i == 0
    return None


def _snippet(desc, at):
    s, e = max(0, at[0] - 70), min(len(desc), at[1] + 90)
    while s > 0 and desc[s - 1] not in " \n":
        s -= 1
    return ("…" if s else "") + " ".join(desc[s:e].split()) + ("…" if e < len(desc) else "")


def match(j, words, phrase):
    """How well a job fits the search words, looking at the title, tags and the advert text.

    Returns {"score", "title_match" (every word is in the title), "where" ("title"/"desc"/""),
    "snippet" (the part of the advert that mentions it, when the title doesn't)}."""
    if not words:                       # "Any job" mode: everything matches, newest first
        return {"score": 1, "title_match": True, "where": "", "snippet": ""}
    title, tags, desc_raw = j["title"].lower(), " ".join(j["tags"]).lower(), j["desc"] or ""
    desc = desc_raw.lower()
    total, in_title, found, first_desc = 0, 0, 0, None
    for w in words:
        t = _find(title, w)
        if t:
            in_title += 1
            found += 1
            total += W_TITLE if t[2] else W_TITLE_ALT
            continue
        if _find(tags, w):
            found += 1
            total += W_TAG
            continue
        d = _find(desc, w)
        if d:
            found += 1
            total += W_DESC
            first_desc = first_desc or d
    if not (tags or desc):
        # nothing but a title to go on (LinkedIn, Glassdoor): the board searched the full advert itself,
        # so most of the words in the title is enough
        if in_title * 2 < len(words) or not in_title:
            return {"score": 0, "title_match": False, "where": "", "snippet": ""}
    elif found < len(words):            # every word must be somewhere in the advert
        return {"score": 0, "title_match": False, "where": "", "snippet": ""}
    if len(words) > 1 and _find(title, phrase, alts=False):
        total += 15                     # the words together, in order, in the title
    elif len(words) > 1 and _find(desc, phrase, alts=False):
        total += 4
    where = "title" if in_title == len(words) else ("desc" if first_desc else "title")
    snippet = _snippet(desc_raw, first_desc) if first_desc and in_title < len(words) else ""
    return {"score": total, "title_match": in_title == len(words), "where": where, "snippet": snippet}


def score(j, words, phrase, strict):
    m = match(j, words, phrase)
    return m["score"] if not strict or m["title_match"] else 0


# ---- job match terms: user-defined job names with aliases, optionally matched in the job TITLE only
# e.g. {"name": "Communications", "aliases": ["comms", "PR", "public relations"], "title_only": True}
# so "communication" listed as a skill in a description doesn't count as a communications job.

def match_groups():
    out = []
    for g in load_settings().get("match_terms", []):
        name = str(g.get("name", "")).strip()
        aliases = [a.strip() for a in (g.get("aliases") or []) if str(a).strip()]
        if name:
            out.append({"name": name, "aliases": aliases, "title_only": bool(g.get("title_only", True))})
    return out


def find_group(q, groups):
    ql = q.strip().lower()
    return next((g for g in groups if ql == g["name"].lower() or ql in (a.lower() for a in g["aliases"])), None)


def phrase_in(text, phrase):
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])", text) is not None


def group_score(j, g):
    title = j["title"].lower()
    terms = [g["name"]] + g["aliases"]
    hits = [t for t in terms if phrase_in(title, t)]
    if hits:
        return 40 + (5 if phrase_in(title, g["name"]) else 0)
    if not g["title_only"]:
        rest = (" ".join(j["tags"]) + " " + j["desc"]).lower()
        if any(phrase_in(rest, t) for t in terms):
            return 4
    return 0
