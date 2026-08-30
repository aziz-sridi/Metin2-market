"""Small, database-free smoke tests for public API basics."""

import asyncio

import httpx

from api.main import app


async def _get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def test_health() -> None:
    response = asyncio.run(_get("/health"))

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_readiness_has_a_machine_readable_result() -> None:
    response = asyncio.run(_get("/ready"))

    assert response.status_code in {200, 503}
    assert response.json()["status"] in {"ready", "not_ready"}


def test_api_info_lists_documentation() -> None:
    response = asyncio.run(_get("/"))

    assert response.status_code == 200
    assert response.json()["endpoints"]["docs"] == "/docs"


def test_bundled_reference_data_is_available() -> None:
    categories = asyncio.run(_get("/api/reference/categories"))
    enchantments = asyncio.run(_get("/api/reference/enchantments"))

    assert categories.status_code == 200
    assert categories.json()
    assert enchantments.status_code == 200
    assert enchantments.json()
