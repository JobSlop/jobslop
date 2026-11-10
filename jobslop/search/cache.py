"""Reusing recent results from a board instead of asking it again.

The cache lives in memory and is copied to cache.json (so it survives a restart). Two searches asking a
board the same thing at the same time share one request. A cache that can't be read or saved (a full
disk, a damaged file) never costs a search its results.
"""

import json
import threading
import time

from jobslop.boards.base import Cancelled, NotHere
from jobslop.boards.registry import BOARDS
from jobslop.config import DATA_DIR
from jobslop.settings import replace_file

CACHE_FILE = DATA_DIR / "cache.json"
KEEP_SECONDS = 24 * 3600          # older results are dropped
MAX_ENTRIES = 150                 # newest searches kept (about 30 jobs each)
cache_lock = threading.Lock()
_mem = {"data": None, "mtime": None}
_inflight: dict[str, dict] = {}   # key -> {"done": Event, "jobs": [...], "error": Exception}


def _mtime():
    try:
        return CACHE_FILE.stat().st_mtime_ns
    except OSError:
        return None


def load_cache():
    """The cache (call with cache_lock held). Re-read only when cache.json changed since we last saw it."""
    m = _mtime()
    if _mem["data"] is None or m != _mem["mtime"]:
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            _mem["data"] = data if isinstance(data, dict) else {}
        except Exception:
            _mem["data"] = {}
        _mem["mtime"] = m
    return _mem["data"]


def _save(c):
    """Write cache.json safely: a new file swapped in, so a crash or full disk never leaves half a file."""
    tmp = CACHE_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(c), encoding="utf-8")
        replace_file(tmp, CACHE_FILE)
        _mem["mtime"] = _mtime()
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def cache_key(name, q, opts):
    return json.dumps([name, q.lower(), opts["where"].lower(), opts["miles"], opts["country"], opts["local"],
                       opts["posted"], opts["jtype"], opts["remote"], opts["salary_min"]])


def fetch_cached(name, q, opts, fresh):
    """Run one source for one query, reusing recent results. Returns (jobs, from_cache)."""
    board = BOARDS.get(name)
    if board is None:
        raise NotHere("switched off - turn it on in Settings → Plugins")
    key = cache_key(name, q, opts)
    with cache_lock:
        hit = load_cache().get(key)
        if hit and not fresh and isinstance(hit, dict) and time.time() - hit.get("t", 0) < board.cache_seconds:
            return hit.get("jobs") or [], True
        waiting = _inflight.get(key)
        if waiting is None:
            waiting = _inflight[key] = {"done": threading.Event(), "jobs": None, "error": None, "since": time.time()}
            mine = True
        else:
            mine = False
    if not mine:                      # the same search is already running: use its answer
        cancel = opts.get("cancel")
        while not waiting["done"].wait(0.25):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            if time.time() - waiting["since"] > 600:
                raise TimeoutError("took too long")
        if isinstance(waiting["error"], Cancelled):
            return fetch_cached(name, q, opts, fresh)     # that one was stopped: ask the board ourselves
        if waiting["error"] is not None:
            raise waiting["error"]
        if waiting["jobs"] is None:
            raise TimeoutError("took too long")
        return waiting["jobs"], True
    try:
        jobs = board.search(q, opts)
        waiting["jobs"] = jobs
    except BaseException as e:
        waiting["error"] = e
        raise
    finally:
        with cache_lock:
            _inflight.pop(key, None)
        waiting["done"].set()
    if isinstance(jobs, list):
        with cache_lock:
            now = time.time()
            c = {k: v for k, v in load_cache().items()
                 if isinstance(v, dict) and now - v.get("t", 0) < KEEP_SECONDS}
            c[key] = {"t": now, "jobs": jobs}
            if len(c) > MAX_ENTRIES:
                c = dict(sorted(c.items(), key=lambda kv: kv[1]["t"])[-MAX_ENTRIES:])
            _mem["data"] = c
            _save(c)
    return jobs, False
