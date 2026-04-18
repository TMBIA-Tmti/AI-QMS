# AI-QMS 修正紀錄 / Change Log

**日期 / Date**: 2026-04-18  
**版本 / Version**: v3.6.x  
**修正者 / Author**: Claude Sonnet 4.6 + MDR  

---

## 問題調查 Q&A

### Q1：文件內容如何對應 ISO 13485 條款？判斷依據為何？會不會誤判？

**機制說明**（`src/analysis/gap_scanner.py` → `filter_relevant_clauses()`）：

目前採用**關鍵字比對（deterministic keyword rules）**，不使用 LLM 預篩選：

1. 讀取文件 ID（如 `QP-730`、`WI-750-01`）與文件標題
2. 對每個 ISO 13485 條款，比對預設的關鍵字規則（如 `7.3 設計` → 比對 "設計"、"design"、"R&D" 等）
3. 匹配的條款才進入 P1 Gap Scan LLM 分析

**誤判風險**：
- 關鍵字規則為靜態設定，若文件命名不按標準（如公司使用非標準編號）可能未匹配
- 每份文件目前掃描 1–13 條款，已通過驗證正確涵蓋 81 份文件
- 若要降低誤判：可在 `gap_scanner.py` 的 `CLAUSE_KEYWORD_RULES` 中新增/調整規則

---

### Q2：為何 remediation_suggestion、remediation_regulation_cite、ra_override、ra_notes 都沒有資料？overall_status 為何是 pending？

**根本原因（已修復）**：

1. **overall_status=pending**：P2/P4/P5 的 `ThreadPoolExecutor` 在發生例外時，只記錄 log 但不推進 row 的 phase。導致這些 row 永遠停在原 phase，`advance_to_next_phase()` 永遠不被呼叫，`overall_status` 不會設為 `completed`。

   **修復**：在 `pipeline.py` 的 P2/P4/P5 例外處理中，補上 `row.advance_to_next_phase()` 和 `self._state.update_row(row)`，確保即使失敗也推進。

2. **remediation 空白**：若 P2 例外中斷，row 停在 CHECKLIST_VERIFY，不會進入 RISK_ASSESSMENT → P3 無法設定 verdict → P4 看到 `verdict=None` 時 `rows_needing_remediation` 過濾為空 → P4 跳過 → `remediation_suggestion` 永遠為空。

   **修復**：同上，修復 phase 推進問題後，P3 可正確設定 verdict，P4 可正確執行改善建議。

3. **ra_override、ra_notes**：這兩個欄位是使用者手動填寫（RA Review 功能），不是 LLM 自動產生。若使用者未操作 RA 覆寫，這些欄位為 None 是正常現象。

---

### Q3：Chainlit 語言設為英文時，為何 Word/Excel 仍顯示中文？

**根本原因（已修復）**：

- `handle_audit_export()` 在 `app.py` 呼叫 `export_to_word()` / `export_to_excel()` 時**未傳遞 `lang` 參數**
- `export_to_word()` 與 `export_to_excel()` 函式中所有字串（標題、欄位名、狀態文字）均硬編碼中文
- `export_regulatory_to_word/excel()` 已有 `lang` 支援，但 `handle_regulatory_export()` 亦未傳遞

**修復**：
- `audit_export.py`：新增 `_UI` 多語言字典（zh-TW/en-US/ja-JP），`export_to_word(lang=)` / `export_to_excel(lang=)` 接受語言參數
- `app.py`：`handle_audit_export()` 讀取 `cl.user_session.get("language")` 並傳入
- `app.py`：`handle_regulatory_export()` 同步補上 `lang=_lang` 傳遞

---

### Q4：analyzer_position / verifier_position 為何截斷？

**根本原因（已修復）**：

`verifier.py` 第 1240 行：
```python
a_position = str(...)[:400]   # 舊：截斷至 400 字元
v_assessment = str(...)[:300] # 舊：截斷至 300 字元
```

**修復**：
```python
a_position = str(...)[:800]   # 新：保留 800 字元
v_assessment = str(...)[:600] # 新：保留 600 字元
```

---

### Q5：所有生成的 Word/Excel 是否都在 exports 資料夾？

