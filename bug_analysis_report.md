# 🔍 Bug 根因分析報告

> 生成日期：2026-03-05  
> 狀態：**已全部修復** ✅  
> 更新：新增 Bug #7/#7b 分析，所有 Bug 已修復

---

## Bug #1 — 啟動順序錯誤（MDSAP/上傳通知出現在簽章詢問之後）

### 現象
每日登入時，Eira 先問「是否啟用簽章偵測？」和「文件階層範圍？」，之後才顯示 MDSAP 啟動通知和手動上傳提醒。使用者期望：先看到 MDSAP/上傳提醒，最後才問簽章。

### 根因
`app.py` 的 `on_chat_start`（第 2934 行起）呼叫順序寫反了：

```python
# 現在的順序（錯誤）— app.py 第 3187-3199 行：
# 第 3190 行：先呼叫 Eira 介紹（問簽章 + 階層）
await _send_eira_introduction(user_name, profile, doc_count, doc_limit)

# 第 3199 行：後呼叫交叉詰問（MDSAP/上傳通知）
asyncio.create_task(_auto_trigger_crossexam())
```

應為：

```python
# 正確順序：
asyncio.create_task(_auto_trigger_crossexam())    # 先顯示 MDSAP/上傳通知
await _send_eira_introduction(...)                 # 最後才問簽章 + 階層
```

### 為什麼之前沒改好
這兩個函數是在 Phase 1 / Phase 3 修復期間分別加入的，當時各自功能測試通過，但沒有檢查**兩者之間的呼叫順序**。`_send_eira_introduction` 是 `await`（同步等待），`_auto_trigger_crossexam` 是 `asyncio.create_task`（背景執行），即使交換順序也不會阻塞。直到使用者在實際操作中截圖反映才發現順序不對。

### 修復方案
交換 `app.py` 第 3188-3199 行的兩個區塊順序：先 `_auto_trigger_crossexam`，後 `_send_eira_introduction`。

---

## Bug #2 — 部分訊息缺少「Eira：」前綴

### 現象
MDSAP 啟動通知、手動上傳提醒等訊息直接顯示內容，沒有「Eira：」開頭，與其他系統訊息風格不一致。

### ⚠️ 修正根因（與先前報告不同）
先前報告寫「i18n key 的值沒有加上 Eira：前綴」——**這是錯的**。

**真正的根因：這 4 個 i18n key 根本不存在於任何 locale JSON 檔中。**

經過對 20 個 locale 檔（`src/chainlit_app/locales/*.json`）完整搜尋，以下 key 完全沒有定義：

| i18n Key | 存在於 locale 檔？ |
|----------|-------------------|
| `crossexam.mdsap_enabled_notice` | ❌ **不存在** |
| `crossexam.upload_reminder_title` | ❌ **不存在** |
| `crossexam.upload_reminder_instruction` | ❌ **不存在** |
| `crossexam.freshness_confirmed` | ❌ **不存在** |

`t()` 函數的 fallback 邏輯（`app.py` 第 481 行）：
```python
text = translations.get(key, I18N["zh-TW"].get(key, key))
#                                                    ^^^ key 不存在時回傳 key 本身
```

所以 `t("crossexam.freshness_confirmed")` 回傳的是字串 `"crossexam.freshness_confirmed"`。
這就是為什麼使用者看到的訊息沒有「Eira：」——**根本沒有翻譯內容**，顯示的是 raw key。

### 為什麼之前沒做好
1. **先前分析就搞錯了**：之前的分析報告假設這些 key 存在但缺少前綴，實際上 key 根本不存在
2. **開發時遺漏**：`_auto_trigger_crossexam()` 函數（`app.py` 第 2865 行）使用了 `t("crossexam.*")`，但從未在 locale JSON 檔中建立對應的翻譯
3. **沒有 i18n key 完整性檢查**：專案沒有腳本或測試驗證「程式碼中用到的所有 `t()` key 都有對應翻譯」
4. **`t()` 的 silent fallback**：key 不存在時不報錯，只是靜默回傳 key 字串，開發時不容易發現

### 修復方案
在 20 個 locale JSON 檔中**新建**這 4 個 key，內容包含「Eira：」前綴和正確翻譯文字。

---

## Bug #3 — Report UI 顯示原始 i18n key（`phase.configTitle`、`phase.toggleBtn` 等）

### 現象
報告頁面中，Phase 設定區塊顯示的不是翻譯後的文字，而是原始 key 字串如 `phase.configTitle`、`phase.toggleBtn`。

