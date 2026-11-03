"""Languages: the screen's words and local job titles from language packs and other plugins."""
import json
import re
import sys

import pytest
from support import ROOT, FakeBoards, base_opts, make_job, no_internet, plugin_module, reset_data

from jobslop.i18n import LANGUAGES, Languages
from jobslop.plugins.manager import PLUGINS
from jobslop.search import engine

sys.path.insert(0, str(ROOT / "tools"))
import extract_strings  # noqa: E402

PACKS = ("nl", "es", "da")


@pytest.fixture
def dutch():
    """The Dutch pack switched on (and off again afterwards)."""
    reset_data()
    PLUGINS.set_enabled("lang-nl", True)
    yield
    PLUGINS.set_enabled("lang-nl", False)


def test_english_and_every_pack_are_offered():
    langs = {x["code"]: x for x in LANGUAGES.available()}
    assert langs["en"]["name"] == "English" and set(PACKS) <= set(langs)
    assert langs["nl"]["name"] == "Nederlands" and langs["nl"]["plugin"] == "lang-nl"


def test_words_come_from_switched_on_packs(dutch):
    words = LANGUAGES.words("nl")
    assert words["Search jobs"] == "Vacatures zoeken" and words["Found {0} jobs"] == "{0} vacatures gevonden"
    PLUGINS.set_enabled("lang-nl", False)
    assert "Search jobs" not in LANGUAGES.words("nl")


def test_switched_off_plugins_still_have_their_name_translated(dutch):
    PLUGINS.set_enabled("accounting", False)
    words = LANGUAGES.words("nl")
    assert words["Accounting"] == "Boekhouding", "its card in Settings is in Dutch"
    assert "Accounting applications" not in words, "but nothing else of a switched-off plugin"


def test_local_job_titles(dutch):
    assert LANGUAGES.local_terms("accountant", "NL")[:1] == ["boekhouder"]
    assert LANGUAGES.local_terms("Senior Accountant", "NL")[0] == "senior boekhouder", "a title inside the search is swapped"
    assert LANGUAGES.local_terms("accountant", "GB") == [], "no other language in the UK"
    assert LANGUAGES.local_terms("zookeeper", "NL") == []
    assert "NL" in [c for p in PLUGINS.all() if p.manifest and p.manifest.language for c in p.manifest.language.countries]


def test_plugins_add_job_titles_for_their_field():
    reset_data()
    PLUGINS.set_enabled("lang-da", False)
    plugin_module("accounting")
    assert "lønbogholder" in Languages().local_terms("payroll", "DK"), "Accounting's Danish titles work without the Danish pack"


def test_searching_in_the_netherlands_also_searches_dutch_titles_on_dutch_boards(dutch):
    plugin_module("jobs-nl")
    fake = FakeBoards({"Jobbird": [make_job("Jobbird", "Boekhouder", location="Utrecht")],
                       "Himalayas": [make_job("Himalayas", "Accountant", location="Remote")]})
    with fake.installed(), no_internet():
        out = engine.search("accountant", ["Jobbird", "Himalayas"], base_opts(country="NL", where=""), fresh=True)
    asked = {(name, q) for name, q, _ in fake.calls}
    assert ("Jobbird", "boekhouder") in asked and ("Jobbird", "accountant") in asked
    assert not any(name == "Himalayas" and q != "accountant" for name, q in asked), "worldwide boards get the English only"
    assert "boekhouder" in out["also_searched"]
    assert any(j["title"] == "Boekhouder" for j in out["results"])


@pytest.mark.usefixtures("app_server")
class TestEndpoint:
    def test_i18n(self, app_server, dutch):
        code, data = app_server.get("/api/i18n?lang=nl")
        assert code == 200 and data["lang"] == "nl" and data["words"]["Tracker"] == "Tracker"
        assert {"en", "nl", "es", "da"} <= {x["code"] for x in data["languages"]}
        assert app_server.get("/api/i18n")[1]["lang"] == "en", "English unless a language was chosen"


# ---------------------------------------------------------------- the packs themselves
def screen_text():
    page = extract_strings.Page()
    page.feed((ROOT / "ui" / "index.html").read_text(encoding="utf-8"))
    found = set(page.found)
    for f in (ROOT / "ui" / "js").glob("*.js"):
        found |= extract_strings.template_text(f.read_text(encoding="utf-8"))
    return {" ".join(s.split()) for s in found}


@pytest.mark.parametrize("code", PACKS)
def test_each_pack_covers_the_screen(code):
    words = {" ".join(k.split()) for k in json.loads((ROOT / f"plugins/lang-{code}/lang/ui.json").read_text(encoding="utf-8"))}
    text = screen_text()
    missing = sorted(s for s in text if s not in words)
    assert len(missing) <= 0.05 * len(text), f"{len(missing)} screen texts have no {code} translation, e.g. {missing[:8]}"


@pytest.mark.parametrize("code", PACKS)
def test_translations_keep_the_blanks(code):
    words = json.loads((ROOT / f"plugins/lang-{code}/lang/ui.json").read_text(encoding="utf-8"))
    for en, tr in words.items():
        assert set(re.findall(r"\{\w+\}", tr)) <= set(re.findall(r"\{\w+\}", en)), (en, tr)
        assert tr.strip(), en


@pytest.mark.parametrize("code", PACKS)
def test_job_titles_file(code):
    terms = json.loads((ROOT / f"plugins/lang-{code}/lang/search_terms.json").read_text(encoding="utf-8"))
    assert len(terms) >= 40 and all(isinstance(v, list) and v for v in terms.values())
