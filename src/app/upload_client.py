"""CLI tool: upload all files from a resources directory to the FastAPI /upload endpoint in parallel."""

from __future__ import annotations

import argparse
import asyncio
import mimetypes
import random
import sys
import time
from pathlib import Path

import httpx2 as httpx

_DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_DEFAULT_RESOURCES = Path(__file__).parent.parent.parent / "resources"
_DEFAULT_CONCURRENCY = 20
_WIDTH = 72


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


async def _run(base_url: str, resources_dir: Path, concurrency: int, limit: int | None = None) -> int:
    all_files = sorted(f for f in resources_dir.rglob("*") if f.is_file())
    available = len(all_files)
    files = random.sample(all_files, min(limit, available)) if limit is not None else all_files
    total = len(files)
    col = max((len(_rel(f)) for f in files), default=40) + 2

    print(_header("upload session starts"))
    print(f"base url:    {base_url}")
    print(f"concurrency: {concurrency}")
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

    async with httpx.AsyncClient(base_url=base_url) as client:
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
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.url, args.resources, args.concurrency, args.limit)))


if __name__ == "__main__":
    main()
