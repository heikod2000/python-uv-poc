from __future__ import annotations

import httpx2 as httpx

from app.client._errors import _describe_error

# ---------------------------------------------------------------------------
# _describe_error  — generic exceptions
# ---------------------------------------------------------------------------


def test_describe_error_includes_type_and_message() -> None:
    lines = _describe_error(ConnectionError("refused"))
    assert lines[0] == "builtins.ConnectionError: refused"


def test_describe_error_omits_colon_when_message_empty() -> None:
    lines = _describe_error(httpx.ConnectError(""))
    assert lines[0] == "httpx2.ConnectError"


def test_describe_error_plain_exception_has_no_target_or_cause() -> None:
    lines = _describe_error(ConnectionError("refused"))
    assert len(lines) == 1


# ---------------------------------------------------------------------------
# _describe_error  — request target
# ---------------------------------------------------------------------------


def test_describe_error_includes_target_when_request_set() -> None:
    request = httpx.Request("GET", "http://example.com/upload")
    exc = httpx.ConnectError("boom", request=request)

    lines = _describe_error(exc)

    assert any("target: GET http://example.com/upload" in line for line in lines)


def test_describe_error_omits_target_when_request_not_set() -> None:
    lines = _describe_error(httpx.ConnectError("boom"))
    assert not any("target:" in line for line in lines)


# ---------------------------------------------------------------------------
# _describe_error  — connection hints
# ---------------------------------------------------------------------------


def test_describe_error_hints_connect_error() -> None:
    lines = _describe_error(httpx.ConnectError("boom"))
    assert any("could not establish a connection" in line for line in lines)


def test_describe_error_hints_connect_timeout() -> None:
    lines = _describe_error(httpx.ConnectTimeout("boom"))
    assert any("timed out before the server responded" in line for line in lines)


def test_describe_error_hints_read_timeout() -> None:
    lines = _describe_error(httpx.ReadTimeout("boom"))
    assert any("did not send a response in time" in line for line in lines)


def test_describe_error_hints_proxy_error() -> None:
    lines = _describe_error(httpx.ProxyError("boom"))
    assert any("through the configured proxy" in line for line in lines)


def test_describe_error_no_hint_for_unrelated_exception() -> None:
    lines = _describe_error(ValueError("boom"))
    assert not any("hint:" in line for line in lines)


# ---------------------------------------------------------------------------
# _describe_error  — cause chain
# ---------------------------------------------------------------------------


def test_describe_error_includes_direct_cause() -> None:
    try:
        try:
            raise OSError("[Errno 111] Connection refused")
        except OSError as inner:
            raise httpx.ConnectError("boom") from inner
    except httpx.ConnectError as exc:
        lines = _describe_error(exc)

    assert any("caused by: builtins.OSError: [Errno 111] Connection refused" in line for line in lines)


def test_describe_error_walks_multiple_causes() -> None:
    try:
        try:
            try:
                raise ValueError("root cause")
            except ValueError as root:
                raise OSError("middle") from root
        except OSError as middle:
            raise httpx.ConnectError("boom") from middle
    except httpx.ConnectError as exc:
        lines = _describe_error(exc)

    text = "\n".join(lines)
    assert "caused by: builtins.OSError: middle" in text
    assert "caused by: builtins.ValueError: root cause" in text


def test_describe_error_without_cause_has_no_caused_by_line() -> None:
    lines = _describe_error(httpx.ConnectError("boom"))
    assert not any("caused by:" in line for line in lines)
