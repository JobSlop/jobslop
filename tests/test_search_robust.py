"""Search keeps working when boards, plugins, the cache or the disk misbehave, and can be stopped.

Each test here is a bug found by stress testing (tests/stress_search.py) that used to make a search
come back empty or "failed".
"""
import threading
import time
from pathlib import Path
from unittest import mock

from support import FakeBoards, base_opts, make_job, no_internet, reset_data

from jobslop.boards import base as board_base
from jobslop.boards import linkedin
from jobslop.search import cache as search_cache
from jobslop.search import engine
from jobslop.search.matching import match, query_words


def run(boards, query="python developer", fresh=True, **opts):
    fake = FakeBoards(boards)
    with fake.installed():
        return engine.search(query, list(boards), base_opts(**opts), fresh=fresh), fake


def with_board(search_fn, name="LinkedIn", **facts):
    return mock.patch.dict(engine.BOARDS._boards, {name: board_base.Board(name, search_fn, **facts)}, clear=True)


def setup_function(_):
    reset_data()


def test_one_odd_job_does_not_sink_the_rest():
    good = make_job("LinkedIn", "Python Developer", "Good")
    odd = [{"source": "LinkedIn", "title": None, "url": "https://e.com/1"},                       # no title
           {"source": "LinkedIn", "title": "Python Developer", "company": None, "url": "https://e.com/2",
            "location": None, "tags": None, "desc": None, "date": "not a date"},                    # Nones
           {"title": "Python Developer", "company": 5, "url": "https://e.com/3", "location": 7,
            "tags": "x", "desc": 9, "date": 20261101},                                               # numbers
           "not a job", None]
    with with_board(lambda q, o: [good, *odd]):
        out = engine.search("python developer", ["LinkedIn"], base_opts(), fresh=True)
    assert out["status"]["LinkedIn"]["error"] is None
    assert {j["company"] for j in out["results"]} == {"Good", "", "5"}
    for j in out["results"]:
        assert isinstance(j["tags"], list) and isinstance(j["desc"], str) and isinstance(j["location"], str)
        assert j["date"] == "" or len(j["date"]) == 10


def test_jobs_shown_under_another_name_count_for_their_board():
    out, _ = run({"Some Board": [make_job("Shown As Something Else", "Python Developer")]})
    assert out["status"]["Some Board"]["found"] == 1
    assert out["results"][0]["source"] == "Shown As Something Else" and "board" not in out["results"][0]


def test_a_board_answer_that_is_not_a_list_is_an_error_not_a_crash():
    for answer in (None, {"title": "x"}, "text"):
        with with_board(lambda q, o, a=answer: a):
            out = engine.search("python developer", ["LinkedIn"], base_opts(), fresh=True)
        assert out["results"] == [] and out["status"]["LinkedIn"]["error"], answer


def test_an_error_without_a_message_still_says_something():
    out, _ = run({"LinkedIn": RuntimeError(""), "Indeed": [make_job("Indeed", "Python Developer")]})
    assert "KeyError" not in out["status"]["LinkedIn"]["error"] and out["status"]["LinkedIn"]["error"]
    assert len(out["results"]) == 1


def test_a_board_that_was_switched_off_says_so():
    out, _ = run({"LinkedIn": [make_job("LinkedIn", "Python Developer")]})
    fake = FakeBoards({"LinkedIn": [make_job("LinkedIn", "Python Developer")]})
    with fake.installed():
        out = engine.search("python developer", ["LinkedIn", "Gone"], base_opts(), fresh=True)
    assert "switched off" in out["status"]["Gone"]["error"]


def test_a_full_disk_keeps_the_results():
    real = Path.write_text

    def full(self, *a, **k):
        if self.parent == search_cache.CACHE_FILE.parent and self.stem == "cache":
            raise OSError(28, "No space left on device")
        return real(self, *a, **k)
    with mock.patch.object(Path, "write_text", full):
        out, _ = run({"LinkedIn": [make_job("LinkedIn", "Python Developer")]})
    assert len(out["results"]) == 1 and out["status"]["LinkedIn"]["error"] is None


def test_a_damaged_cache_file_is_ignored():
    search_cache.CACHE_FILE.write_text('{"half a fi', encoding="utf-8")
    out, _ = run({"LinkedIn": [make_job("LinkedIn", "Python Developer")]}, fresh=False)
    assert len(out["results"]) == 1


