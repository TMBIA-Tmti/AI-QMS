"""Per-user settings persistence for AI-QMS.

Saves and loads user preferences (LLM provider, model, API key, user name)
to data/user_settings/<user_hash>.json so settings survive browser
disconnection/restart and multiple users don't overwrite each other.

TTL (Time-To-Live):
  Settings auto-expire after _SETTINGS_TTL_SECONDS of inactivity.
  Each save/interaction refreshes updated_at; if the gap between
  updated_at and current time exceeds TTL, the settings file is
  deleted and load returns {}. This prevents stale credentials
  from persisting after a user disconnects.

Architecture:
  data/user_settings/
    _last_user.json          — stores last active user_id (for auto-load)
    <user_hash>.json         — per-user settings file

Future Auth integration:
  When Chainlit Auth is enabled, pass user_id=cl.user_session.get("user").id
  to save/load functions instead of relying on name-based hashing.
"""

import hashlib
import json
import base64
import os
import time
import tempfile
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from cryptography.fernet import Fernet as _Fernet

logger = logging.getLogger(__name__)

# Encryption key for user settings (API keys at rest).
#
# The key is NOT derived from machine-identifiable data (e.g. MAC address)
# since that is not a secret and provides no real confidentiality. Instead:
#   1. USER_SETTINGS_ENCRYPTION_KEY env var takes precedence, if set — lets
#      production deployments inject a key via secrets management.
#   2. Otherwise a random key is generated on first run and persisted
#      OUTSIDE the settings files it protects, at data/.secrets/.
_KEY_DIR = Path(__file__).parent.parent.parent / "data" / ".secrets"
_KEY_PATH = _KEY_DIR / "user_settings_key"
_ENV_KEY_VAR = "USER_SETTINGS_ENCRYPTION_KEY"

_cached_key: Optional[bytes] = None


def _load_or_create_key() -> bytes:
    """Resolve the Fernet key for user settings encryption (cached after first call)."""
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    env_key = os.environ.get(_ENV_KEY_VAR, "").strip()
    if env_key:
        try:
            candidate = env_key.encode("utf-8")
            _Fernet(candidate)  # validate format
            _cached_key = candidate
            return _cached_key
        except Exception:
            logger.warning(
                "%s is set but is not a valid Fernet key; ignoring it and "
                "falling back to the file-based key.",
                _ENV_KEY_VAR,
            )

    try:
        if _KEY_PATH.exists():
            existing = _KEY_PATH.read_bytes().strip()
            if existing:
                _Fernet(existing)  # validate format
                _cached_key = existing
                return _cached_key
    except Exception:
        logger.warning(
            "Failed to read existing encryption key at %s; a new key will "
            "be generated (previously saved API keys will no longer decrypt).",
            _KEY_PATH,
        )

    # No valid key found from env or disk — generate and persist a new one.
    new_key = _Fernet.generate_key()
    try:
        _KEY_DIR.mkdir(parents=True, exist_ok=True)
        _KEY_PATH.write_bytes(new_key)
        try:
            os.chmod(_KEY_PATH, 0o600)  # best-effort; Windows ACLs differ
        except OSError:
            pass
    except Exception as exc:
        logger.warning(
            "Failed to persist encryption key to %s: %s. Key will only "
            "live for this process's lifetime.",
            _KEY_PATH,
            exc,
        )

    _cached_key = new_key
    return _cached_key


def _get_fernet() -> _Fernet:
    """Get a Fernet cipher using the env-provided or persisted encryption key."""
    return _Fernet(_load_or_create_key())


def _encrypt_key(api_key: str) -> str:
    if not api_key:
        return ""
    return _get_fernet().encrypt(api_key.encode()).decode()


def _decrypt_key(encrypted: str) -> str:
    if not encrypted:
        return ""
    try:
        return _get_fernet().decrypt(encrypted.encode()).decode()
    except Exception:
        logger.warning(
            "Failed to decrypt stored API key — it was likely encrypted "
            "with a previous encryption key (e.g. before a key rotation or "
            "migration). Treating as no saved API key; user will need to "
            "re-enter it."
        )
        return ""


_SETTINGS_DIR = Path(__file__).parent.parent.parent / "data" / "user_settings"
_LAST_USER_PATH = _SETTINGS_DIR / "_last_user.json"
# Language preference stored without TTL — language is not a credential.
_LANGUAGE_PATH = Path(__file__).parent.parent.parent / "data" / "user_language.json"

# Time-To-Live for saved settings (seconds).
# After this many seconds of inactivity (no save/update), settings are
# considered expired and will be auto-deleted on next load attempt.
# 90 seconds = middle of user-requested 60-100s range.
_SETTINGS_TTL_SECONDS = 90

# Default language when no user preference is recorded.
from src.chainlit_app.lang_config import DEFAULT_LANG

# Legacy single-file path (for migration)
_LEGACY_PATH = Path(__file__).parent.parent.parent / "data" / "user_settings.json"


def _user_id_from_name(user_name: str) -> str:
    """Generate a stable user_id from user name. Uses SHA-256 prefix for uniqueness."""
    if not user_name:
        return "anonymous"
    return hashlib.sha256(user_name.strip().lower().encode("utf-8")).hexdigest()[:12]


