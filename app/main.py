import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI

from app.config import settings
from app.routes.scans import router as scans_router

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    formatter = logging.Formatter(fmt)

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    if settings.log_file:
        file_handler = RotatingFileHandler(
            settings.log_file, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("ScanPod started")
    yield


app = FastAPI(title="ScanPod", lifespan=lifespan)

app.include_router(scans_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
