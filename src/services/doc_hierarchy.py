"""
AI-QMS - Document Hierarchy Configuration System
=================================================

Manages document hierarchy levels (文件階層) with:
- Default hierarchy: 1階-品質手冊, 2階-程序書, 3階-作業指導書, 4階-表單, 外來法規文件
- User-defined custom hierarchy levels
- Persistent storage in JSON
- Backward compatibility with legacy doc_type (SOP/WI/FORM/DHF/OTHER)
- System scope setting (品質系統範圍): configurable max hierarchy level (e.g., 1-3 or 1-4)

Each hierarchy level has:
- id: unique identifier (e.g., "L1", "L2", "L3", "L4", "REG", "CUSTOM-1")
- order: display sort order (1, 2, 3, ...)
- labels: multi-language display labels {"zh-TW": "...", "en-US": "...", "ja-JP": "..."}
- storage_type: the folder name used in markdown_storage/documents/ (SOP, WI, FORM, DHF, OTHER)
- is_default: True for built-in levels, False for user-created
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


# ============================================================
# Default Hierarchy Definition
# ============================================================

DEFAULT_HIERARCHY = [
    {
        "id": "L1",
        "order": 1,
        "labels": {
            "zh-TW": "1階-品質手冊",
            "zh-CN": "1阶-质量手册",
            "en-US": "L1-Quality Manual",
            "ja-JP": "1階-品質マニュアル",
        },
        "storage_type": "SOP",
        "is_default": True,
    },
    {
        "id": "L2",
        "order": 2,
        "labels": {
            "zh-TW": "2階-程序書",
            "zh-CN": "2阶-程序文件",
            "en-US": "L2-Procedure",
            "ja-JP": "2階-手順書",
        },
        "storage_type": "SOP",
        "is_default": True,
    },
    {
        "id": "L3",
        "order": 3,
        "labels": {
            "zh-TW": "3階-作業指導書",
            "zh-CN": "3阶-作业指导书",
            "en-US": "L3-Work Instruction",
            "ja-JP": "3階-作業指導書",
        },
        "storage_type": "WI",
        "is_default": True,
    },
    {
        "id": "L4",
        "order": 4,
        "labels": {
            "zh-TW": "4階-表單",
            "zh-CN": "4阶-表单",
            "en-US": "L4-Form",
            "ja-JP": "4階-フォーム",
        },
        "storage_type": "FORM",
        "is_default": True,
    },
    {
        "id": "REG",
        "order": 99,
        "labels": {
            "zh-TW": "外來法規文件",
            "zh-CN": "外来法规文件",
            "en-US": "Regulatory Document",
            "ja-JP": "外部規制文書",
        },
        "storage_type": "OTHER",
        "is_default": True,
    },
]

# Legacy doc_type → hierarchy ID mapping (for backward compatibility)
LEGACY_DOCTYPE_MAP = {
    "SOP": "L2",  # Most SOP-labeled docs are procedures (Level 2)
    "WI": "L3",  # Work Instructions → Level 3
    "FORM": "L4",  # Forms → Level 4
    "DHF": "L3",  # Design History File → treat as Level 3
    "OTHER": None,  # OTHER needs LLM classification or user input
}


# ============================================================
# Document Hierarchy Manager
# ============================================================


class DocHierarchyManager:
    """Manages document hierarchy configuration with persistence."""

    def __init__(self, config_path: str = "./data/doc_hierarchy.json"):
        self._config_path = Path(config_path)
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._hierarchy: list[dict] = []
        self._system_scope: dict = {"max_level": 4, "configured": False}
        self._load()

    def _load(self) -> None:
        """Load hierarchy from file, or initialize with defaults."""
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._hierarchy = data.get("hierarchy", [])
                self._system_scope = data.get("system_scope", {
                    "max_level": 4,
                    "configured": False,
                })
                # Ensure all default levels exist (in case new defaults were added)
                self._ensure_defaults()
            except (json.JSONDecodeError, KeyError):
                self._hierarchy = [level.copy() for level in DEFAULT_HIERARCHY]
                self._system_scope = {"max_level": 4, "configured": False}
                self._save()
        else:
            self._hierarchy = [level.copy() for level in DEFAULT_HIERARCHY]
            self._system_scope = {"max_level": 4, "configured": False}
            self._save()

    def _ensure_defaults(self) -> None:
        """Ensure all default hierarchy levels exist in current config."""
        existing_ids = {h["id"] for h in self._hierarchy}
        changed = False
        for default in DEFAULT_HIERARCHY:
            if default["id"] not in existing_ids:
                self._hierarchy.append(default.copy())
                changed = True
        if changed:
            self._hierarchy.sort(key=lambda h: h["order"])
            self._save()

    def _save(self) -> None:
        """Save hierarchy to file with atomic write."""
        data = {
            "hierarchy": self._hierarchy,
            "system_scope": self._system_scope,
            "updated_at": datetime.now().isoformat(),
        }
        temp_path = self._config_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self._config_path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    # ---- Read Operations ----

    def get_all_levels(self) -> list[dict]:
        """Get all hierarchy levels sorted by order."""
        return sorted(self._hierarchy, key=lambda h: h["order"])

    def get_level(self, level_id: str) -> Optional[dict]:
        """Get a specific hierarchy level by ID."""
        for h in self._hierarchy:
            if h["id"] == level_id:
                return h.copy()
        return None

    def get_label(self, level_id: str, lang: str = "zh-TW") -> str:
        """Get display label for a hierarchy level in the given language."""
        level = self.get_level(level_id)
        if not level:
            return level_id
        labels = level.get("labels", {})
        return labels.get(lang, labels.get("zh-TW", labels.get("en-US", level_id)))

    def get_storage_type(self, level_id: str) -> str:
        """Get the storage folder type for a hierarchy level."""
        level = self.get_level(level_id)
        if not level:
            return "OTHER"
        return level.get("storage_type", "OTHER")

    def get_level_choices(self, lang: str = "zh-TW", respect_scope: bool = True) -> list[dict]:
        """Get hierarchy levels as choices for UI display.

        Args:
            lang: Language for display labels.
            respect_scope: If True, filter out levels beyond system_scope.max_level.
                           REG and CUSTOM-* levels are always included.

        Returns:
            List of {"id": "L1", "label": "1階-品質手冊", "order": 1}
        """
        levels = self.get_all_levels()
        if respect_scope:
            levels = self._filter_by_scope(levels)
        return [
            {
                "id": h["id"],
                "label": self.get_label(h["id"], lang),
                "order": h["order"],
            }
            for h in levels
        ]
    def _filter_by_scope(self, levels: list[dict]) -> list[dict]:
        """Filter hierarchy levels based on system_scope.max_level.

        Rules:
        - L1-L{max_level} are included
        - L{max_level+1} and above default levels are excluded
        - REG is always included (order=99, not a numbered level)
        - CUSTOM-* levels are always included
        """
        max_level = self._system_scope.get("max_level", 4)
        result = []
        for h in levels:
            hid = h["id"]
            # Always include REG and CUSTOM levels
            if hid == "REG" or hid.startswith("CUSTOM-"):
                result.append(h)
                continue
            # For default Lx levels, check against max_level
            if hid.startswith("L") and hid[1:].isdigit():
                level_num = int(hid[1:])
                if level_num <= max_level:
                    result.append(h)
            else:
                # Unknown ID format — include it
                result.append(h)
        return result

    # ---- System Scope Operations ----

    def get_system_scope(self) -> dict:
        """Get the current system scope configuration.

        Returns:
            {"max_level": int, "configured": bool}
        """
        return self._system_scope.copy()

    def set_system_scope(self, max_level: int) -> dict:
        """Set the quality system's maximum hierarchy level.

        Args:
            max_level: Maximum level number (e.g., 3 for 1-3階, 4 for 1-4階).
                       Must be >= 1 and <= 10.

        Returns:
            Updated system_scope dict.
        """
        if not (1 <= max_level <= 10):
            raise ValueError(f"max_level must be between 1 and 10, got {max_level}")
        with self._lock:
            self._system_scope = {
                "max_level": max_level,
                "configured": True,
            }
            self._save()
        return self._system_scope.copy()

    def is_scope_configured(self) -> bool:
        """Check if the user has configured the system scope."""
        return self._system_scope.get("configured", False)

    def get_filtered_levels(self, lang: str = "zh-TW") -> list[dict]:
        """Get hierarchy levels filtered by system scope.

        Convenience method: same as get_level_choices(lang, respect_scope=True).
        """
        return self.get_level_choices(lang=lang, respect_scope=True)
    # ---- Write Operations ----

    def add_level(
        self,
        label_zh: str,
        label_en: str = "",
        label_ja: str = "",
        storage_type: str = "OTHER",
        order: Optional[int] = None,
    ) -> dict:
        """Add a new custom hierarchy level.

        Args:
            label_zh: Chinese label (e.g., "5階-設計文件")
            label_en: English label (e.g., "L5-Design Doc")
            label_ja: Japanese label
            storage_type: Storage folder type (SOP, WI, FORM, DHF, OTHER)
            order: Display order (auto-assigned if None)

        Returns:
            The created hierarchy level dict.
        """
        with self._lock:
            # Generate unique ID
            custom_ids = [
                h["id"] for h in self._hierarchy if h["id"].startswith("CUSTOM-")
            ]
            if custom_ids:
                max_num = max(
                    int(cid.split("-")[1]) for cid in custom_ids if "-" in cid
                )
                new_id = f"CUSTOM-{max_num + 1}"
            else:
                new_id = "CUSTOM-1"

            # Auto-assign order if not provided
            if order is None:
                non_reg_orders = [
                    h["order"] for h in self._hierarchy if h["id"] != "REG"
                ]
                order = max(non_reg_orders) + 1 if non_reg_orders else 5

            new_level = {
                "id": new_id,
                "order": order,
                "labels": {
                    "zh-TW": label_zh,
                    "zh-CN": label_zh,  # fallback to zh-TW
                    "en-US": label_en or label_zh,
                    "ja-JP": label_ja or label_zh,
                },
                "storage_type": storage_type
                if storage_type in ("SOP", "WI", "FORM", "DHF", "OTHER")
                else "OTHER",
                "is_default": False,
            }

            self._hierarchy.append(new_level)
            self._hierarchy.sort(key=lambda h: h["order"])
            self._save()
            return new_level.copy()

    def update_level(self, level_id: str, **kwargs) -> Optional[dict]:
        """Update a hierarchy level's labels or order.

        Only non-default levels can have their ID changed.
        Labels can be updated for any level.
        """
        with self._lock:
            for i, h in enumerate(self._hierarchy):
                if h["id"] == level_id:
                    if "labels" in kwargs:
                        h["labels"].update(kwargs["labels"])
                    if "order" in kwargs:
                        h["order"] = kwargs["order"]
                    if "storage_type" in kwargs and not h.get("is_default"):
                        h["storage_type"] = kwargs["storage_type"]
                    self._hierarchy.sort(key=lambda x: x["order"])
                    self._save()
                    return h.copy()
        return None

    def remove_level(self, level_id: str) -> bool:
        """Remove a custom hierarchy level. Default levels cannot be removed."""
        with self._lock:
            for i, h in enumerate(self._hierarchy):
                if h["id"] == level_id:
                    if h.get("is_default"):
                        return False  # Cannot remove default levels
                    self._hierarchy.pop(i)
                    self._save()
                    return True
        return False

    # ---- Legacy Compatibility ----

    def legacy_to_hierarchy_id(self, doc_type: str) -> Optional[str]:
        """Convert legacy doc_type (SOP/WI/FORM/DHF/OTHER) to hierarchy ID."""
        return LEGACY_DOCTYPE_MAP.get(doc_type)

    def resolve_display_label(
        self,
        level_id: Optional[str],
        legacy_doc_type: str = "OTHER",
        lang: str = "zh-TW",
    ) -> str:
        """Get display label, falling back to legacy doc_type mapping if needed."""
        if level_id:
            label = self.get_label(level_id, lang)
            if label != level_id:  # get_label returns ID if not found
                return label

        # Fall back to legacy mapping
        mapped_id = self.legacy_to_hierarchy_id(legacy_doc_type)
        if mapped_id:
            return self.get_label(mapped_id, lang)

        # Final fallback
        return legacy_doc_type


# ============================================================
# Singleton
# ============================================================

_instance: Optional[DocHierarchyManager] = None
_singleton_lock = threading.Lock()


def get_doc_hierarchy() -> DocHierarchyManager:
    """Get the singleton DocHierarchyManager instance."""
    global _instance
    if _instance is None:
        with _singleton_lock:
            if _instance is None:
                _instance = DocHierarchyManager()
    return _instance
