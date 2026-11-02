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
    "country-boards": {"Reed", "Adzuna", "Jobs2Careers", "USAJOBS", "Jobindex", "Jobbird"},
    "remote-boards": {"Himalayas", "Jobicy", "Remotive", "RemoteOK", "Arbeitnow"},
    "accounting": {"ICAEW", "ACCA"},
    "artists": {"ArtStation"},
    "gamedev": {"WorkWithIndies"},
}
ON_BY_DEFAULT = {"country-boards", "remote-boards"}


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
