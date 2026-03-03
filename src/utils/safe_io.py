"""Safe file I/O utilities for AI-QMS.

Provides atomic, permission-resilient file write operations for Windows
environments where PermissionError is common due to:
- Read-only folder attributes (git clone, ZIP extract)
- Anti-virus file locking
- Background process holding file handles
- Multiple app instances

All write operations:
1. Write to a temp file in the same directory (same filesystem)
2. Atomically replace the target via os.replace()
3. Retry on PermissionError with exponential backoff
4. Log warnings on transient failures, raise on persistent failures

Usage:
    from src.utils.safe_io import atomic_write_json, atomic_write_text, safe_save_binary

    atomic_write_json(Path("data/config.json"), {"key": "value"})
    atomic_write_text(Path("data/config.md"), "# Hello")
    safe_save_binary(Path("data/exports/report.docx"), doc.save)
"""

import json
import logging
import os
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Default retry configuration
_DEFAULT_RETRIES = 3
_BASE_DELAY = 0.3  # seconds, multiplied by attempt number


def _fix_readonly(path: Path) -> None:
    """Remove read-only attribute from a file or directory on Windows."""
    if sys.platform != "win32":
        return
    try:
        if path.exists():
            current = os.stat(path).st_mode
            if not (current & stat.S_IWRITE):
                os.chmod(path, current | stat.S_IWRITE)
    except OSError:
        pass


def atomic_write_json(
    path: Path,
    data: dict,
    retries: int = _DEFAULT_RETRIES,
    ensure_ascii: bool = False,
    indent: int = 2,
) -> None:
    """Write JSON atomically: temp file → os.replace(). Retries on PermissionError.

    Args:
        path: Target file path.
        data: Dictionary to serialize as JSON.
        retries: Number of retry attempts on PermissionError.
        ensure_ascii: json.dump ensure_ascii parameter.
        indent: json.dump indent parameter.

    Raises:
        PermissionError: If all retries exhausted.
        OSError: On non-permission I/O errors.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(retries):
        try:
            fd, tmp = tempfile.mkstemp(
                dir=str(path.parent), suffix=".tmp", prefix=path.stem
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
                # Fix read-only on target before replace (Windows)
                _fix_readonly(path)
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
                delay = _BASE_DELAY * (attempt + 1)
                logger.warning(
                    "PermissionError writing %s (attempt %d/%d), retrying in %.1fs...",
                    path,
                    attempt + 1,
                    retries,
                    delay,
                )
                _fix_readonly(path)
                _fix_readonly(path.parent)
                time.sleep(delay)
            else:
                logger.error(
                    "PermissionError writing %s after %d retries", path, retries
                )
                raise


def atomic_write_text(
    path: Path,
    content: str,
    retries: int = _DEFAULT_RETRIES,
    encoding: str = "utf-8",
) -> None:
    """Write text atomically: temp file → os.replace(). Retries on PermissionError.

    Args:
        path: Target file path.
        content: Text content to write.
        retries: Number of retry attempts on PermissionError.
        encoding: File encoding.

    Raises:
        PermissionError: If all retries exhausted.
        OSError: On non-permission I/O errors.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(retries):
        try:
            fd, tmp = tempfile.mkstemp(
                dir=str(path.parent), suffix=".tmp", prefix=path.stem
            )
            try:
                with os.fdopen(fd, "w", encoding=encoding) as f:
                    f.write(content)
                _fix_readonly(path)
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
                delay = _BASE_DELAY * (attempt + 1)
                logger.warning(
                    "PermissionError writing %s (attempt %d/%d), retrying in %.1fs...",
                    path,
                    attempt + 1,
                    retries,
                    delay,
                )
                _fix_readonly(path)
                _fix_readonly(path.parent)
                time.sleep(delay)
            else:
                logger.error(
                    "PermissionError writing %s after %d retries", path, retries
                )
                raise


def safe_save_binary(
    path: Path,
    save_func: Callable,
    retries: int = _DEFAULT_RETRIES,
) -> None:
    """Save a binary file (Word/Excel) with PermissionError retry.

    Unlike atomic_write_json/text, this uses the library's own .save() method
    which writes directly to the path. We wrap it with retry logic.

    Args:
        path: Target file path.
        save_func: Callable that accepts a file path string, e.g. doc.save or wb.save.
                   Will be called as save_func(str(path)).
        retries: Number of retry attempts on PermissionError.

    Raises:
        PermissionError: If all retries exhausted.

    Example:
        from docx import Document
        doc = Document()
        safe_save_binary(Path("report.docx"), doc.save)
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(retries):
        try:
            _fix_readonly(path)
            save_func(str(path))
            return
        except PermissionError:
            if attempt < retries - 1:
                delay = _BASE_DELAY * (attempt + 1)
                logger.warning(
                    "PermissionError saving %s (attempt %d/%d), retrying in %.1fs...",
                    path,
                    attempt + 1,
                    retries,
                    delay,
                )
                _fix_readonly(path)
                _fix_readonly(path.parent)
                time.sleep(delay)
            else:
                logger.error(
                    "PermissionError saving %s after %d retries", path, retries
                )
                raise
