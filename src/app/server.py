from __future__ import annotations

import asyncio
import logging
import random
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI()

_processing_semaphore = asyncio.Semaphore(2)
_MAX_UPLOAD_SIZE_KB = 400


class EchoRequest(BaseModel):
    message: str


@app.get("/health")
async def health() -> dict[str, str]:
    """Simple healthcheck endpoint."""
    return {"status": "ok"}


@app.post("/echo")
async def echo(payload: EchoRequest) -> dict[str, str]:
    """Echo the message back to the caller."""
    return {"message": payload.message}


@app.post("/upload")
async def upload(file_id: Annotated[str, Form()], file: Annotated[UploadFile, File()]) -> dict[str, str | None]:
    logger.info("upload file_id=%s content_type=%s size=%s", file_id, file.content_type, file.size)
    if file.size is not None and file.size > _MAX_UPLOAD_SIZE_KB * 1024:
        raise HTTPException(status_code=422, detail=f"File exceeds {_MAX_UPLOAD_SIZE_KB} KB limit")
    async with _processing_semaphore:
        await asyncio.sleep(random.uniform(1, 4))
    return {"file_id": file_id, "content_type": file.content_type, "size": str(file.size)}
