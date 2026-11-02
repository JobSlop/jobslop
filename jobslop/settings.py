"""The settings file: API keys, preferences and everything else that is remembered between runs."""

import json
import os
import threading
import time

from jobslop.config import DATA_DIR

SETTINGS_FILE = DATA_DIR / "settings.json"


# ---------------------------------------------------------------- settings

KEY_NAMES = ("apify_token",)          # the app's own keys; plugins add theirs (Reed, Adzuna, ...)

def load_settings():
    if not SETTINGS_FILE.exists():
        return {}
    for attempt in range(5):                 # retry briefly if the file is being swapped in
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
        except Exception:
            time.sleep(0.05)
    return {}


settings_lock = threading.RLock()


def update_settings(change):
    """Change settings.json safely: one change at a time, and written to a temporary file first,
    so two quick saves can't overwrite each other and a half-written file is never read."""
    with settings_lock:
        s = load_settings()
        change(s)
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
        os.replace(tmp, SETTINGS_FILE)
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
