from fastapi import APIRouter

from app.api import core, events, explore, library, media, metadata, settings, system, workflows


api_router = APIRouter()
api_router.include_router(core.router)
api_router.include_router(media.router)
api_router.include_router(workflows.router)
api_router.include_router(metadata.router)
api_router.include_router(events.router)
api_router.include_router(explore.router)
api_router.include_router(library.router)
api_router.include_router(settings.router)
api_router.include_router(system.router)
