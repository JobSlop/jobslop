"""Plugins: reading plugin.json, loading, switching on and off, and what they may add.

Each test builds small plugins in a temporary folder and runs them in a separate plugin manager,
so the app's real plugins are never touched.
"""
import json
import tempfile
import textwrap
from pathlib import Path
from unittest import mock

import pytest
from support import reset_data

from jobslop.boards.registry import BoardRegistry
from jobslop.plugins import manifest as mf
from jobslop.plugins.manager import PluginManager
from jobslop.plugins.points import ExtensionPoints
from jobslop.server import plugin_routes
from jobslop.settings import load_settings

BOARD_PLUGIN = '''
def search(q, o):
    return [api_ref[0].jobs.make("Test Board", "Bookkeeper " + q, "Acme", "https://example.com/1")]

api_ref = []

def register(api):
    api_ref.append(api)
    api.add_board("Test Board", search, "A board for tests", countries={"GB"})
    api.add_endpoint("hello", lambda params, body: {"hi": params.get("name") or (body or {}).get("name")})
'''


def make_plugin(base: Path, pid: str, files: dict | None = None, **manifest) -> Path:
    folder = base / pid
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in (files or {}).items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(textwrap.dedent(text), encoding="utf-8")
    data = {"id": pid, "name": pid.title(), "version": "1.0.0", "api": 1, **manifest}
    (folder / "plugin.json").write_text(json.dumps(data), encoding="utf-8")
    return folder


@pytest.fixture
def world():
    """A plugin manager with its own built-in and installed folders, boards and extension points."""
    reset_data()
    tmp = Path(tempfile.mkdtemp(prefix="jobslop-plugins-"))
    boards, points = BoardRegistry(), ExtensionPoints()
    mgr = PluginManager(tmp / "builtin", tmp / "installed", boards, points)
    yield mgr, tmp, boards, points
    for p in mgr.all():
        mgr.unload(p.id)


