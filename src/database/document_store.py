"""
AI-QMS Phase 1 - 文件儲存模組
管理文件元資料與版本控制
"""

import json
import re
import threading

from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.safe_io import atomic_write_json

# 版本號分隔符（同時支援 "." 與 "_"，與 chainlit_app 偵測版本的正規化規則一致）
_VERSION_SPLIT_RE = re.compile(r"[._]")


def _parse_version(version: Optional[str]) -> Optional[tuple]:
    """
    將版本字串解析為可比較的整數 tuple（例如 "2.1" -> (2, 1)、"v1.0" -> (1, 0)）。

    無法解析成整數序列時（例如自由格式文字版本號）回傳 None，
    表示無法安全地判斷版本新舊。
    """
    if not version:
        return None
    normalized = version.strip().lstrip("vV").strip()
    if not normalized:
        return None
    parts = _VERSION_SPLIT_RE.split(normalized)
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


class DocumentStore:
    """
    文件儲存庫
    管理上傳文件的元資料與版本控制
    """

    def __init__(self, store_file: str = "./data/document_store.json"):
        self.store_file = Path(store_file)
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        if not self.store_file.exists():
            self._init_store()

    def _init_store(self):
        """初始化儲存檔案"""
        atomic_write_json(self.store_file, {"documents": {}})

    def _load_store(self) -> dict:
        """載入儲存資料"""
        try:
            with open(self.store_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"documents": {}}

    def _save_store(self, data: dict):
        """儲存資料"""
        atomic_write_json(self.store_file, data)

    def save_document(
        self,
        doc_id: str,
        filename: str,
        filepath: str,
        version: str,
        is_new: bool = True,
        sig_result: dict | None = None,
    ) -> dict:
        """
        儲存文件資訊

        Args:
            doc_id: 文件編號
            filename: 檔案名稱
            filepath: 檔案路徑
            version: 版本號
            is_new: 是否為新文件
            sig_result: 簽章偵測結果 (detected, reason, stamps, signatures, keyword_hits)

        Returns:
            儲存的文件資訊。若版本檢查未通過，回傳 {"error": <訊息>, "doc_id": doc_id}
            而不會寫入任何資料。
        """
        with self._lock:
            store = self._load_store()

            if doc_id in store["documents"]:
                # 更新現有文件
                doc = store["documents"][doc_id]

                # 檢查是否為完全重複的版本號（不論是否為目前版本）
                normalized_new = (version or "").strip().lstrip("vV").strip()
                for v in doc["versions"]:
                    normalized_existing = (
                        (v.get("version") or "").strip().lstrip("vV").strip()
                    )
                    if normalized_new and normalized_new == normalized_existing:
                        return {
                            "error": (
                                f"版本 {version} 與文件 {doc_id} 已存在的版本重複，"
                                "請確認上傳的版本號是否正確。"
                            ),
                            "doc_id": doc_id,
                        }

                # 檢查新版本是否嚴格新於目前版本，避免舊版覆蓋新版
                current_version = doc.get("current_version")
                new_parsed = _parse_version(version)
                current_parsed = _parse_version(current_version)
                if new_parsed is None or current_parsed is None:
                    return {
                        "error": (
                            f"無法比較版本 {version} 與文件 {doc_id} 目前版本 "
                            f"{current_version} 的新舊，請使用可比較的版本號格式（如 1.0、2.1）。"
                        ),
                        "doc_id": doc_id,
                    }
                if not (new_parsed > current_parsed):
                    return {
                        "error": (
                            f"版本 {version} 未新於文件 {doc_id} 目前的版本 "
                            f"{current_version}，已拒絕儲存以避免覆蓋較新版本。"
                        ),
                        "doc_id": doc_id,
                    }

                doc["versions"].append(
                    {
                        "version": version,
                        "filepath": filepath,
                        "uploaded_at": datetime.now().isoformat(),
                        "status": "effective",
                        "sig_result": sig_result,
                    }
                )
                # 標記舊版本為 superseded
                for v in doc["versions"][:-1]:
                    v["status"] = "superseded"
                doc["current_version"] = version
                doc["updated_at"] = datetime.now().isoformat()
                if sig_result is not None:
                    doc["sig_result"] = sig_result
            else:
                # 新文件
                store["documents"][doc_id] = {
                    "doc_id": doc_id,
                    "filename": filename,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "current_version": version,
                    "is_master": is_new,
                    "versions": [
                        {
                            "version": version,
                            "filepath": filepath,
                            "uploaded_at": datetime.now().isoformat(),
                            "status": "effective",
                            "sig_result": sig_result,
                        }
                    ],
                    "sig_result": sig_result,
                }
            self._save_store(store)
            return store["documents"][doc_id]

    def get_document(self, doc_id: str) -> Optional[dict]:
        """取得文件資訊"""
        store = self._load_store()
        return store["documents"].get(doc_id)

    def get_all_documents(self) -> list:
        """取得所有文件"""
        store = self._load_store()
        return list(store["documents"].values())

    def search_by_filename(self, keyword: str) -> list:
        """依檔名搜尋"""
        store = self._load_store()
        return [
            doc
            for doc in store["documents"].values()
            if keyword.lower() in doc["filename"].lower()
        ]

    def find_documents_referencing_version(self, doc_id: str, old_version: str) -> list:
        """
        找出引用指定版本的文件
        TODO: 整合向量資料庫搜尋
        """
        try:
            from src.services.vector_store import get_vector_store
            import asyncio
            store = get_vector_store()
            loop = asyncio.new_event_loop()
            results = loop.run_until_complete(store.search_similar(f"{doc_id} version {old_version}", n_results=10))
            loop.close()
            return [r["doc_id"] for r in results if r.get("doc_id") != doc_id]
        except Exception:
            return []


# 測試
if __name__ == "__main__":
    store = DocumentStore("./test_doc_store.json")

    # 新增文件
    doc1 = store.save_document(
        doc_id="SOP-001",
        filename="品質手冊.pdf",
        filepath="./uploads/品質手冊.pdf",
        version="1.0",
        is_new=True,
    )
    print(f"新增文件: {doc1['doc_id']} v{doc1['current_version']}")

    # 進版
    doc1_v2 = store.save_document(
        doc_id="SOP-001",
        filename="品質手冊.pdf",
        filepath="./uploads/品質手冊_v2.pdf",
        version="2.0",
        is_new=False,
    )
    print(f"進版文件: {doc1_v2['doc_id']} v{doc1_v2['current_version']}")
    print(f"版本歷史: {len(doc1_v2['versions'])} 個版本")
