from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from quran_mcp.server import get_or_create_mcp


@pytest.mark.integration
def test_public_http_surface_smoke() -> None:
    app = get_or_create_mcp().http_app()

    with TestClient(app) as client:
        landing = client.get("/")
        docs_json = client.get("/documentation/data.json")
        skill = client.get("/SKILL.md")
        icon = client.head("/icon.png")

    assert landing.status_code == 200
    assert "text/html" in landing.headers["content-type"]

    assert docs_json.status_code == 200
    assert "application/json" in docs_json.headers["content-type"]

    assert skill.status_code == 200
    assert "text/markdown" in skill.headers["content-type"]
    assert skill.headers["content-disposition"] == "attachment; filename=SKILL.md"

    assert icon.status_code == 200
    assert icon.headers["content-type"] == "image/png"
