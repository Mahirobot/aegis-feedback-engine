import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel

from app.config import settings
from app.database import enable_wal_mode, engine
from app.logging import setup_logging

# Import Routers
from app.routers import admin, feedback

# IMPORT WORKERS HERE, NOT IN MODELS
from app.workers import run_periodic_reconciliation

logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup
    enable_wal_mode()
    SQLModel.metadata.create_all(engine)
    logger.info("Scheduler starting...")
    # This calls the worker function properly
    scheduler = asyncio.create_task(run_periodic_reconciliation())

    yield

    # 2. Shutdown
    scheduler.cancel()
    try:
        await scheduler
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.APP_TITLE, lifespan=lifespan, description="Refactored Aegis Engine"
)

app.include_router(feedback.router)
app.include_router(admin.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def root():
    return FileResponse("app/static/index.html")
