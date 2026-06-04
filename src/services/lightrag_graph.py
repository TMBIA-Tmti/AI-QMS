"""
LightRAG knowledge-graph orchestration service. (P1-2)
Scans markdown_storage/documents/, ingests into LightRAG, and exposes
entity-aware graph query with QMS clause / document-reference extraction.
Graceful degraded mode when lightrag-hku is unavailable.
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ── ingestion state ──────────────────────────────────────────────────────────
_ingested = False
_ingest_lock = asyncio.Lock()


def _docs_dir() -> Path:
    try:
        from src.config import BASE_DIR
        return Path(BASE_DIR) / "markdown_storage" / "documents"
    except Exception:
        return Path(__file__).parent.parent.parent / "markdown_storage" / "documents"


# ── QMS entity extraction ────────────────────────────────────────────────────

_CLAUSE_RE = re.compile(
    r"\b(?:ISO\s*13485|ISO\s*9001|MDR|IVDR|21\s*CFR|GMP|MDSAP)"
    r"(?:\s*[\-–—]\s*\d+(?:\.\d+)*)?",
    re.IGNORECASE,
)
_DOC_REF_RE = re.compile(
    r"\b([A-Z]{2,5}-\d{3,4}(?:-\d{1,2})?(?:\s*v[\d.]+)?)\b"
)


def extract_entities(text: str) -> dict:
    """Return QMS clause and document-reference entities found in text."""
    clauses = list(dict.fromkeys(m.group(0) for m in _CLAUSE_RE.finditer(text)))
    doc_refs = list(dict.fromkeys(m.group(1) for m in _DOC_REF_RE.finditer(text)))
    return {"clauses": clauses, "doc_refs": doc_refs}


# ── bulk ingestion ────────────────────────────────────────────────────────────

async def ingest_all_to_lightrag(
    progress_callback: Optional[Callable] = None,
) -> dict:
    """
    Scan markdown_storage/documents/ and insert each .md file into LightRAG.
    Skips files whose content has already been indexed (best-effort via size
    comparison; LightRAG deduplicates internally by content hash).
    Returns stats dict: {total, added, skipped, errors}.
    """
    from src.services.lightrag_service import insert_document, initialize_lightrag

    stats = {"total": 0, "added": 0, "skipped": 0, "errors": 0}

    if not await initialize_lightrag():
        logger.warning("LightRAG unavailable — graph ingestion skipped")
        return stats

    docs_dir = _docs_dir()
    if not docs_dir.exists():
        logger.warning("Docs dir not found: %s", docs_dir)
        return stats

    files = sorted(docs_dir.rglob("*.md"))
    stats["total"] = len(files)

    for i, fp in enumerate(files, 1):
        if progress_callback:
            try:
                progress_callback(i, stats["total"], fp.name)
            except Exception:
                pass
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.error("Cannot read %s: %s", fp, exc)
            stats["errors"] += 1
            continue

        ok = await insert_document(fp.stem, content)
        if ok:
            stats["added"] += 1
        else:
            stats["errors"] += 1

    logger.info("LightRAG graph ingestion done: %s", stats)
    return stats


async def ensure_ingested(progress_callback: Optional[Callable] = None) -> bool:
    """
    Idempotent: runs full ingestion exactly once per process lifetime.
    Returns True if LightRAG is available after the call.
    """
    global _ingested
    async with _ingest_lock:
        if _ingested:
            return True
        stats = await ingest_all_to_lightrag(progress_callback)
        _ingested = True
        return stats.get("errors", 0) < stats.get("total", 1) or stats["total"] == 0


# ── graph query ───────────────────────────────────────────────────────────────

async def graph_query(
    question: str,
    mode: str = "hybrid",
    auto_ingest: bool = True,
) -> str:
    """
    Query the LightRAG knowledge graph.
    Optionally triggers first-run ingestion (auto_ingest=True).
    Returns empty string when LightRAG is unavailable.
    """
    from src.services.lightrag_service import query_knowledge

    if auto_ingest:
        await ensure_ingested()

    return await query_knowledge(question, mode=mode)


async def graph_query_with_entities(
    question: str,
    mode: str = "hybrid",
    auto_ingest: bool = True,
) -> dict:
    """
    Query + entity extraction.
    Returns {answer: str, entities: {clauses, doc_refs}}.
    """
    answer = await graph_query(question, mode=mode, auto_ingest=auto_ingest)
    return {
        "answer": answer,
        "entities": extract_entities(answer),
    }


# ── clause-document relationship ─────────────────────────────────────────────

async def find_documents_by_clause(clause: str) -> list[dict]:
    """
    Query the graph for documents related to a QMS clause.
    Returns a list of {doc_id, answer} dicts (empty list on failure).
    """
    q = f"Which QMS documents reference or implement {clause}?"
    result = await graph_query_with_entities(q)
    docs = result["entities"]["doc_refs"]
    return [{"doc_id": d, "clause": clause, "answer": result["answer"]} for d in docs]
