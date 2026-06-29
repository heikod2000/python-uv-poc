"""CLI tool: upload all files from a resources directory to the FastAPI /upload endpoint in parallel."""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import time
from pathlib import Path

import httpx2 as httpx

from app.client._fmt import _header, _human_size, _rel
from app.client._proxy import _env_proxy, _resolve_no_proxy, _resolve_proxy
from app.client._thumbnail import _DEFAULT_THUMB_DIR, _DEFAULT_THUMB_WIDTH, _make_thumb
from app.client._uploader import _build_client_kwargs, _upload

_DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_DEFAULT_RESOURCES = Path(__file__).parent.parent.parent.parent / "resources"
_DEFAULT_CONCURRENCY = 20


async def _run(
    base_url: str,
    resources_dir: Path,
    concurrency: int,
    limit: int | None = None,
    proxy: str | None = None,
    no_proxy: list[str] | None = None,
    thumb_width: int = _DEFAULT_THUMB_WIDTH,
    thumb_dir: Path = _DEFAULT_THUMB_DIR,
    generate_thumbs: bool = True,
) -> int:
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

    client_kwargs = _build_client_kwargs(base_url, effective_proxy, effective_no_proxy)
    async with httpx.AsyncClient(**client_kwargs) as client:
        outcomes = await asyncio.gather(
            *(_upload(sem, client, f) for f in files),
            return_exceptions=True,
        )

    elapsed = time.monotonic() - start
    passed = failed = thumbs_generated = 0

    for i, outcome in enumerate(outcomes, 1):
        pct = f"[{i * 100 // total:3d}%]"
        if isinstance(outcome, BaseException):
            print(f"{_rel(files[i - 1]):<{col}} ERROR  {pct}")
            print(f"  {type(outcome).__name__}: {outcome}")
            failed += 1
        else:
            path, status, size, secs, error_text, content = outcome
            ok = 200 <= status < 300
            print(f"{_rel(path):<{col}} {'PASSED' if ok else 'FAILED'} {pct}  {_human_size(size):>7}  {secs:.0f}s")
            if not ok:
                print(f"  HTTP {status}  {error_text}".rstrip())
            elif generate_thumbs:
                try:
                    out_path = thumb_dir / path.relative_to(resources_dir).with_suffix(".png")
                    await asyncio.to_thread(_make_thumb, content, thumb_width, out_path)
                    thumbs_generated += 1
                except Exception as exc:
                    print(f"  thumbnail failed: {exc}")
            passed += ok
            failed += not ok

    print()
    parts = []
    if passed:
        parts.append(f"{passed} passed")
    if failed:
        parts.append(f"{failed} failed")
    if thumbs_generated:
        parts.append(f"{thumbs_generated} thumbnail{'s' if thumbs_generated != 1 else ''} → {thumb_dir}")
    print(_header(f"{', '.join(parts)} in {elapsed:.2f}s"))
    return 0 if failed == 0 else 1


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="Upload all resource files to the FastAPI /upload endpoint in parallel.")
    parser.add_argument(
        "--url",
        default=os.environ.get("SERVER_URL", _DEFAULT_BASE_URL),
        metavar="URL",
        help=f"Base URL of the server (default: {_DEFAULT_BASE_URL}, env: SERVER_URL)",
    )
    parser.add_argument(
        "--resources",
        default=Path(os.environ.get("RESOURCES_DIR", str(_DEFAULT_RESOURCES))),
        type=Path,
        metavar="DIR",
        help=f"Directory with files to upload (default: {_DEFAULT_RESOURCES}, env: RESOURCES_DIR)",
    )
    parser.add_argument(
        "--concurrency",
        default=int(os.environ.get("CONCURRENCY", str(_DEFAULT_CONCURRENCY))),
        type=int,
        metavar="N",
        help=f"Max simultaneous uploads (default: {_DEFAULT_CONCURRENCY}, env: CONCURRENCY)",
    )
    parser.add_argument("--limit", default=None, type=int, metavar="N", help="Process only N randomly selected files (default: all files)")
    parser.add_argument(
        "--proxy", default=None, metavar="URL", help="Proxy URL, e.g. http://proxy.example.com:8080 or socks5://localhost:1080"
    )
    parser.add_argument(
        "--no-proxy", default=None, metavar="HOSTS", help="Comma-separated list of hosts that bypass the proxy, e.g. localhost,127.0.0.1"
    )
    parser.add_argument(
        "--thumb-width",
        default=int(os.environ.get("THUMB_WIDTH", str(_DEFAULT_THUMB_WIDTH))),
        type=int,
        metavar="PX",
        help=f"Width in pixels for generated PDF thumbnails (default: {_DEFAULT_THUMB_WIDTH}, env: THUMB_WIDTH)",
    )
    parser.add_argument(
        "--thumb-dir",
        default=Path(os.environ.get("THUMB_DIR", str(_DEFAULT_THUMB_DIR))),
        type=Path,
        metavar="DIR",
        help=f"Output directory for thumbnails (default: {_DEFAULT_THUMB_DIR}, env: THUMB_DIR)",
    )
    parser.add_argument(
        "--no-thumbnails",
        action="store_true",
        default=os.environ.get("NO_THUMBNAILS", "").lower() in ("1", "true", "yes"),
        help="Skip thumbnail generation (env: NO_THUMBNAILS)",
    )
    args = parser.parse_args()
    no_proxy = [h.strip() for h in args.no_proxy.split(",")] if args.no_proxy else None
    proxy = args.proxy or _env_proxy()
    if proxy and no_proxy is None:
        no_proxy = ["localhost", "127.0.0.1"]
    sys.exit(
        asyncio.run(
            _run(
                args.url,
                args.resources,
                args.concurrency,
                args.limit,
                proxy,
                no_proxy,
                args.thumb_width,
                args.thumb_dir,
                not args.no_thumbnails,
            )
        )
    )


if __name__ == "__main__":
    main()
