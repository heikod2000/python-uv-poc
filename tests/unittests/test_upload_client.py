from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.upload_client import (
    _DEFAULT_BASE_URL,
    _DEFAULT_CONCURRENCY,
    _WIDTH,
    _header,
    _human_size,
    _rel,
    _run,
    _upload,
)

# ---------------------------------------------------------------------------
# _human_size
# ---------------------------------------------------------------------------


def test_human_size_bytes() -> None:
    assert _human_size(0) == "0 B"
    assert _human_size(1023) == "1023 B"


def test_human_size_kilobytes() -> None:
    assert _human_size(1024) == "1 KB"
    assert _human_size(1536) == "1 KB"  # truncates, no rounding


def test_human_size_megabytes() -> None:
    assert _human_size(1024 * 1024) == "1 MB"


def test_human_size_gigabytes() -> None:
    assert _human_size(1024**3) == "1 GB"


def test_human_size_no_decimals() -> None:
    assert "." not in _human_size(1_500_000)


# ---------------------------------------------------------------------------
# _header
# ---------------------------------------------------------------------------


def test_header_without_label_is_all_equals() -> None:
    assert _header() == "=" * _WIDTH


def test_header_total_width_without_label() -> None:
    assert len(_header()) == _WIDTH


def test_header_total_width_with_label() -> None:
    assert len(_header("some label")) == _WIDTH


def test_header_contains_label() -> None:
    assert "upload session starts" in _header("upload session starts")


# ---------------------------------------------------------------------------
# _rel
# ---------------------------------------------------------------------------


def test_rel_returns_relative_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    file = tmp_path / "sub" / "file.pdf"
    assert _rel(file) == str(Path("sub") / "file.pdf")


def test_rel_falls_back_to_absolute_outside_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    other = tmp_path.parent / "other" / "file.pdf"
    result = _rel(other)
    assert Path(result).is_absolute()


# ---------------------------------------------------------------------------
# _upload
# ---------------------------------------------------------------------------


def _mock_client(status: int = 200, text: str = "") -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.text = text
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    return client


def test_upload_returns_path(tmp_path: Path) -> None:
    file = tmp_path / "doc.pdf"
    file.write_bytes(b"x" * 10)

    path, *_ = asyncio.run(_upload(asyncio.Semaphore(1), _mock_client(), file))

    assert path == file


def test_upload_returns_status_code(tmp_path: Path) -> None:
    file = tmp_path / "doc.pdf"
    file.write_bytes(b"x" * 10)

    _, status, *_ = asyncio.run(_upload(asyncio.Semaphore(1), _mock_client(422), file))

    assert status == 422


def test_upload_returns_correct_size(tmp_path: Path) -> None:
    file = tmp_path / "doc.pdf"
    file.write_bytes(b"x" * 42)

    _, _, size, *_ = asyncio.run(_upload(asyncio.Semaphore(1), _mock_client(), file))

    assert size == 42


def test_upload_returns_non_negative_elapsed(tmp_path: Path) -> None:
    file = tmp_path / "doc.pdf"
    file.write_bytes(b"x")

    _, _, _, elapsed, _ = asyncio.run(_upload(asyncio.Semaphore(1), _mock_client(), file))

    assert elapsed >= 0


def test_upload_uses_stem_as_file_id(tmp_path: Path) -> None:
    file = tmp_path / "my-report.pdf"
    file.write_bytes(b"data")
    client = _mock_client()

    asyncio.run(_upload(asyncio.Semaphore(1), client, file))

    assert client.post.call_args.kwargs["data"]["file_id"] == "my-report"


def test_upload_detects_pdf_content_type(tmp_path: Path) -> None:
    file = tmp_path / "doc.pdf"
    file.write_bytes(b"data")
    client = _mock_client()

    asyncio.run(_upload(asyncio.Semaphore(1), client, file))

    _, _, content_type = client.post.call_args.kwargs["files"]["file"]
    assert content_type == "application/pdf"


def test_upload_falls_back_to_octet_stream(tmp_path: Path) -> None:
    file = tmp_path / "doc.unknownxyz"
    file.write_bytes(b"data")
    client = _mock_client()

    asyncio.run(_upload(asyncio.Semaphore(1), client, file))

    _, _, content_type = client.post.call_args.kwargs["files"]["file"]
    assert content_type == "application/octet-stream"


def test_upload_returns_empty_error_text_on_success(tmp_path: Path) -> None:
    file = tmp_path / "doc.pdf"
    file.write_bytes(b"x")

    *_, error_text = asyncio.run(_upload(asyncio.Semaphore(1), _mock_client(200), file))

    assert error_text == ""


