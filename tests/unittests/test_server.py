from __future__ import annotations

import io
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.server import _processing_semaphore, app

client = TestClient(app)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /echo
# ---------------------------------------------------------------------------


def test_echo_endpoint() -> None:
    response = client.post("/echo", json={"message": "hello world"})

    assert response.status_code == 200
    assert response.json() == {"message": "hello world"}


def test_echo_empty_message() -> None:
    response = client.post("/echo", json={"message": ""})

    assert response.status_code == 200
    assert response.json() == {"message": ""}


def test_echo_missing_message_field() -> None:
    response = client.post("/echo", json={})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /upload
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def skip_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.server.asyncio.sleep", AsyncMock())


def _upload(file_id: str = "abc123", content: bytes = b"hello", filename: str = "test.txt", content_type: str = "text/plain") -> object:
    return client.post(
        "/upload",
        data={"file_id": file_id},
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


def test_upload_returns_file_id() -> None:
    response = _upload(file_id="xyz")

    assert response.status_code == 200
    assert response.json()["file_id"] == "xyz"


def test_upload_returns_content_type() -> None:
    response = _upload(content_type="application/pdf")

    assert response.json()["content_type"] == "application/pdf"


def test_upload_returns_size() -> None:
    data = b"A" * 42
    response = _upload(content=data)

    assert response.json()["size"] == "42"


def test_upload_missing_file_id() -> None:
    response = client.post(
        "/upload",
        files={"file": ("test.txt", io.BytesIO(b"data"), "text/plain")},
    )

    assert response.status_code == 422


def test_upload_missing_file() -> None:
    response = client.post("/upload", data={"file_id": "abc"})

    assert response.status_code == 422


def test_upload_logs_content_type_and_size(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="app.server"):
        _upload(content=b"X" * 10, content_type="image/png")

    assert "image/png" in caplog.text
    assert "10" in caplog.text


def test_upload_semaphore_released_after_request() -> None:
    available_before = _processing_semaphore._value  # noqa: SLF001
    _upload()
    assert _processing_semaphore._value == available_before
