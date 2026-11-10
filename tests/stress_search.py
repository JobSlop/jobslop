"""Stress test for search (not part of the normal test run: python tests/stress_search.py).

Throws odd searches, odd jobs from boards, failing boards, many searches at once and a broken
cache at the search engine and the app's own server, using fake boards (no internet), and
reports anything that crashes or comes back wrong.
"""
import json
import random
import sys
import threading
import time
import traceback
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from support import AppServer, FakeBoards, base_opts, make_job, no_internet, reset_data  # noqa: E402

from jobslop.boards import base as board_base  # noqa: E402
from jobslop.search import cache as search_cache  # noqa: E402
from jobslop.search import engine  # noqa: E402

PROBLEMS = []
random.seed(7)


def short(e):
    """Where an error happened (the last line of app code) and what it was, on one line."""
    tb = [f for f in traceback.extract_tb(e.__traceback__) if "jobslop" in f.filename and "tests" not in f.filename]
    at = f"{Path(tb[-1].filename).name}:{tb[-1].lineno} {tb[-1].line}" if tb else "?"
    return f"{type(e).__name__}: {e} @ {at}"


def problem(what, detail=""):
    PROBLEMS.append(f"{what}: {detail}")
    print("  PROBLEM", what, str(detail)[:300])


ODD_QUERIES = [
    "c++", "C#", ".net", "c++ developer", "(senior)", "[lead]", "dev\\ops", "*", "?", "+", "a|b", "^$",
    "ux/ui designer", "front-end", "node.js", "r&d engineer", "q/a", "100% remote", "€50k", "😀 job",
    "Projectleider", "ingeniør", "développeur", "数据分析", ",", ",,,", " , , ", "the", "a, the, of",
    "x" * 300, "data analyst, " * 30, "manager,manager,MANAGER", "senior .net developer (remote)",
    "\t\n", "'; DROP TABLE jobs; --", "<script>alert(1)</script>", "%", "%%", "\\", "\"quoted\"",
]
WORDS = ["developer", "engineer", "manager", "analyst", "nurse", "teacher", ".net", "c#", "python", "senior",
         "junior", "remote", "sales", "data", "designer", "accountant", "game", "artist", "c++", "react"]


def odd_job(source, i):
    title = " ".join(random.choice(WORDS + ["(", ")", "[", "?", "C++", "ASP.NET", "Développeur"]) for _ in range(random.randint(1, 5)))
    j = make_job(source, title, company=random.choice(["Acme", "", "Ünïcødé Ltd", "A&B"]),
                 location=random.choice(["Birmingham, UK", "", "Remote", "Remote (US only)", "London", "Nowhere, ZZ",
                                         "Daytona Beach, FL", "Amsterdam, Netherlands"]),
                 desc=random.choice(["", "Work with C# and ASP.NET Core.", "x" * 5000, "Python, Django, remote friendly.",
                                     "<b>HTML</b> &amp; stuff", None]),
                 url=random.choice([f"https://e.com/{source}/{i}", "", None]))
    if random.random() < .2:
        j["date"] = random.choice(["", "2026-11-01", "not a date", None])
    if random.random() < .1:
        j["tags"] = random.choice([None, ["a", None], "notalist"])
    if random.random() < .05:
        j["title"] = None
    return j


def run_engine(boards, query, **opts):
    fake = FakeBoards(boards)
    with fake.installed():
        return engine.search(query, list(boards), base_opts(**opts), fresh=True)


def check_result(out, where):
    for j in out["results"]:
        for k in ("title", "company", "url", "location", "score", "title_match", "source"):
            if k not in j:
                problem(f"{where}: result without {k}", j)
                return
        if not j["url"]:
            problem(f"{where}: result without a link", j)
    json.dumps(out)


def stage(name):
    print(f"\n== {name}")


