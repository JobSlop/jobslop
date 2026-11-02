"""The board registry: boards describe themselves, and plugins can add and take away boards."""
import pytest
from support import reset_data

from jobslop.boards import registry
from jobslop.boards.base import Board
from jobslop.settings import update_settings


def search(q, o):
    return []


def test_boards_are_grouped_in_screen_order():
    r = registry.BoardRegistry()
    r.add(Board("Remote1", search, group="remote"))
    r.add(Board("Main1", search))
    r.add(Board("Country1", search, group="country"))
    r.add(Board("Main2", search))
    assert r.names() == ["Main1", "Main2", "Country1", "Remote1"]


def test_a_plugin_cannot_take_another_ones_board_name():
    r = registry.BoardRegistry()
    r.add(Board("Same", search, plugin="one"))
    with pytest.raises(ValueError):
        r.add(Board("Same", search, plugin="two"))
    r.add(Board("Same", search, description="newer", plugin="one"))       # the same plugin may replace its own
    assert r.get("Same").description == "newer"


def test_turning_a_plugin_off_removes_its_boards():
    r = registry.BoardRegistry()
    r.add(Board("Core", search))
    r.add(Board("Extra", search, plugin="extra"))
    r.remove_plugin("extra")
    assert r.names() == ["Core"] and "Extra" not in r


def test_a_board_rejects_an_unknown_group():
    with pytest.raises(ValueError):
        Board("X", search, group="somewhere")


def test_countries_and_keys():
    b = Board("Keyed", search, countries={"gb"}, needs=("a_key",), slow_without="speed")
    assert b.covers("GB") and not b.covers("US") and Board("Any", search).covers("US")
    assert b.describe({})["needs_key"] and not b.describe({"a_key": "x"})["needs_key"]
    assert b.describe({})["slow"] and not b.describe({"speed": "y"})["slow"]
    assert b.describe({})["countries"] == ["GB"]


@pytest.mark.usefixtures("app_server")
class TestBoardsEndpoint:
    def test_the_screen_gets_every_board_with_its_facts(self, app_server):
        reset_data()
        code, data = app_server.get("/api/boards")
        boards = {b["name"]: b for b in data}
        assert code == 200 and list(boards)[:4] == ["LinkedIn", "Indeed", "Glassdoor", "ZipRecruiter"]
        assert boards["Reed"]["countries"] == ["GB"] and boards["Reed"]["needs_key"]
        assert boards["Himalayas"]["countries"] is None and boards["Himalayas"]["group"] == "remote"
        assert "DE" in boards["Adzuna"]["countries"] and "DK" not in boards["Adzuna"]["countries"]
        update_settings(lambda s: s.update(reed_key="k"))
        assert not {b["name"]: b for b in app_server.get("/api/boards")[1]}["Reed"]["needs_key"]
