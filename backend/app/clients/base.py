import asyncio
import json
from time import monotonic
from typing import Any

import httpx

from app.cache.memory import MemoryCache
from app.config import Settings


class PublicDataClient:
    """One instance per provider: cache, pacing, timeout and bounded transient retries."""

    def __init__(
        self,
        base_url: str,
        *,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        cache: MemoryCache | None = None,
    ):
        self.settings = settings or Settings()
        self.cache = cache or MemoryCache()
        self._http = httpx.AsyncClient(
            base_url=base_url,
            transport=transport,
            timeout=self.settings.upstream_timeout_seconds,
            headers={"User-Agent": self.settings.user_agent, "Accept": "application/json"},
        )
        self._lock = asyncio.Lock()
        self._next_request = 0.0

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        key = str(self._http.base_url) + path + json.dumps(params or {}, sort_keys=True)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        for attempt in range(3):
            async with self._lock:
                await asyncio.sleep(max(0, self._next_request - monotonic()))
                self._next_request = monotonic() + self.settings.upstream_interval_seconds
                try:
                    response = await self._http.get(path, params=params)
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt == 2:
                        raise
                    continue
            if (response.status_code == 429 or response.status_code >= 500) and attempt < 2:
                try:
                    delay = float(response.headers.get("Retry-After", 2**attempt))
                except ValueError:
                    delay = 2**attempt
                await asyncio.sleep(min(max(delay, 0), 5))
                continue
            response.raise_for_status()
            payload = response.json() if response.status_code != 204 else []
            self.cache.put(key, payload, self.settings.cache_ttl_seconds)
            return payload
        raise RuntimeError("Unreachable retry state")

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()