def test_the_same_search_at_the_same_time_asks_the_board_once():
    calls = []

    def slow(q, o):
        calls.append(q)
        time.sleep(.4)
        return [make_job("LinkedIn", "Python Developer")]
    with with_board(slow):
        outs = []
        ts = [threading.Thread(target=lambda: outs.append(engine.search("python developer", ["LinkedIn"], base_opts(), fresh=False)))
              for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
    assert len(calls) == 1 and all(len(o["results"]) == 1 for o in outs)


def test_stopping_a_search_frees_the_board_for_the_next_one():
    lock = threading.Lock()

    def one_at_a_time(q, o):
        with board_base.take_turn(lock, o):
            board_base.pause(5 if q == "old" else 0, o)     # the old search waits a long time for its turn
            return [make_job("LinkedIn", f"{q} developer")]
    with with_board(one_at_a_time):
        old = engine.run_event("old-run")
        t = threading.Thread(target=lambda: engine.search("old", ["LinkedIn"], {**base_opts(), "cancel": old}, fresh=True))
        t.start()
        time.sleep(.2)
        engine.cancel_run("old-run")                        # what the screen's Stop / new search does
        start = time.time()
        out = engine.search("new", ["LinkedIn"], {**base_opts(), "cancel": engine.run_event("new-run")}, fresh=True)
        t.join(3)
    assert time.time() - start < 2 and len(out["results"]) == 1 and not t.is_alive()


def test_a_stopped_board_says_stopped():
    def waits(q, o):
        board_base.pause(5, o)
        return []
    ev = threading.Event()
    ev.set()
    with with_board(waits):
        out = engine.search("python", ["LinkedIn"], {**base_opts(), "cancel": ev}, fresh=True)
    assert out["status"]["LinkedIn"]["error"] == "stopped"


def test_linkedin_keeps_the_first_page_when_the_second_fails():
    page = "<li>" + ('<h3 class="base-search-card__title">Python Developer</h3>'
                     '<a class="base-card__full-link" href="https://uk.linkedin.com/jobs/view/1"></a>') + "</li>"
    pages = iter([page * 10, RuntimeError("LinkedIn asked us to slow down")])

    def fake_page(q, o, start):
        p = next(pages)
        if isinstance(p, Exception):
            raise p
        return p
    with mock.patch.object(linkedin, "_guest_page", fake_page), \
            mock.patch.object(linkedin, "load_settings", return_value={}):
        jobs = linkedin.src_linkedin("python developer", base_opts())
    assert len(jobs) == 10


def test_the_server_always_answers_a_search(app_server):
    srv = app_server
    with no_internet(), mock.patch.object(engine, "match", side_effect=ValueError("broken")), \
            with_board(lambda q, o: [make_job("LinkedIn", "Python Developer")]):
        code, body, _ = srv.request("/api/search?q=python&sources=LinkedIn&fresh=1")
    assert code == 200 and "went wrong" in body["status"]["LinkedIn"]["error"]
    code, body, _ = srv.request("/api/search/stop?run=abc")
    assert code == 200 and engine.run_event("abc").is_set()


def test_role_words_stand_in_for_each_other_once_the_field_is_named():
    def m(title, desc, q):
        return match({"title": title, "tags": [], "desc": desc}, query_words(q), q)
    hit = m("Senior Software Engineer", "Our stack is C# and .NET 8.", ".net developer")
    assert hit["score"] > 0 and not hit["title_match"]           # kept, but "Title must match" stays strict
    assert m("Software Engineer", "x", "software developer")["score"] > 0
    assert m("Civil Engineer", "Bridges and roads.", "developer")["score"] == 0   # "developer" alone stays as typed


def test_settings_save_while_searches_read_them():
    # searches read settings.json all the time; on Windows a save at that instant used to fail ("Access is denied")
    from jobslop import settings
    stop, errors = threading.Event(), []

    def reader():
        while not stop.is_set():
            settings.load_settings()

    def writer(i):
        try:
            for n in range(60):
                settings.update_settings(lambda s: s.setdefault("ui", {}).update({f"k{i}": str(n)}))
        except Exception as e:
            errors.append(e)
    readers = [threading.Thread(target=reader) for _ in range(4)]
    writers = [threading.Thread(target=writer, args=(i,)) for i in range(3)]
    for t in readers + writers:
        t.start()
    for t in writers:
        t.join()
    stop.set()
    for t in readers:
        t.join()
    assert not errors, errors[:2]
    assert settings.load_settings()["ui"] == {"k0": "59", "k1": "59", "k2": "59"}
