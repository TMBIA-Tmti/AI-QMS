"""
AI-QMS Phase 2 — 雙模式任務派發器
====================================

根據 QMS_MODE 環境變數自動選擇任務執行方式：

  standalone 模式（預設）：
    asyncio.create_task() 直接在事件迴圈中執行
    適合單機使用（1-5 人，RTX 5060 Ti 硬體）

  server 模式：
    Celery 排入任務佇列（需要 Redis + Celery Worker）
    適合多人伺服器部署

設計原則：
  - 呼叫端介面完全相同，不需關心底層模式
  - SQLite parse_status 欄位即時反映任務進度
  - 系統重啟時自動恢復 parsing/indexing 狀態的任務

Phase 2a 狀態：
  _parse_document_async 和 _index_document_async 為 Stub 實作，
  記錄狀態變化。完整解析/索引邏輯在 Phase 2b 實作。

使用範例：
    from src.services.task_dispatcher import dispatch_parse, dispatch_index

    task_id = await dispatch_parse("SOP-001", "./uploads/SOP-001.pdf", "user_01")
    status  = await get_task_status(task_id)
    print(status)  # {"task_id": "...", "status": "parsing", "doc_id": "SOP-001"}
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 內部任務狀態快取（standalone 模式使用）
# ============================================================

_task_registry: dict[str, dict] = {}
_registry_lock = asyncio.Lock() if False else __import__("threading").Lock()


def _register_task(task_id: str, doc_id: str, task_type: str) -> dict:
    """在本地登錄簿新增任務記錄"""
    record = {
        "task_id": task_id,
        "doc_id": doc_id,
        "task_type": task_type,
        "status": "queued",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "error": None,
    }
    with _registry_lock:
        _task_registry[task_id] = record
    return record


def _update_task(task_id: str, **kwargs) -> None:
    """更新任務狀態"""
    with _registry_lock:
        if task_id in _task_registry:
            _task_registry[task_id].update(kwargs)
            _task_registry[task_id]["updated_at"] = datetime.now().isoformat()


# ============================================================
# 文件解析任務（Phase 2a Stub）
# ============================================================


async def _parse_document_async(
    task_id: str,
    doc_id: str,
    filepath: str,
    user_id: str,
) -> None:
    """
    文件解析任務（asyncio 執行）

    Phase 2a：更新 SQLite parse_status，記錄執行狀態。
    Phase 2b：整合 DoclingEngine 實際解析文件。
    """
    _update_task(task_id, status="running")
    _update_parse_status(doc_id, "parsing")

    try:
        logger.info(
            "[parse_task] 開始解析 doc_id=%s filepath=%s user=%s",
            doc_id, filepath, user_id,
        )

        # Phase 2a：Stub — 模擬解析延遲
        # Phase 2b 替換為：
        #   from src.ocr.docling_engine import get_engine
        #   result = get_engine().parse(filepath)
        #   _save_markdown(doc_id, result.markdown)
        await asyncio.sleep(0)  # yield control

        _update_parse_status(doc_id, "parsed")
        _update_task(task_id, status="completed")
        logger.info("[parse_task] 解析完成 doc_id=%s（Phase 2a stub）", doc_id)

    except Exception as e:
        _update_parse_status(doc_id, "error", str(e))
        _update_task(task_id, status="failed", error=str(e))
        logger.error("[parse_task] 解析失敗 doc_id=%s：%s", doc_id, e)
        raise


# ============================================================
# LightRAG 建圖任務（Phase 2a Stub）
# ============================================================


async def _index_document_async(
    task_id: str,
    doc_id: str,
    content: str,
    user_id: str,
) -> None:
    """
    LightRAG 知識圖譜建圖任務（asyncio 執行）

    Phase 2a：更新 SQLite parse_status，記錄執行狀態。
    Phase 2b：整合 LightRAG 實際建立知識圖譜。
    """
    _update_task(task_id, status="running")
    _update_parse_status(doc_id, "indexing")

    try:
        logger.info(
            "[index_task] 開始建圖 doc_id=%s content_len=%d user=%s",
            doc_id, len(content), user_id,
        )

        # Phase 2a：Stub — 模擬建圖延遲
        # Phase 2b 替換為：
        #   from src.storage.lightrag_store import get_lightrag
        #   await get_lightrag().ainsert(content)
        await asyncio.sleep(0)  # yield control

        _update_parse_status(doc_id, "indexed")
        _update_task(task_id, status="completed")
        logger.info("[index_task] 建圖完成 doc_id=%s（Phase 2a stub）", doc_id)

    except Exception as e:
        _update_parse_status(doc_id, "error", str(e))
        _update_task(task_id, status="failed", error=str(e))
        logger.error("[index_task] 建圖失敗 doc_id=%s：%s", doc_id, e)
        raise


# ============================================================
# SQLite 狀態更新輔助
# ============================================================


def _update_parse_status(
    doc_id: str,
    status: str,
    error: Optional[str] = None,
) -> None:
    """更新 SQLite documents 表的 parse_status"""
    try:
        from src.database.sqlite_backend import get_db
        db = get_db()
        if error:
            db.execute(
                "UPDATE documents SET parse_status=?, parse_error=?, updated_at=CURRENT_TIMESTAMP WHERE doc_id=?",
                (status, error, doc_id),
            )
        else:
            db.execute(
                "UPDATE documents SET parse_status=?, updated_at=CURRENT_TIMESTAMP WHERE doc_id=?",
                (status, doc_id),
            )
    except Exception as e:
        logger.warning("更新 parse_status 失敗（doc_id=%s）：%s", doc_id, e)


# ============================================================
# 公開 API
# ============================================================


async def dispatch_parse(
    doc_id: str,
    filepath: str,
    user_id: str,
) -> str:
    """
    派發文件解析任務

    Args:
        doc_id:   文件 ID
        filepath: 文件檔案路徑
        user_id:  操作者 ID

    Returns:
        task_id（可用於查詢狀態）
    """
    task_id = f"parse-{uuid.uuid4().hex[:12]}"
    _register_task(task_id, doc_id, "parse")

    try:
        from src.config import DEPLOYMENT_MODE
    except ImportError:
        DEPLOYMENT_MODE = "standalone"

    if DEPLOYMENT_MODE == "server":
        # Server 模式：使用 Celery（延遲匯入）
        try:
            from src.tasks.parse_tasks import parse_document  # type: ignore
            celery_result = parse_document.delay(doc_id, filepath, user_id)
            _update_task(task_id, status="queued", celery_id=celery_result.id)
            logger.info(
                "[dispatch] Celery 解析任務已排入：task_id=%s celery=%s",
                task_id, celery_result.id,
            )
        except ImportError:
            logger.warning("Celery 未安裝，降級至 asyncio 執行")
            asyncio.create_task(
                _parse_document_async(task_id, doc_id, filepath, user_id)
            )
    else:
        # Standalone 模式：asyncio 直接執行
        asyncio.create_task(
            _parse_document_async(task_id, doc_id, filepath, user_id)
        )
        logger.info("[dispatch] asyncio 解析任務已建立：task_id=%s", task_id)

    return task_id


async def dispatch_index(
    doc_id: str,
    content: str,
    user_id: str,
) -> str:
    """
    派發 LightRAG 建圖任務

    Args:
        doc_id:  文件 ID
        content: Markdown 格式的文件內容
        user_id: 操作者 ID

    Returns:
        task_id（可用於查詢狀態）
    """
    task_id = f"index-{uuid.uuid4().hex[:12]}"
    _register_task(task_id, doc_id, "index")

    try:
        from src.config import DEPLOYMENT_MODE
    except ImportError:
        DEPLOYMENT_MODE = "standalone"

    if DEPLOYMENT_MODE == "server":
        try:
            from src.tasks.index_tasks import index_document  # type: ignore
            celery_result = index_document.delay(doc_id, content, user_id)
            _update_task(task_id, status="queued", celery_id=celery_result.id)
            logger.info(
                "[dispatch] Celery 建圖任務已排入：task_id=%s celery=%s",
                task_id, celery_result.id,
            )
        except ImportError:
            logger.warning("Celery 未安裝，降級至 asyncio 執行")
            asyncio.create_task(
                _index_document_async(task_id, doc_id, content, user_id)
            )
    else:
        asyncio.create_task(
            _index_document_async(task_id, doc_id, content, user_id)
        )
        logger.info("[dispatch] asyncio 建圖任務已建立：task_id=%s", task_id)

    return task_id


async def get_task_status(task_id: str) -> dict:
    """
    查詢任務狀態

    Args:
        task_id: dispatch_parse 或 dispatch_index 回傳的 task_id

    Returns:
        任務狀態 dict，包含 status / created_at / updated_at / error 等欄位
    """
    with _registry_lock:
        record = _task_registry.get(task_id)

    if record is None:
        return {
            "task_id": task_id,
            "status": "not_found",
            "error": "找不到此任務 ID",
        }

    return dict(record)


async def recover_pending_tasks() -> int:
    """
    系統重啟恢復：找出 SQLite 中狀態為 parsing/indexing 的文件並重新排入佇列

    Returns:
        重新排入的任務數
    """
    try:
        from src.database.sqlite_backend import get_db
        db = get_db()
        stuck_docs = db.execute(
            "SELECT doc_id, filepath FROM documents WHERE parse_status IN ('parsing','indexing')",
            fetch="all",
        )
    except Exception as e:
        logger.error("重啟恢復失敗，無法查詢 SQLite：%s", e)
        return 0

    if not stuck_docs:
        return 0

    recovered = 0
    for doc in stuck_docs:
        doc_id = doc["doc_id"]
        filepath = doc.get("filepath", "")
        logger.warning(
            "恢復卡住的任務：doc_id=%s status=parsing/indexing", doc_id
        )
        await dispatch_parse(doc_id, filepath, "system_recovery")
        recovered += 1

    logger.info("已恢復 %d 個任務", recovered)
    return recovered
