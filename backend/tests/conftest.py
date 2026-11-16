"""Tests may replay fixtures, but must never reach a public HTTP API."""

import httpx
import pytest


@pytest.fixture(autouse=True)
def block_live_http(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Live HTTP is forbidden in tests; use recorded fixtures")

    async def async_blocked(*args, **kwargs):
        blocked()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked)
