"""
Settings management for user preferences.
"""
import os
import json
import requests
from datetime import datetime, timedelta

SETTINGS_FILE = "data/settings.json"
MODELS_CACHE_FILE = "data/models_cache.json"
CACHE_DURATION = timedelta(hours=24)  # Cache models for 24 hours

def fetch_openrouter_models():
    """Fetch available models from OpenRouter API"""
    try:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            print("Warning: OPENROUTER_API_KEY not found, using cached models")
            return None
        
        # Get base URL from settings (with fallback)
        base_url = os.getenv("API_BASE_URL", "https://openrouter.ai/api/v1")
        
        response = requests.get(
            f"{base_url}/models",
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            # Extract model IDs from the response
            models = [model["id"] for model in data.get("data", [])]
            
            # Cache the results
            cache_data = {
                "models": models,
                "timestamp": datetime.now().isoformat(),
            }
            os.makedirs(os.path.dirname(MODELS_CACHE_FILE), exist_ok=True)
            with open(MODELS_CACHE_FILE, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            return models
        else:
            print(f"Failed to fetch models from OpenRouter: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Error fetching models from OpenRouter: {e}")
        return None

def get_cached_models():
    """Get models from cache if available and not expired"""
    try:
        if os.path.exists(MODELS_CACHE_FILE):
            with open(MODELS_CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
                
            # Check if cache is still valid
            cache_time = datetime.fromisoformat(cache_data["timestamp"])
            if datetime.now() - cache_time < CACHE_DURATION:
                return cache_data.get("models", [])
    except Exception as e:
        print(f"Error reading models cache: {e}")
    
    return None

def get_available_models(force_refresh=False):
    """Get available models, using cache if available"""
    # Try cache first unless force refresh
    if not force_refresh:
        cached = get_cached_models()
        if cached:
            return cached
    
    # Fetch fresh data
    models = fetch_openrouter_models()
    
    # If fetch failed, try cache even if expired
    if models is None:
        cached = get_cached_models()
        if cached:
            print("Using expired cache due to API fetch failure")
            return cached
        
        # Last resort: return minimal default list
        print("Warning: Using fallback model list")
        return [
            "openrouter/pony-alpha",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4-turbo",
            "google/gemini-pro-1.5",
        ]
    
    return models

def get_default_settings():
    """Get default system settings"""
    return {
        "model_name": os.getenv("MODEL_NAME", "openrouter/pony-alpha"),
        "base_url": os.getenv("API_BASE_URL", "https://openrouter.ai/api/v1"),
        "available_models": get_available_models(),
        "watch_library": os.getenv("WATCH_LIBRARY", "false").lower() == "true",
        "watch_mode": os.getenv("WATCH_MODE", "events"),
        "watch_debounce_seconds": int(os.getenv("WATCH_DEBOUNCE_SECONDS", "5")),
        "watch_interval_seconds": int(os.getenv("WATCH_INTERVAL_SECONDS", "5")),
        "media_file_stable_seconds": int(os.getenv("MEDIA_FILE_STABLE_SECONDS", "15")),
        "auto_organize_root_videos": os.getenv("AUTO_ORGANIZE_ROOT_VIDEOS", "false").lower() == "true",
        "organize_min_confidence": float(os.getenv("ORGANIZE_MIN_CONFIDENCE", "85")),
        "organize_rename_style": os.getenv("ORGANIZE_RENAME_STYLE", "preserve_stem"),
        "scrape_require_confirmation": os.getenv("SCRAPE_REQUIRE_CONFIRMATION", "false").lower() == "true",
        "missing_policy": os.getenv("MISSING_POLICY", "mark_missing"),
    }

def load_settings():
    """Load settings from file"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                saved = json.load(f)
                defaults = get_default_settings()
                # Merge saved settings with defaults, refresh models list
                return {
                    **defaults,
                    **saved,
                    "available_models": get_available_models()  # Always use latest models
                }
    except Exception as e:
        print(f"Error loading settings: {e}")
    
    return get_default_settings()

def save_settings(settings: dict):
    """Save settings to file"""
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        # Don't save the models list, it will be fetched dynamically
        settings_to_save = {k: v for k, v in settings.items() if k != "available_models"}
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

def _get_saved_tmdb_api_key():
    try:
        if not os.path.exists(SETTINGS_FILE):
            return None
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
        saved_key = settings.get("tmdb_api_key")
        return saved_key.strip() if isinstance(saved_key, str) and saved_key.strip() else None
    except Exception as e:
        print(f"Error reading TMDB API key setting: {e}")
        return None

def get_tmdb_api_key():
    """Get the TMDB API key from env first, then saved settings."""
    env_key = os.getenv("TMDB_API_KEY")
    if env_key:
        return env_key

    return _get_saved_tmdb_api_key()

def get_tmdb_key_status():
    """Return TMDB key status without exposing the key value."""
    if os.getenv("TMDB_API_KEY"):
        return {"configured": True, "source": "environment"}

    if _get_saved_tmdb_api_key():
        return {"configured": True, "source": "settings"}

    return {"configured": False, "source": None}

def set_tmdb_api_key(api_key: str):
    """Persist a TMDB API key in settings.json when env does not own it."""
    if os.getenv("TMDB_API_KEY"):
        return False

    settings = load_settings()
    key = api_key.strip()
    if key:
        settings["tmdb_api_key"] = key
    else:
        settings.pop("tmdb_api_key", None)
    return save_settings(settings)

def get_current_model():
    """Get currently selected model"""
    settings = load_settings()
    return settings.get("model_name", os.getenv("MODEL_NAME", "openrouter/pony-alpha"))

def set_current_model(model_name: str):
    """Set current model"""
    settings = load_settings()
    settings["model_name"] = model_name
    return save_settings(settings)

def get_base_url():
    """Get current API base URL"""
    settings = load_settings()
    return settings.get("base_url", os.getenv("API_BASE_URL", "https://openrouter.ai/api/v1"))

def set_base_url(base_url: str):
    """Set API base URL"""
    settings = load_settings()
    settings["base_url"] = base_url
    return save_settings(settings)

def refresh_models_cache():
    """Force refresh the models cache"""
    return get_available_models(force_refresh=True)

def get_media_dir():
    """Get current media directory"""
    settings = load_settings()
    # Default to environment variable or hardcoded default
    default_media_dir = os.getenv("MEDIA_DIR", "/media")
    return settings.get("media_dir", default_media_dir)

def set_media_dir(media_dir: str):
    """Set media directory"""
    # Simply save the path, validation happens at usage time
    settings = load_settings()
    settings["media_dir"] = media_dir
    return save_settings(settings)

def get_language():
    """Get language preference, 'zh' or 'en'"""
    settings = load_settings()
    return settings.get("language", "zh")

def set_language(language: str):
    """Set language preference"""
    if language not in ["zh", "en"]:
        language = "zh"
    settings = load_settings()
    settings["language"] = language
    return save_settings(settings)

def get_watch_library():
    """Return whether automatic library watching is enabled."""
    settings = load_settings()
    return bool(settings.get("watch_library", False))

def set_watch_library(enabled: bool):
    settings = load_settings()
    settings["watch_library"] = bool(enabled)
    return save_settings(settings)

def get_watch_debounce_seconds():
    settings = load_settings()
    return int(settings.get("watch_debounce_seconds", 5))

def get_watch_interval_seconds():
    settings = load_settings()
    return int(settings.get("watch_interval_seconds", 5))

def get_watch_mode():
    settings = load_settings()
    mode = str(settings.get("watch_mode", "events")).lower()
    return mode if mode in {"events", "polling"} else "events"

def get_media_file_stable_seconds():
    settings = load_settings()
    return int(settings.get("media_file_stable_seconds", 15))

def get_auto_organize_root_videos():
    settings = load_settings()
    return bool(settings.get("auto_organize_root_videos", False))

def set_auto_organize_root_videos(enabled: bool):
    settings = load_settings()
    settings["auto_organize_root_videos"] = bool(enabled)
    return save_settings(settings)

def get_scrape_require_confirmation():
    settings = load_settings()
    return bool(settings.get("scrape_require_confirmation", False))

def set_scrape_require_confirmation(enabled: bool):
    settings = load_settings()
    settings["scrape_require_confirmation"] = bool(enabled)
    return save_settings(settings)

def get_organize_min_confidence():
    settings = load_settings()
    return float(settings.get("organize_min_confidence", 85))

def get_organize_rename_style():
    settings = load_settings()
    style = str(settings.get("organize_rename_style", "preserve_stem"))
    return style if style in {"preserve_stem", "title_year"} else "preserve_stem"

def get_missing_policy():
    settings = load_settings()
    return settings.get("missing_policy", "mark_missing")