# ---------------------------------------------------------------- plugin.json
class TestManifest:
    def read(self, tmp, **data):
        folder = make_plugin(tmp, "good", {"plugin.py": "def register(api): pass\n"}, **data)
        return mf.read(folder)

    def test_a_good_manifest(self, tmp_path):
        m = self.read(tmp_path, description="Accounting boards", python="plugin.py",
                      profile_fields=[{"key": "acca_number", "label": "ACCA number", "autofill": ["acca.*number"]}],
                      settings=[{"key": "my_key", "label": "My key", "link": "https://example.com"}],
                      language={"code": "nl", "name": "Nederlands", "countries": ["NL", "BE"]})
        assert (m.id, m.version, m.api, m.python) == ("good", "1.0.0", 1, "plugin.py")
        assert m.profile_fields[0].section == "Good" and m.profile_fields[0].autofill == ("acca.*number",)
        assert m.language.countries == ("NL", "BE")
        assert m.adds() == ["runs Python code", "1 profile field", "settings", "the Nederlands language"]

    @pytest.mark.parametrize("change, message", [
        ({"id": "Bad Id"}, "may only use"),
        ({"version": "one"}, "1.0.0"),
        ({"api": 99}, "newer jobslop"),
        ({"api": "1"}, "plugin API version"),
        ({"python": "../evil.py"}, "inside the plugin"),
        ({"python": "missing.py"}, "not in the plugin"),
        ({"homepage": "http://example.com"}, "https://"),
        ({"profile_fields": [{"key": "x1", "label": "X", "autofill": ["("]}]}, "not a valid pattern"),
        ({"profile_fields": [{"key": "x1", "label": "X", "type": "password"}]}, "type must be"),
        ({"settings": [{"key": "Bad-Key", "label": "X"}]}, "a-z"),
        ({"language": {"code": "dutch", "name": "Dutch"}}, "two letters"),
    ])
    def test_bad_manifests_are_refused(self, tmp_path, change, message):
        with pytest.raises(mf.ManifestError, match=message):
            self.read(tmp_path, **change)

    def test_no_or_broken_manifest(self, tmp_path):
        with pytest.raises(mf.ManifestError, match="no plugin.json"):
            mf.read(tmp_path)
        (tmp_path / "plugin.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(mf.ManifestError, match="can't be read"):
            mf.read(tmp_path)


# ---------------------------------------------------------------- loading and switching
class TestManager:
    def test_plugins_are_off_unless_they_say_otherwise(self, world):
        mgr, tmp, boards, _ = world
        make_plugin(tmp / "builtin", "quiet", {"plugin.py": BOARD_PLUGIN}, python="plugin.py")
        make_plugin(tmp / "builtin", "eager", {"plugin.py": BOARD_PLUGIN.replace("Test Board", "Eager Board")},
                    python="plugin.py", enabled_by_default=True)
        mgr.discover()
        mgr.load_enabled()
        assert boards.names() == ["Eager Board"]
        assert not mgr.is_enabled("quiet") and mgr.is_enabled("eager")

    def test_switching_on_and_off_adds_and_removes_everything(self, world):
        mgr, tmp, boards, points = world
        make_plugin(tmp / "builtin", "acct", {"plugin.py": BOARD_PLUGIN}, python="plugin.py",
                    settings=[{"key": "acct_key", "label": "Key"}],
                    profile_fields=[{"key": "acct_no", "label": "Member number"}])
        mgr.discover()
        mgr.set_enabled("acct", True)
        assert boards.get("Test Board").plugin == "acct" and boards.get("Test Board").countries == {"GB"}
        assert points.setting_keys() == ["acct_key"] and [f.key for f in points.profile_fields] == ["acct_no"]
        assert points.endpoint("acct", "hello")({"name": "Ann"}, None) == {"hi": "Ann"}
        assert load_settings()["plugins"]["acct"]["enabled"] is True
        mgr.set_enabled("acct", False)
        assert len(boards) == 0 and points.setting_keys() == [] and points.endpoint("acct", "hello") is None
        assert load_settings()["plugins"]["acct"]["enabled"] is False
        mgr.set_enabled("acct", True)                         # comes back cleanly, code loaded afresh
        assert boards.get("Test Board").search("x", {})[0]["title"] == "Bookkeeper x"

    def test_a_crashing_plugin_leaves_nothing_behind(self, world):
        mgr, tmp, boards, points = world
        make_plugin(tmp / "builtin", "broken", {"plugin.py": '''
            def register(api):
                api.add_board("Half Board", lambda q, o: [])
                api.add_setting("half_key", "Half")
                raise RuntimeError("oops")
        '''}, python="plugin.py")
        mgr.discover()
        mgr.set_enabled("broken", True)
        p = mgr.get("broken")
        assert not p.loaded and "RuntimeError: oops" in p.error
        assert len(boards) == 0 and points.setting_keys() == []
        assert any("oops" in m for m in mgr.messages)

    def test_a_plugin_without_register_is_reported(self, world):
        mgr, tmp, _, _ = world
        make_plugin(tmp / "builtin", "empty", {"plugin.py": "x = 1\n"}, python="plugin.py")
        mgr.discover()
        mgr.set_enabled("empty", True)
        assert "no register(api)" in mgr.get("empty").error

    def test_a_bad_manifest_is_listed_with_its_problem(self, world):
        mgr, tmp, _, _ = world
        make_plugin(tmp / "installed", "future", api=7)
        mgr.discover()
        d = mgr.describe(mgr.get("future"))
        assert "newer jobslop" in d["error"] and not d["enabled"]
        with pytest.raises(ValueError):
            mgr.set_enabled("future", True)

    def test_plugins_can_import_their_own_files(self, world):
        mgr, tmp, boards, _ = world
        make_plugin(tmp / "builtin", "multi", {
            "plugin.py": "from . import helpers\n\ndef register(api):\n    api.add_board(helpers.NAME, lambda q, o: [])\n",
            "helpers.py": 'NAME = "Helper Board"\n'}, python="plugin.py")
        mgr.discover()
        mgr.set_enabled("multi", True)
        assert boards.names() == ["Helper Board"], mgr.get("multi").error

    def test_newer_installed_copy_replaces_the_built_in_one(self, world):
        mgr, tmp, _, _ = world
        make_plugin(tmp / "builtin", "art", version="1.0.0")
        make_plugin(tmp / "installed", "art", version="1.2.0")
        mgr.discover()
        assert mgr.get("art").manifest.version == "1.2.0" and not mgr.get("art").builtin

    def test_an_older_installed_copy_loses_to_a_newer_built_in_one(self, world):
        mgr, tmp, _, _ = world
        make_plugin(tmp / "builtin", "art", version="2.0.0")
        make_plugin(tmp / "installed", "art", version="1.2.0")
        mgr.discover()
        assert mgr.get("art").manifest.version == "2.0.0" and mgr.get("art").builtin

    def test_language_files_and_search_terms_from_the_manifest(self, world):
        mgr, tmp, _, points = world
        make_plugin(tmp / "builtin", "lang-nl", {"lang/ui.json": '{"Search": "Zoeken"}',
                                                  "lang/terms.json": '{"accountant": ["boekhouder"]}'},
                    language={"code": "nl", "name": "Nederlands", "countries": ["NL"]},
                    translations={"nl": "lang/ui.json"}, search_terms={"nl": "lang/terms.json"})
        mgr.discover()
        mgr.set_enabled("lang-nl", True)
        assert [t.words for t in points.translations] == [{"Search": "Zoeken"}]
        assert [(t.lang, t.words) for t in points.search_terms] == [("nl", {"accountant": ["boekhouder"]})]


# ---------------------------------------------------------------- through the app's server
@pytest.mark.usefixtures("app_server")
class TestServer:
    @pytest.fixture(autouse=True)
    def routes(self, world):
        mgr, tmp, boards, points = world
        make_plugin(tmp / "builtin", "acct", {"plugin.py": BOARD_PLUGIN, "ui.js": "console.log('hi')",
                                              "secret.txt": "not served"},
                    python="plugin.py", ui="ui.js", settings=[{"key": "acct_key", "label": "Key"}])
        mgr.discover()
        with mock.patch.object(plugin_routes, "ROUTES", plugin_routes.PluginRoutes(mgr, points)), \
                mock.patch("jobslop.server.handler.POINTS", points):
            yield mgr

    def test_list_and_switch(self, app_server):
        code, data = app_server.get("/api/plugins")
        assert code == 200 and data["plugins"][0]["id"] == "acct" and not data["plugins"][0]["enabled"]
        code, data = app_server.post("/api/plugins", {"id": "acct", "enabled": True})
        assert data["plugins"][0]["loaded"] and data["settings"][0]["key"] == "acct_key"
        assert data["plugins"][0]["ui"] == "/plugins/acct/ui.js"
        assert app_server.post("/api/plugins", {"id": "nope", "enabled": True})[0] == 404

    def test_endpoints_and_files(self, app_server, routes):
        assert app_server.get("/plugins/acct/ui.js")[0] == 404            # not served while it's off
        routes.set_enabled("acct", True)
        assert app_server.get("/api/plugin/acct/hello?name=Bo") == (200, {"hi": "Bo"})
        assert app_server.post("/api/plugin/acct/hello", {"name": "Cy"}) == (200, {"hi": "Cy"})
        assert app_server.get("/api/plugin/acct/nothing")[0] == 404
        code, text = app_server.get("/plugins/acct/ui.js")
        assert code == 200 and "console.log" in text
        assert app_server.get("/plugins/acct/secret.txt")[0] == 404
        assert app_server.get("/plugins/acct/..%2Fplugin.json")[0] == 404

    def test_plugin_settings_are_saved_and_hidden(self, app_server, routes):
        routes.set_enabled("acct", True)
        app_server.post("/api/settings", {"acct_key": "abcdefghij"})
        assert load_settings()["acct_key"] == "abcdefghij"
        assert app_server.get("/api/settings")[1]["acct_key"] == "abc••••••ij"

    def test_a_crashing_endpoint_answers_with_an_error(self, app_server, routes):
        routes.set_enabled("acct", True)
        routes.points.endpoints.add("acct", type(routes.points.endpoints.items()[0][1])("boom", lambda p, b: 1 / 0))
        code, data = app_server.get("/api/plugin/acct/boom")
        assert code == 500 and "ZeroDivisionError" in data["error"]
