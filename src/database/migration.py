"""
AI-QMS Phase 2 — JSON → SQLite 遷移腳本
=========================================

將 Phase 1 的 JSON 資料遷移至 Phase 2 的 SQLite 資料庫。

遷移策略（漸進式，符合設計原則）：
  Phase 2a: 新功能直接用 SQLite，舊 JSON 資料以此腳本手動/自動遷移
  Phase 2b: 舊資料自動遷移驗證
  Phase 2c: 移除 JSON 讀寫邏輯，統一 SQLite

冪等性保證：
  使用 INSERT OR IGNORE，重複執行不會產生重複資料。

使用方式：
  # 程式呼叫
  from src.database.migration import migrate_all
  migrate_all(json_data_dir="./data", db_path="./data/qms.db")

  # CLI 執行
  python -m src.database.migration --data-dir ./data --db ./data/qms.db
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================
# 遷移函式：document_store.json → documents + document_versions
# ============================================================


def migrate_document_store(conn, json_path: Path) -> tuple[int, int]:
    """
    遷移 document_store.json 到 documents 和 document_versions 資料表

    Args:
        conn:      sqlite3 連線（呼叫者管理 commit/rollback）
        json_path: document_store.json 路徑

    Returns:
        (遷移文件數, 遷移版本數)
    """
    if not json_path.exists():
        logger.warning("找不到 document_store.json：%s（跳過）", json_path)
        return 0, 0

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("讀取 document_store.json 失敗：%s", e)
        return 0, 0

    documents = data.get("documents", {})
    doc_count = 0
    version_count = 0

    for doc_id, doc in documents.items():
        # 推斷文件類型
        filename: str = doc.get("filename", "")
        doc_type = _infer_doc_type(filename)

        # 插入 documents 表（已存在則跳過）
        conn.execute(
            """
            INSERT OR IGNORE INTO documents
                (doc_id, filename, doc_type, current_version, status,
                 parse_status, is_master, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                filename,
                doc_type,
                doc.get("current_version", "1.0"),
                "obsolete" if doc.get("is_obsolete") else "active",
                "parsed",           # JSON 中已存在的文件視為已解析
                1 if doc.get("is_master", True) else 0,
                doc.get("created_at") or datetime.now().isoformat(),
                doc.get("updated_at") or datetime.now().isoformat(),
            ),
        )

        # 如果 documents 表中此列是新增的才計數
        if conn.execute(
            "SELECT changes()"
        ).fetchone()[0]:
            doc_count += 1

        # 插入版本歷史
        for version_info in doc.get("versions", []):
            conn.execute(
                """
                INSERT OR IGNORE INTO document_versions
                    (doc_id, version, filepath, uploaded_at, status, hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    version_info.get("version", "1.0"),
                    version_info.get("filepath", ""),
                    version_info.get("uploaded_at") or datetime.now().isoformat(),
                    version_info.get("status", "effective"),
                    version_info.get("hash"),
                ),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                version_count += 1

    logger.info(
        "document_store 遷移完成：%d 份文件、%d 個版本", doc_count, version_count
    )
    return doc_count, version_count


# ============================================================
# 遷移函式：audit_log.json → audit_log 資料表
# ============================================================


def migrate_audit_log(conn, json_path: Path) -> int:
    """
    遷移 audit_log.json 到 audit_log 資料表

    Args:
        conn:      sqlite3 連線
        json_path: audit_log.json 路徑

    Returns:
        遷移的紀錄數
    """
    if not json_path.exists():
        logger.warning("找不到 audit_log.json：%s（跳過）", json_path)
        return 0

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("讀取 audit_log.json 失敗：%s", e)
        return 0

    records = data.get("records", [])
    migrated = 0

    for record in records:
        details = record.get("details", {})
        if isinstance(details, dict):
            details_str = json.dumps(details, ensure_ascii=False)
        else:
            details_str = str(details)

        conn.execute(
            """
            INSERT OR IGNORE INTO audit_log
                (record_id, timestamp, action, document_id,
                 user_id, details, previous_hash, current_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("record_id", ""),
                record.get("timestamp") or datetime.now().isoformat(),
                record.get("action", "UNKNOWN"),
                record.get("document_id", ""),
                record.get("user_id", ""),
                details_str,
                record.get("previous_hash", ""),
                record.get("current_hash", ""),
            ),
        )
        if conn.execute("SELECT changes()").fetchone()[0]:
            migrated += 1

    logger.info("audit_log 遷移完成：%d 筆紀錄", migrated)
    return migrated