**確認**：是。`EXPORT_DIR = Path("data/exports")` 在所有 export 模組中一致：
- `src/utils/audit_export.py`
- `src/utils/regulatory_export.py`
- `src/utils/crossexam_export.py`
- `src/utils/doclist_export.py`

檔案路徑：`data/exports/<timestamp>_<type>.docx/.xlsx`

---

### Q6：法規清單 Word/Excel 是否有相同問題？

**確認**：`regulatory_export.py` 已有完整 `lang` 支援（透過 `_t(key, lang)` 讀取 locale JSON）。  
問題在於 `app.py` 的 `handle_regulatory_export()` 未傳遞 `lang`，已在本次修復。

---

### Q7：API 中斷時，Word/Excel 是否有記錄所有資料？

**修復前**：API 例外時 `result.run_id` 未設定，partial state 未儲存，報告連結無法產生。

**修復後**（`pipeline_runner.py`）：  
在 `except Exception` 區塊中補上：
```python
pipeline._state.status = PhaseStatus.FAILED.value
pipeline._save_state()
result.run_id = pipeline.state.run_id
result.state = pipeline.state
result.table = pipeline.table
```
確保即使中斷，已分析的部分結果仍會寫入 JSON，HTML 報告可顯示已完成的條款。

---

## 修正清單

| # | 問題 | 修改檔案 | 修改內容 |
|---|------|---------|---------|
| 1 | overall_status=pending（P2 例外不推進） | `src/analysis/pipeline.py` | P2 except 補上 advance_to_next_phase |
| 2 | overall_status=pending（P4 例外不推進） | `src/analysis/pipeline.py` | P4 except 補上 advance_to_next_phase |
| 3 | overall_status=pending（P5 例外不推進） | `src/analysis/pipeline.py` | P5 except 補上 advance_to_next_phase |
| 4 | remediation 空白（連鎖自 #1-3） | `src/analysis/pipeline.py` | 同上（修復 phase 推進後 P4 可正確執行） |
| 5 | position 截斷 400/300 字元 | `src/analysis/verifier.py` | [:400]→[:800], [:300]→[:600] |
| 6 | P5 對 full_compliance 行浪費 token | `src/analysis/verifier.py` | 過濾 verdict in (full_compliance, not_applicable) |
| 7 | 新增 not_applicable verdict | `src/analysis/risk_matrix.py` | 加入 NOT_APPLICABLE、LLM_SKIP 集合、VERDICT_DISPLAY |
| 8 | API 中斷後無部分報告 | `src/analysis/pipeline_runner.py` | except 補上 partial state 儲存 |
| 9 | Word/Excel 缺 remediation/position 欄位 | `src/analysis/comparison_table.py` | to_flat_rows() 補上 4 個欄位 + helper 函式 |
| 10 | Excel 合規表缺 4 欄 | `src/utils/crossexam_export.py` | 新增 4 個欄位標頭與資料 |
| 11 | 英文介面仍輸出中文 Word/Excel（稽核紀錄） | `src/utils/audit_export.py` | 新增 _UI 多語言字典，函式加 lang= 參數 |
| 12 | 英文介面未傳 lang 給稽核匯出 | `src/chainlit_app/app.py` | handle_audit_export 讀取 session language |
| 13 | 英文介面未傳 lang 給法規清單匯出 | `src/chainlit_app/app.py` | handle_regulatory_export 補上 lang=_lang |

## 未完成項目（需後續處理）

| 項目 | 原因 | 建議 |
|------|------|------|
| P2 HTML 空白（P2 面板） | 需確認 checklist_verifier output 結構與 report.js 的對應 | 查看 `report.js` P2 panel render 邏輯 |
| P3 HTML 空白 + 404 | 需確認 report.html 的 phase_3 SSE 事件結構 | 查看 `report.js` phase_3_result handler |
| 進度不即時更新 | report.js 缺 polling | 在 report.js 加 setInterval 每 3 秒 fetch state JSON |
| Word/Excel 中 LLM prompt 語言 | gap_scanner/remediation/verifier 的 prompt 為中文 | 在各 module 根據 `row_state.lang` 選擇 prompt 語言 |