def engine_fuzz():
    stage("odd searches against odd jobs (search engine)")
    sources = ["LinkedIn", "Indeed", "Glassdoor"]
    for q in ODD_QUERIES + [" ".join(random.sample(WORDS, random.randint(1, 4))) for _ in range(150)]:
        boards = {s: [odd_job(s, i) for i in range(random.randint(0, 25))] for s in sources}
        for where in ("", "Birmingham", "B3 2BJ", "Austin, TX", "Nowhere at all", "United Kingdom"):
            try:
                out = run_engine(boards, q, where=where, intern=random.random() < .2)
                check_result(out, f"q={q[:40]!r} where={where!r}")
            except Exception as e:
                problem(f"engine crashed for q={q[:40]!r} where={where!r}", short(e))
                break


def plugin_shaped_jobs():
    stage("boards that give jobs in other shapes")
    cases = {
        "job under another board's name": [make_job("Some Other Board", "Python Developer")],
        "missing tags/desc keys": [{"source": "LinkedIn", "title": "Python Developer", "company": "A", "url": "https://e.com/1",
                                   "location": "Birmingham, UK", "date": "", "salary": "", "type": ""}],
        "None everywhere": [{"source": "LinkedIn", "title": None, "company": None, "url": "https://e.com/2", "location": None,
                             "date": None, "salary": None, "type": None, "tags": None, "desc": None, "remote": None}],
        "numbers instead of text": [{"source": "LinkedIn", "title": 123, "company": 4, "url": "https://e.com/3", "location": 5,
                                     "date": 20261101, "salary": 50000, "type": 1, "tags": [1, 2], "desc": 7, "remote": 0}],
        "board returns None": None,
        "board returns a dict": {"title": "x"},
        "board returns strings": ["Python Developer"],
    }
    for label, jobs in cases.items():
        try:
            fake = FakeBoards({"LinkedIn": jobs})
            fake.jobs_by_board["LinkedIn"] = jobs
            with fake.installed(), mock.patch.object(FakeBoards, "installed", FakeBoards.installed):
                # bypass dict(j) in the fake so odd shapes reach the engine as the board gave them
                board = board_base.Board("LinkedIn", lambda q, o, jobs=jobs: jobs)
                with mock.patch.dict(engine.BOARDS._boards, {"LinkedIn": board}, clear=True):
                    out = engine.search("python developer", ["LinkedIn"], base_opts(), fresh=True)
            check_result(out, label)
            st = out["status"].get("LinkedIn", {})
            print(f"  {label}: {len(out['results'])} results, status {st}")
        except Exception as e:
            problem(f"engine crashed: {label}", short(e))


def failing_boards():
    stage("boards that fail in different ways")
    errs = {"plain": RuntimeError("boom"), "empty message": RuntimeError(""), "key error": KeyError("x"),
            "timeout": TimeoutError("timed out"), "http 429": RuntimeError("HTTP Error 429: Too Many Requests"),
            "not here": board_base.NotHere(""), "needs key": board_base.NeedsKey("x"), "unicode": RuntimeError("✗ ünïcødé"),
            "huge message": RuntimeError("x" * 100000)}
    for label, e in errs.items():
        try:
            out = run_engine({"LinkedIn": e, "Indeed": [make_job("Indeed", "Python Developer")]}, "python developer")
            st = out["status"]["LinkedIn"]
            if not st.get("error"):
                problem(f"failing board shows no error: {label}", st)
            if len(out["results"]) != 1:
                problem(f"one failing board lost the others' results: {label}", out["results"])
        except Exception as ex:
            problem(f"engine crashed when a board failed: {label}", repr(ex))


def broken_cache():
    stage("cache that can't be read or written")
    jobs = {"LinkedIn": [make_job("LinkedIn", "Python Developer")]}
    search_cache.CACHE_FILE.write_text("{not json", encoding="utf-8")
    try:
        out = run_engine(jobs, "python developer")
        if len(out["results"]) != 1:
            problem("corrupt cache file lost results", out["status"])
    except Exception as e:
        problem("corrupt cache file crashed the search", repr(e))
    real_write = Path.write_text

    def full_disk(self, *a, **k):
        if self == search_cache.CACHE_FILE:
            raise OSError(28, "No space left on device")
        return real_write(self, *a, **k)
    with mock.patch.object(Path, "write_text", full_disk):
        try:
            out = run_engine(jobs, "python developer")
            if len(out["results"]) != 1:
                problem("full disk: the board's jobs were thrown away", out["status"])
        except Exception as e:
            problem("full disk crashed the search", repr(e))
    search_cache.CACHE_FILE.unlink(missing_ok=True)


