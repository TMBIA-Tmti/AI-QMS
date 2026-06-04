"""
RAG ingestion pipeline — scans markdown_storage/documents/ and indexes .md files. (P1-1)
Chunks documents > 2000 chars with 200-char overlap.
"""
from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)
CHUNK_SIZE, CHUNK_OVERLAP = 2000, 200
_DIR_TYPE = {"sop": "SOP", "wi": "WI", "form": "FORM", "record": "RECORD", "manual": "MANUAL"}


def _docs_dir() -> Path:
    try:
        from src.config import BASE_DIR
        return Path(BASE_DIR) / "markdown_storage" / "documents"
    except Exception:
        return Path(__file__).parent.parent.parent / "markdown_storage" / "documents"


def _doc_id(p: Path) -> str:
    m = re.match(r"^([A-Za-z0-9\-]+?)(?:_v[\d.]+)?$", p.stem)
    return m.group(1) if m else p.stem


def _version(p: Path) -> str:
    m = re.search(r"_v([\d.]+)", p.stem)
    return m.group(1) if m else "1.0"


def _doc_type(p: Path) -> str:
    for part in p.parts:
        for k, v in _DIR_TYPE.items():
            if part.lower().startswith(k):
                return v
    return "DOCUMENT"


def _chunks(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]
    result, start = [], 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        result.append(text[start:end])
        if end == len(text):
            break
        start = end - CHUNK_OVERLAP
    return result


async def ingest_document(filepath: Path) -> bool:
    from src.services.vector_store import get_vector_store
    store = get_vector_store()
    if not store.is_available:
        return False
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.error("Cannot read %s: %s", filepath, exc)
        return False
    doc_id = _doc_id(filepath)
    meta = {"filepath": str(filepath), "doc_type": _doc_type(filepath),
            "version": _version(filepath), "filename": filepath.name}
    try:
        parts = _chunks(content)
        if len(parts) == 1:
            if not await store.document_exists(doc_id):
                await store.add_document(doc_id, content, meta)
        else:
            for i, chunk in enumerate(parts):
                cid = f"{doc_id}__chunk{i}"
                if not await store.document_exists(cid):
                    await store.add_document(cid, chunk, {**meta, "chunk_index": i, "total_chunks": len(parts)})
        return True
    except Exception as exc:
        logger.error("Ingest failed for %s: %s", filepath, exc)
        return False


async def ingest_all_documents(progress_callback: Optional[Callable] = None) -> dict:
    from src.services.vector_store import get_vector_store
    stats = {"total": 0, "added": 0, "skipped": 0, "errors": 0}
    docs_dir = _docs_dir()
    if not docs_dir.exists():
        logger.warning("Documents dir not found: %s", docs_dir)
        return stats
    store = get_vector_store()
    if not store.is_available:
        return stats
    files = sorted(docs_dir.rglob("*.md"))
    stats["total"] = len(files)
    for i, fp in enumerate(files, 1):
        if progress_callback:
            try:
                progress_callback(i, stats["total"], fp.name)
            except Exception:
                pass
        doc_id = _doc_id(fp)
        if await store.document_exists(doc_id) or await store.document_exists(f"{doc_id}__chunk0"):
            stats["skipped"] += 1
            continue
        if await ingest_document(fp):
            stats["added"] += 1
        else:
            stats["errors"] += 1
    logger.info("Ingestion done: %s", stats)
    return stats
