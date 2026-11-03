"""The plugins that come with jobslop: valid, they start cleanly, and they add what they promise."""
from pathlib import Path

import pytest
from support import ROOT, plugin_module

from jobslop.boards.registry import BOARDS
from jobslop.plugins import manifest as mf
from jobslop.plugins.manager import PLUGINS
from jobslop.plugins.points import POINTS

BUILTIN = sorted(p.name for p in (ROOT / "plugins").iterdir() if (p / "plugin.json").exists())

EXPECTED_BOARDS = {
    "jobs-uk": {"Reed"},
    "jobs-us": {"Jobs2Careers", "USAJOBS"},
    "jobs-dk": {"Jobindex"},
    "jobs-nl": {"Jobbird"},
    "adzuna": {"Adzuna"},
    "remote-boards": {"Himalayas", "Jobicy", "Remotive", "RemoteOK", "Arbeitnow"},
    "accounting": {"ICAEW", "ACCA"},
    "artists": {"ArtStation"},
    "gamedev": {"WorkWithIndies"},
}
ON_BY_DEFAULT = set()                 # every plugin starts switched off; the welcome tour offers them


def test_the_expected_plugins_are_built_in():
    assert set(EXPECTED_BOARDS) <= set(BUILTIN)


@pytest.mark.parametrize("pid", BUILTIN)
def test_manifest_is_valid_and_points_to_its_repo(pid):
    m = mf.read(ROOT / "plugins" / pid)
    assert m.id == pid and m.api == mf.API_VERSION and m.author == "jobslop"
    assert m.homepage == f"https://github.com/JobSlop/jobslop-plugin-{pid}"
    assert m.enabled_by_default == (pid in ON_BY_DEFAULT)
    assert m.description


@pytest.mark.parametrize("pid", BUILTIN)
def test_starts_without_errors_and_adds_its_boards(pid):
    plugin_module(pid) if PLUGINS.get(pid).manifest.python else PLUGINS.set_enabled(pid, True)
    p = PLUGINS.get(pid)
    assert p.loaded and not p.error
    mine = {b.name for b in BOARDS if b.plugin == pid}
    assert mine == EXPECTED_BOARDS.get(pid, set())


@pytest.mark.parametrize("pid", BUILTIN)
def test_plugins_only_use_the_api(pid):
    """Plugins must not reach into jobslop's internals: everything goes through `api`."""
    for f in Path(ROOT / "plugins" / pid).rglob("*.py"):
        assert "jobslop." not in f.read_text(encoding="utf-8").replace("jobslop.exe", ""), f


def test_profile_fields_from_plugins():
    for pid in ("accounting", "artists", "gamedev"):
        plugin_module(pid)
    keys = {f.key for f in POINTS.profile_fields}
    assert {"acca_number", "artstation", "showreel", "engines"} <= keys


def test_the_extension_is_told_about_plugin_fields():
    from jobslop.extension import extension_payload
    plugin_module("accounting")
    extra = {f["key"]: f for f in extension_payload()["extra_fields"]}
    assert "acca_number" in extra and extra["acca_number"]["patterns"]
    PLUGINS.set_enabled("accounting", False)
    assert "acca_number" not in {f["key"] for f in extension_payload()["extra_fields"]}
    PLUGINS.set_enabled("accounting", True)


def test_the_plugin_template_works(tmp_path):
    """docs/plugin-template is what plugin makers start from: it must be valid and start cleanly."""
    import shutil

    from jobslop.boards.registry import BoardRegistry
    from jobslop.plugins.manager import PluginManager
    from jobslop.plugins.points import ExtensionPoints
    shutil.copytree(ROOT / "docs" / "plugin-template", tmp_path / "installed" / "my-plugin")
    boards, points = BoardRegistry(), ExtensionPoints()
    mgr = PluginManager(tmp_path / "builtin", tmp_path / "installed", boards, points)
    mgr.discover()
    mgr.set_enabled("my-plugin", True)
    assert mgr.get("my-plugin").loaded, mgr.get("my-plugin").error
    assert boards.names() == ["My Board"] and [f.key for f in points.profile_fields] == ["my_plugin_link"]
    mgr.set_enabled("my-plugin", False)
