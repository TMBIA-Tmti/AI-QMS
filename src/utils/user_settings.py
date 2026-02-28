"""User settings persistence for AI-QMS.

Saves and loads user preferences (LLM provider, model, API key, user name)
to data/user_settings.json so settings survive browser disconnection/restart.
"""

import json
import base64
from pathlib import Path
from datetime import datetime

_SETTINGS_PATH = Path(__file__).parent.parent.parent / "data" / "user_settings.json"


def save_user_settings(
    user_name: str = "",
    provider_id: str = "",
    provider_name: str = "",
    model_name: str = "",
    api_key: str = "",
    language: str = "zh-TW",
):
    """Save user settings to JSON file. API key is base64 encoded (obfuscation only)."""
    settings = {
        "user_name": user_name,
        "provider_id": provider_id,
        "provider_name": provider_name,
        "model_name": model_name,
        "api_key_b64": base64.b64encode(api_key.encode()).decode() if api_key else "",
        "language": language,
        "updated_at": datetime.now().isoformat(),
    }
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def load_user_settings() -> dict:
    """Load user settings from JSON file. Returns empty dict if not found."""
    if not _SETTINGS_PATH.exists():
        return {}
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)
        # Decode API key
        if settings.get("api_key_b64"):
            settings["api_key"] = base64.b64decode(settings["api_key_b64"]).decode()
        else:
            settings["api_key"] = ""
        return settings
    except Exception:
        return {}


def has_saved_settings() -> bool:
    """Check if user settings file exists and has a saved provider + API key."""
    if not _SETTINGS_PATH.exists():
        return False
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)
        return bool(settings.get("provider_id") and settings.get("api_key_b64"))
    except Exception:
        return False
