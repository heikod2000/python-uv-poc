from __future__ import annotations

import asyncio
import mimetypes
import time
from pathlib import Path

import httpx2 as httpx


async def _upload(sem: asyncio.Semaphore, client: httpx.AsyncClient, path: Path) -> tuple[Path, int, int, float, str, bytes]:
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    data = await asyncio.to_thread(path.read_bytes)
    async with sem:
        t0 = time.monotonic()
        response = await client.post(
            "/upload",
            data={"file_id": path.stem},
            files={"file": (path.name, data, content_type)},
            timeout=60.0,
        )
        elapsed = time.monotonic() - t0
    ok = 200 <= response.status_code < 300
    return path, response.status_code, len(data), elapsed, "" if ok else response.text, response.content if ok else b""


def _build_client_kwargs(base_url: str, effective_proxy: str | None, effective_no_proxy: list[str]) -> dict:
    kwargs: dict = {"base_url": base_url, "trust_env": False}
    if effective_proxy and effective_no_proxy:
        kwargs["mounts"] = {
            "all://": httpx.AsyncHTTPTransport(proxy=effective_proxy),
            **{f"all://{host}": None for host in effective_no_proxy},
        }
    elif effective_proxy:
        kwargs["proxy"] = effective_proxy
    return kwargs