def board_turned_off():
    stage("searching a board that is no longer there (plugin switched off)")
    try:
        out = run_engine({"LinkedIn": [make_job("LinkedIn", "Python Developer")]}, "python developer")
        fake = FakeBoards({"LinkedIn": [make_job("LinkedIn", "Python Developer")]})
        with fake.installed():
            out = engine.search("python developer", ["LinkedIn", "Gone Board"], base_opts(), fresh=False)
        if "Gone Board" not in out["status"]:
            problem("a board that's gone gets no status (screen shows 0 and no reason)", out["status"])
        # cached result for a board that then disappears
        with mock.patch.dict(engine.BOARDS._boards, {}, clear=True):
            search_cache.fetch_cached  # noqa
            try:
                search_cache.fetch_cached("LinkedIn", "python developer", base_opts(), False)
            except AttributeError as e:
                problem("cache lookup for a missing board crashes", repr(e))
            except Exception:
                pass
    except Exception as e:
        problem("missing board crashed the search", short(e))


def server_load():
    stage("many searches at once through the app's server")
    reset_data()
    boards = {s: [odd_job(s, i) for i in range(30)] for s in ("LinkedIn", "Indeed", "Glassdoor")}

    def slow(name):
        def src(q, o):
            time.sleep(random.uniform(0, .3))
            if random.random() < .1:
                raise RuntimeError("random failure")
            return [dict(j) for j in boards[name]]
        return src
    fakes = {n: board_base.Board(n, slow(n), country_native=True, location_aware=True) for n in boards}
    srv = AppServer()
    from jobslop.runtime import state
    errors, times, lock = [], [], threading.Lock()
    try:
        with mock.patch.dict(engine.BOARDS._boards, fakes, clear=True):
            def one(i):
                q = random.choice(ODD_QUERIES[:20] + WORDS)
                src = random.choice(list(boards))
                path = "/api/search?" + urllib.parse.urlencode({"q": q, "where": random.choice(["", "Birmingham", "B3 2BJ"]),
                                                               "country": random.choice(["GB", "US", "NL", "XX", ""]),
                                                               "miles": random.choice(["15", "abc", "-5", "1e9", ""]),
                                                               "sources": src, "fresh": random.choice(["0", "1"])})
                t = time.time()
                try:
                    code, body, _ = srv.request(path, headers={"Host": f"127.0.0.1:{state['port']}"} if state.get("port") else None)
                except Exception as e:
                    with lock:
                        errors.append(f"{q!r} {src}: no answer ({e!r})")
                    return
                with lock:
                    times.append(time.time() - t)
                    if code != 200 or not isinstance(body, dict) or "results" not in body:
                        errors.append(f"{q!r} {src}: {code} {str(body)[:150]}")
            with ThreadPoolExecutor(24) as ex:
                list(ex.map(one, range(300)))
    finally:
        srv.close()
    if errors:
        problem(f"{len(errors)} of 300 server searches failed", errors[:5])
    times.sort()
    if times:
        print(f"  300 searches: median {times[len(times) // 2]:.2f}s, slowest {times[-1]:.2f}s")
    try:
        json.loads(search_cache.CACHE_FILE.read_text(encoding="utf-8"))
        print(f"  cache file OK ({search_cache.CACHE_FILE.stat().st_size // 1024} KB)")
    except Exception as e:
        problem("cache file broken after many searches at once", repr(e))


if __name__ == "__main__":
    with no_internet():
        reset_data()
        for fn in (engine_fuzz, plugin_shaped_jobs, failing_boards, broken_cache, board_turned_off, server_load):
            try:
                fn()
            except Exception as e:
                problem(f"{fn.__name__} itself crashed", short(e))
    print(f"\n{len(PROBLEMS)} problem(s)")
    for p in PROBLEMS:
        print(" -", p[:400])
