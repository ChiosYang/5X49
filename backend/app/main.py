import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.common import MEDIA_DIR
from app.api.router import api_router
from app.database import create_db_and_tables
from app.jobs import job_runtime
from app.services.artwork_cache import ARTWORK_CACHE_DIR
from app.services.settings import get_watch_library
from app.services.watcher import library_watcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    job_runtime.start()
    if get_watch_library():
        library_watcher.start()
    yield
    job_runtime.stop()
    library_watcher.stop()


app = FastAPI(lifespan=lifespan)

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5549,http://127.0.0.1:5549",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

if os.path.exists(MEDIA_DIR):
    app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
else:
    print(f"⚠️ Warning: MEDIA_DIR does not exist: {MEDIA_DIR}")

ARTWORK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/artwork-cache", StaticFiles(directory=ARTWORK_CACHE_DIR), name="artwork-cache")

app.include_router(api_router)
