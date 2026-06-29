from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI

from app.server.routes import router

load_dotenv()


app = FastAPI()
app.include_router(router)
