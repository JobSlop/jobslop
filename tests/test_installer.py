"""Installing plugins from a GitHub link: checked before anything runs, unpacked safely, removable.

GitHub is never asked: its answers and the downloaded zips are made up here.
"""
import io
import json
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

import pytest
from support import reset_data

from jobslop import net
from jobslop.boards.registry import BoardRegistry
from jobslop.plugins import installer as inst
from jobslop.plugins.manager import SOURCE_FILE, PluginManager
from jobslop.plugins.points import ExtensionPoints
from jobslop.server import plugin_routes

GOOD_PY = '''
def register(api):
    api.add_board("Linked Board", lambda q, o: [], "From a link")
'''
EVIL_IMPORT = "raise SystemExit('plugin code ran while only previewing!')\n"


def make_zip(files: dict, top="someone-cool-plugin-abc1234", symlink=None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(f"{top}/{name}" if top and not name.startswith(("/", "..")) else name, text)
        if symlink:
            info = zipfile.ZipInfo(f"{top}/{symlink}")
            info.external_attr = 0o120777 << 16
            z.writestr(info, "/etc/passwd")
    return buf.getvalue()


def manifest(pid="cool", **extra):
    return json.dumps({"id": pid, "name": "Cool", "version": "1.0.0", "api": 1, "author": "someone",
                       "description": "A cool plugin", "python": "plugin.py", **extra})


@pytest.fixture
def world():
    reset_data()
    tmp = Path(tempfile.mkdtemp(prefix="jobslop-install-"))
    boards, points = BoardRegistry(), ExtensionPoints()
    mgr = PluginManager(tmp / "builtin", tmp / "installed", boards, points)
    mgr.discover()
    installer = inst.Installer(mgr, tmp / "staging")
    yield installer, mgr, boards, tmp
    for p in mgr.all():
        mgr.unload(p.id)


def fake_github(zip_bytes, tag="v1.0.0"):
    """Patches: GitHub's API answers with a release; the download gives zip_bytes."""
    def api(url, **k):
        if url.endswith("/releases/latest"):
            return {"tag_name": tag, "body": "notes"}
        return {"default_branch": "main"}
    return mock.patch.object(net, "get_json", side_effect=api), mock.patch.object(inst, "download", return_value=zip_bytes)


def test_links():
    assert inst.parse_link("https://github.com/JobSlop/jobslop-plugin-accounting") == inst.Repo("JobSlop", "jobslop-plugin-accounting")
    assert inst.parse_link("github.com/a-b/c.d_e.git") == inst.Repo("a-b", "c.d_e")
    assert inst.parse_link("https://github.com/x/y/tree/main/src").name == "y"
    for bad in ("https://gitlab.com/x/y", "https://github.com/x", "https://evil.com/github.com/x/y", "", "github.com/x/.."):
        with pytest.raises(inst.InstallError):
            inst.parse_link(bad)


def test_preview_runs_no_code_then_install_switches_it_on(world):
    installer, mgr, boards, tmp = world
    data = make_zip({"plugin.json": manifest(), "plugin.py": EVIL_IMPORT + GOOD_PY})
    a, b = fake_github(data)
    with a, b:
        preview = installer.prepare("https://github.com/someone/cool-plugin")
    assert (preview["id"], preview["version"], preview["author"]) == ("cool", "1.0.0", "someone")
    assert preview["runs_code"] and "runs Python code" in preview["adds"] and preview["replaces"] == ""
    assert not (tmp / "installed").exists(), "nothing is installed before the user says yes"
    (tmp / "staging" / preview["token"]).exists()
    # the plugin's code would stop the tests if it ran; replace it with good code before confirming
    staged = next((tmp / "staging" / preview["token"]).iterdir()) / "plugin.py"
    staged.write_text(GOOD_PY, encoding="utf-8")
    assert installer.confirm(preview["token"]) == "cool"
    src = json.loads((tmp / "installed" / "cool" / SOURCE_FILE).read_text(encoding="utf-8"))
    assert src["url"] == "https://github.com/someone/cool-plugin" and src["ref"] == "v1.0.0"
    assert mgr.get("cool").loaded and boards.names() == ["Linked Board"]
    assert not (tmp / "staging" / preview["token"]).exists(), "the staging copy is tidied away"
    with pytest.raises(inst.InstallError, match="expired"):
        installer.confirm(preview["token"])


def test_branch_is_used_when_there_are_no_releases():
    def api(url, **k):
        if url.endswith("/releases/latest"):
            raise OSError("HTTP Error 404: Not Found")
        return {"default_branch": "trunk"}
    with mock.patch.object(net, "get_json", side_effect=api):
        where = inst.latest(inst.Repo("a", "b"))
    assert where["zip"].endswith("/zipball/trunk") and where["ref"] == "trunk"


@pytest.mark.parametrize("files, symlink, message", [
    ({"plugin.json": manifest(), "../../evil.py": "x"}, None, "outside its folder"),
    ({"plugin.json": manifest(), "/abs.py": "x"}, None, "outside its folder"),
    ({"plugin.json": manifest(), "plugin.py": GOOD_PY}, "link.py", "links to other files"),
    ({"README.md": "no manifest here"}, None, "isn't a jobslop plugin"),
    ({"plugin.json": manifest(api=9), "plugin.py": GOOD_PY}, None, "newer jobslop"),
    ({"plugin.json": manifest(), "plugin.py": GOOD_PY, **{f"f{i}.txt": "" for i in range(inst.MAX_FILES + 1)}}, None, "too many files"),
])
def test_unsafe_or_broken_downloads_are_refused(world, files, symlink, message):
    installer, _, _, tmp = world
    a, b = fake_github(make_zip(files, symlink=symlink))
    with a, b, pytest.raises(inst.InstallError, match=message):
        installer.prepare("github.com/someone/cool-plugin")
    assert not list((tmp / "staging").glob("*/*")), "a refused download leaves nothing behind"


def test_not_a_zip(world):
    installer, *_ = world
    a, b = fake_github(b"<html>not a zip</html>")
    with a, b, pytest.raises(inst.InstallError, match="valid zip"):
        installer.prepare("github.com/someone/cool-plugin")


def test_downloads_only_come_from_github():
    with pytest.raises(inst.InstallError, match="only be downloaded from GitHub"):
        inst.download("https://evil.example.com/plugin.zip")


def test_too_big_download_is_stopped():
    class Resp(io.BytesIO):
        def geturl(self):
            return "https://codeload.github.com/x/y/zip/main"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    with mock.patch("urllib.request.urlopen", return_value=Resp(b"x" * 2000)), \
            pytest.raises(inst.InstallError, match="too big"):
        inst.download("https://api.github.com/repos/x/y/zipball/main", max_bytes=1000)


def test_a_link_cannot_replace_a_built_in_plugin(world):
    installer, mgr, _, tmp = world
    (tmp / "builtin" / "cool").mkdir(parents=True)
    (tmp / "builtin" / "cool" / "plugin.json").write_text(
        manifest(homepage="https://github.com/JobSlop/jobslop-plugin-cool", python=""), encoding="utf-8")
    mgr.discover()
    a, b = fake_github(make_zip({"plugin.json": manifest(version="9.0.0"), "plugin.py": GOOD_PY}))
    with a, b, pytest.raises(inst.InstallError, match="comes with jobslop"):
        installer.prepare("github.com/someone/cool-plugin")
    with a, b:                                     # its own repository may update it
        preview = installer.prepare("github.com/JobSlop/jobslop-plugin-cool")
    assert preview["replaces"] == "1.0.0"


def test_remove(world):
    installer, mgr, boards, tmp = world
    a, b = fake_github(make_zip({"plugin.json": manifest(), "plugin.py": GOOD_PY}))
    with a, b:
        installer.confirm(installer.prepare("github.com/someone/cool-plugin")["token"])
    installer.remove("cool")
    assert not (tmp / "installed" / "cool").exists() and mgr.get("cool") is None and len(boards) == 0
    (tmp / "builtin" / "core-thing").mkdir(parents=True)
    (tmp / "builtin" / "core-thing" / "plugin.json").write_text(json.dumps(
        {"id": "core-thing", "name": "Core", "version": "1.0.0", "api": 1}), encoding="utf-8")
    mgr.discover()
    with pytest.raises(inst.InstallError, match="switched off"):
        installer.remove("core-thing")


def test_update_check(world):
    installer, mgr, _, tmp = world
    a, b = fake_github(make_zip({"plugin.json": manifest(), "plugin.py": GOOD_PY}))
    with a, b:
        installer.confirm(installer.prepare("github.com/someone/cool-plugin")["token"])
    a2, _ = fake_github(b"", tag="v1.1.0")
    with a2:
        assert installer.check_updates() == [{"id": "cool", "current": "1.0.0", "latest": "1.1.0",
                                              "link": "https://github.com/someone/cool-plugin"}]
    a3, _ = fake_github(b"", tag="v1.0.0")
    with a3:
        assert installer.check_updates() == []
    with mock.patch.object(net, "get_json", side_effect=OSError("offline")):
        assert installer.check_updates() == [], "offline: nothing offered, nothing broken"


@pytest.mark.usefixtures("app_server")
class TestEndpoints:
    def test_install_through_the_app(self, app_server, world):
        installer, mgr, boards, _ = world
        routes = plugin_routes.PluginRoutes(mgr, ExtensionPoints(), installer)
        a, b = fake_github(make_zip({"plugin.json": manifest(), "plugin.py": GOOD_PY}))
        with a, b, mock.patch.object(plugin_routes, "ROUTES", routes):
            code, data = app_server.post("/api/plugins/install", {"link": "github.com/someone/cool-plugin"})
            assert code == 200 and data["preview"]["name"] == "Cool"
            code, data = app_server.post("/api/plugins/install", {"token": data["preview"]["token"]})
            assert code == 200 and data["installed"] == "cool" and data["plugins"][0]["id"] == "cool"
            code, data = app_server.post("/api/plugins/install", {"link": "https://gitlab.com/x/y"})
            assert code == 400 and "GitHub link" in data["error"]
            code, data = app_server.post("/api/plugins/remove", {"id": "cool"})
            assert code == 200 and data["plugins"] == []
