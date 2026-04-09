# AI-QMS 簡報講者備註 (Speaker Notes)

**簡報檔案**: `AI-QMS-Presentation.html`
**總頁數**: 18 頁
**建議時間**: 25-35 分鐘

---

## 操作說明

- 用瀏覽器開啟 `AI-QMS-Presentation.html` 即可簡報
- 鍵盤 **左/右箭頭** 或 **空白鍵** 切換頁面
- 觸控螢幕支援左右滑動
- 按 **Home/End** 跳至首頁/末頁
- 支援列印 (Ctrl+P)

---

## Slide 1 - 封面 (30 秒)

**重點**: 點出 AI-QMS 是依據 ISO 13485 標準開發的 AI 智慧品質管理系統。強調 Phase 1 文件管制已完成，Phase 2 稽核子系統即將啟動。

---

## Slide 2 - 計畫緣由 (2 分鐘)

**重點**:
- 開頭提到經濟部產發署的 **AI 輔導團** 與 **AI 製造業升級** 計畫背景
- 說明醫材公會 (TMBIA) 目前面臨的產業痛點：QA/RA 人員工作繁重，文件管理耗時
- 因此以 QMS 為主題，開發此 AI 項目
- 目標效益：減少 70% 文件管理時間、100% 稽核覆蓋率、30+ 國法規自動識別

**講稿要點**: 「本計畫源自經濟部產業發展署的 AI 輔導團計畫，以及 AI 製造業升級專案。醫材公會希望透過 AI 技術減輕廠商 QA/RA 人員在文件管理、稽核追蹤等方面的工作負擔。因此我們以 ISO 13485 品質管理系統為核心，開發了這套 AI-QMS 系統。」

---

## Slide 3 - 專案總覽 (2 分鐘)

**重點**:
- Phase 1 文件管制已完成 v3.4.0
- Phase 2 稽核子系統規劃中
- 16+ LLM 提供商、20 種語言、OCR ~1 秒
- 技術數據一覽

---

## Slide 4 - 系統架構 (3 分鐘)

**重點**:
- Main Agent + Sub-Agent 模組化架構設計
- 上層: Chainlit UI 聊天介面 (Port 3000)
- 中層: LiteLLM 統一 LLM 抽象層 + Arize Phoenix 可觀測性
- 下層: OCR 處理、Markdown DB、匯出工具
- 稽核子 Agent 預留在 Phase 2 位置

**講稿要點**: 「系統採用 Main Agent 加上 Sub-Agent 的架構。主 Agent 統籌品質管理系統各模組，文件管制子 Agent 負責文件的上傳、OCR、版本控制等。所有 LLM 呼叫都透過 LiteLLM 統一管理，並由 Arize Phoenix 做即時追蹤。」

---

## Slide 5 - 主 Agent 功能 (2 分鐘)

**重點**:
- 9 大核心功能一覽
- 特別強調: LLM 智慧問答 (No-hallucination)、/web 網路搜尋、16+ LLM 提供商、20 國語言、Phoenix 可觀測性

---

## Slide 6 - 文件管制子 Agent 核心功能 (2 分鐘)

**重點**:
- 這是 Phase 1 的主體，9 大功能
- OCR、版本偵測、簽章偵測、稽核紀錄、文件作廢、交叉引用、法規識別等

---

## Slide 7 - MarkItDown OCR 引擎 (2 分鐘)

**重點**:
- 使用 Microsoft MarkItDown 取代原本的 LLM Vision OCR
- 效能對比表是亮點：從 30-150 秒降到 ~1 秒，零 Token 消耗
- 支援 PDF、Word、Excel、PowerPoint、圖片等格式

**講稿要點**: 「OCR 是我們在 v3.1.0 做的重大改進。原本使用 LLM Vision 每個檔案要花 30 到 150 秒，而且消耗大量 Token。改用 Microsoft 的 MarkItDown 後，處理速度降到約 1 秒，而且完全不消耗 Token，可以離線使用。」

---

## Slide 8 - 文件版本控制流程 (2 分鐘)

**重點**:
- 完整的 3 步驟流程圖
- 三種判定結果: 新文件 / 版本更新 / 重複拒絕
- 進版確認需要 Action Button + 確認者姓名
- 簽章偵測: 15+ 語言、200+ 關鍵字

---

## Slide 9 - 防竄改稽核紀錄 (2 分鐘)

**重點**:
- SHA-256 雜湊鏈 (類似區塊鏈)
- 每筆紀錄包含前一筆的 hash，形成不可竄改的鏈
- 符合 21 CFR Part 11 和 ISO 13485 4.2.4 要求
- 支援 Word/Excel 匯出

