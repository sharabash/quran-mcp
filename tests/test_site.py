from __future__ import annotations

from pathlib import Path

import pytest

from quran_mcp.lib.site import handlers, manifest


def _scope(path: str, *, method: str = "GET", accept: str | None = None) -> dict:
    headers: list[tuple[bytes, bytes]] = []
    if accept is not None:
        headers.append((b"accept", accept.encode("latin-1")))
    return {
        "type": "http",
        "path": path,
        "method": method,
        "headers": headers,
        "client": ("127.0.0.1", 12345),
    }


def test_validate_required_assets_reports_missing_required_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        manifest,
        "routes",
        {
            "static": {
                "/icon.png": {
                    "file": tmp_path / "missing-icon.png",
                    "type": "image/png",
                }
            },
            "pages": {},
            "downloads": {},
            "dirs": {},
        },
    )

    assert manifest.validate_required_assets() == [
        f"/icon.png -> {tmp_path / 'missing-icon.png'} (file)"
    ]


def test_should_serve_landing_for_browser_requests_only() -> None:
    assert handlers._should_serve_landing(_scope("/", accept="text/html")) is True
    assert handlers._should_serve_landing(_scope("/", accept="text/event-stream")) is False
    assert handlers._should_serve_landing(_scope("/documentation", accept="text/html")) is False
    assert handlers._should_serve_landing(_scope("/", method="POST", accept="text/html")) is False


def test_dir_response_blocks_traversal_and_unknown_extensions(tmp_path: Path) -> None:
    base_dir = tmp_path / "assets"
    base_dir.mkdir()
    valid_png = base_dir / "ok.png"
    valid_png.write_bytes(b"png")
    (base_dir / "ok.txt").write_text("not-served", encoding="utf-8")
    outside_png = tmp_path / "escape.png"
    outside_png.write_bytes(b"escape")

    entry = {
        "dir": base_dir,
        "types": {".png": "image/png"},
    }

    allowed = handlers._dir_response(entry, "/assets/ok.png", "/assets/")
    blocked_traversal = handlers._dir_response(entry, "/assets/../escape.png", "/assets/")
    blocked_extension = handlers._dir_response(entry, "/assets/ok.txt", "/assets/")

    assert allowed is not None
    assert blocked_traversal is None
    assert blocked_extension is None


# ---------------------------------------------------------------------------
# _real_ip
# ---------------------------------------------------------------------------


def test_real_ip_from_cf_header() -> None:
    scope = {
        "headers": [(b"cf-connecting-ip", b"203.0.113.50")],
        "client": ("127.0.0.1", 12345),
    }
    assert handlers._real_ip(scope) == "203.0.113.50"


def test_real_ip_falls_back_to_client() -> None:
    scope = {"headers": [], "client": ("10.0.0.1", 9999)}
    assert handlers._real_ip(scope) == "10.0.0.1"


def test_real_ip_unknown_when_no_client() -> None:
    scope = {"headers": []}
    assert handlers._real_ip(scope) == "unknown"


# ---------------------------------------------------------------------------
# _static_file_response
# ---------------------------------------------------------------------------


def test_static_file_response_existing_file(tmp_path: Path) -> None:
    f = tmp_path / "icon.png"
    f.write_bytes(b"PNG")
    entry = {"file": f, "type": "image/png"}
    response = handlers._static_file_response(entry)
    assert response is not None


def test_static_file_response_missing_required(tmp_path: Path) -> None:
    entry = {"file": tmp_path / "missing.png", "type": "image/png", "required": True}
    response = handlers._static_file_response(entry)
    assert response is not None  # returns 500 PlainTextResponse


def test_static_file_response_missing_optional(tmp_path: Path) -> None:
    entry = {"file": tmp_path / "missing.png", "type": "image/png", "required": False}
    response = handlers._static_file_response(entry)
    assert response is None
