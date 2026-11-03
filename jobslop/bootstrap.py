"""Puts the app together at start-up: the core boards, then the plugins. Safe to call more than once."""

import shutil
import threading

from jobslop.boards.catalog import core_boards
from jobslop.boards.registry import BOARDS
from jobslop.plugins.installer import STAGING_DIR
from jobslop.plugins.manager import PLUGINS
from jobslop.plugins.migrate import migrate
from jobslop.settings import update_settings

_lock = threading.Lock()
_done = {"core": False}


def setup() -> None:
    with _lock:
        if not _done["core"]:
            BOARDS.add_all(core_boards())
            _done["core"] = True
            shutil.rmtree(STAGING_DIR, ignore_errors=True)     # half-finished installs from last time
            migrate(update_settings)                           # plugins split up or defaults changed
            PLUGINS.discover()
            PLUGINS.load_enabled()
