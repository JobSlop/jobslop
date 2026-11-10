"""The settings file: API keys, preferences and everything else that is remembered between runs."""

import json
import os
import threading
import time

from jobslop.config import DATA_DIR

SETTINGS_FILE = DATA_DIR / "settings.json"


# ---------------------------------------------------------------- settings

KEY_NAMES = ("apify_token",)          # the app's own keys; plugins add theirs (Reed, Adzuna, ...)

# reading and saving take turns: on Windows a file can't be swapped in while it is open for reading
settings_lock = threading.RLock()


def load_settings():
    for attempt in range(5):                 # retry briefly if something outside the app has it open
        with settings_lock:
            if not SETTINGS_FILE.exists():
                return {}
            try:
                return json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
            except Exception:
                pass
        time.sleep(0.05)
    return {}


def replace_file(tmp, target, tries=20):
    """os.replace that waits a moment when Windows refuses because something is reading the file
    (another part of the app, antivirus, backup software) at that instant."""
    for attempt in range(tries):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(0.05)


def update_settings(change):
    """Change settings.json safely: one change at a time, and written to a temporary file first,
    so two quick saves can't overwrite each other and a half-written file is never read."""
    with settings_lock:
        s = load_settings()
        change(s)
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
        replace_file(tmp, SETTINGS_FILE)
        return s


def save_settings(data, keys=KEY_NAMES):
    """Store the given keys (API keys etc.) from what the Settings window sent."""
    def change(s):
        for k in keys:
            if k in data:
                s[k] = (data[k] or "").strip()
    return update_settings(change)


def public_settings(keys=KEY_NAMES):
    """The keys for the screen: never the full value, just enough to recognise it."""
    s = load_settings()
    mask = lambda v: (v[:3] + "•" * 6 + v[-2:]) if v and len(v) > 6 else ("set" if v else "")
    return {k: mask(s.get(k, "")) for k in keys}
