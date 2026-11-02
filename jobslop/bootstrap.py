"""Puts the app together at start-up: the core boards, then the plugins. Safe to call more than once."""

import threading

from jobslop.boards.catalog import core_boards
from jobslop.boards.registry import BOARDS
from jobslop.plugins.manager import PLUGINS

_lock = threading.Lock()
_done = {"core": False}


def setup() -> None:
    with _lock:
        if not _done["core"]:
            BOARDS.add_all(core_boards())
            _done["core"] = True
            PLUGINS.discover()
            PLUGINS.load_enabled()
