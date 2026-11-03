"""
AI-QMS Phase 1 - 防竄改稽核紀錄模組
符合 21 CFR Part 11 要求

安全模型
--------
1. 每筆紀錄的 current_hash 為 HMAC-SHA256(key, previous_hash + record_json)，
   金鑰不在被保護的 JSON 檔內，因此無金鑰者無法重算鏈上任何雜湊。
2. 另存一份「錨點狀態檔」(.audit_log_state.json)，內含紀錄總數、起始
   (genesis) 雜湊與鏈尾雜湊，並以同一把金鑰簽章。無金鑰者無法偽造，
   因此整批刪除尾端紀錄（截斷）會被紀錄數／鏈尾比對抓出來。
3. 舊版（無 HMAC）紀錄以 chain_version 區分，遷移時寫入一筆 HMAC 簽章的
   遷移錨點紀錄，將舊資料的雜湊與筆數釘在受保護的鏈上。
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import stat
import subprocess
import sys
import threading
import uuid

from datetime import datetime, timezone
from typing import TypedDict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

from src.utils.safe_io import atomic_write_json, atomic_write_text

try:
    from src import config as _config

    _DEFAULT_ENV_KEY = _config.AUDIT_LOG_HMAC_KEY
    _DEFAULT_KEY_FILE = _config.AUDIT_LOG_KEY_FILE
except Exception:  # pragma: no cover - config 匯入失敗時仍可運作
    _DEFAULT_ENV_KEY = os.getenv("AUDIT_LOG_HMAC_KEY", "")
    _DEFAULT_KEY_FILE = os.getenv("AUDIT_LOG_KEY_FILE", "./data/.audit_key")


# 目前的鏈格式版本：2 = HMAC-SHA256 簽章；1（或缺欄位）= 舊版純 SHA-256
CHAIN_VERSION = 2
GENESIS_PREVIOUS_HASH = "GENESIS_BLOCK"
MIGRATION_ACTION = "AUDIT_CHAIN_HMAC_MIGRATION"

# 以金鑰檔路徑為鍵的快取（ImmutableAuditLog 會被大量重複建立）
_KEY_CACHE: dict[str, bytes] = {}
_KEY_CACHE_LOCK = threading.Lock()


def _restrict_key_file_permissions(path: Path) -> None:
    """盡力將金鑰檔權限限縮為僅目前使用者可讀寫（失敗不影響運作）。"""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600 (POSIX)
    except OSError:
        pass

    if sys.platform != "win32":
        return

    # Windows 的 chmod 只切換唯讀旗標，需以 icacls 移除繼承並限縮 ACL
    user = os.environ.get("USERNAME")
    if not user:
        return
    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _load_or_create_hmac_key(key_file: str) -> bytes:
    """取得稽核鏈 HMAC 金鑰。

    順序：環境變數 AUDIT_LOG_HMAC_KEY → 金鑰檔 → 自動產生並寫入金鑰檔。
    """
    env_key = (_DEFAULT_ENV_KEY or os.getenv("AUDIT_LOG_HMAC_KEY", "")).strip()
    if env_key:
        return env_key.encode("utf-8")

    with _KEY_CACHE_LOCK:
        cached = _KEY_CACHE.get(key_file)
        if cached:
            return cached

        path = Path(key_file)
        key_str = ""
        if path.exists():
            try:
                key_str = path.read_text(encoding="utf-8").strip()
            except OSError as e:
                logger.error("無法讀取稽核金鑰檔 %s：%s", path, e)

        if not key_str:
            key_str = secrets.token_hex(32)
            try:
                atomic_write_text(path, key_str)
                _restrict_key_file_permissions(path)
                logger.warning(
                    "已自動產生稽核紀錄鏈 HMAC 金鑰並存於 %s。"
                    "生產環境請改以環境變數 AUDIT_LOG_HMAC_KEY 提供金鑰，"
                    "並將金鑰備份於稽核紀錄檔以外的安全位置；遺失金鑰將無法驗證既有紀錄鏈。",
                    path,
                )
            except OSError as e:
                logger.error(
                    "無法寫入稽核金鑰檔 %s：%s。本次執行將使用暫時金鑰，"
                    "重新啟動後既有紀錄鏈將無法驗證。請設定 AUDIT_LOG_HMAC_KEY 環境變數。",
                    path,
                    e,
                )

        key_bytes = key_str.encode("utf-8")
        _KEY_CACHE[key_file] = key_bytes
        return key_bytes


class AuditRecord(TypedDict):
    record_id: str
    timestamp: str
    action: str
    document_id: str
    user_id: str
    details: dict
    previous_hash: str
    current_hash: str
    chain_version: int


class ImmutableAuditLog:
    """
    防竄改稽核紀錄
    使用 HMAC-SHA256 雜湊鏈 + 獨立簽章錨點確保紀錄不可竄改、不可截斷
    """

    _lock = threading.RLock()

    def __init__(
        self,
        log_file: str = "./data/audit_log.json",
        hmac_key: Optional[str] = None,
        key_file: Optional[str] = None,
    ):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # 錨點狀態檔：與被保護的 audit_log.json 分開存放
        self.state_file = self.log_file.with_name(f".{self.log_file.stem}_state.json")

        if hmac_key:
            self._key = hmac_key.encode("utf-8")
        else:
            self._key = _load_or_create_hmac_key(key_file or _DEFAULT_KEY_FILE)
        self._key_id = hashlib.sha256(self._key).hexdigest()[:16]

        if not self.log_file.exists():
            self._init_log_file()

        self._ensure_anchor()

    def _init_log_file(self):
        """初始化日誌檔案"""
        atomic_write_json(self.log_file, {"records": []})

    def _load_records(self) -> list:
        """載入所有紀錄"""
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("records", [])
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            logger.error("Corrupt audit log JSON at %s", self.log_file)
            raise json.JSONDecodeError(
                f"Corrupt audit log file: {self.log_file}", "", 0
            )

    def _save_records(self, records: list):
        """儲存紀錄"""
        atomic_write_json(self.log_file, {"records": records})

    # ------------------------------------------------------------------
    # 雜湊 / 簽章
    # ------------------------------------------------------------------

    def _compute_hash(self, previous_hash: str, record_without_hash: dict) -> str:
        """依紀錄的 chain_version 計算 current_hash。

        v2 以上：HMAC-SHA256(key, previous_hash + record_json)
        v1（舊格式）：SHA-256(previous_hash + record_json)
        """
        record_json = json.dumps(
            record_without_hash, sort_keys=True, ensure_ascii=False
        )
        payload = f"{previous_hash}{record_json}".encode("utf-8")

        if int(record_without_hash.get("chain_version", 1)) >= 2:
            return hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return hashlib.sha256(payload).hexdigest()

    def _sign_state(self, payload: dict) -> str:
        """簽章錨點狀態內容"""
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hmac.new(
            self._key, canonical.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _write_state(self, records: list) -> None:
        """寫入（更新）簽章錨點狀態檔"""
        payload = {
            "chain_version": CHAIN_VERSION,
            "key_id": self._key_id,
            "record_count": len(records),
            "genesis_hash": (
                records[0].get("current_hash", "") if records else GENESIS_PREVIOUS_HASH
            ),
            "tip_hash": (
                records[-1].get("current_hash", "")
                if records
                else GENESIS_PREVIOUS_HASH
            ),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        payload["state_hmac"] = self._sign_state(payload)
        atomic_write_json(self.state_file, payload)

    def _read_state(self) -> Optional[dict]:
        """讀取錨點狀態檔（不存在或毀損時回傳 None）"""
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            return state if isinstance(state, dict) else None
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    # ------------------------------------------------------------------
    # 遷移 / 錨點建立
    # ------------------------------------------------------------------

    def _ensure_anchor(self) -> None:
        """確保錨點狀態檔存在；必要時執行一次性舊格式遷移。

        安全考量：若鏈上已存在 HMAC 簽章紀錄卻找不到錨點狀態檔，代表狀態檔
        遭刪除（可能為了掩蓋截斷），此時**不**自動重建錨點，交由
        verify_chain_integrity 回報異常。
        """
        with self._lock:
            if self._read_state() is not None:
                return

            records = self._load_records()
            has_signed = any(
                int(r.get("chain_version", 1)) >= CHAIN_VERSION for r in records
            )
            if has_signed:
                logger.error(
                    "稽核鏈錨點狀態檔遺失（%s），但鏈上已有 HMAC 簽章紀錄；"
                    "拒絕自動重建錨點，請進行調查。",
                    self.state_file,
                )
                return

            try:
                if records:
                    legacy_ok, legacy_msg = self._verify_links(records)
                    logger.warning(
                        "偵測到 %d 筆舊格式（未簽章）稽核紀錄，正在建立 HMAC 遷移錨點：%s",
                        len(records),
                        legacy_msg,
                    )
                    self._append_record(
                        records,
                        action=MIGRATION_ACTION,
                        document_id="AUDIT_CHAIN",
                        user_id="SYSTEM",
                        details={
                            "legacy_record_count": len(records),
                            "legacy_tip_hash": records[-1].get("current_hash", ""),
                            "legacy_chain_valid_at_migration": legacy_ok,
                            "legacy_verification_message": legacy_msg,
                            "note": (
                                "此錨點之前的紀錄以未加金鑰的 SHA-256 產生，"
                                "僅能證明遷移後未被更動。"
                            ),
                        },
                    )
                else:
                    self._write_state(records)
            except OSError as e:
                logger.error("建立稽核鏈錨點失敗：%s", e)

    # ------------------------------------------------------------------
    # 寫入
    # ------------------------------------------------------------------

    def _append_record(
        self,
        records: list,
        action: str,
        document_id: str,
        user_id: str,
        details: dict,
    ) -> AuditRecord:
        """建立、簽章並保存一筆紀錄（呼叫端須持有 self._lock）"""
        if records:
            previous_hash = records[-1].get("current_hash", GENESIS_PREVIOUS_HASH)
        else:
            previous_hash = GENESIS_PREVIOUS_HASH

        # Part 11 要求時間戳明確無歧義：一律使用 UTC（含時區位移）
        now = datetime.now(timezone.utc)
        record = {
            "record_id": f"AUD-{now.strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:8]}",
            "timestamp": now.isoformat(),
            "action": action,
            "document_id": document_id,
            "user_id": user_id,
            "details": details,
            "previous_hash": previous_hash,
            "chain_version": CHAIN_VERSION,
        }

        record["current_hash"] = self._compute_hash(previous_hash, record)

        records.append(record)
        self._save_records(records)
        self._write_state(records)

        return record

    def create_record(
        self, action: str, document_id: str, user_id: str, details: dict
    ) -> AuditRecord:
        """
        建立新的稽核紀錄

        Args:
            action: 操作類型 (FILE_UPLOADED, VERSION_CONFIRMED, etc.)
            document_id: 文件編號或檔名
            user_id: 操作者 ID
            details: 操作詳細內容

        Returns:
            建立的稽核紀錄
        """
        with self._lock:
            records = self._load_records()
            return self._append_record(
                records, action, document_id, user_id, details
            )

    # ------------------------------------------------------------------
    # 讀取
    # ------------------------------------------------------------------

    def get_all_records(self) -> list:
        """取得所有稽核紀錄"""
        return self._load_records()

    def get_latest_record(self) -> Optional[AuditRecord]:
        """取得最新紀錄"""
        records = self._load_records()
        return records[-1] if records else None

    # ------------------------------------------------------------------
    # 驗證
    # ------------------------------------------------------------------

    def _verify_links(self, records: list) -> tuple[bool, str]:
        """逐筆驗證雜湊鏈連結（不含錨點檢查）"""
        signed = 0
        legacy = 0

        for i, record in enumerate(records):
            if i == 0:
                if record.get("previous_hash") != GENESIS_PREVIOUS_HASH:
                    return False, "第一筆紀錄的 previous_hash 不正確"
            else:
                if record.get("previous_hash") != records[i - 1].get("current_hash"):
                    return (
                        False,
                        f"紀錄 {record.get('record_id')} 的 previous_hash 不符",
                    )

            verify_record = {k: v for k, v in record.items() if k != "current_hash"}
            recalculated = self._compute_hash(
                record.get("previous_hash", ""), verify_record
            )

            if not hmac.compare_digest(
                recalculated, str(record.get("current_hash", ""))
            ):
                if int(record.get("chain_version", 1)) >= CHAIN_VERSION:
                    return (
                        False,
                        f"紀錄 {record.get('record_id')} 的 HMAC 簽章不符 "
                        f"(可能被竄改，或簽章金鑰不正確)",
                    )
                return (
                    False,
                    f"紀錄 {record.get('record_id')} 的 hash 不符 (可能被竄改)",
                )

            if int(record.get("chain_version", 1)) >= CHAIN_VERSION:
                signed += 1
            else:
                legacy += 1

        return True, f"連結完整（HMAC 簽章 {signed} 筆、舊格式 {legacy} 筆）"

    def verify_chain_integrity(self) -> tuple[bool, str]:
        """
        驗證稽核紀錄鏈完整性

        檢查項目：
          1. 每筆紀錄的 previous_hash 串接正確
          2. 每筆紀錄的 current_hash 可用金鑰重算（v2 為 HMAC-SHA256）
          3. 簽章錨點：紀錄總數、起始雜湊、鏈尾雜湊（可偵測整批截斷）

        Returns:
            (是否完整, 錯誤訊息)
        """
        records = self._load_records()
        state = self._read_state()

        # ── 錨點存在性與金鑰檢查（先做，錯誤訊息較精確） ──────────────
        if state is None:
            return (
                False,
                "稽核鏈錨點狀態檔遺失或毀損，無法確認紀錄未遭整批刪除",
            )

        if state.get("key_id") and state.get("key_id") != self._key_id:
            return (
                False,
                "稽核鏈簽章金鑰與錨點不符（金鑰遭更換或設定錯誤），無法驗證",
            )

        expected_sig = self._sign_state(
            {k: v for k, v in state.items() if k != "state_hmac"}
        )
        if not hmac.compare_digest(expected_sig, str(state.get("state_hmac", ""))):
            return False, "稽核鏈錨點狀態檔簽章不符 (可能被竄改)"

        # ── 逐筆連結驗證 ─────────────────────────────────────────────
        ok, msg = self._verify_links(records)
        if not ok:
            return False, msg

        # ── 錨點比對 ─────────────────────────────────────────────────
        expected_count = state.get("record_count")
        if expected_count != len(records):
            if isinstance(expected_count, int) and len(records) > expected_count:
                # 紀錄多於錨點：通常是寫入紀錄後、更新錨點前程序中斷所致，
                # 但仍屬異常，須人工調查後才能接受。
                reason = "紀錄多於錨點 (可能為寫入中斷，或遭插入紀錄)"
            else:
                reason = "紀錄少於錨點 (可能遭整批刪除／截斷)"
            return (
                False,
                f"紀錄筆數與錨點不符：錨點記錄 {expected_count} 筆，"
                f"實際 {len(records)} 筆 — {reason}",
            )

        expected_genesis = state.get("genesis_hash")
        expected_tip = state.get("tip_hash")
        if records:
            if expected_genesis != records[0].get("current_hash"):
                return False, "起始紀錄與錨點不符 (可能遭前段刪除或插入)"
            if expected_tip != records[-1].get("current_hash"):
                return False, "鏈尾 hash 與錨點不符 (可能遭尾端刪除或竄改)"
        elif expected_tip not in (GENESIS_PREVIOUS_HASH, "", None):
            return False, "錨點顯示應有紀錄，但稽核紀錄為空 (可能遭整批刪除)"

        signed = sum(
            1 for r in records if int(r.get("chain_version", 1)) >= CHAIN_VERSION
        )
        legacy = len(records) - signed
        if legacy:
            return (
                True,
                f"文件更動紀錄鏈完整（HMAC 簽章 {signed} 筆；"
                f"另有 {legacy} 筆遷移前舊格式紀錄，由遷移錨點保護）",
            )
        return True, f"文件更動紀錄鏈完整（HMAC-SHA256 簽章 {signed} 筆）"


# 測試
if __name__ == "__main__":
    log = ImmutableAuditLog("./test_audit.json")

    # 建立測試紀錄
    r1 = log.create_record("FILE_UPLOADED", "SOP-001.pdf", "user_01", {"size": 1024})
    print(f"Record 1: {r1['record_id']}")
    print(f"Hash: {r1['current_hash'][:32]}...")

    r2 = log.create_record(
        "VERSION_CONFIRMED", "SOP-001.pdf", "user_01", {"version": "1.0"}
    )
    print(f"Record 2: {r2['record_id']}")
    print(f"Hash: {r2['current_hash'][:32]}...")

    # 驗證完整性
    is_valid, msg = log.verify_chain_integrity()
    print(f"\n驗證結果: {msg}")