### 根因
`report.html`（第 85-163 行）使用了 **22 個 `data-i18n="phase.*"` 屬性**，但 `report_i18n.js` 的 `TRANSLATIONS` 字典中**一個 `phase.*` 翻譯都沒有**（0 筆）。

缺少的 22 個 key（含 `phase.p05` 和 `phase.p05Risk`，共 24 個）：
```
phase.configTitle, phase.configDesc, phase.toggleBtn,
phase.p0, phase.p05, phase.p1, phase.p2, phase.p3, phase.p4, phase.p5, phase.p6,
phase.p0Risk, phase.p05Risk, phase.p1Risk, phase.p2Risk, phase.p3Risk, phase.p4Risk, phase.p5Risk, phase.p6Risk,
phase.noSkip, phase.apply, phase.reset
```

`report_i18n.js` 的 `t()` 函數找不到 key 時，直接回傳 key 本身：
```javascript
function t(key) {
    return TRANSLATIONS[lang]?.[key] ?? TRANSLATIONS['en']?.[key] ?? key;
    //                                                              ^^^^ 找不到就顯示 key
}
```

### 為什麼之前沒改好
`report.html` 的 Phase 設定區塊是在報告 UI 重構時加入的 HTML 結構，但**對應的翻譯從未被加入** `report_i18n.js`。HTML 和 JS 由不同階段的修改產生，沒有交叉驗證。

### 修復方案
在 `report_i18n.js` 的每個語言區塊中加入 24 個 `phase.*` 翻譯（`report_i18n.js` 單一檔案，20 個語言區塊）。

---

## Bug #4 — Pipeline 顯示 0/323、0%（實際正在執行中）

### 現象
報告 UI 顯示進度為 `0/323 (0%)`，但 SSE 串流確實在輸出 gap scan 結果（FM-630-01、FM-640-01 等），表示 Pipeline **實際上正在運作**。

### ⚠️ 修正根因（與先前報告不同）
先前報告寫「PipelineState 沒有 total_rows/completed_rows 欄位」——**這是錯的**。

**真正的根因：`PipelineState` 有 `@property` 計算屬性，但 `to_dict()` 用的是 `asdict(self)` 只序列化 `@dataclass` fields，不包含 properties。**

```python
# state.py 第 515-531 行 — 這些 @property 已經存在且正確
@property
def total_rows(self) -> int:
    return len(self.rows)          # ✅ 計算正確

@property
def completed_rows(self) -> int:
    return sum(1 for d in self.rows.values()
               if d.get("overall_status") == "completed")  # ✅ 計算正確

@property
def progress_percent(self) -> float:
    if self.total_rows == 0: return 0.0
    return round((self.completed_rows / self.total_rows) * 100, 1)  # ✅ 計算正確
```

```python
# state.py 第 561-562 行 — 問題在這裡
def to_dict(self) -> dict:
    return asdict(self)  # ❌ asdict() 只序列化 field，不包含 @property
```

所以 JSON 檔中根本沒有 `total_rows`、`completed_rows`、`progress_percent` 這三個欄位。

但 `app.py` 第 3132-3143 行在 `on_chat_start` 顯示報告連結時，是**直接讀 JSON 檔**，不經過 `PipelineState` 物件：
```python
_run_data = json.loads(_rf.read_text(encoding="utf-8"))  # 直接讀 JSON
_total = _run_data.get("total_rows", 0)      # JSON 中沒有這個 key → 取得 0
_completed = _run_data.get("completed_rows", 0)  # 同上 → 0
```

所以顯示 `0/323 (0%)`——但 323 是從哪來的？是 `len(rows)` 在前端算的。

### 為什麼之前沒做好
1. **先前分析就搞錯了**：之前的報告說 `PipelineState` 沒有這些欄位，實際上有 `@property` 但 `to_dict()` 不包含
2. **`asdict()` 的限制不明顯**：Python `dataclasses.asdict()` 只序列化 `field()`，不包含 `@property`，這是 Python 語言層面的行為，不容易在 code review 中發現
3. **讀取路徑不一致**：`progress_summary()` 方法（第 533 行）有正確包含 `self.total_rows` 等 property 值，但 `on_chat_start` 的報告連結顯示沒有呼叫這個方法，而是直接讀 JSON

### 修復方案
覆寫 `to_dict()` 方法，在 `asdict(self)` 的結果上補入 `@property` 的計算值：
```python
def to_dict(self) -> dict:
    d = asdict(self)
    d["total_rows"] = self.total_rows
    d["completed_rows"] = self.completed_rows
    d["progress_percent"] = self.progress_percent
    return d
```

