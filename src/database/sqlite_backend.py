"""
AI-QMS Phase 2 — SQLite 後端
============================

管理 SQLite 資料庫連線與資料表結構。
提供 ACID 保證、WAL 模式（支援併發讀取）、外鍵約束。

注意：本模組為 Phase 2 新增的並行儲存後端，不取代 Phase 1 的
      JSON-based ImmutableAuditLog 與 DocumentStore（兩者繼續運行）。
      Phase 2c 遷移完成後才會統一切換。
"""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)

# ============================================================
# DDL：建立所有資料表
# ============================================================

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- 文件元資料表
CREATE TABLE IF NOT EXISTS documents (
    doc_id          TEXT PRIMARY KEY,
    filename        TEXT NOT NULL,
    doc_type        TEXT CHECK(doc_type IN ('SOP','WI','FORM','DHF','OTHER')),
    current_version TEXT,
    status          TEXT DEFAULT 'active'
                    CHECK(status IN ('active','obsolete','draft')),
    parse_status    TEXT DEFAULT 'pending'
                    CHECK(parse_status IN (
                        'pending','parsing','parsed',
                        'indexing','indexed','error'
                    )),
    parse_error     TEXT,
    is_master       INTEGER DEFAULT 1,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 版本歷史表
CREATE TABLE IF NOT EXISTS document_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT REFERENCES documents(doc_id),
    version         TEXT NOT NULL,
    filepath        TEXT,
    markdown_path   TEXT,
    uploaded_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    status          TEXT DEFAULT 'effective',
    hash            TEXT,
    UNIQUE(doc_id, version)
);

-- 稽核紀錄表（SHA-256 雜湊鏈，符合 21 CFR Part 11）
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id       TEXT UNIQUE NOT NULL,
    timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
    action          TEXT NOT NULL,
    document_id     TEXT,
    user_id         TEXT,
    details         TEXT,           -- JSON 字串
    previous_hash   TEXT NOT NULL,
    current_hash    TEXT NOT NULL
);

-- 用戶表（多人模式預留；單機模式自動登入，此表留空）
CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,
    username        TEXT UNIQUE NOT NULL,
    email           TEXT,
    password_hash   TEXT NOT NULL,
    role            TEXT DEFAULT 'admin'
                    CHECK(role IN ('admin','auditor','editor','viewer')),
    department      TEXT,
    is_active       INTEGER DEFAULT 1,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login      DATETIME
);

-- CAPA 記錄表（矯正與預防措施，符合 ISO 13485 §8.5.2/§8.5.3）
CREATE TABLE IF NOT EXISTS capa_records (
    capa_id             TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    type                TEXT NOT NULL
                        CHECK(type IN ('corrective','preventive')),
    status              TEXT DEFAULT 'open'
                        CHECK(status IN (
                            'open','investigating','action_planned',
                            'implementing','verifying','closed','cancelled'
                        )),
    priority            TEXT DEFAULT 'medium'
                        CHECK(priority IN ('low','medium','high','critical')),
    source              TEXT,
    source_ref          TEXT,
    description         TEXT,
    root_cause          TEXT,
    root_cause_method   TEXT,
    action_plan         TEXT,
    due_date            DATE,
    responsible_person  TEXT,
    verification_method TEXT,
    verification_result TEXT,
    effectiveness_check TEXT,
    closed_date         DATETIME,
    linked_documents    TEXT,       -- JSON 陣列
    linked_ncrs         TEXT,       -- JSON 陣列
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by          TEXT
);

-- 不符合事項表（符合 ISO 13485 §8.3）
CREATE TABLE IF NOT EXISTS ncr_records (
    ncr_id      TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    severity    TEXT NOT NULL
                CHECK(severity IN ('minor','major','critical')),
    status      TEXT DEFAULT 'open'
                CHECK(status IN ('open','investigating','capa_linked','closed')),
    finding     TEXT NOT NULL,
    evidence    TEXT,
    clause_ref  TEXT,
    linked_capa TEXT REFERENCES capa_records(capa_id),
    audit_ref   TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by  TEXT
);

-- 內部稽核排程表（符合 ISO 13485 §8.2.4）
CREATE TABLE IF NOT EXISTS internal_audits (
    audit_id        TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    audit_type      TEXT DEFAULT 'internal'
                    CHECK(audit_type IN ('internal','external','supplier','process')),
    status          TEXT DEFAULT 'planned'
                    CHECK(status IN ('planned','in_progress','completed','cancelled')),
    scope           TEXT,
    criteria        TEXT,
    lead_auditor    TEXT,
    auditee         TEXT,
    planned_date    DATE,
    actual_date     DATE,
    findings_count  INTEGER DEFAULT 0,
    report_path     TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by      TEXT
);

