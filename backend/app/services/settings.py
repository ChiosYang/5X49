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
        "available_models": get_available_models()
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
