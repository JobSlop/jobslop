"""The boards the app can search right now. Core boards and plugins add theirs here at start-up."""

import threading
from collections.abc import Iterable, Iterator

from jobslop.boards.base import GROUPS, Board


class BoardRegistry:
    """Boards by name, in the order they were added (grouped for the screen)."""

    def __init__(self) -> None:
        self._boards: dict[str, Board] = {}
        self._lock = threading.Lock()

    def add(self, board: Board) -> None:
        with self._lock:
            if board.name in self._boards and self._boards[board.name].plugin != board.plugin:
                raise ValueError(f"A board called {board.name} already exists ({self._boards[board.name].plugin})")
            self._boards[board.name] = board

    def add_all(self, boards: Iterable[Board]) -> None:
        for b in boards:
            self.add(b)

    def remove_plugin(self, plugin: str) -> None:
        """Take away every board a plugin added (when it is turned off)."""
        with self._lock:
            self._boards = {n: b for n, b in self._boards.items() if b.plugin != plugin}

    def get(self, name: str) -> Board | None:
        return self._boards.get(name)

    def names(self) -> list[str]:
        return [b.name for b in self]

    def __contains__(self, name: str) -> bool:
        return name in self._boards

    def __iter__(self) -> Iterator[Board]:
        boards = list(self._boards.values())
        return iter(sorted(boards, key=lambda b: GROUPS.index(b.group)))      # stable: keeps adding order

    def __len__(self) -> int:
        return len(self._boards)


BOARDS = BoardRegistry()
