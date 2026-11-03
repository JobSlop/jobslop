"""One-time changes to which plugins are on, when plugins are split up or their defaults change.

jobslop 3.0 had "Country boards" and "Remote boards" switched on for everyone. From 3.1 every plugin
starts switched off (new users choose in the welcome tour) and Country boards became one plugin per
country. People who used 3.0 keep the boards they had.
"""

from collections.abc import Callable

SPLIT = {"country-boards": ("jobs-uk", "jobs-us", "jobs-dk", "jobs-nl", "adzuna")}
WERE_ON_BY_DEFAULT = ("country-boards", "remote-boards")
VERSION = 2                         # settings["plugin_defaults"]: which of these changes are done


def migrate_choices(s: dict) -> None:
    """Change settings (in place) once."""
    if s.get("plugin_defaults", 0) >= VERSION:
        return
    choices = s.setdefault("plugins", {})
    used_before = (s.get("ui") or {}).get("onboarded") == "1"      # set up jobslop before this version

    def was_on(pid: str) -> bool:
        choice = choices.get(pid)
        return bool(choice["enabled"]) if isinstance(choice, dict) and "enabled" in choice \
            else used_before and pid in WERE_ON_BY_DEFAULT

    for old, new in SPLIT.items():
        on = was_on(old)
        choices.pop(old, None)
        for pid in new:
            choices.setdefault(pid, {"enabled": on})
    for pid in WERE_ON_BY_DEFAULT:
        if pid not in SPLIT and pid not in choices and used_before:
            choices[pid] = {"enabled": True}
    s["plugin_defaults"] = VERSION


def migrate(update_settings: Callable) -> None:
    update_settings(migrate_choices)
