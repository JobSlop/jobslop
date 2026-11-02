"""Fetching web pages and JSON."""

import json
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (personal JobFinder app)"}


# ---------------------------------------------------------------- helpers

def get_json(url, timeout=20, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# ---- country boards: Denmark, Netherlands, US; and ArtStation (art / games, worldwide)

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


# ---- ZipRecruiter UK, games (Work With Indies) and accounting (ICAEW, ACCA) boards

def fetch_html(url, timeout=25):
    with urllib.request.urlopen(urllib.request.Request(url, headers={**BROWSER_UA, "Accept-Language": "en-GB,en;q=0.9"}),
                                timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")
