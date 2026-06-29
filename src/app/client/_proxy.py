from __future__ import annotations

import os

_PROXY_ENV_VARS = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")
_NO_PROXY_ENV_VARS = ("NO_PROXY", "no_proxy")


def _env_proxy() -> str | None:
    return next((os.environ[v] for v in _PROXY_ENV_VARS if v in os.environ), None)


def _env_no_proxy() -> list[str]:
    raw = next((os.environ[v] for v in _NO_PROXY_ENV_VARS if v in os.environ), "")
    return [h.strip() for h in raw.split(",") if h.strip()]


def _resolve_proxy(cli_proxy: str | None) -> str | None:
    return cli_proxy or _env_proxy()


def _resolve_no_proxy(cli_no_proxy: list[str] | None) -> list[str]:
    combined = (cli_no_proxy or []) + _env_no_proxy()
    return list(dict.fromkeys(combined))
