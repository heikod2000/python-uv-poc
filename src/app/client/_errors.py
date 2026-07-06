from __future__ import annotations

import httpx2 as httpx

_CONNECTION_HINTS: tuple[tuple[type[BaseException], str], ...] = (
    (httpx.ProxyError, "failed to negotiate the connection through the configured proxy"),
    (httpx.ConnectTimeout, "connection attempt timed out before the server responded"),
    (httpx.PoolTimeout, "timed out waiting for a free connection slot in the pool (try lowering --concurrency)"),
    (httpx.WriteTimeout, "connection was established but sending the request timed out"),
    (httpx.ReadTimeout, "connection was established but the server did not send a response in time"),
    (httpx.RemoteProtocolError, "the server violated the HTTP protocol while responding"),
    (httpx.ConnectError, "could not establish a connection to the server (DNS failure, connection refused, or network unreachable)"),
)


def _exc_label(exc: BaseException) -> str:
    name = f"{type(exc).__module__}.{type(exc).__qualname__}"
    return f"{name}: {exc}" if str(exc) else name


def _describe_error(exc: BaseException) -> list[str]:
    """Render diagnostic detail for a failed upload: target, category hint, and cause chain."""
    lines = [_exc_label(exc)]

    try:
        request = exc.request  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError):
        request = None
    if request is not None:
        lines.append(f"  target: {request.method} {request.url}")

    for exc_type, hint in _CONNECTION_HINTS:
        if isinstance(exc, exc_type):
            lines.append(f"  hint: {hint}")
            break

    seen = {id(exc)}
    cause = exc.__cause__ or exc.__context__
    depth = 0
    while cause is not None and id(cause) not in seen and depth < 3:
        lines.append(f"  caused by: {_exc_label(cause)}")
        seen.add(id(cause))
        cause = cause.__cause__ or cause.__context__
        depth += 1

    return lines
