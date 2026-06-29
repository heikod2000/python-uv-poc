from __future__ import annotations

from fastapi import FastAPI

from app.server.routes import router

app = FastAPI()
app.include_router(router)
