from copy import deepcopy
from time import monotonic
from typing import Any


class MemoryCache:
    """Process-local development cache. Replace with persistent storage before production."""

    def __init__(self, clock=monotonic):
        self._clock = clock
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires, value = entry
        if expires <= self._clock():
            del self._entries[key]
            return None
        return deepcopy(value)

    def put(self, key: str, value: Any, ttl: float) -> None:
        self._entries[key] = (self._clock() + ttl, deepcopy(value))
