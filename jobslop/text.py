"""Small text helpers: HTML to text, dates, salaries."""

import html
import re
from datetime import datetime, timedelta, timezone


def strip_html(text, limit=600):
    if not text:
        return ""
    text = html.unescape(html.unescape(str(text)))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def to_date(value):
    """Turn epoch numbers, ISO strings or dd/mm/yyyy into 'YYYY-MM-DD'."""
    if value in (None, "", 0):
        return ""
    try:
        s = str(value)
        if isinstance(value, (int, float)) or s.isdigit():
            return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%d")
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
        if m:
            return f"{m[3]}-{m[2]}-{m[1]}"
        return s[:10]
    except Exception:
        return ""


def money(lo, hi, cur="USD"):
    sym = {"GBP": "£", "USD": "$", "EUR": "€", "INR": "₹", "JPY": "¥", "AUD": "A$", "CAD": "C$",
           "NZD": "NZ$", "SGD": "S$", "HKD": "HK$", "BRL": "R$", "ZAR": "R", "CHF": "CHF ",
           "PLN": "zł ", "SEK": "kr ", "NOK": "kr ", "DKK": "kr ", "MXN": "MX$"}.get((cur or "").upper())

    def fmt(n):
        try:
            n = float(n)
        except (TypeError, ValueError):
            return None
        if n <= 0:
            return None
        return f"{n/1000:.0f}k" if n >= 1000 else f"{n:.0f}"
    lo, hi = fmt(lo), fmt(hi)
    pre = sym or (cur + " ")
    if lo and hi and lo != hi:
        return f"{pre}{lo}–{pre}{hi}"
    if lo or hi:
        return f"{pre}{lo or hi}"
    return ""


def rel_date(text):
    """'3 days ago', 'Just posted', '30+ days ago', '2d', '24h' -> YYYY-MM-DD."""
    if not text:
        return ""
    s = str(text).lower()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    if any(w in s for w in ("just", "today", "hour", "minute")) or re.fullmatch(r"\d+\s*h", s.strip()):
        days = 0
    else:
        m = re.search(r"(\d+)\s*\+?\s*(d|day|w|week|mo|month)", s)
        if not m:
            return to_date(text)
        n, unit = int(m[1]), m[2]
        days = n * (30 if unit.startswith("mo") else 7 if unit.startswith("w") else 1)
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")      # calendar days, so clock changes don't matter


def short_date(text):
    """'24 Oct' / '3 days ago' -> YYYY-MM-DD (ZipRecruiter UK)."""
    s = (text or "").strip()
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3})", s)
    if m:
        try:
            d = datetime.strptime(f"{m[1]} {m[2]} {datetime.now().year}", "%d %b %Y")
            if d > datetime.now():
                d = d.replace(year=d.year - 1)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return rel_date(s)