**講稿要點**: 「稽核紀錄採用 SHA-256 雜湊鏈，類似區塊鏈的機制。每一筆操作紀錄都包含前一筆的雜湊值，任何竄改都會破壞鏈的完整性。這符合美國 FDA 21 CFR Part 11 對電子簽章和稽核追蹤的要求。」

---

## Slide 10 - 國際法規自動識別 (1.5 分鐘)

**重點**:
- 正則表達式掃描 30+ 國法規
- 涵蓋 ISO, FDA, EU MDR, TFDA, NMPA, PMDA 等
- 支援 Word/Excel 匯出
- 來源可信度排序 (用於 /web 搜尋)

---

## Slide 11 - 16+ LLM 提供商 (1.5 分鐘)

**重點**:
- 雲端 8 家 + 閘道 6 家 + 本地 2 家
- 透過 ChatSettings 動態切換
- 可以用免費的 Ollama 本地離線運行

---

## Slide 12 - Phoenix 可觀測性 (2 分鐘)

**重點**:
- v3.4.0 新增的功能
- 零程式碼變更，自動攔截所有 LLM 呼叫
- 追蹤 Token 用量、延遲、成本
- 多 Agent 追蹤分離 (為 Phase 2 預做準備)
- 一鍵啟動

---

## Slide 13 - 技術堆疊 (1 分鐘)

**重點**:
- Python 3.11 全棧方案
- 效能指標: OCR ~1-5 秒、法規掃描 <1 秒
- 硬體需求: GPU 僅本地 LLM 需要

---

## Slide 14 - 網路搜尋 & 多語言 (1.5 分鐘)

**重點**:
- /web 指令: DuckDuckGo 搜尋 + 本地 DB 雙重上下文
- 20 國語言即時切換
- API Key 安全遮罩

---

## Slide 15 - 對話指令系統 (1 分鐘)

**重點**:
- 所有操作透過自然語言對話完成
- 12 大指令清單
- UX 亮點: Chat-based 取代傳統表單

---

## Slide 16 - 品質驗證結果 (1.5 分鐘)

**重點**:
- 11 項回歸測試 100% 通過
- Playwright 自動化測試
- 6 項 Bug 修復

---

## Slide 17 - Phase 2 稽核子 Agent (2-3 分鐘)

**重點 (重要! 這是下一階段的預告)**:
- CAPA 管理、內部稽核排程、不符合事項管理、報告自動生成
- 與 Phase 1 的整合：文件管制提供文件基礎，稽核子系統在上層做品質管理
- Phoenix 追蹤已預留 `ai-qms-audit` 專案
- 技術規劃: 向量資料庫、電子簽章、多使用者權限

**講稿要點**: 「Phase 2 稽核子 Agent 是我們即將啟動的下一個開發項目。它將涵蓋 CAPA 矯正預防措施、內部稽核排程、不符合事項管理，以及稽核報告的自動生成。在技術上，我們規劃導入向量資料庫做語義搜尋，並實作完整的電子簽章符合 21 CFR Part 11 要求。」

---

## Slide 18 - 感謝聆聽 (30 秒)

**重點**:
- 總結: Phase 1 完成、Phase 2 即將啟動
- GitHub 開源: github.com/TMBIA-Tmti/AI-QMS
- Q&A 時間

---

## Q&A 準備問題

1. **Q: 為什麼選擇 Chainlit 而不是其他 UI 框架?**
   A: Chainlit 專為 AI Agent 設計，原生支援 Chat Profile、Action Button、File Upload 等功能，不需要額外開發。之前用 Gradio 需要兩個 Port，Chainlit 只要一個。

2. **Q: OCR 準確度如何?**
   A: MarkItDown 對數位 PDF 和 Word 檔案準確度很高。對掃描的 PDF/圖片，系統會自動切換到 LLM Vision 作為備援。

3. **Q: 如何確保資料安全?**
   A: 系統可以完全本地部署 (Ollama + MarkItDown)，不需要連網。API Key 在 UI 中自動遮罩。稽核紀錄使用 SHA-256 雜湊鏈防竄改。

4. **Q: Phase 2 預計時程?**
   A: Phase 2 稽核子 Agent 目前處於規劃階段，預計將在 Phase 1 穩定後啟動開發。

5. **Q: 系統能處理多少文件?**
   A: 目前 POC 建議上限 15 份，Phase 2 規劃導入向量資料庫和 PostgreSQL 後可支援 20000+ 頁文件。