# ============================================================
# 主遷移函式
# ============================================================


def migrate_all(
    json_data_dir: str = "./data",
    db_path: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """
    執行完整的 JSON → SQLite 資料遷移

    Args:
        json_data_dir: 含有 JSON 檔案的目錄（通常是 ./data）
        db_path:       SQLite 資料庫路徑（None 則使用 config.py 設定值）
        dry_run:       True = 只統計，不實際寫入

    Returns:
        遷移統計資訊 dict
    """
    import sqlite3

    if db_path is None:
        try:
            from src.config import SQLITE_DB_PATH
            db_path = SQLITE_DB_PATH
        except ImportError:
            db_path = "./data/qms.db"

    data_dir = Path(json_data_dir)
    db_file = Path(db_path)

    logger.info("開始遷移：%s → %s", data_dir, db_file)

    if dry_run:
        logger.info("[dry_run] 模擬執行，不寫入資料庫")

    # 確保 SQLite 資料庫已初始化
    from src.database.sqlite_backend import get_db
    db = get_db(db_path)

    stats = {
        "documents": 0,
        "document_versions": 0,
        "audit_log_records": 0,
        "errors": [],
    }

    if dry_run:
        # 僅統計 JSON 內容
        doc_json = data_dir / "document_store.json"
        audit_json = data_dir / "audit_log.json"
        if doc_json.exists():
            d = json.loads(doc_json.read_text(encoding="utf-8"))
            docs = d.get("documents", {})
            stats["documents"] = len(docs)
            stats["document_versions"] = sum(
                len(v.get("versions", [])) for v in docs.values()
            )
        if audit_json.exists():
            d = json.loads(audit_json.read_text(encoding="utf-8"))
            stats["audit_log_records"] = len(d.get("records", []))
        logger.info("[dry_run] 預計遷移：%s", stats)
        return stats

    # 實際遷移（在同一個 transaction 中執行）
    raw_conn = db._get_raw_connection()
    try:
        doc_count, ver_count = migrate_document_store(
            raw_conn, data_dir / "document_store.json"
        )
        audit_count = migrate_audit_log(
            raw_conn, data_dir / "audit_log.json"
        )
        raw_conn.commit()

        stats["documents"] = doc_count
        stats["document_versions"] = ver_count
        stats["audit_log_records"] = audit_count

    except Exception as e:
        raw_conn.rollback()
        logger.error("遷移失敗，已回滾：%s", e)
        stats["errors"].append(str(e))
        raise

    logger.info(
        "遷移完成：文件 %d 份、版本 %d 個、稽核紀錄 %d 筆",
        doc_count, ver_count, audit_count,
    )
    return stats


# ============================================================
# 輔助函式
# ============================================================


def _infer_doc_type(filename: str) -> str:
    """從檔名推斷文件類型"""
    name_upper = filename.upper()
    if "SOP" in name_upper:
        return "SOP"
    if "WI" in name_upper or "WORK" in name_upper:
        return "WI"
    if "FORM" in name_upper or "表單" in name_upper:
        return "FORM"
    if "DHF" in name_upper or "設計" in name_upper:
        return "DHF"
    return "OTHER"


# ============================================================
# CLI 入口
# ============================================================


def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="AI-QMS Phase 2 — JSON → SQLite 資料遷移工具"
    )
    parser.add_argument(
        "--data-dir",
        default="./data",
        help="含有 JSON 檔案的目錄（預設：./data）",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite 資料庫路徑（預設：config.py 設定值）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="模擬執行，只統計不寫入",
    )

    args = parser.parse_args()

    try:
        stats = migrate_all(
            json_data_dir=args.data_dir,
            db_path=args.db,
            dry_run=args.dry_run,
        )
        print("\n遷移統計：")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] 遷移失敗：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _main()
