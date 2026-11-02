"""Extension points: the places plugins can add things to (besides job boards, see boards.registry).

Everything a plugin adds is kept under its id, so turning the plugin off takes all of it away again.
"""

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Generic, TypeVar

from jobslop.plugins.manifest import ProfileField, SettingField

T = TypeVar("T")


class PluginItems(Generic[T]):
    """Items in the order they were added, remembered by the plugin that added them."""

    def __init__(self) -> None:
        self._items: list[tuple[str, T]] = []
        self._lock = threading.Lock()

    def add(self, plugin: str, item: T) -> None:
        with self._lock:
            self._items.append((plugin, item))

    def remove_plugin(self, plugin: str) -> None:
        with self._lock:
            self._items = [(p, i) for p, i in self._items if p != plugin]

    def items(self) -> list[tuple[str, T]]:
        with self._lock:
            return list(self._items)

    def __iter__(self) -> Iterator[T]:
        return iter([i for _, i in self.items()])


Endpoint = Callable[[dict, dict | None], object]      # (query parameters, posted JSON or None) -> JSON-able answer


@dataclass(frozen=True)
class NamedEndpoint:
    name: str
    fn: Endpoint


@dataclass(frozen=True)
class Terms:
    """Words in one language: screen text (English -> translation) or job titles (English -> local titles)."""
    lang: str
    words: dict


class ExtensionPoints:
    def __init__(self) -> None:
        self.settings: PluginItems[SettingField] = PluginItems()
        self.profile_fields: PluginItems[ProfileField] = PluginItems()
        self.endpoints: PluginItems[NamedEndpoint] = PluginItems()
        self.translations: PluginItems[Terms] = PluginItems()
        self.search_terms: PluginItems[Terms] = PluginItems()

    def _all(self) -> list[PluginItems]:
        return [self.settings, self.profile_fields, self.endpoints, self.translations, self.search_terms]

    def remove_plugin(self, plugin: str) -> None:
        for items in self._all():
            items.remove_plugin(plugin)

    def endpoint(self, plugin: str, name: str) -> Endpoint | None:
        return next((e.fn for p, e in self.endpoints.items() if p == plugin and e.name == name), None)

    def setting_keys(self, secret_only: bool = False) -> list[str]:
        return [s.key for s in self.settings if not secret_only or s.type == "secret"]


POINTS = ExtensionPoints()