-- 效能索引
CREATE INDEX IF NOT EXISTS idx_documents_status
    ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_parse_status
    ON documents(parse_status);
CREATE INDEX IF NOT EXISTS idx_capa_status
    ON capa_records(status);
CREATE INDEX IF NOT EXISTS idx_capa_priority
    ON capa_records(priority);
CREATE INDEX IF NOT EXISTS idx_ncr_status
    ON ncr_records(status);
CREATE INDEX IF NOT EXISTS idx_audit_status
    ON internal_audits(status);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
    ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_action
    ON audit_log(action);
"""


# ============================================================
# QMSDatabase 類別
# ============================================================


class QMSDatabase:
    """
    AI-QMS SQLite 資料庫管理員

    功能：
    - WAL 模式（允許多個讀取者 + 一個寫入者）
    - 外鍵約束啟用
    - 執行緒安全（每個執行緒獨立連線）
    - Context manager 支援

    使用範例：
        db = QMSDatabase("./data/qms.db")
        with db.get_connection() as conn:
            conn.execute("SELECT * FROM capa_records")
    """

    def __init__(self, db_path: str = "./data/qms.db"):
        self.db_path = Path(db_path)
        self._local = threading.local()  # 每個執行緒獨立連線
        self._init_lock = threading.Lock()
        self._initialized = False

        # 確保目錄存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 初始化資料庫結構
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        """建立所有資料表與索引（冪等操作）"""
        with self._init_lock:
            if self._initialized:
                return
            try:
                conn = self._get_raw_connection()
                conn.executescript(_SCHEMA_SQL)
                conn.commit()
                self._initialized = True
                logger.info("QMSDatabase 已初始化：%s", self.db_path)
            except sqlite3.Error as e:
                logger.error("資料庫初始化失敗：%s", e)
                raise

    def _get_raw_connection(self) -> sqlite3.Connection:
        """取得執行緒本地連線（內部使用）"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0,
            )
            conn.row_factory = sqlite3.Row  # 讓查詢結果可以用欄位名稱存取
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=10000")  # 10 秒等待
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        取得資料庫連線的 Context Manager

        自動 commit/rollback：
        - 成功離開 with 區塊 → commit
        - 例外 → rollback

        使用範例：
            with db.get_connection() as conn:
                conn.execute("INSERT INTO capa_records ...")
        """
        conn = self._get_raw_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(
        self, sql: str, params: tuple = (), fetch: Optional[str] = None
    ) -> Any:
        """
        執行 SQL 語句的便利方法

        Args:
            sql:    SQL 語句
            params: 參數 tuple（防 SQL Injection）
            fetch:  None=不取結果, "one"=fetchone, "all"=fetchall

        Returns:
            依 fetch 參數回傳結果
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            if fetch == "one":
                row = cursor.fetchone()
                return dict(row) if row else None
            elif fetch == "all":
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
            return cursor

    def execute_many(self, sql: str, params_list: list[tuple]) -> int:
        """
        批次執行 SQL（適合大量插入）

        Returns:
            影響的列數
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, params_list)
            return cursor.rowcount

    def close(self) -> None:
        """關閉目前執行緒的連線"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def __enter__(self) -> "QMSDatabase":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def get_table_stats(self) -> dict[str, int]:
        """取得各資料表的列數（除錯用）"""
        tables = [
            "documents", "document_versions", "audit_log",
            "users", "capa_records", "ncr_records", "internal_audits",
        ]
        stats = {}
        with self.get_connection() as conn:
            for table in tables:
                row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
                stats[table] = row["cnt"] if row else 0
        return stats


# ============================================================
# Singleton 管理
# ============================================================

_db_instance: Optional[QMSDatabase] = None
_db_lock = threading.Lock()


def get_db(db_path: Optional[str] = None) -> QMSDatabase:
    """
    取得 QMSDatabase Singleton 實例

    Args:
        db_path: 資料庫路徑（僅第一次呼叫時有效）
                 若為 None，使用 config.py 的 SQLITE_DB_PATH

    Returns:
        QMSDatabase 實例
    """
    global _db_instance

    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                if db_path is None:
                    try:
                        from src.config import SQLITE_DB_PATH
                        db_path = SQLITE_DB_PATH
                    except ImportError:
                        db_path = "./data/qms.db"
                _db_instance = QMSDatabase(db_path)

    return _db_instance


def reset_db_singleton() -> None:
    """重設 Singleton（測試用途）"""
    global _db_instance
    with _db_lock:
        if _db_instance:
            _db_instance.close()
        _db_instance = None