---

## Bug #5 — 手動上傳提醒訊息重複出現

### 現象
使用者看到兩則內容幾乎相同的「請手動上傳法規」訊息。

### 根因
兩個獨立的程式碼路徑各自產生一則訊息：

**路徑 A** — `regulatory_crawler.py` 的 `check_regulation_freshness()` 回傳**硬編碼**的公告文字（第 1761-1804 行），當有不完整的國家資料時，把上傳提醒直接附加到 `announcement_text` / `announcement_text_zh` 裡：
```python
# regulatory_crawler.py 第 1791-1804 行
upload_notice_zh = "\n\n📤 需要手動上傳\n以下國家的法規資料無法完整爬取..."
announcement_zh = announcement_zh + upload_notice_zh
```

**路徑 B** — `app.py` 第 2891-2914 行（`_auto_trigger_crossexam()`），另外從 `freshness["country_completeness"]` 讀取不完整國家清單，用 i18n key 組合第二則訊息：
```python
# app.py 第 2905-2908 行
upload_msg = t("crossexam.upload_reminder_title") + "\n" + "\n".join(lines)
             + "\n\n" + t("crossexam.upload_reminder_instruction")
```

路徑 A 的公告在第 2883-2884 行被發送，路徑 B 的訊息在第 2914 行被發送 → **使用者看到兩則幾乎相同的上傳提醒**。

### 為什麼之前沒改好
路徑 A 是爬蟲模組本身的回傳值（早期實作），路徑 B 是後來加入 i18n 支援時新增的。兩者分屬不同模組（`services/` vs `chainlit_app/`），在各自的修改中都測試通過，但**合併後沒有端對端測試**檢查是否重複。

### 修復方案
移除路徑 A 中 `check_regulation_freshness()` 對 `announcement_text` 附加上傳提醒的邏輯（第 1783-1804 行），只保留 `country_completeness` 資料回傳。統一由路徑 B 的 i18n 版本（`app.py`）負責組合和顯示上傳提醒。

---

## Bug #6 — MDSAP 啟動時無進度指示器（使用者不知道有在動）

### 現象
使用者啟用 MDSAP 五國交叉詰問後，只看到一則靜態訊息「🌐 MDSAP 五國交叉詰問已啟用」，之後沒有任何進度更新。使用者無法得知：
- 分析是否已經開始
- 目前進行到第幾筆/共幾筆
- 預計還要多久

### 根因
`_auto_trigger_crossexam()` 函數（`app.py` 第 2920-2924 行）在偵測到 MDSAP 啟用時，只發送一則靜態通知訊息就結束了：
```python
if mdsap_enabled:
    await cl.Message(
        content=t("crossexam.mdsap_enabled_notice"),
        author="Eira",
    ).send()
# ← 之後什麼都沒有，沒有進度回報
```

沒有任何機制向使用者報告：
1. Pipeline 是否已經因 MDSAP 而啟動
2. 目前的分析進度（百分比、已完成/總數）
3. Pipeline 的執行狀態（running/paused/completed）

### 為什麼之前沒做好
MDSAP toggle 功能是在「MDSAP 五國交叉詰問」需求中加入的，當時重點在於「是否啟用」的邏輯正確性。啟用通知被設計為一次性靜態訊息，**從未設計進度回報機制**。使用者明確表示「不然我怎麼知道有在動」，這是 UX 設計遺漏。

### 修復方案
在 MDSAP 啟用通知中加入 Pipeline 進度資訊：
1. 讀取當前 Pipeline 狀態（如果有 running 的 pipeline）
2. 在啟動通知中顯示進度條或百分比
3. 加入 i18n key 支援進度文字

