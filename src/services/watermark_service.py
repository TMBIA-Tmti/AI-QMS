"""
AI-QMS - Watermark Configuration Management Service
====================================================

Manages watermark settings (浮水印設定) including:
- Image storage (user-uploaded watermark image)
- Appearance settings (angle, opacity, scale, position, repeat, color tint)
- Auto-apply rules per hierarchy level
- Persistent storage in JSON (data/watermark_config.json)

The watermark configuration controls how watermark images are applied to
uploaded documents. Settings are stored globally and shared across all
upload sessions.
"""

import datetime
import json
import logging
import os
import shutil
from pathlib import Path

from src.utils.safe_io import atomic_write_json

logger = logging.getLogger(__name__)

# Valid position values
VALID_POSITIONS = {"center", "top-left", "top-right", "bottom-left", "bottom-right"}


class WatermarkService:
    """浮水印配置管理服務。"""

    def __init__(self, config_path: str = "./data/watermark_config.json"):
        self._config_path = config_path
        self._image_dir = os.path.join(os.path.dirname(config_path), "watermark")
        self._config: dict = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        """Whether the user has completed first-time watermark setup."""
        return self._config.get("configured", False)

    def is_enabled(self) -> bool:
        """Whether watermark is globally enabled."""
        return self._config.get("enabled", False)

    def get_config(self) -> dict:
        """Return a copy of the full config."""
        return json.loads(json.dumps(self._config))

    def save_image(self, source_path: str, original_name: str) -> str:
        """
        Copy watermark image to data/watermark/ directory.

        Args:
            source_path: Path to the uploaded image file.
            original_name: Original filename from the user.

        Returns:
            The destination path where the image was saved.
        """
        os.makedirs(self._image_dir, exist_ok=True)

        # Determine extension from original name
        ext = Path(original_name).suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg"):
            ext = ".png"

        dest_filename = f"user_watermark{ext}"
        dest_path = os.path.join(self._image_dir, dest_filename)

        shutil.copy2(source_path, dest_path)

        self._config["image_path"] = dest_path
        self._config["image_original_name"] = original_name
        self._save()

        logger.info("Watermark image saved: %s -> %s", original_name, dest_path)
        return dest_path

    def update_settings(self, **kwargs) -> dict:
        """
        Update watermark appearance settings.

        Supported kwargs: angle, opacity, scale, repeat, position, color_tint.
        Validates ranges and returns the updated settings dict.

        Raises:
            ValueError: If any parameter is out of valid range.
        """
        settings = self._config.setdefault("settings", self._default_settings())

        if "angle" in kwargs:
            angle = kwargs["angle"]
            if not isinstance(angle, (int, float)) or not (-180 <= angle <= 180):
                raise ValueError(f"angle must be between -180 and 180, got {angle}")
            settings["angle"] = int(angle)

        if "opacity" in kwargs:
            opacity = kwargs["opacity"]
            if not isinstance(opacity, (int, float)) or not (0.0 <= opacity <= 1.0):
                raise ValueError(f"opacity must be between 0.0 and 1.0, got {opacity}")
            settings["opacity"] = float(opacity)

        if "scale" in kwargs:
            scale = kwargs["scale"]
            if not isinstance(scale, (int, float)) or not (0.1 <= scale <= 3.0):
                raise ValueError(f"scale must be between 0.1 and 3.0, got {scale}")
            settings["scale"] = float(scale)

        if "repeat" in kwargs:
            settings["repeat"] = bool(kwargs["repeat"])

        if "position" in kwargs:
            position = kwargs["position"]
            if position not in VALID_POSITIONS:
                raise ValueError(
                    f"position must be one of {VALID_POSITIONS}, got {position!r}"
                )
            settings["position"] = position

        if "color_tint" in kwargs:
            color_tint = kwargs["color_tint"]
            if color_tint is not None and not isinstance(color_tint, str):
                raise ValueError(
                    f"color_tint must be a hex string or None, got {type(color_tint)}"
                )
            settings["color_tint"] = color_tint

        self._save()
        return dict(settings)

    def update_auto_apply_rules(self, rules: dict) -> dict:
        """
        Update auto-apply rules for hierarchy levels.

        Args:
            rules: Dict mapping hierarchy level IDs to bool.
                   Keys: "L1", "L2", "L3", "L4", "REG", "CUSTOM-*"

        Returns:
            The updated rules dict.
        """
        current_rules = self._config.setdefault(
            "auto_apply_rules", self._default_auto_apply_rules()
        )
        for key, value in rules.items():
            current_rules[key] = bool(value)

        self._save()
        return dict(current_rules)

    def should_apply_watermark(self, hierarchy_id: str) -> bool:
        """
        Check if watermark should be applied for a given hierarchy ID.

        Args:
            hierarchy_id: The hierarchy level ID (e.g., "L1", "L2", "REG", "CUSTOM-3").

        Returns:
            True if watermark should be applied, False otherwise.
        """
        if not self.is_enabled() or not self.is_configured():
            return False

        if not self._config.get("image_path"):
            return False

        rules = self._config.get("auto_apply_rules", {})

        # Direct match first
        if hierarchy_id in rules:
            return bool(rules[hierarchy_id])

        # Custom hierarchy wildcard match
        if hierarchy_id.startswith("CUSTOM-"):
            return bool(rules.get("CUSTOM-*", False))

        # Default: don't apply
        return False

    def set_enabled(self, enabled: bool) -> None:
        """Toggle global watermark on/off."""
        self._config["enabled"] = bool(enabled)
        self._save()

    def reset_config(self) -> None:
        """Reset to default config. Keeps image file if it exists."""
        image_path = self._config.get("image_path")
        image_name = self._config.get("image_original_name")

        self._config = self._default_config()

        # Preserve existing image reference if file still exists
        if image_path and os.path.isfile(image_path):
            self._config["image_path"] = image_path
            self._config["image_original_name"] = image_name

        self._save()
        logger.info("Watermark config reset to defaults.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        """Load config from JSON file, creating default if not exists."""
        if os.path.isfile(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.debug("Loaded watermark config from %s", self._config_path)
                return data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(
                    "Failed to load watermark config from %s: %s. Using defaults.",
                    self._config_path,
                    e,
                )
                return self._default_config()
        else:
            logger.info(
                "Watermark config not found at %s. Creating default.", self._config_path
            )
            config = self._default_config()
            # Write default config to disk
            self._config = config
            self._save()
            return config

    def _save(self) -> None:
        """Save current config to JSON file."""
        self._config["updated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        try:
            atomic_write_json(Path(self._config_path), self._config, indent=4)
            logger.debug("Saved watermark config to %s", self._config_path)
        except OSError as e:
            logger.error("Failed to save watermark config: %s", e)

    @staticmethod
    def _default_settings() -> dict:
        """Return default appearance settings."""
        return {
            "angle": -45,
            "opacity": 0.15,
            "scale": 1.0,
            "repeat": False,
            "position": "center",
            "color_tint": None,
        }

    @staticmethod
    def _default_auto_apply_rules() -> dict:
        """Return default auto-apply rules."""
        return {
            "L1": True,
            "L2": True,
            "L3": True,
            "L4": False,
            "REG": True,
            "CUSTOM-*": False,
        }

    @staticmethod
    def _default_config() -> dict:
        """Return the complete default config structure."""
        return {
            "enabled": True,
            "image_path": None,
            "image_original_name": None,
            "settings": WatermarkService._default_settings(),
            "auto_apply_rules": WatermarkService._default_auto_apply_rules(),
            "configured": False,
            "updated_at": None,
        }
