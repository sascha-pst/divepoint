from fastapi.testclient import TestClient

from app.cache.memory import MemoryCache
from app.main import app


def test_cache_expiration_and_isolation():
    now = [0]
    cache = MemoryCache(clock=lambda: now[0])
    cache.put("a", {"items": [1]}, 10)
    value = cache.get("a")
    value["items"].append(2)
    assert cache.get("a") == {"items": [1]}
    now[0] = 10
    assert cache.get("a") is None


def test_health_and_unimplemented_plan():
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.post("/v1/dives/plan", json={"text": "Monterey"}).status_code == 501
