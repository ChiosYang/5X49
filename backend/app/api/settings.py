import os
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.metadata.scraper import metadata_scraper
from app.services.settings import (
    get_artwork_language,
    get_auto_organize_root_videos,
    get_base_url,
    get_language,
    get_media_dir,
    get_scrape_require_confirmation,
    get_tmdb_key_status,
    get_watch_library,
    load_settings,
    refresh_models_cache,
    set_artwork_language,
    set_auto_organize_root_videos,
    set_base_url,
    set_current_model,
    set_language,
    set_media_dir,
    set_scrape_require_confirmation,
    set_tmdb_api_key,
    set_watch_library,
)
from app.services.watcher import library_watcher


router = APIRouter()


class TmdbApiKeyUpdate(BaseModel):
    api_key: str = ""


@router.get("/settings")
def get_settings():
    """Get current system settings"""
    settings = load_settings()
    settings.pop("tmdb_api_key", None)
    settings["tmdb"] = get_tmdb_key_status()
    return settings


@router.get("/settings/model")
def get_model_setting():
    """Get current model configuration"""
    settings = load_settings()
    return {
        "current_model": settings.get("model_name"),
        "available_models": settings.get("available_models", []),
    }


@router.put("/settings/model")
def update_model_setting(model_name: str):
    """Update the current model"""
    success = set_current_model(model_name)
    if success:
        return {"message": "Model updated", "model_name": model_name}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")


@router.get("/settings/media-dir")
def get_media_directory():
    return {"media_dir": get_media_dir()}


@router.put("/settings/media-dir")
def update_media_directory(media_dir: str):
    if not media_dir:
        raise HTTPException(status_code=400, detail="Media directory cannot be empty")

    try:
        resolved_media_dir = Path(media_dir).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(status_code=400, detail="Media directory does not exist") from None
    if not resolved_media_dir.is_dir() or not os.access(resolved_media_dir, os.R_OK):
        raise HTTPException(status_code=400, detail="Media directory is not readable")

    normalized_media_dir = str(resolved_media_dir)
    success = set_media_dir(normalized_media_dir)
    if success:
        return {
            "status": "success",
            "media_dir": normalized_media_dir,
            "message": "Media directory updated and is available immediately.",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")


@router.get("/settings/language")
def get_language_setting():
    return {"language": get_language()}


@router.put("/settings/language")
def update_language_setting(language: str):
    if language not in ["zh", "en"]:
        raise HTTPException(status_code=400, detail="Language must be 'zh' or 'en'")
    success = set_language(language)
    if success:
        return {"status": "success", "language": language}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")


@router.get("/settings/artwork-language")
def get_artwork_language_setting():
    return {"artwork_language": get_artwork_language()}


@router.put("/settings/artwork-language")
def update_artwork_language_setting(language: str):
    if language not in {"metadata", "zh", "en", "none"}:
        raise HTTPException(status_code=400, detail="Artwork language must be 'metadata', 'zh', 'en', or 'none'")
    success = set_artwork_language(language)
    if success:
        return {"status": "success", "artwork_language": language}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")


@router.get("/settings/library-watch")
def get_library_watch_setting():
    return {"watch_library": get_watch_library(), "watcher": library_watcher.status()}


@router.put("/settings/library-watch")
def update_library_watch_setting(enabled: bool):
    success = set_watch_library(enabled)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save settings")

    if enabled:
        watcher_status = library_watcher.start()
    else:
        watcher_status = library_watcher.stop()

    return {"status": "success", "watch_library": enabled, "watcher": watcher_status}


@router.get("/settings/auto-organize-root")
def get_auto_organize_root_setting():
    return {"auto_organize_root_videos": get_auto_organize_root_videos()}


@router.put("/settings/auto-organize-root")
def update_auto_organize_root_setting(enabled: bool):
    success = set_auto_organize_root_videos(enabled)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save settings")
    return {"status": "success", "auto_organize_root_videos": enabled}


@router.get("/settings/scrape-confirmation")
def get_scrape_confirmation_setting():
    return {"scrape_require_confirmation": get_scrape_require_confirmation()}


@router.put("/settings/scrape-confirmation")
def update_scrape_confirmation_setting(enabled: bool):
    success = set_scrape_require_confirmation(enabled)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save settings")
    return {"status": "success", "scrape_require_confirmation": enabled}


@router.get("/settings/tmdb")
def get_tmdb_setting():
    """Get TMDB API key configuration status without exposing the key."""
    return get_tmdb_key_status()


@router.put("/settings/tmdb")
def update_tmdb_setting(payload: TmdbApiKeyUpdate):
    """Persist a TMDB API key unless TMDB_API_KEY is managed by the environment."""
    if get_tmdb_key_status()["source"] == "environment":
        raise HTTPException(status_code=409, detail="TMDB_API_KEY is configured by environment")

    success = set_tmdb_api_key(payload.api_key)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save settings")
    return {"status": "success", **get_tmdb_key_status()}


@router.post("/settings/tmdb/test")
def test_tmdb_api_key():
    """Test the currently configured TMDB API key."""
    try:
        metadata_scraper.tmdb.configuration()
        return {"status": "success", "message": "TMDB API key is valid"}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 502
        if status_code == 401:
            return {"status": "error", "message": "Invalid TMDB API key"}
        raise HTTPException(status_code=502, detail=f"TMDB API test failed: {str(exc)}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TMDB API test failed: {str(exc)}")


@router.get("/settings/base-url")
def get_base_url_setting():
    """Get current API base URL"""
    return {"base_url": get_base_url()}


@router.put("/settings/base-url")
def update_base_url_setting(base_url: str):
    """Update the API base URL"""
    success = set_base_url(base_url)
    if success:
        return {"message": "Base URL updated", "base_url": base_url}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")


@router.post("/settings/models/refresh")
def refresh_models():
    """Force refresh the available models from OpenRouter API"""
    models = refresh_models_cache()
    if models:
        return {
            "message": "Models refreshed successfully",
            "count": len(models),
            "models": models,
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to refresh models")


@router.get("/settings/test-api-key")
def test_api_key():
    """Test if OpenRouter API key is working"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {
            "status": "error",
            "message": "OPENROUTER_API_KEY not configured",
        }

    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            model_count = len(data.get("data", []))
            return {
                "status": "success",
                "message": f"API key is valid. {model_count} models available.",
                "model_count": model_count,
            }
        elif response.status_code == 401:
            return {
                "status": "error",
                "message": "Invalid API key. Please check your OPENROUTER_API_KEY.",
            }
        else:
            return {
                "status": "error",
                "message": f"API returned status code {response.status_code}",
            }
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "message": "Request timeout. Please check your network connection.",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error testing API: {str(e)}",
        }
