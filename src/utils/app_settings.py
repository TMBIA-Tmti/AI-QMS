"""AI-QMS — 應用程式層級持久化設定

獨立於 user_settings.py（有 90 秒 TTL），本模組提供
不會自動過期的持久化設定，用於：
  - MDSAP 五國交叉詰問按鈕記憶 (mdsap_verify_enabled)
  - 自訂跳過階段 (custom_skip_phases)
  - 其他需要跨 session 保存的 app-level 設定

儲存路徑: data/app_settings.json
"""

import json
import os
import tempfile
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_APP_SETTINGS_PATH = Path(__file__).parent.parent.parent / "data" / "app_settings.json"


def _atomic_write_json(path: Path, data: dict, retries: int = 3) -> None:
    """Write JSON atomically: write to temp file then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            fd, tmp = tempfile.mkstemp(
                dir=str(path.parent), suffix=".tmp", prefix=path.stem
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, str(path))
                return
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except PermissionError:
            if attempt < retries - 1:
                logger.warning(
                    "PermissionError writing %s (attempt %d/%d), retrying...",
                    path,
                    attempt + 1,
                    retries,
                )
                time.sleep(0.3 * (attempt + 1))
            else:
                logger.error(
                    "PermissionError writing %s after %d retries", path, retries
                )
                raise


def load_app_settings() -> dict:
    """載入應用程式設定（無 TTL，永久保存直到明確修改）。"""
    if not _APP_SETTINGS_PATH.exists():
        return {}
    try:
        with open(_APP_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_app_settings(settings: dict) -> None:
    """儲存應用程式設定（完整覆寫）。"""
    _atomic_write_json(_APP_SETTINGS_PATH, settings)


def get_app_setting(key: str, default=None):
    """取得單一設定值。"""
    return load_app_settings().get(key, default)


def set_app_setting(key: str, value) -> None:
    """設定單一值（讀取-修改-寫入）。"""
    settings = load_app_settings()
    settings[key] = value
    save_app_settings(settings)
