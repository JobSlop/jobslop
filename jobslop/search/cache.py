"""Reusing recent results from a board instead of asking it again."""

import json
import threading
import time

from jobslop.boards.registry import BOARDS
from jobslop.config import DATA_DIR

CACHE_FILE = DATA_DIR / "cache.json"
cache_lock = threading.Lock()


def load_cache():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fetch_cached(name, q, opts, fresh):
    """Run one source for one query, reusing recent results. Returns (jobs, from_cache)."""
    key = json.dumps([name, q.lower(), opts["where"].lower(), opts["miles"], opts["country"], opts["local"],
                      opts["posted"], opts["jtype"], opts["remote"], opts["salary_min"]])
    board = BOARDS.get(name)
    ttl = board.cache_seconds
    with cache_lock:
        hit = load_cache().get(key)
    if hit and not fresh and time.time() - hit["t"] < ttl:
        return hit["jobs"], True
    jobs = board.search(q, opts)
    with cache_lock:
        c = {k: v for k, v in load_cache().items() if time.time() - v["t"] < 24 * 3600}
        c[key] = {"t": time.time(), "jobs": jobs}
        CACHE_FILE.write_text(json.dumps(c), encoding="utf-8")
    return jobs, False
