"""CLI tool: upload all files from a resources directory to the FastAPI /upload endpoint in parallel."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import mimetypes
import random
import sys
import time
from pathlib import Path
from urllib.request import getproxies

import httpx2 as httpx

_DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_DEFAULT_RESOURCES = Path(__file__).parent.parent.parent / "resources"
_DEFAULT_CONCURRENCY = 20
_WIDTH = 72


def _env_proxy() -> str | None:
    """Return the effective proxy URL from environment/system (including Windows Registry)."""
    info = getproxies()
    for scheme in ("https", "http", "all"):
        if info.get(scheme):
            url = info[scheme]
            return url if "://" in url else f"http://{url}"
    return None


def _env_no_proxy() -> list[str]:
    """Return no-proxy hosts from environment/system (including Windows Registry)."""
    raw = getproxies().get("no", "")
    return [h.strip() for h in raw.split(",") if h.strip()]


def _resolve_proxy(cli_proxy: str | None) -> str | None:
    return cli_proxy if cli_proxy is not None else _env_proxy()


def _resolve_no_proxy(cli_no_proxy: list[str] | None) -> list[str]:
    combined = (cli_no_proxy or []) + _env_no_proxy()
    return list(dict.fromkeys(combined))


def _no_proxy_mount_key(host: str) -> str:
    """Return the httpx mount-key pattern for a no-proxy host, mirroring httpx's NO_PROXY parsing."""
    if "://" in host:
        return host
    if host.lower() == "localhost":
        return f"all://{host}"
    try:
        ipaddress.IPv4Address(host.split("/")[0])
        return f"all://{host}"
    except ValueError:
        pass
    try:
        ipaddress.IPv6Address(host.split("/")[0])
        return f"all://[{host}]"
    except ValueError:
        pass
    return f"all://*{host}"


def _header(label: str = "") -> str:
    inner = f" {label} " if label else ""
    pad = (_WIDTH - len(inner)) // 2
    return "=" * pad + inner + "=" * (_WIDTH - pad - len(inner))


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n} {unit}"
        n //= 1024
    return f"{n} PB"


async def _upload(sem: asyncio.Semaphore, client: httpx.AsyncClient, path: Path) -> tuple[Path, int, int, float, str]:
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
    return path, response.status_code, len(data), elapsed, "" if ok else response.text


async def _run(base_url: str, resources_dir: Path, concurrency: int, limit: int | None = None, proxy: str | None = None, no_proxy: list[str] | None = None) -> int:
    effective_proxy = _resolve_proxy(proxy)
    effective_no_proxy = _resolve_no_proxy(no_proxy)

    all_files = sorted(f for f in resources_dir.rglob("*") if f.is_file())
    available = len(all_files)
    files = random.sample(all_files, min(limit, available)) if limit is not None else all_files
    total = len(files)
    col = max((len(_rel(f)) for f in files), default=40) + 2

    print(_header("upload session starts"))
    print(f"base url:    {base_url}")
    print(f"concurrency: {concurrency}")
    if effective_proxy:
        print(f"proxy:       {effective_proxy}")
    if effective_no_proxy:
        print(f"no-proxy:    {', '.join(effective_no_proxy)}")
    if limit is not None:
        print(f"resources:   {resources_dir}  ({total} of {available} file{'s' if available != 1 else ''}, random sample)")
    else:
        print(f"resources:   {resources_dir}  ({total} file{'s' if total != 1 else ''})")
    print(f"collected {total} file{'s' if total != 1 else ''}\n")

    if not files:
        print("no files collected — nothing to do")
        return 0

    start = time.monotonic()
    sem = asyncio.Semaphore(concurrency)

    # trust_env=False only when an explicit CLI proxy is given — otherwise let httpx read
    # env vars and (on Windows) the system proxy registry via its own trust_env=True default.
    client_kwargs: dict = {"base_url": base_url}
    if proxy is not None:
        # Explicit CLI proxy: we own the full configuration, disable auto-detection.
        client_kwargs["trust_env"] = False
        no_proxy_mounts = {_no_proxy_mount_key(h): None for h in effective_no_proxy}
        if no_proxy_mounts:
            client_kwargs["mounts"] = {"all://": httpx.AsyncHTTPTransport(proxy=proxy), **no_proxy_mounts}
        else:
            client_kwargs["proxy"] = proxy
    elif no_proxy:
        # No explicit CLI proxy, but --no-proxy specified: let httpx discover the proxy via
        # trust_env=True (env vars + Windows Registry), and override specific hosts to go direct.
        client_kwargs["mounts"] = {_no_proxy_mount_key(h): None for h in no_proxy}
    # else: nothing explicit — httpx defaults (trust_env=True) handle everything.

    async with httpx.AsyncClient(**client_kwargs) as client:
        outcomes = await asyncio.gather(
            *(_upload(sem, client, f) for f in files),
            return_exceptions=True,
        )

    elapsed = time.monotonic() - start
    passed = failed = 0

    for i, outcome in enumerate(outcomes, 1):
        pct = f"[{i * 100 // total:3d}%]"
        if isinstance(outcome, BaseException):
            label = "ERROR "
            print(f"{_rel(files[i - 1]):<{col}} {label} {pct}")
            print(f"  {type(outcome).__name__}: {outcome}")
            failed += 1
        else:
            path, status, size, secs, error_text = outcome
            ok = 200 <= status < 300
            label = "PASSED" if ok else "FAILED"
            print(f"{_rel(path):<{col}} {label} {pct}  {_human_size(size):>7}  {secs:.0f}s")
            if not ok:
                print(f"  HTTP {status}  {error_text}".rstrip())
            passed += ok
            failed += not ok

    print()
    parts = []
    if passed:
        parts.append(f"{passed} passed")
    if failed:
        parts.append(f"{failed} failed")
    print(_header(f"{', '.join(parts)} in {elapsed:.2f}s"))
    return 0 if failed == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload all resource files to the FastAPI /upload endpoint in parallel.")
    parser.add_argument(
        "--url",
        default=_DEFAULT_BASE_URL,
        metavar="URL",
        help=f"Base URL of the server (default: {_DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--resources",
        default=_DEFAULT_RESOURCES,
        type=Path,
        metavar="DIR",
        help=f"Directory with files to upload (default: {_DEFAULT_RESOURCES})",
    )
    parser.add_argument(
        "--concurrency",
        default=_DEFAULT_CONCURRENCY,
        type=int,
        metavar="N",
        help=f"Max simultaneous uploads (default: {_DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--limit",
        default=None,
        type=int,
        metavar="N",
        help="Process only N randomly selected files (default: all files)",
    )
    parser.add_argument(
        "--proxy",
        default=None,
        metavar="URL",
        help="Proxy URL, e.g. http://proxy.example.com:8080 or socks5://localhost:1080",
    )
    parser.add_argument(
        "--no-proxy",
        default=None,
        metavar="HOSTS",
        help="Comma-separated list of hosts that bypass the proxy, e.g. localhost,127.0.0.1",
    )
    args = parser.parse_args()
    no_proxy = [h.strip() for h in args.no_proxy.split(",")] if args.no_proxy else None
    sys.exit(asyncio.run(_run(args.url, args.resources, args.concurrency, args.limit, args.proxy, no_proxy)))


if __name__ == "__main__":
    main()
