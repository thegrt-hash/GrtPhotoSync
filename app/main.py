"""FastAPI application entry point."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database.database import init_db
from app.auth.router import router as auth_router
from app.api.settings import router as settings_router
from app.api.sync import router as sync_router
from app.api.browse import router as browse_router
from app.api.status import router as status_router
from app.sync.scheduler import start_scheduler, stop_scheduler

# ── Logging ────────────────────────────────────────────────────────────────────

os.makedirs(settings.LOG_PATH, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(settings.LOG_PATH, "app.log")),
    ],
)
logger = logging.getLogger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(settings.DESTINATION_PATH, exist_ok=True)
    os.makedirs(settings.THUMBNAIL_CACHE_PATH, exist_ok=True)
    os.makedirs(os.path.dirname(settings.GOOGLE_TOKEN_FILE), exist_ok=True)
    await init_db()
    start_scheduler()
    logger.info("Google Photo Downloader started – UI at http://%s:%d", settings.HOST, settings.PORT)
    yield
    # Shutdown
    stop_scheduler()
    logger.info("Google Photo Downloader stopped")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Google Photo Downloader",
    version="1.0.0",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten for production if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(sync_router)
app.include_router(browse_router)
app.include_router(status_router)

# ── Static files / SPA ────────────────────────────────────────────────────────

_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/")
@app.get("/{path:path}")
async def spa_catch_all(path: str = ""):
    """Serve the SPA index for all non-API routes."""
    if path.startswith("api/"):
        from fastapi import HTTPException
        raise HTTPException(404)
    return FileResponse(os.path.join(_static_dir, "index.html"))