def test_upload_returns_error_text_on_failure(tmp_path: Path) -> None:
    file = tmp_path / "doc.pdf"
    file.write_bytes(b"x")

    *_, error_text = asyncio.run(_upload(asyncio.Semaphore(1), _mock_client(422, text='{"detail": "too large"}'), file))

    assert error_text == '{"detail": "too large"}'


def test_upload_respects_semaphore(tmp_path: Path) -> None:
    file = tmp_path / "doc.pdf"
    file.write_bytes(b"x")
    sem = asyncio.Semaphore(1)

    asyncio.run(_upload(sem, _mock_client(), file))

    assert sem._value == 1  # released after call  # noqa: SLF001


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------


def _fake_upload(status: int = 200, error_text: str = ""):
    async def _inner(sem: asyncio.Semaphore, client: object, path: Path) -> tuple[Path, int, int, float, str]:
        return path, status, path.stat().st_size, 1.0, error_text if status >= 400 else ""

    return _inner


@pytest.fixture()
def mock_http_client() -> MagicMock:
    client = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    with patch("app.upload_client.httpx.AsyncClient", return_value=ctx):
        yield client


def test_run_returns_0_when_all_pass(tmp_path: Path, mock_http_client: MagicMock) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x" * 10)
    (tmp_path / "b.pdf").write_bytes(b"x" * 20)

    with patch("app.upload_client._upload", new=_fake_upload(200)):
        result = asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    assert result == 0


def test_run_returns_1_when_any_fails(tmp_path: Path, mock_http_client: MagicMock) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x" * 10)

    with patch("app.upload_client._upload", new=_fake_upload(422)):
        result = asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    assert result == 1


def test_run_returns_0_for_empty_dir(tmp_path: Path) -> None:
    result = asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    assert result == 0


def test_run_prints_nothing_to_do_for_empty_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    assert "nothing to do" in capsys.readouterr().out


def test_run_output_shows_passed(tmp_path: Path, mock_http_client: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "file.pdf").write_bytes(b"x" * 10)

    with patch("app.upload_client._upload", new=_fake_upload(200)):
        asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    assert "PASSED" in capsys.readouterr().out


def test_run_output_shows_failed(tmp_path: Path, mock_http_client: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "file.pdf").write_bytes(b"x" * 10)

    with patch("app.upload_client._upload", new=_fake_upload(422)):
        asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    assert "FAILED" in capsys.readouterr().out


def test_run_output_shows_http_status_on_failure(tmp_path: Path, mock_http_client: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "file.pdf").write_bytes(b"x" * 10)

    with patch("app.upload_client._upload", new=_fake_upload(422)):
        asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    assert "HTTP 422" in capsys.readouterr().out


def test_run_output_shows_error_text_on_failure(tmp_path: Path, mock_http_client: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "file.pdf").write_bytes(b"x" * 10)

    with patch("app.upload_client._upload", new=_fake_upload(422, error_text='{"detail": "File exceeds 400 KB limit"}')):
        asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    assert '{"detail": "File exceeds 400 KB limit"}' in capsys.readouterr().out


def test_run_discovers_files_recursively(tmp_path: Path, mock_http_client: MagicMock) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.pdf").write_bytes(b"x")
    found: list[Path] = []

    async def capturing_upload(sem: asyncio.Semaphore, client: object, path: Path) -> tuple[Path, int, int, float, str]:
        found.append(path)
        return path, 200, 1, 0.1, ""

    with patch("app.upload_client._upload", new=capturing_upload):
        asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    assert any(p.name == "deep.pdf" for p in found)


def test_run_counts_exception_as_failed(tmp_path: Path, mock_http_client: MagicMock) -> None:
    (tmp_path / "file.pdf").write_bytes(b"x")

    async def raising_upload(sem: asyncio.Semaphore, client: object, path: Path) -> tuple[Path, int, int, float]:
        raise ConnectionError("refused")

    with patch("app.upload_client._upload", new=raising_upload):
        result = asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    assert result == 1


def test_run_output_shows_error_label(tmp_path: Path, mock_http_client: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "file.pdf").write_bytes(b"x")

    async def raising_upload(sem: asyncio.Semaphore, client: object, path: Path) -> tuple[Path, int, int, float]:
        raise ConnectionError("refused")

    with patch("app.upload_client._upload", new=raising_upload):
        asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    assert "ERROR" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _run  --limit
