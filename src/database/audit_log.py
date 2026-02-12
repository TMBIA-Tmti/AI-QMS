"""
AI-QMS Phase 1 - 防竄改稽核紀錄模組
符合 21 CFR Part 11 要求
"""

import hashlib
import json
import os
from datetime import datetime
from typing import TypedDict, Optional
from pathlib import Path


class AuditRecord(TypedDict):
    record_id: str
    timestamp: str
    action: str
    document_id: str
    user_id: str
    details: dict
    previous_hash: str
    current_hash: str


class ImmutableAuditLog:
    """
    防竄改稽核紀錄
    使用 SHA-256 雜湊鏈確保紀錄不可竄改
    """

    def __init__(self, log_file: str = "./data/audit_log.json"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.log_file.exists():
            self._init_log_file()

    def _init_log_file(self):
        """初始化日誌檔案"""
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump({"records": []}, f, ensure_ascii=False)

    def _load_records(self) -> list:
        """載入所有紀錄"""
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("records", [])
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_records(self, records: list):
        """儲存紀錄"""
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump({"records": records}, f, ensure_ascii=False, indent=2)

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
        records = self._load_records()

        # 取得前一筆紀錄的 hash
        if records:
            previous_hash = records[-1].get("current_hash", "GENESIS_BLOCK")
        else:
            previous_hash = "GENESIS_BLOCK"

        # 建立紀錄
        record = {
            "record_id": f"AUD-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "document_id": document_id,
            "user_id": user_id,
            "details": details,
            "previous_hash": previous_hash,
        }

        # 計算當前 hash
        record_json = json.dumps(record, sort_keys=True, ensure_ascii=False)
        current_hash = hashlib.sha256(
            f"{previous_hash}{record_json}".encode("utf-8")
        ).hexdigest()

        record["current_hash"] = current_hash

        # 儲存
        records.append(record)
        self._save_records(records)

        return record

    def get_all_records(self) -> list:
        """取得所有稽核紀錄"""
        return self._load_records()

    def get_latest_record(self) -> Optional[AuditRecord]:
        """取得最新紀錄"""
        records = self._load_records()
        return records[-1] if records else None

    def verify_chain_integrity(self) -> tuple[bool, str]:
        """
        驗證稽核紀錄鏈完整性

        Returns:
            (是否完整, 錯誤訊息)
        """
        records = self._load_records()

        for i, record in enumerate(records):
            # 驗證 previous_hash
            if i == 0:
                if record.get("previous_hash") != "GENESIS_BLOCK":
                    return False, f"第一筆紀錄的 previous_hash 不正確"
            else:
                if record.get("previous_hash") != records[i - 1].get("current_hash"):
                    return False, f"紀錄 {record['record_id']} 的 previous_hash 不符"

            # 重新計算 hash 驗證
            verify_record = {k: v for k, v in record.items() if k != "current_hash"}
            record_json = json.dumps(verify_record, sort_keys=True, ensure_ascii=False)
            recalculated = hashlib.sha256(
                f"{record['previous_hash']}{record_json}".encode("utf-8")
            ).hexdigest()

            if recalculated != record.get("current_hash"):
                return False, f"紀錄 {record['record_id']} 的 hash 不符 (可能被竄改)"

        return True, "文件更動紀錄鏈完整"


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
