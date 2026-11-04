"""
LightRAG index for crawled national regulations.

One isolated LightRAG graph per country/region (its own working directory), so
that a query about e.g. Singapore can never return Japanese text. The internal
QMS document graph (``lightrag_service``) is untouched.

Flow:
  1. ``ingest_region`` reads the active crawled documents of a region from the
     regulatory markdown registry and inserts them into the region graph
     (resumable: a manifest records what is already indexed).
  2. ``retrieve_context`` returns graph + chunk context relevant to a question
     (``only_need_context``), which ``regulation_analyzer`` hands to the LLM
     that judges coverage against ISO 13485.

Everything degrades gracefully: if LightRAG is unavailable or the region has not
been ingested, callers fall back to the keyword-filtered text path.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_MIN_DOC_CHARS = 200
_instances: dict[str, Any] = {}
_init_lock: Optional[asyncio.Lock] = None


def _lightrag_root() -> Path:
    from src.config import LIGHTRAG_WORKING_DIR

    return Path(str(LIGHTRAG_WORKING_DIR)) / "regulatory"


def region_key(region_name: str) -> str:
    """Stable ASCII directory key for a REGION_SITES name."""
    from src.analysis.compliance_rules import generate_profile_id_from_region

    return generate_profile_id_from_region(region_name)


def region_dir(region_name: str) -> Path:
    return _lightrag_root() / region_key(region_name)


def _manifest_path(region_name: str) -> Path:
    return region_dir(region_name) / "ingest_manifest.json"


def load_manifest(region_name: str) -> dict[str, str]:
    """doc_id -> content_hash of everything already indexed for the region."""
    try:
        return json.loads(_manifest_path(region_name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_manifest(region_name: str, manifest: dict[str, str]) -> None:
    from src.utils.safe_io import atomic_write_json

    path = _manifest_path(region_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, manifest)


def has_region_index(region_name: str) -> bool:
    """True when at least one regulatory document is indexed for the region."""
    try:
        return bool(load_manifest(region_name))
    except Exception:
        return False


def list_region_documents(region_name: str, include_failed: bool = False) -> list[dict]:
    """Active, non-portal crawled documents of a region with their text.

    Documents that fail provenance/completeness verification (bot-block pages,
    search-result stubs, raw PDF bytes, truncated laws, ...) are excluded unless
    ``include_failed``. Returns dicts: doc_id, agency, doc_type, url, status,
    issues, content_hash, content.
    """
    from src.storage.regulatory_markdown_storage import get_regulatory_markdown_store
    from src.services.regulatory_source_check import verify_document

    try:
        from src.services.regulatory_crawler import get_site_doc_type
    except ImportError:  # pragma: no cover
        get_site_doc_type = None

    store = get_regulatory_markdown_store()
    out: list[dict] = []
    for entry in store.list_documents(region=region_name, status="active"):
        agency = entry.get("agency", "")
        doc_type = get_site_doc_type({"agency": agency}) if get_site_doc_type else "primary"
        if doc_type == "portal":
            continue
        md_rel = (entry.get("markdown_path") or "").replace("\\", "/")
        if not md_rel:
            continue
        path = store.base_path / md_rel
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Regulatory doc unreadable (%s): %s", path, exc)
            continue
        if len(content.strip()) < _MIN_DOC_CHARS:
            continue
        chk = verify_document(entry, content)
        if chk.status == "fail" and not include_failed:
            logger.warning("Skipping %s/%s: %s", region_name, entry.get("doc_id"), "; ".join(chk.issues))
            continue
        out.append(
            {
                "doc_id": entry.get("doc_id", path.stem),
                "agency": agency,
                "doc_type": doc_type,
                "url": entry.get("url", ""),
                "status": chk.status,
                "issues": chk.issues,
                "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "content": content,
            }
        )
    return out


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def clean_for_index(content: str) -> str:
    """Drop crawler annotations (``<!-- QMS_RELEVANT ... -->``) that the entity
    extractor would otherwise index as if they were regulatory content."""
    return _HTML_COMMENT.sub("", content)


def _with_provenance(doc: dict) -> str:
    """Prefix inserted text so every retrieved chunk carries its source."""
    head = f"[Source: {doc['agency']} | {doc['doc_type']} | {doc['url']}]\n\n"
    return head + clean_for_index(doc["content"])


async def _get_instance(region_name: str) -> Optional[Any]:
    """Create/initialise the LightRAG graph of one region (cached)."""
    global _init_lock
    from src.services import lightrag_service as svc

    if not svc._AVAILABLE:
        return None
    key = region_key(region_name)
    if key in _instances:
        return _instances[key]
    if _init_lock is None:
        _init_lock = asyncio.Lock()
    async with _init_lock:
        if key in _instances:
            return _instances[key]
        try:
            wd = region_dir(region_name)
            wd.mkdir(parents=True, exist_ok=True)
            ef = await svc._build_embed_func()
            if ef is None:
                return None
            inst = svc.LightRAG(
                working_dir=str(wd),
                embedding_func=ef,
                llm_model_func=svc._llm_model_func,
                llm_model_max_async=svc._llm_max_async(),
            )
            await inst.initialize_storages()
            _instances[key] = inst
            return inst
        except Exception as exc:
            logger.warning("Regulatory LightRAG init failed for %s: %s", region_name, exc)
            return None


async def ingest_region(
    region_name: str,
    max_docs: Optional[int] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> dict[str, int]:
    """Index a region's active crawled documents into its LightRAG graph.

    Resumable and incremental: documents whose content hash is already in the
    manifest are skipped; the manifest is written after every document so an
    interrupted run continues where it stopped.
    """
    stats = {"total": 0, "added": 0, "skipped": 0, "errors": 0}
    docs = list_region_documents(region_name)
    stats["total"] = len(docs)
    if not docs:
        return stats
    inst = await _get_instance(region_name)
    if inst is None:
        stats["errors"] = len(docs)
        return stats

    manifest = load_manifest(region_name)
    done_this_run = 0
    for i, doc in enumerate(docs, 1):
        if progress:
            try:
                progress(i, len(docs), doc["doc_id"])
            except Exception:
                pass
        if manifest.get(doc["doc_id"]) == doc["content_hash"]:
            stats["skipped"] += 1
            continue
        if max_docs is not None and done_this_run >= max_docs:
            break
        try:
            await inst.ainsert(
                _with_provenance(doc),
                ids=doc["doc_id"],
                file_paths=doc["url"] or doc["doc_id"],
            )
        except Exception as exc:
            logger.error("Regulatory insert failed (%s/%s): %s", region_name, doc["doc_id"], exc)
            stats["errors"] += 1
            continue
        manifest[doc["doc_id"]] = doc["content_hash"]
        _save_manifest(region_name, manifest)
        stats["added"] += 1
        done_this_run += 1
    return stats


async def retrieve_context(
    region_name: str,
    question: str,
    max_chars: int = 40000,
    mode: str = "hybrid",
) -> str:
    """Graph + chunk context for ``question`` from the region graph ('' if none)."""
    if not has_region_index(region_name):
        return ""
    inst = await _get_instance(region_name)
    if inst is None:
        return ""
    from src.services import lightrag_service as svc

    try:
        param = svc.QueryParam(
            mode=mode,
            only_need_context=True,
            max_total_tokens=int(os.getenv("LIGHTRAG_REG_CONTEXT_TOKENS", "12000")),
        )
        ctx = await inst.aquery(question, param=param)
    except Exception as exc:
        logger.warning("Regulatory LightRAG query failed (%s): %s", region_name, exc)
        return ""
    if not isinstance(ctx, str):
        return ""
    ctx = ctx.strip()
    # LightRAG returns a canned message when nothing matched.
    if not ctx or ctx.lower().startswith(("sorry", "[no-context]", "no relevant")):
        return ""
    return ctx[:max_chars]


# ── recall spot-check ────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    return "".join(text.split()).lower()


def build_probes(content: str, n: int) -> list[tuple[str, str]]:
    """Evenly spaced (query, expected_snippet) pairs from a document.

    The query is the first 60 characters of a paragraph (what a user or the
    analyzer would look up); the expected snippet is the *following* 50
    characters of the same paragraph. A hit means retrieval surfaced the real
    passage, not just something topically similar.
    """
    paras = [
        p.strip()
        for p in content.split("\n\n")
        if len(p.strip()) >= 140 and not p.lstrip().startswith(("[Source:", "#", "|", "<!--"))
    ]
    if not paras or n <= 0:
        return []
    step = max(1, len(paras) // n)
    chosen = paras[::step][:n]
    return [(p[:60], _norm(p[60:110])) for p in chosen if len(_norm(p[60:110])) >= 20]


async def measure_recall(region_name: str, sample: int = 8, mode: str = "hybrid") -> dict:
    """Probe the region graph with passages from its own indexed documents.

    Returns {"probes": int, "hits": int, "recall": float, "misses": [...]}.
    A low recall means LightRAG cannot reliably find what the corpus contains.
    """
    result = {"probes": 0, "hits": 0, "recall": None, "misses": []}
    manifest = load_manifest(region_name)
    if not manifest:
        return result
    docs = [d for d in list_region_documents(region_name) if d["doc_id"] in manifest]
    if not docs:
        return result
    per_doc = max(1, sample // len(docs)) if len(docs) <= sample else 1
    for doc in docs[:sample]:
        for query, expected in build_probes(doc["content"], per_doc):
            ctx = await retrieve_context(region_name, query, max_chars=10**7, mode=mode)
            result["probes"] += 1
            if expected in _norm(ctx):
                result["hits"] += 1
            else:
                result["misses"].append({"doc_id": doc["doc_id"], "query": query})
    if result["probes"]:
        result["recall"] = round(result["hits"] / result["probes"], 3)
    return result
