"""Plugins start switched off; people who used jobslop 3.0 keep the boards they had (Country boards was
split into one plugin per country)."""
from jobslop.plugins.migrate import SPLIT, migrate_choices

COUNTRY_PLUGINS = SPLIT["country-boards"]


def enabled(s):
    return {pid for pid, c in s.get("plugins", {}).items() if c.get("enabled")}


def test_a_new_user_starts_with_every_plugin_off():
    s = {}
    migrate_choices(s)
    assert enabled(s) == set() and s["plugin_defaults"] == 2


def test_someone_who_used_3_0_keeps_country_and_remote_boards():
    s = {"ui": {"onboarded": "1"}}
    migrate_choices(s)
    assert enabled(s) == set(COUNTRY_PLUGINS) | {"remote-boards"}
    assert "country-boards" not in s["plugins"]


def test_a_choice_made_in_3_0_is_kept():
    s = {"ui": {"onboarded": "1"}, "plugins": {"country-boards": {"enabled": False}, "accounting": {"enabled": True}}}
    migrate_choices(s)
    assert enabled(s) == {"remote-boards", "accounting", "jobs-uk"}, (
        "country boards were switched off, so they stay off - except the UK one, which now holds ZipRecruiter UK")


def test_it_only_happens_once():
    s = {"ui": {"onboarded": "1"}}
    migrate_choices(s)
    s["plugins"]["jobs-uk"]["enabled"] = False             # switched off afterwards
    migrate_choices(s)
    assert "jobs-uk" not in enabled(s)
