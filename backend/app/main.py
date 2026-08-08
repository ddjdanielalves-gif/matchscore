from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import matches

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("matchscore")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("MatchScore ready. Mock mode=%s api_key=%s",
                settings.mock_mode, bool(settings.api_key))
    yield


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(matches.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


# Serve the built frontend (frontend/dist) when available so the whole app
# runs from a single service. API routes are registered first and take
# precedence over this catch-all mount.
_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
    logger.info("Serving frontend from %s", _frontend_dist)
else:
    logger.warning("Frontend build not found at %s", _frontend_dist)