def _settings_path(user_id: str) -> Path:
    """Get the settings file path for a given user_id."""
    return _SETTINGS_DIR / f"{user_id}.json"


def _migrate_legacy() -> dict:
    """Migrate from legacy single-file user_settings.json to per-user format.

    Returns the migrated settings dict if found, empty dict otherwise.
    """
    if not _LEGACY_PATH.exists():
        return {}
    try:
        with open(_LEGACY_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)
        if settings.get("api_key_b64"):
            settings["api_key"] = base64.b64decode(settings["api_key_b64"]).decode()
        else:
            settings["api_key"] = ""

        # Save in new per-user format
        user_name = settings.get("user_name", "")
        user_id = _user_id_from_name(user_name)
        save_user_settings(
            user_id=user_id,
            user_name=user_name,
            provider_id=settings.get("provider_id", ""),
            provider_name=settings.get("provider_name", ""),
            model_name=settings.get("model_name", ""),
            api_key=settings.get("api_key", ""),
            language=settings.get("language", DEFAULT_LANG),
        )

        # Remove legacy file after successful migration
        _LEGACY_PATH.unlink(missing_ok=True)
        return settings
    except Exception:
        return {}


def _atomic_write_json(path: Path, data: dict, retries: int = 3) -> None:
    from src.utils.safe_io import atomic_write_json

    atomic_write_json(path, data, retries=retries)


def save_user_settings(
    user_name: str = "",
    provider_id: str = "",
    provider_name: str = "",
    model_name: str = "",
    api_key: str = "",
    language: str = DEFAULT_LANG,
    user_id: str = "",
):
    """Save user settings to per-user JSON file.

    Args:
        user_id: Explicit user identifier (for future Auth integration).
                 If empty, auto-generated from user_name hash.
    """
    if not user_id:
        user_id = _user_id_from_name(user_name)

    settings = {
        "user_id": user_id,
        "user_name": user_name,
        "provider_id": provider_id,
        "provider_name": provider_name,
        "model_name": model_name,
        "api_key_encrypted": _encrypt_key(api_key),
        "language": language,
        "updated_at": datetime.now().isoformat(),
    }
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(_settings_path(user_id), settings)

    # Persist language without TTL so it survives credential expiry.
    try:
        _LANGUAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(_LANGUAGE_PATH, {"language": language})
    except Exception as _lang_err:
        import logging as _logging
        _logging.getLogger(__name__).warning("Failed to save language preference: %s", _lang_err)

    # Update last active user pointer
    _atomic_write_json(
        _LAST_USER_PATH, {"last_user_id": user_id, "user_name": user_name}
    )


def load_user_settings(user_id: str = "") -> dict:
    """Load user settings from per-user JSON file.

    Args:
        user_id: Explicit user identifier. If empty, loads last active user.

    Returns empty dict if not found or if settings have expired (TTL exceeded).
    """
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

    # If no user_id specified, try last active user
    if not user_id:
        # Check for legacy file migration first
        if _LEGACY_PATH.exists():
            migrated = _migrate_legacy()
            if migrated:
                return migrated

        if not _LAST_USER_PATH.exists():
            return {}
        try:
            with open(_LAST_USER_PATH, "r", encoding="utf-8") as f:
                last = json.load(f)
            user_id = last.get("last_user_id", "")
        except Exception:
            return {}

    if not user_id:
        return {}

    path = _settings_path(user_id)
    if not path.exists():
        try:
            if _LANGUAGE_PATH.exists():
                with open(_LANGUAGE_PATH, "r", encoding="utf-8") as _lf:
                    _lang_data = json.load(_lf)
                _lang = _lang_data.get("language", "")
                if _lang:
                    return {"language": _lang}
        except Exception:
            pass
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            settings = json.load(f)

        # --- TTL check ---
        updated_str = settings.get("updated_at", "")
        if updated_str:
            try:
                updated_at = datetime.fromisoformat(updated_str)
                if datetime.now() - updated_at > timedelta(
                    seconds=_SETTINGS_TTL_SECONDS
                ):
                    # Settings expired — delete file and last-user pointer
                    path.unlink(missing_ok=True)
                    _LAST_USER_PATH.unlink(missing_ok=True)
                    # Language is not a credential — recover it from TTL-free store
                    try:
                        if _LANGUAGE_PATH.exists():
                            with open(_LANGUAGE_PATH, "r", encoding="utf-8") as _lf:
                                _lang_data = json.load(_lf)
                            _lang = _lang_data.get("language", "")
                            if _lang:
                                return {"language": _lang}
                    except Exception:
                        pass
                    return {}
            except (ValueError, TypeError):
                pass  # Malformed timestamp — proceed without TTL enforcement

        # Decode API key (supports both new encrypted and legacy base64 formats)
        settings["api_key"] = _decrypt_key(
            settings.get("api_key_encrypted", settings.get("api_key_b64", ""))
        )
        return settings
    except Exception:
        return {}


def has_saved_settings(user_id: str = "") -> bool:
    """Check if user settings exist with a saved provider + API key."""
    settings = load_user_settings(user_id)
    return bool(settings.get("provider_id") and (settings.get("api_key_encrypted") or settings.get("api_key_b64")))