新增 i18n key：
- `crossexam.mdsap_progress` — 進度文字模板（如「📊 目前進度：{completed}/{total} ({percent}%）」）
- `crossexam.pipeline_running` — Pipeline 正在執行中的提示
- `crossexam.pipeline_not_started` — 尚未開始分析的提示

---

## Bug #7 — SSE 卡片水平對齊 + 格式不一致

### 現象
在「即時 LLM 互動」分頁中，交叉詰問的 SSE 卡片（`.crossexam-card`）各項標籤（📄 品質文件、§ ISO 條款、🔍 證據、⚡ Token）寬度不一致，沒有水平對齊。不同卡片的標籤位置跳動，視覺上顯得凌亂。

### 根因
`report.css` 中 `.crossexam-card-header` 使用 `display: flex; flex-wrap: wrap;` 排版，各個 `.card-tag` 沒有固定寬度，純靠內容撐開。當不同卡片的文件名稱或條款 ID 長度不同時，後面的標籤就會錯位。

### 為什麼之前沒改好
卡片佈局在初次實作時以「功能正確」為優先，沒有針對「多卡片水平對齊」做 CSS grid 排版。使用者明確要求「所有資料的呈現要呈現水平，格式、大小要一致切齊」才暴露此問題。

### 修復方案
將 `.crossexam-card-header` 從 `display: flex` 改為 `display: grid`，使用 `grid-template-columns` 固定各欄位寬度比例，確保所有卡片的標籤對齊。響應式斷點下回退為 wrap 佈局。

---

## Bug #7b — 主分析表格中無法直接看到 LLM 分析結果

### 現象
使用者反映「完全無法看出 LLM prompt 機器語言轉成人的語言的內容，與所對應的品質文件、ISO 條文是哪一條，在同一列」。目前 LLM 分析摘要（`remediation`）需要點擊 🔍 詳情按鈕才能看到。

### 根因
1. `renderRow()` 函數（`report.js` 第 1011 行）只渲染 8 欄：條款、品質文件、稽核問題、證據、判定、風險、標記、操作
2. `remediation`（LLM 改善建議）、`llm_reasoning`（LLM 推理）等欄位只在 `openDetail()` 的 detail modal 中顯示
3. 使用者需要在主表格中一眼看到「ISO 條文 + 品質文件 + LLM 分析結果」三者並列

### 為什麼之前沒改好
表格在設計時以「簡潔概覽」為目標，將詳細內容放在 modal 中。使用者的需求是「一眼看到完整資訊」，與原始設計理念衝突。直到使用者明確表達「在同一列」的需求才發現需要增加欄位。

### 修復方案
1. 在 `report.html` 表頭新增「LLM 分析」欄（`<th class="col-llm-analysis">`）
2. 在 `renderRow()` 中新增 `<td class="col-llm-analysis">`，顯示 `r.remediation` 截取前 80 字，hover 時顯示完整內容
3. 在 `report.css` 新增 `.col-llm-analysis` 和 `.llm-analysis-text` 樣式
4. 在 `report_i18n.js` 的 zh-TW/en-US/ja-JP 語言區塊新增 `table.llmAnalysis` 翻譯

---

## 總結

| # | Bug | 根因類型 | 修復狀態 | 修復難度 |
|---|-----|---------|---------|---------|
| 1 | 啟動順序錯誤 | 呼叫順序寫反 | ✅ 已修復 | 🟢 小 |
| 2 | 缺少「Eira：」前綴 | **i18n key 根本不存在** | ✅ 已修復 | 🟡 中 |
| 3 | Report UI 顯示 raw key | 翻譯完全未建立 | ✅ 已修復 | 🟡 中 |
| 4 | Pipeline 顯示 0% | **`to_dict()` 用 `asdict()` 不含 property** | ✅ 已修復 | 🟢 小 |
| 5 | 上傳提醒重複 | 兩條獨立程式碼路徑產生相同訊息 | ✅ 已修復 | 🟢 小 |
| 6 | MDSAP 無進度指示 | 只有靜態通知，無進度回報機制 | ✅ 已修復 | 🟡 中 |
| 7 | SSE 卡片未對齊 | CSS flex 無固定寬度 | ✅ 已修復 | 🟢 小 |
| 7b | 主表格缺 LLM 分析欄 | 表格設計僅 8 欄，LLM 內容藏在 modal | ✅ 已修復 | 🟡 中 |

### 共通問題

1. **各模組獨立開發測試通過，但缺少端對端整合驗證**（Bug #1, #5）
2. **先前分析不夠深入，假設了不正確的根因**（Bug #2, #4）
3. **i18n key 完整性沒有自動化檢查**（Bug #2, #3）
4. **UX 設計只做到「功能有」但沒做到「使用者看得到」**（Bug #4, #6, #7, #7b）

### 修復檔案清單

| 檔案 | 修復的 Bug |
|------|----------|
| `src/chainlit_app/app.py` | #1, #6 |
| `src/analysis/state.py` | #4 |
| `src/services/regulatory_crawler.py` | #5 |
| `src/chainlit_app/locales/*.json` (20 檔) | #2 |
| `report_ui/report_i18n.js` | #3, #7b |
| `report_ui/report.html` | #7b |
| `report_ui/report.js` | #7b |
| `report_ui/report.css` | #7, #7b |
