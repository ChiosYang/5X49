import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.database import create_db_and_tables, engine
from app.jobs import job_runtime
from app.services.artwork_cache import ARTWORK_CACHE_DIR
from app.services.settings import get_watch_library
from app.services.projections import ProjectionUnavailable
from app.services.watcher import library_watcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        create_db_and_tables()
        job_runtime.start()
        if get_watch_library():
            library_watcher.start()
        yield
    finally:
        try:
            library_watcher.stop()
        finally:
            try:
                job_runtime.stop()
            finally:
                engine.dispose()


app = FastAPI(lifespan=lifespan)


@app.exception_handler(ProjectionUnavailable)
async def projection_unavailable_handler(_request: Request, exc: ProjectionUnavailable):
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "code": exc.code,
                "message": str(exc),
            }
        },
    )

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5549,http://127.0.0.1:5549",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)

ARTWORK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/artwork-cache", StaticFiles(directory=ARTWORK_CACHE_DIR), name="artwork-cache")

app.include_router(api_router)
