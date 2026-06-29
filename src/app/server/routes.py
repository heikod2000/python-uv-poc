from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()
_processing_semaphore = asyncio.Semaphore(int(os.environ.get("MAX_CONCURRENT_UPLOADS", "2")))
_MAX_UPLOAD_SIZE_KB = int(os.environ.get("MAX_UPLOAD_SIZE_KB", "2000"))


class EchoRequest(BaseModel):
    message: str


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/echo")
async def echo(payload: EchoRequest) -> dict[str, str]:
    return {"message": payload.message}


@router.post("/upload")
async def upload(file_id: Annotated[str, Form()], file: Annotated[UploadFile, File()]) -> Response:
    logger.info("upload file_id=%s content_type=%s size=%s", file_id, file.content_type, file.size)
    if file.size is not None and file.size > _MAX_UPLOAD_SIZE_KB * 1024:
        raise HTTPException(status_code=422, detail=f"File exceeds {_MAX_UPLOAD_SIZE_KB} KB limit")
    content = await file.read()
    async with _processing_semaphore:
        await asyncio.sleep(random.uniform(1, 4))
    return Response(content=content, media_type=file.content_type or "application/octet-stream")
