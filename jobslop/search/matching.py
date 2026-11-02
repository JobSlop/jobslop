"""Scoring how well a job matches a search, and the user's job match terms."""

import re

from jobslop.settings import load_settings

STOPWORDS = {"a", "an", "the", "and", "or", "of", "for", "in", "to", "job", "jobs", "remote"}


def score(j, words, phrase, strict):
    if not words:                       # "Any job" mode: everything matches, newest first
        return 1
    title = j["title"].lower()
    tags = " ".join(j["tags"]).lower()
    desc = j["desc"].lower()

    def has(text, w):
        return re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text) is not None

    t = sum(has(title, w) for w in words)
    g = sum(has(tags, w) for w in words)
    d = sum(has(desc, w) for w in words)
    if strict and t < len(words):
        return 0
    if t == 0 and g < len(words) and d < len(words):
        return 0
    # Rank on the title so sites without descriptions (LinkedIn, Glassdoor) aren't pushed down
    if t:
        return 10 * t + (15 if phrase in title else 0)
    return 3 * g + d


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