# ---------------------------------------------------------------------------


def test_run_limit_restricts_file_count(tmp_path: Path, mock_http_client: MagicMock) -> None:
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        (tmp_path / name).write_bytes(b"x")
    found: list[Path] = []

    async def capturing(sem: asyncio.Semaphore, client: object, path: Path) -> tuple[Path, int, int, float, str]:
        found.append(path)
        return path, 200, 1, 0.1, ""

    with patch("app.upload_client._upload", new=capturing):
        asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY, limit=2))

    assert len(found) == 2


def test_run_limit_clamps_to_available(tmp_path: Path, mock_http_client: MagicMock) -> None:
    (tmp_path / "only.pdf").write_bytes(b"x")
    found: list[Path] = []

    async def capturing(sem: asyncio.Semaphore, client: object, path: Path) -> tuple[Path, int, int, float, str]:
        found.append(path)
        return path, 200, 1, 0.1, ""

    with patch("app.upload_client._upload", new=capturing):
        asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY, limit=10))

    assert len(found) == 1


def test_run_limit_output_shows_random_sample(tmp_path: Path, mock_http_client: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        (tmp_path / name).write_bytes(b"x")

    with patch("app.upload_client._upload", new=_fake_upload(200)):
        asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY, limit=2))

    assert "random sample" in capsys.readouterr().out


def test_run_no_limit_output_does_not_show_random_sample(tmp_path: Path, mock_http_client: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")

    with patch("app.upload_client._upload", new=_fake_upload(200)):
        asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    assert "random sample" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _run  --proxy
# ---------------------------------------------------------------------------


def test_run_proxy_is_passed_to_async_client(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")
    client_mock = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client_mock)
    ctx.__aexit__ = AsyncMock(return_value=None)
    constructor = MagicMock(return_value=ctx)

    with patch("app.upload_client.httpx.AsyncClient", new=constructor):
        with patch("app.upload_client._upload", new=_fake_upload(200)):
            asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY, proxy="http://proxy.example.com:8080"))

    _, kwargs = constructor.call_args
    assert kwargs.get("proxy") == "http://proxy.example.com:8080"


def test_run_no_proxy_does_not_pass_proxy_key(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")
    client_mock = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client_mock)
    ctx.__aexit__ = AsyncMock(return_value=None)
    constructor = MagicMock(return_value=ctx)

    with patch("app.upload_client.httpx.AsyncClient", new=constructor):
        with patch("app.upload_client._upload", new=_fake_upload(200)):
            asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY))

    _, kwargs = constructor.call_args
    assert "proxy" not in kwargs


def test_run_proxy_shown_in_output(tmp_path: Path, mock_http_client: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")

    with patch("app.upload_client._upload", new=_fake_upload(200)):
        asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY, proxy="http://proxy.example.com:8080"))

    assert "http://proxy.example.com:8080" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _run  --no-proxy
# ---------------------------------------------------------------------------


def _make_constructor() -> tuple[MagicMock, MagicMock]:
    client_mock = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client_mock)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=ctx), client_mock


def test_run_no_proxy_uses_mounts_when_proxy_set(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")
    constructor, _ = _make_constructor()

    with patch("app.upload_client.httpx.AsyncClient", new=constructor):
        with patch("app.upload_client._upload", new=_fake_upload(200)):
            asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY, proxy="http://proxy.example.com:8080", no_proxy=["localhost", "127.0.0.1"]))

    _, kwargs = constructor.call_args
    assert "mounts" in kwargs
    assert "proxy" not in kwargs


def test_run_no_proxy_excludes_hosts_from_mounts(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")
    constructor, _ = _make_constructor()

    with patch("app.upload_client.httpx.AsyncClient", new=constructor):
        with patch("app.upload_client._upload", new=_fake_upload(200)):
            asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY, proxy="http://proxy.example.com:8080", no_proxy=["localhost", "127.0.0.1"]))

    _, kwargs = constructor.call_args
    mounts: dict = kwargs["mounts"]
    assert mounts.get("all://localhost") is None
    assert mounts.get("all://127.0.0.1") is None


def test_run_no_proxy_shown_in_output(tmp_path: Path, mock_http_client: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")

    with patch("app.upload_client._upload", new=_fake_upload(200)):
        asyncio.run(_run(_DEFAULT_BASE_URL, tmp_path, _DEFAULT_CONCURRENCY, proxy="http://proxy.example.com:8080", no_proxy=["localhost"]))

    assert "localhost" in capsys.readouterr().out
